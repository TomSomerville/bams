"""OpenSubtitles.com: find subtitles for a video while it plays, and download the one picked into the data dir.

Their API (https://opensubtitles.stoplight.io/docs/opensubtitles-api/e3750fd63a100-getting-started) and how BAMS uses it:
  - Each BAMS server's admin pastes their own OpenSubtitles API key in Settings, like the TMDB key (owner's decision,
    2026-10-11). OpenSubtitles' own rules ask for one key per application and say they may ban apps that make users
    bring their own; the owner chose per-server keys anyway. The key is checked with a search before it's kept (a
    wrong one gets 403 "You cannot consume this service") and never sent back to the browser.
  - Searching needs only the key. Downloads are limited: 5 a day per IP without an account; signed in, what the
    account allows (20 a day free, 1000 VIP). The admin can also enter an OpenSubtitles account (kept in the
    settings table, like the key); BAMS signs in with it and keeps the 24-hour token in memory. Credentials it
    refused are not tried again until they change (their login is rate limited).
  - User-Agent "BAMS v<version>"; at most 5 requests a second per IP; follow redirects.
  - Subtitles arrive as UTF-8 SRT. They're kept in the data dir (`subtitles/opensubtitles/<id>.srt`) and listed with
    the file's own tracks as "d<n>" (table subtitle_downloads). A copy is also saved next to the video
    ("Episode.en.srt", so other players find it too) unless the admin turns that off: the one write BAMS makes in a
    media folder (owner's decision 2026-10-12, readonly.create_sidecar: new files only, never overwriting).

Network calls happen outside transactions; tests pass a `transport=` (httpx.MockTransport).
"""

from __future__ import annotations

import base64
import errno
import hashlib
import json
import logging
import os
import re
import shlex
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import readonly, subtitles
from .config import VERSION
from .db import Tx, get_setting, jdump, jload, set_setting

log = logging.getLogger(__name__)

API = "https://api.opensubtitles.com/api/v1"
CONSUMERS_URL = "https://www.opensubtitles.com/en/consumers"  # where an account makes an API key ("API consumers")
KEY_SETTING = "opensubtitles_key"
SAVE_SETTING = "opensubtitles_save_beside"   # "0" = don't save copies next to videos; on by default (owner, 2026-10-12)
SAVE_ERROR_SETTING = "opensubtitles_save_error"  # the last copy that couldn't be saved: {at, folder, why}
USER_AGENT = f"BAMS v{VERSION}"
PROVIDER = "opensubtitles"
FOLDER = "subtitles/opensubtitles"  # under the data dir
MAX_BYTES = 5_000_000               # a subtitle file is a few hundred KB; anything bigger isn't one
_MIN_INTERVAL = 0.25                # 4 requests a second, under their 5 per IP
_LOGIN_INTERVAL = 1.0               # /login: 1 a second
_LANGS_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2,4})?(?:,[a-z]{2,3}(?:-[a-z]{2,4})?)*$")


class OpenSubtitlesError(Exception):
    """Something to tell the person in the player or in Settings (the message is written for them)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status  # OpenSubtitles' HTTP status, when it answered


class NotSetUp(OpenSubtitlesError):
    pass


class InvalidKey(OpenSubtitlesError):
    pass


class LoginRefused(OpenSubtitlesError):
    pass


class QuotaReached(OpenSubtitlesError):
    pass


def api_key(con: sqlite3.Connection) -> str | None:
    """This server's OpenSubtitles API key (Settings), None when there's none: the feature is off."""
    return (get_setting(con, KEY_SETTING) or "").strip() or None


def valid_key_format(key: str) -> bool:
    """Only rules out what can't be a key (spaces, a few characters, a whole page): what a key looks like isn't
    documented, so OpenSubtitles decides (save_key asks them). A 64-character limit refused a real paste once."""
    return bool(re.fullmatch(r"[!-~]{8,4096}", key.strip()))


def _sign_in_token(key: str) -> str | None:
    """Why a pasted value is a sign-in token rather than an API key, or None. Their sign-in tokens (JWTs from
    /login, also what the website hands out) carry an `exp` a day away; an API key doesn't expire."""
    parts = key.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        exp = float(json.loads(base64.urlsafe_b64decode(parts[1] + "=="))["exp"])
    except (ValueError, KeyError, TypeError):
        return None
    when = datetime.fromtimestamp(exp, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if exp > time.time() + 30 * 86400:
        return None  # lives for months: not a sign-in token, let OpenSubtitles judge it
    return (f"That's an OpenSubtitles sign-in token (it {'expired' if exp < time.time() else 'expires'} {when}), not an "
            f"API key. The API key is on {CONSUMERS_URL}: open the consumer you made and copy its API key.")


# Process-wide: requests spaced out, the signed-in account's token, credentials OpenSubtitles refused.
_lock = threading.Lock()
_last = 0.0
_last_login = 0.0
_session: dict | None = None        # {secret, token, base, exp}
_refused: dict[str, str] = {}       # secret -> OpenSubtitles' answer


def reset() -> None:
    """Forget the token and refusals (tests; an account change)."""
    global _session
    with _lock:
        _session = None
        _refused.clear()


def _throttle(interval: float = _MIN_INTERVAL, login: bool = False) -> None:
    global _last, _last_login
    with _lock:
        now = time.monotonic()
        wait = max(_last + _MIN_INTERVAL, (_last_login + interval) if login else 0) - now
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()
        if login:
            _last_login = _last


def _message(r: httpx.Response) -> str:
    try:
        d = r.json()
    except ValueError:
        return r.text.strip()[:200]
    if isinstance(d, dict):
        m = d.get("message") or d.get("errors") or d.get("error")
        if isinstance(m, list):
            m = "; ".join(str(x) for x in m)
        if m:
            return str(m)
    return f"HTTP {r.status_code}"


class Client:
    """The OpenSubtitles REST API with this server's API key."""

    def __init__(self, key: str | None, transport: httpx.BaseTransport | None = None):
        if not key:
            raise NotSetUp("No OpenSubtitles API key on this server yet. An admin can add one under Settings → "
                           "Playback → OpenSubtitles.")
        self.key = key.strip()
        self.http = httpx.Client(timeout=20, follow_redirects=True, transport=transport,
                                 headers={"Api-Key": self.key, "User-Agent": USER_AGENT, "Accept": "application/json"})

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def request(self, method: str, path: str, *, token: str | None = None, base: str | None = None,
                params: dict | None = None, body: dict | None = None, login: bool = False) -> dict:
        url = (f"https://{base}/api/v1" if base else API) + path
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        for attempt in range(3):
            _throttle(_LOGIN_INTERVAL if login else _MIN_INTERVAL, login)
            try:
                r = self.http.request(method, url, params=params, json=body, headers=headers)
            except httpx.HTTPError as e:
                raise OpenSubtitlesError(f"OpenSubtitles can't be reached right now ({e.__class__.__name__}).") from e
            if r.status_code == 429 and attempt < 2 and not login:  # too fast: wait as long as they say
                time.sleep(min(5.0, float(r.headers.get("ratelimit-reset") or r.headers.get("retry-after") or 1)))
                continue
            break
        if r.status_code == 401 and login:
            raise LoginRefused(f"OpenSubtitles didn't accept that name and password ({_message(r)}).")
        if r.status_code == 403 and not token:  # their answer to a key they don't know: "You cannot consume this service"
            if login:  # refused before the name and password were looked at: they're not what's wrong (tester, 0.13.1)
                raise InvalidKey(f"OpenSubtitles refused this server's API key ({_message(r)}), so it couldn't sign in to "
                                 f"the account; the name and password weren't checked. Press Test next to the key; if "
                                 f"it's refused too, paste the API key again from {CONSUMERS_URL}.", 403)
            raise InvalidKey(f"OpenSubtitles didn't accept the API key ({_message(r)}).", 403)
        if r.status_code in (406, 429) and path == "/download":
            raise QuotaReached(_message(r))
        if r.status_code >= 400:
            raise OpenSubtitlesError(f"OpenSubtitles refused the request: {_message(r)}", r.status_code)
        try:
            return r.json()
        except ValueError:
            raise OpenSubtitlesError("OpenSubtitles sent an answer BAMS doesn't understand.") from None

    def check(self) -> None:
        """Is the key good? A small search (searching costs nothing against the download limit); InvalidKey if not."""
        self.request("GET", "/subtitles", params=[("imdb_id", "133093"), ("languages", "en")])

    def fetch(self, url: str) -> bytes:
        """The subtitle file behind a download link (a temporary URL on opensubtitles.com)."""
        _throttle()
        try:
            with self.http.stream("GET", url, headers={"Accept": "*/*"}) as r:
                if r.status_code >= 400:
                    raise OpenSubtitlesError(f"OpenSubtitles didn't send the subtitle file (HTTP {r.status_code}).")
                data = b""
                for chunk in r.iter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        raise OpenSubtitlesError("OpenSubtitles sent something too big to be a subtitle file.")
                return data
        except httpx.HTTPError as e:
            raise OpenSubtitlesError(f"OpenSubtitles can't be reached right now ({e.__class__.__name__}).") from e


# ------------------------------------------------------------------ the admin's account

def _secret(key: str, user: str, password: str) -> str:
    """Identifies a sign-in: a token belongs to the account and the API key it was made with."""
    return hashlib.sha256(f"{key}\0{user}\0{password}".encode()).hexdigest()


def _expiry(token: str) -> float:
    """When a token stops working: its `exp` claim, else 23 hours from now (they're good for 24)."""
    try:
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        return float(claims["exp"])
    except (IndexError, ValueError, KeyError, TypeError):
        return time.time() + 23 * 3600


def _remember(secret: str, d: dict) -> None:
    global _session
    tok = d.get("token")
    if not tok:
        raise OpenSubtitlesError("OpenSubtitles signed in but sent no token.")
    with _lock:
        _session = {"secret": secret, "token": tok, "base": d.get("base_url") or None, "exp": _expiry(tok)}


def _forget_token() -> None:
    global _session
    with _lock:
        _session = None


def account(con: sqlite3.Connection) -> tuple[str, str] | None:
    u, p = get_setting(con, "opensubtitles_user"), get_setting(con, "opensubtitles_password")
    return (u, p) if u and p else None


def status(con: sqlite3.Connection) -> dict:
    """For Settings: whether this server has a key (only its last 4 characters, never the key) and the account it
    signs in with (never the password)."""
    key, acc = api_key(con), account(con)
    with _lock:
        refused = _refused.get(_secret(key, *acc)) if key and acc else None
    return {"configured": key is not None, "last4": key[-4:] if key else None,
            "verified_at": get_setting(con, "opensubtitles_verified_at") if key else None,
            "user": acc[0] if acc else None,
            "account": jload(get_setting(con, "opensubtitles_account")) if acc else None, "error": refused,
            "save_beside": save_beside_on(con), "save_error": jload(get_setting(con, SAVE_ERROR_SETTING))}


def save_key(con: sqlite3.Connection, client: Client) -> dict:
    """Settings: keep the client's key once OpenSubtitles accepted it (InvalidKey: it isn't kept). When they can't be
    reached, it's kept unchecked, like the TMDB key."""
    if why := _sign_in_token(client.key):
        raise InvalidKey(why)
    verified = None
    try:
        client.check()
        verified = datetime.now(timezone.utc).isoformat(timespec="seconds")
    except InvalidKey:
        raise
    except OpenSubtitlesError as e:
        log.warning("OpenSubtitles key saved unchecked: %s", e)
    _forget_token()  # a token belongs to the key it was made with
    with Tx(con):
        set_setting(con, KEY_SETTING, client.key)
        set_setting(con, "opensubtitles_verified_at", verified)
    return status(con)


def remove_key(con: sqlite3.Connection) -> dict:
    """Settings: no key, no OpenSubtitles (subtitles already downloaded stay and keep working)."""
    _forget_token()
    with Tx(con):
        set_setting(con, KEY_SETTING, None)
        set_setting(con, "opensubtitles_verified_at", None)
    return status(con)


def sign_in(con: sqlite3.Connection, client: Client) -> tuple[str | None, str | None]:
    """(token, API host) for the admin's account, signing in when there's no fresh token; (None, None) without an
    account (downloads then count against this IP's 5 a day)."""
    acc = account(con)
    if not acc:
        return None, None
    secret = _secret(client.key, *acc)
    with _lock:
        if _session and _session["secret"] == secret and _session["exp"] > time.time() + 60:
            return _session["token"], _session["base"]
        if secret in _refused:
            raise LoginRefused(f"The OpenSubtitles account in Settings was refused: {_refused[secret]} "
                               "An admin can sign in again under Settings → Playback → OpenSubtitles.")
    try:
        d = client.request("POST", "/login", body={"username": acc[0], "password": acc[1]}, login=True)
    except LoginRefused as e:
        with _lock:
            _refused[secret] = str(e)
        raise
    _remember(secret, d)
    return d["token"], d.get("base_url") or None


def save_account(con: sqlite3.Connection, client: Client, user: str, password: str) -> dict:
    """Settings: sign in with an OpenSubtitles account (so a wrong one is never kept) and keep it."""
    secret = _secret(client.key, user, password)
    with _lock:
        _refused.pop(secret, None)  # the admin asked again: they may have fixed the account on the site
    d = client.request("POST", "/login", body={"username": user, "password": password}, login=True)
    _remember(secret, d)
    u = d.get("user") or {}
    info = {"level": u.get("level"), "allowed_downloads": u.get("allowed_downloads"), "vip": bool(u.get("vip"))}
    with Tx(con):
        set_setting(con, "opensubtitles_user", user)
        set_setting(con, "opensubtitles_password", password)
        set_setting(con, "opensubtitles_account", jdump(info))
    return status(con)


def forget_account(con: sqlite3.Connection, client: Client | None) -> None:
    """Settings: stop using the account (its token is closed on OpenSubtitles too, as they ask)."""
    global _session
    with _lock:
        tok, base, _session = (_session or {}).get("token"), (_session or {}).get("base"), None
    if tok and client:
        try:
            client.request("DELETE", "/logout", token=tok, base=base)
        except OpenSubtitlesError:
            pass  # gone already: nothing to close
    with Tx(con):
        for k in ("opensubtitles_user", "opensubtitles_password", "opensubtitles_account"):
            set_setting(con, k, None)


# ------------------------------------------------------------------ searching

def _imdb_number(imdb: str | None) -> int | None:
    m = re.fullmatch(r"(?:tt)?0*(\d+)", (imdb or "").strip())
    return int(m[1]) if m else None


def lookup(con: sqlite3.Connection, file_id: int) -> tuple[dict, dict]:
    """What OpenSubtitles is asked for a video file: its title's TMDB/IMDb id (+ season/episode), else its name, and
    the file's moviehash (BAMS's quick_hash is their hash), as (by ids, by name). Also what it is, for the dialog."""
    f = con.execute("SELECT quick_hash, size FROM files WHERE id=?", (file_id,)).fetchone()
    if not f:
        raise LookupError("no such file")
    it = con.execute("""SELECT i.* FROM file_items fi JOIN items i ON i.id=fi.item_id WHERE fi.file_id=?
                        AND i.kind IN ('movie', 'episode') ORDER BY i.episode_number LIMIT 1""", (file_id,)).fetchone()
    if not it:
        raise OpenSubtitlesError("This file isn't placed as a movie or an episode yet, so there's nothing to look up.")
    ids: dict = {}
    name: dict = {}
    what = {"kind": it["kind"], "title": it["title"], "year": it["year"]}
    if it["kind"] == "episode":
        season = con.execute("SELECT * FROM items WHERE id=?", (it["parent_id"],)).fetchone()
        show = con.execute("SELECT * FROM items WHERE id=?", (season["parent_id"],)).fetchone() if season else None
        what.update(show=show["title"] if show else None, season=it["season_number"], episode=it["episode_number"])
        ids["type"] = name["type"] = "episode"
        if show and show["tmdb_id"]:
            ids["parent_tmdb_id"] = show["tmdb_id"]
        elif show and _imdb_number(show["imdb_id"]):
            ids["parent_imdb_id"] = _imdb_number(show["imdb_id"])
        if show:
            name["query"] = show["title"]
        for p in (ids, name):
            if it["season_number"] is not None:
                p["season_number"] = it["season_number"]
            if it["episode_number"] is not None:
                p["episode_number"] = it["episode_number"]
        if it["episode_number"] is None:  # an unnumbered extra: its name is all there is
            name["query"] = f"{show['title'] if show else ''} {it['title'] or ''}".strip()
            ids = {}
    else:
        ids["type"] = name["type"] = "movie"
        if it["tmdb_id"]:
            ids["tmdb_id"] = it["tmdb_id"]
        elif _imdb_number(it["imdb_id"]):
            ids["imdb_id"] = _imdb_number(it["imdb_id"])
        name["query"] = it["title"]
        if it["year"]:
            name["year"] = it["year"]
    if f["quick_hash"] and (f["size"] or 0) >= 131072:  # their hash reads 64 KiB at each end
        ids["moviehash"] = name["moviehash"] = f["quick_hash"]
    if not any(k in ids for k in ("tmdb_id", "imdb_id", "parent_tmdb_id", "parent_imdb_id")):
        ids = {}
    if not name.get("query"):
        name = {}
    return {"ids": ids, "name": name}, what


def _params(p: dict, languages: str) -> list[tuple[str, str]]:
    """Their advice for fast (cached, redirect-free) answers: parameters sorted, values lowercase."""
    q = {**p, "languages": languages} if languages else dict(p)
    return sorted((k, str(v).lower()) for k, v in q.items())


def _result(d: dict) -> dict | None:
    a = d.get("attributes") or {}
    files = a.get("files") or []
    if len(files) != 1:  # a subtitle split over 2 CDs belongs to a video split the same way
        return None
    up = a.get("uploader") or {}
    return {"file_id": files[0].get("file_id"), "language": a.get("language"),
            "release": (a.get("release") or files[0].get("file_name") or "").strip()[:200],
            "hearing_impaired": bool(a.get("hearing_impaired")), "fps": a.get("fps") or None,
            "downloads": a.get("download_count") or 0, "rating": a.get("ratings") or None,
            "trusted": bool(a.get("from_trusted")), "ai": bool(a.get("ai_translated")),
            "machine": bool(a.get("machine_translated")), "hash_match": bool(a.get("moviehash_match")),
            "uploader": up.get("name"), "uploaded": a.get("upload_date"), "url": a.get("url")}


def search(con: sqlite3.Connection, client: Client, file_id: int, languages: str) -> dict:
    """Subtitles OpenSubtitles has for a file, best first (theirs: the ones made for this exact file lead)."""
    languages = ",".join(sorted(set(languages.lower().split(",")))) if languages else ""
    if languages and not _LANGS_RE.match(languages):
        raise ValueError("languages: codes like en or pt-br, separated by commas")
    asks, what = lookup(con, file_id)
    try:  # searching needs no account; signed in, it goes to the account's API host as they ask
        token, base = sign_in(con, client)
    except LoginRefused:
        token = base = None
    results: list[dict] = []
    by = None
    for by, p in asks.items():  # by ids (and hash) first; by name when that finds nothing
        if not p:
            continue
        d = client.request("GET", "/subtitles", params=_params(p, languages), token=token, base=base)
        results = [r for x in d.get("data") or [] if (r := _result(x)) and r["file_id"]]
        if results:
            break
    have = {r["ext_id"]: f"d{r['id']}" for r in con.execute(
        "SELECT id, ext_id FROM subtitle_downloads WHERE file_id=? AND provider=?", (file_id, PROVIDER))}
    for r in results:
        r["track"] = have.get(str(r["file_id"]))  # already downloaded for this file: just pick it
    return {"what": what, "by": by if results else None, "results": results, "account": token is not None}


# ------------------------------------------------------------------ downloading, the file's tracks

# ------------------------------------------------------------------ a copy next to the video

def save_beside_on(con: sqlite3.Connection) -> bool:
    return get_setting(con, SAVE_SETTING, "1") != "0"


def _beside_name(stem: str, language: str | None, hearing_impaired: bool, n: int) -> str:
    """"Episode.en.srt", "Episode.en.sdh.srt", then "Episode.en.2.srt"...: what BAMS, Jellyfin and Plex read as a
    subtitle of that video in that language ("pt-br" is written "pt-BR", as they expect)."""
    lang = re.sub(r"[^a-z0-9-]", "", (language or "").lower())[:12].strip("-") or "und"
    if "-" in lang:
        a, _, b = lang.partition("-")
        lang = f"{a}-{b.upper()}"
    return f"{stem}.{lang}{'.sdh' if hearing_impaired else ''}{f'.{n}' if n > 1 else ''}.srt"


def save_beside(video: Path, language: str | None, hearing_impaired: bool, data: bytes) -> str:
    """Save a downloaded subtitle next to its video through readonly.create_sidecar (a new file only: a name that's
    taken gets the next number). A file there with the same bytes is used as it is. Returns the file name; OSError
    when the OS refuses (a read-only mount, the service's sandbox, permissions)."""
    for n in range(1, 21):
        name = _beside_name(video.stem, language, hearing_impaired, n)
        there = video.parent / name
        if os.path.lexists(there):
            try:
                if there.stat().st_size == len(data):
                    with readonly.open_ro(there) as f:
                        if f.read(len(data) + 1) == data:
                            return name
            except OSError:
                pass
            continue
        try:
            readonly.create_sidecar(video, name, data)
            return name
        except FileExistsError:
            continue
    raise OSError(errno.EEXIST, "there are already 20 subtitle files with that name next to the video")


def _save_problem(e: Exception) -> str:
    """Why a copy couldn't be saved, for the player and Settings."""
    err = getattr(e, "errno", None)
    if err == errno.EROFS:
        return ("this server lets BAMS write only in its own data folder; Settings → Playback → OpenSubtitles shows "
                "how to allow it for your library folders")
    if err in (errno.EACCES, errno.EPERM):
        return "the account BAMS runs as isn't allowed to write in that folder"
    return getattr(e, "strerror", None) or str(e)


def _video(con: sqlite3.Connection, file_id: int) -> Path | None:
    r = con.execute("""SELECT f.rel_path, f.available, lr.path root FROM files f
                       JOIN library_roots lr ON lr.id=f.root_id WHERE f.id=?""", (file_id,)).fetchone()
    return Path(r["root"]) / r["rel_path"] if r and r["available"] else None


def keep_beside(con: sqlite3.Connection, data_dir: Path, file_id: int, row_id: int) -> tuple[str | None, str | None]:
    """A downloaded subtitle's copy next to its video, saved now if the setting is on and there's none yet:
    (file name, None), or (None, why not). The disk work happens before the short write that records it."""
    r = con.execute("SELECT * FROM subtitle_downloads WHERE id=?", (row_id,)).fetchone()
    if r["sidecar"] or not save_beside_on(con):
        return r["sidecar"], None
    video = _video(con, file_id)
    try:
        if video is None:
            raise OSError(errno.ENOENT, "the video isn't reachable right now (drive offline, or moved)")
        name = save_beside(video, r["language"], bool(r["hearing_impaired"]), (data_dir / r["path"]).read_bytes())
    except (OSError, ValueError) as e:
        why = _save_problem(e)
        log.warning("OpenSubtitles: couldn't save subtitle %s next to %s: %s", r["ext_id"], video, e)
        with Tx(con):
            set_setting(con, SAVE_ERROR_SETTING, jdump({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                        "folder": str(video.parent) if video else None, "why": why}))
        return None, why
    with Tx(con):
        con.execute("UPDATE subtitle_downloads SET sidecar=? WHERE id=?", (name, row_id))
        set_setting(con, SAVE_ERROR_SETTING, None)
    log.info("OpenSubtitles: saved %s next to its video", name)
    return name, None


def save_check(con: sqlite3.Connection) -> dict:
    """Settings: can BAMS save copies in each TV/movie library folder (the OS's answer, checked without writing; on
    Windows only the read-only flag is visible, so `null`)? `fix`: the command that allows it when the Linux
    service's sandbox (ProtectSystem=strict) is what says no."""
    out = []
    for r in con.execute("""SELECT l.name, r.path FROM library_roots r JOIN libraries l ON l.id=r.library_id
                            WHERE l.type IN ('show', 'movie') ORDER BY l.name COLLATE NOCASE, r.path"""):
        p = Path(r["path"])
        exists = p.is_dir()
        writable = (os.access(p, os.W_OK) if sys.platform != "win32" else None) if exists else False
        out.append({"library": r["name"], "path": r["path"], "exists": exists, "writable": writable})
    fix = None
    blocked = [x["path"] for x in out if x["exists"] and x["writable"] is False]
    if blocked and sys.platform.startswith("linux") and os.environ.get("INVOCATION_ID"):  # a systemd service
        conf = "/etc/systemd/system/bams.service.d/20-subtitles.conf"
        # "-": a folder that's missing at start-up (an unmounted drive) doesn't stop the service
        rw = "ReadWritePaths=" + " ".join(f'"-{b}"' if " " in b else f"-{b}" for b in blocked)
        fix = (f"sudo mkdir -p {os.path.dirname(conf)} && printf '%s\n' '[Service]' {shlex.quote(rw)} | sudo tee {conf}"
               " && sudo systemctl daemon-reload && sudo systemctl restart bams")
    return {"roots": out, "fix": fix}


def set_save_beside(con: sqlite3.Connection, on: bool) -> dict:
    with Tx(con):
        set_setting(con, SAVE_SETTING, "1" if on else "0")
        if not on:
            set_setting(con, SAVE_ERROR_SETTING, None)
    return status(con)


def listing(con: sqlite3.Connection, file_id: int, own: list[dict]) -> list[dict]:
    """A file's subtitle tracks for the player: its own (subtitles.tracks) and its downloaded ones, without the copies
    BAMS saved next to the video (they're the same subtitle as their download, which has the better label). A copy
    whose download was removed stays: it's an ordinary sidecar then."""
    saved = {r[0] for r in con.execute(
        "SELECT sidecar FROM subtitle_downloads WHERE file_id=? AND sidecar IS NOT NULL", (file_id,))}
    return [t for t in own if not (t.get("source") == "file" and t.get("file") in saved)] + tracks(con, file_id)


def tracks(con: sqlite3.Connection, file_id: int) -> list[dict]:
    """The file's downloaded subtitles, as subtitles.tracks() lists a file's own ("d<row id>")."""
    out = []
    for r in con.execute("SELECT * FROM subtitle_downloads WHERE file_id=? ORDER BY id", (file_id,)):
        code, name = subtitles.language(r["language"])
        release = r["release"] or ""
        if len(release) > 60:
            release = release[:57] + "…"
        out.append({"id": f"d{r['id']}", "index": r["id"], "source": "download", "provider": r["provider"],
                    "language": code or r["language"], "codec": "srt",
                    "label": " · ".join(filter(None, [name or r["language"] or "Subtitles", release,
                                                      "SDH" if r["hearing_impaired"] else None])),
                    "forced": False, "sdh": bool(r["hearing_impaired"]), "image": False, "ext_id": r["ext_id"],
                    "added_by": r["added_by"], "url": f"/api/files/{file_id}/subtitles/d{r['id']}.vtt"})
    return out


def stored(data_dir: Path, con: sqlite3.Connection, track: dict) -> Path:
    """Where a downloaded track's file is."""
    r = con.execute("SELECT path FROM subtitle_downloads WHERE id=?", (track["index"],)).fetchone()
    return data_dir / r["path"]


def _clean(data: bytes) -> bytes:
    """The subtitle as UTF-8 text (they send UTF-8; anything that isn't text is refused)."""
    text = subtitles._decode(data)
    if "\x00" in text or "-->" not in text:
        raise OpenSubtitlesError("OpenSubtitles sent something that isn't a subtitle file. Try another one.")
    return text.encode("utf-8")


def download(con: sqlite3.Connection, client: Client, data_dir: Path, file_id: int, sub_file_id: int,
             language: str | None, release: str | None, hearing_impaired: bool, user_id: int | None) -> dict:
    """Get one of the search's subtitles for a file and keep it as one of the file's tracks. A subtitle this
    server already has (for this file or another) isn't downloaded again, so it doesn't count against the quota."""
    ext = str(sub_file_id)
    if not con.execute("SELECT 1 FROM files WHERE id=?", (file_id,)).fetchone():
        raise LookupError("no such file")
    mine = con.execute("SELECT id FROM subtitle_downloads WHERE file_id=? AND provider=? AND ext_id=?",
                       (file_id, PROVIDER, ext)).fetchone()
    if mine:  # picked before: just that track (and its copy next to the video, if that failed or was off before)
        saved, why = keep_beside(con, data_dir, file_id, mine["id"])
        return {"track": next(t for t in tracks(con, file_id) if t["index"] == mine["id"]), "remaining": None,
                "message": None, "saved": saved, "save_error": why}
    rel = f"{FOLDER}/{ext}.srt"
    dest = data_dir / rel
    remaining = message = None
    if not dest.is_file():
        token, base = sign_in(con, client)
        try:
            d = client.request("POST", "/download", body={"file_id": sub_file_id}, token=token, base=base)
        except OpenSubtitlesError as e:
            # a token can stop working before its day is up (they answer 401, or 500 "invalid"): sign in again once
            if not token or e.status not in (401, 500) or isinstance(e, QuotaReached):
                raise
            _forget_token()
            token, base = sign_in(con, client)
            d = client.request("POST", "/download", body={"file_id": sub_file_id}, token=token, base=base)
        if not d.get("link"):
            raise OpenSubtitlesError(d.get("message") or "OpenSubtitles didn't give a download link.")
        text = _clean(client.fetch(d["link"]))
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(text)
        os.replace(tmp, dest)
        remaining, message = d.get("remaining"), d.get("message")
        log.info("OpenSubtitles: subtitle %s for file %s (%s left today)", ext, file_id, remaining)
    with Tx(con):
        cur = con.execute(
            """INSERT INTO subtitle_downloads (file_id, provider, ext_id, language, release, hearing_impaired, path,
               added_by, added_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (file_id, PROVIDER, ext, (language or "")[:16] or None, (release or "")[:200] or None,
             int(bool(hearing_impaired)), rel, user_id, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    row_id = cur.lastrowid
    saved, why = keep_beside(con, data_dir, file_id, row_id)
    return {"track": next(t for t in tracks(con, file_id) if t["index"] == row_id), "remaining": remaining,
            "message": message, "saved": saved, "save_error": why}


def remove(con: sqlite3.Connection, data_dir: Path, row_id: int) -> None:
    """Take a downloaded subtitle off a file; its file in the data dir goes too once no other video uses it. A copy
    saved next to the video stays (BAMS never deletes in media folders): it's one of the file's own tracks then."""
    r = con.execute("SELECT path FROM subtitle_downloads WHERE id=?", (row_id,)).fetchone()
    if not r:
        return
    with Tx(con):
        con.execute("DELETE FROM subtitle_downloads WHERE id=?", (row_id,))
    if not con.execute("SELECT 1 FROM subtitle_downloads WHERE path=?", (r["path"],)).fetchone():
        (data_dir / r["path"]).unlink(missing_ok=True)
