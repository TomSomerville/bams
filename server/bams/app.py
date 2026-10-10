"""HTTP API (FastAPI). Interactive docs at /docs while the server runs."""

from __future__ import annotations

import logging
import mimetypes
import os
import socket
import sqlite3
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request
import anyio
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, fsbrowse, hls, identify, library, matcher, music_match, probe, readonly, stream, subtitles, watch
from . import devices, netflow, security, updates
from .config import VERSION, Paths
from .db import Tx, connect, get_setting, jdump, jload, migrate, set_setting
from .jobs import Scheduler, language, music_lookup_enabled, tmdb_client
from .musicbrainz import MusicBrainz, MusicLookupError
from .parse import guess, parse_episode, parse_movie
from .tmdb import InvalidKey, Tmdb, TmdbError, key_kind

log = logging.getLogger(__name__)


def bootstrap(paths: Paths) -> None:
    """Data dir, schema, and the read-only guard. Called by the server and the CLI."""
    paths.ensure()
    con = connect(paths.db)
    try:
        migrate(con, backup_dir=paths.root / "backups")
        readonly.install_guard()
        library.refresh_guard(con)
    finally:
        con.close()


# ------------------------------------------------------------------ serialisation

def _img(rel: str | None) -> str | None:
    return f"/api/images/{rel}" if rel else None


# Item rows plus how many children they have (seasons of a show, episodes of a season, albums of an
# artist, tracks of an album), their parent's title (an album's artist), and for an artist without an
# image of their own, the cover of their earliest album.
ITEM_SELECT = """SELECT items.*, (SELECT COUNT(*) FROM items c WHERE c.parent_id = items.id) AS child_count,
    (SELECT p.title FROM items p WHERE p.id = items.parent_id) AS parent_title,
    CASE WHEN items.kind = 'artist' AND items.poster IS NULL THEN
        (SELECT a.poster FROM items a WHERE a.parent_id = items.id AND a.poster IS NOT NULL
         ORDER BY a.year IS NULL, a.year LIMIT 1) END AS fallback_poster
    FROM items"""
MUSIC_KINDS = ("artist", "album", "track")


def item_summary(r: sqlite3.Row) -> dict:
    keys = r.keys()
    poster = r["poster"] or (r["fallback_poster"] if "fallback_poster" in keys else None)
    d = {
        "id": r["id"], "kind": r["kind"], "library_id": r["library_id"], "title": r["title"], "year": r["year"],
        "poster": _img(poster), "backdrop": _img(r["backdrop"]), "overview": r["overview"],
        "genres": jload(r["genres"]) or [], "rating": r["rating"], "runtime": r["runtime"],
        "match_status": r["match_status"], "added_at": r["added_at"],
        "child_count": r["child_count"] if "child_count" in keys else None,
    }
    if r["kind"] in ("album", "track"):
        d.update(parent_id=r["parent_id"], parent_title=r["parent_title"] if "parent_title" in keys else None,
                 duration=r["duration"])
    if r["kind"] == "track":
        d.update(track_number=r["track_number"], disc_number=r["disc_number"], artist=r["artist"])
    if r["kind"] == "season":
        d["season_number"] = r["season_number"]
    if r["kind"] == "episode":
        d.update(season_number=r["season_number"], episode_number=r["episode_number"],
                 still=_img(r["still"]), air_date=r["air_date"])
    return d


def item_detail(r: sqlite3.Row) -> dict:
    d = item_summary(r)
    d.update(
        parent_id=r["parent_id"], tagline=r["tagline"], air_date=r["air_date"], still=_img(r["still"]),
        parsed_title=r["parsed_title"],
        ids={"tmdb": r["tmdb_id"], "imdb": r["imdb_id"], "tvdb": r["tvdb_id"], "musicbrainz": r["mbid"]},
        extra=jload(r["extra"]) or {},
        match_score=r["match_score"], metadata_at=r["metadata_at"],
    )
    return d


def audio_tracks(pr: dict | None) -> list[dict]:
    """The file's audio tracks as the player's menu lists them ("English · AC3 5.1 · Commentary")."""
    out = []
    for n, a in enumerate((pr or {}).get("audio") or []):
        code, name = subtitles.language(a.get("language"))
        ch = a.get("channels")
        layout = {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}.get(ch, f"{ch} ch" if ch else None)
        title = a.get("title")
        label = " · ".join(filter(None, [name or (f"Track {n + 1}" if not title else None),
                                         " ".join(filter(None, [a.get("codec"), layout])) or None,
                                         title if title and title != name else None]))
        out.append({"index": n, "label": label, "language": code, "codec": a.get("codec"), "channels": ch,
                    "default": bool(a.get("default"))})
    return out


def music_output(con: sqlite3.Connection) -> str:
    """What music browsers can't play is converted to (Settings → Music): "aac" (default) or "flac"."""
    v = get_setting(con, "music_output", "aac")
    return v if v in stream.MUSIC_OUTPUTS else "aac"


def file_info(r: sqlite3.Row, with_subtitles: bool = False, music_out: str = "aac") -> dict:
    """A file as the API returns it. `with_subtitles` also lists sidecar subtitle files, which means listing
    the file's folder (fine for one title's files, not for long lists)."""
    pr, pa = jload(r["probe"]), jload(r["parse"])
    if (pa or {}).get("kind") == "track":  # music
        pb = stream.plan_audio(pr, r["rel_path"], music_out)
        pb["url"] = f"/api/files/{r['id']}/{'audio' if pb['mode'] == 'transcode' else 'stream'}"
    else:
        pb = stream.plan(pr, pa)
        # where the player should point <video>: the original bytes, the audio-fixing remux, or a transcode
        pb["url"] = f"/api/files/{r['id']}/{ {'remux': 'remux', 'transcode': 'transcode'}.get(pb['mode'], 'stream')}"
        # for browsers that turn out not to decode the video (HEVC/AV1 in Firefox...) or a lower quality:
        # an HLS session (POST hls_url) where the player can, else the plain fMP4 transcode
        ff = bool(stream.ffmpeg_path())
        pb["transcode_url"] = f"/api/files/{r['id']}/transcode" if ff else None
        pb["hls_url"] = f"/api/files/{r['id']}/hls" if ff else None
    d = {
        "id": r["id"], "path": r["rel_path"], "root": r["root"], "size": r["size"],
        "available": bool(r["available"]), "probe": pr,
        "release": (pa or {}).get("release"), "playback": pb,
        "stream_url": f"/api/files/{r['id']}/stream",
    }
    if (pa or {}).get("kind") != "track":
        d["audio_tracks"] = audio_tracks(pr)
        if with_subtitles:
            video = Path(r["root"]) / r["rel_path"] if r["available"] else None
            d["subtitles"] = subtitles.tracks(pr, video, r["id"])
    return d


def _probe_now(con: sqlite3.Connection, rows: list[sqlite3.Row]) -> bool:
    """Read the details of a movie's/episode's files the scan hasn't probed yet (a scan still running, or
    one that skipped it). Without them the player knows no duration: no HLS, no timeline, and no saved
    position. Probed first, then one short write (never hold a write while touching the disk)."""
    todo = [(f["id"], Path(f["root"]) / f["rel_path"]) for f in rows if f["probe"] is None and f["available"]]
    found = [(fid, info) for fid, path in todo if (info := probe.probe(path, timeout=30))]
    if found:
        with Tx(con):
            for fid, info in found:
                con.execute("UPDATE files SET probe=?, probed_at=? WHERE id=? AND probe IS NULL",
                            (jdump(info), time.time(), fid))
    return bool(found)


def unrecognized_hint(rel: str, lib_type: str) -> str:
    """Why a file wasn't placed. Most often: a movie in a TV library or vice versa."""
    if lib_type == "music":
        return "Couldn't read this file's tags or name."
    if lib_type == "show":
        m = parse_movie(rel.replace("\\", "/").rsplit("/", 1)[-1])  # the file's own name: show folders have years too
        if m.title and m.year:
            return (f"Looks like a movie ({m.title}, {m.year}), but this is a TV library. "
                    "Put movies in their own folder and add it as a Movies library.")
        return ("No season/episode number found in the name. Name episodes like "
                "'Show Name/Season 01/Show Name - S01E01.mkv'.")
    e = parse_episode(rel)
    if e.recognized:
        return (f"Looks like a TV episode ({e.title} S{e.season:02d}E{e.episodes[0]:02d}), but this is a Movies "
                "library. Add its folder to a TV Shows library instead.")
    return "No movie title found in the name. Name movies like 'Movie Title (Year)/Movie Title (Year).mkv'."


# ------------------------------------------------------------------ request models

class LibraryIn(BaseModel):
    name: str
    type: str = Field(pattern="^(movie|show|music)$")
    paths: list[str]
    scan_interval_hours: float = 6


class LibraryPatch(BaseModel):
    name: str | None = None
    scan_interval_hours: float | None = None
    add_paths: list[str] | None = None
    remove_paths: list[str] | None = None


class KeyIn(BaseModel):
    key: str


class MatchIn(BaseModel):
    tmdb_id: int


class IdentifyIn(BaseModel):
    """What a file is, entered by hand. TV libraries need a season; no episode numbers = an extra."""
    title: str = Field(min_length=1, max_length=200)
    year: int | None = Field(None, ge=1870, le=2100)
    season: int | None = Field(None, ge=0, le=9999)
    episodes: list[int] = Field(default_factory=list, max_length=50)
    episode_title: str | None = Field(None, max_length=300)
    edition: str | None = Field(None, max_length=100)
    tmdb_id: int | None = Field(None, ge=1)


class LinkIn(BaseModel):
    link: str = Field(min_length=1, max_length=500)
    library_id: int


class MusicMatchIn(BaseModel):
    mbid: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")


class ToggleIn(BaseModel):
    enabled: bool


class MusicOutputIn(BaseModel):
    output: str = Field(pattern="^(aac|flac)$")


class TranscodingIn(BaseModel):
    max_transcodes: int = Field(ge=0, le=32)  # 0 = automatic


class OrderIn(BaseModel):
    ids: list[int] = Field(max_length=1000)


class EncoderIn(BaseModel):
    encoder: str | None = None  # an id from stream.ENCODERS that works here; None = automatic


class WatchSettingsIn(BaseModel):
    watched_percent: int = Field(ge=50, le=100)   # a title counts as watched past this share of its length
    resume_after: int = Field(ge=0, le=600)       # seconds before it counts as started (saved, Continue Watching)


class HomeRowIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    show: bool


class PrefsIn(BaseModel):
    home_hero: bool | None = None
    home_rows: list[HomeRowIn] | None = Field(None, max_length=auth.MAX_HOME_ROWS)  # Home's rows, in order


class HlsIn(BaseModel):
    audio: int = Field(0, ge=0, le=31)
    height: int | None = Field(None, ge=144, le=4320)  # quality picker; None = as large as the encoder allows
    auto: bool = False       # automatic quality: several sizes, the player picks by throughput
    remux: bool = False      # audio-only remux: the video is copied, only the audio converted
    channels: int = Field(2, ge=1, le=8)  # 6 = keep 5.1 when the source has it
    # picture subtitles to paint onto the picture: a track id ("e1" embedded, "x0-0" a VobSub sidecar), or the
    # number of an embedded subtitle stream
    burn: int | str | None = None
    passthrough: bool = False  # remux: copy AC3/EAC3 audio as-is (the player's device says it decodes it)
    ts: bool = False           # remux: MPEG-TS segments instead of fMP4 (the TV app: Samsung's player takes no fMP4 HLS)
    start: float = Field(0, ge=0)  # where the player starts, so the first FFmpeg run starts there


class LoginIn(BaseModel):
    name: str = Field(max_length=100)
    password: str = Field(max_length=1024)
    code: str | None = Field(None, max_length=20)  # the authenticator app's code, for accounts with two-step sign-in


class TokenLoginIn(LoginIn):
    device: str = Field("TV", max_length=100)  # shown in Settings → Your TVs


class ServerNameIn(BaseModel):
    name: str = Field(max_length=60)  # "" = the default


def default_server_name(con: sqlite3.Connection) -> str:
    """"<first admin>'s BAM Server": named after the oldest admin account (the one made at setup, unless it was
    removed since); the computer's name until there is one."""
    r = con.execute("SELECT name FROM users WHERE is_admin=1 ORDER BY created_at, id LIMIT 1").fetchone()
    return f"{r['name']}'s BAM Server" if r else socket.gethostname()


def server_name(con: sqlite3.Connection) -> dict:
    """{name, default, custom}: the admin's name for this server (settings.server_name), else the default."""
    default = default_server_name(con)
    custom = get_setting(con, "server_name")
    return {"name": custom or default, "default": default, "custom": bool(custom)}


class LinkStartIn(BaseModel):
    name: str = Field("TV", max_length=100)


class LinkPollIn(BaseModel):
    secret: str = Field(max_length=200)


class LinkCodeIn(BaseModel):
    code: str = Field(max_length=20)


class PasswordIn(BaseModel):
    current: str = Field(max_length=1024)
    new: str = Field(max_length=1024)


class UserIn(BaseModel):
    name: str = Field(max_length=100)
    password: str = Field(max_length=1024)
    is_admin: bool = False
    must_change_password: bool = False  # they set their own password at their first sign-in


class UserPatch(BaseModel):
    name: str | None = Field(None, max_length=100)
    password: str | None = Field(None, max_length=1024)
    is_admin: bool | None = None
    must_change_password: bool | None = None  # on: signs them out; their next sign-in asks for a new password


class TwoFactorIn(BaseModel):
    secret: str = Field(pattern="^[A-Z2-7]{16,64}$")  # from POST /api/auth/2fa/setup
    code: str = Field(max_length=20)
    password: str = Field(max_length=1024)


class PasswordCheckIn(BaseModel):
    password: str = Field(max_length=1024)


class LockoutIn(BaseModel):
    threshold: int = Field(ge=1, le=security.MAX_THRESHOLD)


class IpEntry(BaseModel):
    cidr: str = Field(max_length=60)
    note: str = Field("", max_length=100)


class IpListsIn(BaseModel):
    mode: str = Field(pattern="^(allow_all|allowlist)$")
    allow: list[IpEntry] = Field(default_factory=list, max_length=security.MAX_IP_ENTRIES)
    block: list[IpEntry] = Field(default_factory=list, max_length=security.MAX_IP_ENTRIES)


class NetflowIn(BaseModel):
    folder: str | None = Field(None, max_length=1000)  # "" = back to the default folder
    max_bytes: int | None = Field(None, ge=netflow.MIN_MAX_BYTES, le=netflow.MAX_MAX_BYTES)


class LockIn(BaseModel):
    locked: bool


class ProgressIn(BaseModel):
    position: float = Field(ge=0)
    duration: float | None = Field(None, gt=0)


class WatchedIn(BaseModel):
    watched: bool


# ------------------------------------------------------------------ login

PUBLIC_API = frozenset({"/api/auth/state", "/api/auth/login", "/api/auth/setup",
                        # apps on other devices (devices.py): find the server, sign in or link with a code
                        "/api/hello", "/api/auth/token", "/api/devices/link", "/api/devices/link/poll"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# all an account that must set a new password (auth.py) can do until it has
MUST_CHANGE_API = frozenset({"/api/auth/password", "/api/auth/logout"})


class CodeNeeded(Exception):
    """A sign-in whose password was right but which needs (another) two-step code: 401 with `code_required`, so
    the client shows the code box."""

    def __init__(self, message: str):
        self.message = message


def bearer_token(req: Request) -> str | None:
    """The session token an app sends as `Authorization: Bearer <token>` (the TV app; browsers use the cookie)."""
    scheme, _, token = (req.headers.get("authorization") or "").partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def request_token(req: Request) -> str | None:
    return req.cookies.get(auth.COOKIE) or bearer_token(req)


class LoginRequired:
    """ASGI middleware: every /api/ route except signing in needs a valid session: the browser's cookie, an
    app's `Authorization: Bearer` token, or a media ticket in the path (`/api/t/<ticket>/files/...`, GET only,
    media only; devices.py). The signed-in user goes into `request.state.user`, the session's digest into
    `request.state.session`. Changes (POST/PUT/PATCH/DELETE) from another site's page are refused; that only
    matters for the cookie, which browsers attach by themselves (a bearer token never is).
    Plain ASGI rather than BaseHTTPMiddleware, which would sit between FFmpeg's streams and the client."""

    def __init__(self, app, lookup, tickets: devices.Tickets):
        self.app, self.lookup, self.tickets = app, lookup, tickets

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/") or path in PUBLIC_API:
            return await self.app(scope, receive, send)
        req = Request(scope)
        digest, cookie = None, False
        tp = devices.split_ticket_path(path)
        if tp:
            # the route sees the real path; the traffic log too (the Gate reads this same scope afterwards)
            scope["path"], scope["raw_path"] = tp[1], tp[1].encode()
        if tp and scope.get("method") in ("GET", "HEAD"):
            digest = self.tickets.check(tp[0])
        # anything else needs the session itself, ticket path or not: a client that keeps a server's media links
        # as ticket URLs (another server's, in the web app) can POST/DELETE them with its token (opening or
        # closing an HLS session); a ticket alone never changes anything
        elif token := req.cookies.get(auth.COOKIE):
            digest, cookie = auth.digest(token) if len(token) <= 100 else None, True
        elif token := bearer_token(req):
            digest = auth.digest(token) if len(token) <= 100 else None
        user = await anyio.to_thread.run_sync(self.lookup, digest) if digest else None
        if user is None:
            return await JSONResponse({"detail": "Sign in to BAMS first."}, status_code=401)(scope, receive, send)
        if cookie and scope.get("method") not in _SAFE_METHODS and not same_origin(req):
            return await JSONResponse({"detail": "Refused: the request came from another site."},
                                      status_code=403)(scope, receive, send)
        if user.get("must_change") and scope.get("path") not in MUST_CHANGE_API:
            return await JSONResponse({"detail": "Set a new password for your account first.",
                                       "must_change_password": True}, status_code=403)(scope, receive, send)
        state = scope.setdefault("state", {})
        state["user"], state["session"] = user, digest
        return await self.app(scope, receive, send)


def same_origin(req: Request) -> bool:
    """Browsers send Origin with every cross-site POST/PUT/DELETE; tools like curl send none (and no cookie
    unless given one). A sandboxed page's "null" origin doesn't match."""
    origin = req.headers.get("origin")
    return not origin or urlsplit(origin).netloc == req.headers.get("host")


def current_user(request: Request) -> dict:
    return request.state.user


def admin_only(request: Request) -> dict:
    u = request.state.user
    if not u["is_admin"]:
        raise HTTPException(403, "Only an admin can do that.")
    return u


ADMIN = [Depends(admin_only)]


# ------------------------------------------------------------------ app

class SpaFiles(StaticFiles):
    """Static files, but unknown paths (client-side routes like /settings) get index.html."""

    async def get_response(self, path, scope):
        try:
            resp = await super().get_response(path, scope)
        except StarletteHTTPException as e:
            p = path.replace("\\", "/")  # OS-normalised path
            if e.status_code != 404 or p.startswith(("api/", "assets/")):  # a missing script stays a 404
                raise
            resp = await super().get_response("index.html", scope)
        if resp.media_type == "text/html":
            # the page names this build's scripts: browsers must re-check it, or after an update they keep
            # an old page whose scripts no longer exist (the hashed scripts themselves can be cached)
            resp.headers["cache-control"] = "no-cache"
        return resp


def create_app(paths: Paths, *, start_scheduler: bool = True, web_dir: Path | None = None) -> FastAPI:
    bootstrap(paths)
    scheduler = Scheduler(paths)
    _con = connect(paths.db)
    try:
        stream.set_preferred(get_setting(_con, "video_encoder"))  # CPU or GPU, as the admin chose (else automatic)
    finally:
        _con.close()

    def transcode_limit() -> int:
        """Simultaneous video conversions allowed: the setting, or 4 on a GPU encoder / 2 on the CPU."""
        con = connect(paths.db)
        try:
            n = int(get_setting(con, "max_transcodes", "0") or 0)
        finally:
            con.close()
        return n or auto_transcode_limit()

    def auto_transcode_limit() -> int:
        return 4 if stream.video_encoder() in stream.HARDWARE else 2

    transcodes = hls.Transcodes(paths.transcode, transcode_limit)
    keyframes = hls.Keyframes(paths.cache / "keyframes")
    throttle = auth.Throttle()
    sec = security.Security(paths.security_db, paths.db)
    sec.load_policy()
    _con = connect(paths.db)
    try:
        flows = netflow.Netflow(Path(get_setting(_con, "netflow_dir") or paths.netflow),
                                int(get_setting(_con, "netflow_max_bytes") or netflow.DEFAULT_MAX_BYTES))
    finally:
        _con.close()

    # Signed-in users by session (its stored digest), for a minute: a playing video asks for a segment every few
    # seconds, and each would otherwise be a DB lookup. Signing out / password changes clear it.
    seen: dict[str, tuple[float, dict]] = {}
    seen_lock = threading.Lock()

    def lookup_digest(digest: str | None) -> dict | None:
        if not digest:
            return None
        t = time.monotonic()
        with seen_lock:
            hit = seen.get(digest)
            if hit and t - hit[0] < 60:
                return hit[1]
        con = connect(paths.db)
        try:
            u = auth.session_user_by_digest(con, digest)
        finally:
            con.close()
        user = {"id": u["id"], "name": u["name"], "is_admin": bool(u["is_admin"]),
                "must_change": bool(u["must_change_password"])} if u else None
        with seen_lock:
            if len(seen) > 1000:
                seen.clear()
            if user:
                seen[digest] = (t, user)
            else:
                seen.pop(digest, None)
        return user

    def lookup(token: str | None) -> dict | None:
        return lookup_digest(auth.digest(token)) if token and len(token) <= 100 else None

    tickets = devices.Tickets()
    link_codes = devices.LinkCodes()
    link_throttle = auth.Throttle()  # wrong TV codes, per account: codes are short

    def forget_sessions() -> None:
        with seen_lock:
            seen.clear()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        transcodes.start()
        if start_scheduler:
            scheduler.start()
            # find the video encoder now (a few test encodes) rather than on the first play
            threading.Thread(target=stream.video_encoder, name="encoder-detect", daemon=True).start()
            # a finished update: its Task Scheduler task and the installer it ran go
            threading.Thread(target=updates.tidy, args=(paths.root / "updates",), name="update-tidy", daemon=True).start()
        yield
        scheduler.stop()
        transcodes.shutdown()

    app = FastAPI(title="BAMS", version=VERSION, lifespan=lifespan,
                  description="Bad Ass Media Server API. Media folders are read-only to this server.")
    app.state.paths = paths
    app.state.scheduler = scheduler
    app.state.transcodes = transcodes
    app.state.security = sec
    app.state.netflow = flows
    app.add_middleware(LoginRequired, lookup=lookup_digest, tickets=tickets)
    # Apps on other devices (the TV app runs from its own origin) may call the API with a bearer token. "*" never
    # lets another site use a browser's cookie: browsers don't send credentials to a wildcard origin.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["authorization", "content-type"], max_age=3600)
    app.add_middleware(security.Gate, security=sec, flows=flows)  # added last = outermost: sees every request

    def db() -> Iterator[sqlite3.Connection]:
        con = connect(paths.db)
        try:
            yield con
        finally:
            con.close()

    @app.exception_handler(library.LibraryError)
    async def _lib_err(_req: Request, e: library.LibraryError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(CodeNeeded)
    async def _code_needed(_req: Request, e: CodeNeeded):
        return JSONResponse({"detail": e.message, "code_required": True}, status_code=401)

    # -- signing in, accounts
    def _set_cookie(resp: Response, request: Request, token: str) -> None:
        resp.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https", path="/")

    def _client(request: Request) -> str:
        return request.client.host if request.client else "?"

    @app.get("/api/auth/state")
    def auth_state(request: Request, con=Depends(db)):
        """Who is signed in (null if nobody), and whether the first admin account still has to be created
        (`setup`), which this browser may do only from the server itself (`setup_here`)."""
        u = lookup(request_token(request))
        row = auth.get_user(con, u["id"]) if u else None
        u = {k: v for k, v in auth.public(row).items()
             if k in ("id", "name", "is_admin", "prefs", "must_change_password", "two_factor")} if row else None
        empty = auth.user_count(con) == 0
        return {"user": u, "setup": empty, "setup_here": empty and auth.is_loopback(_client(request))}

    @app.post("/api/auth/setup")
    def auth_setup(body: LoginIn, request: Request, response: Response, con=Depends(db)):
        """Create the first account (an admin). Only while there are no accounts, and only from a browser on
        the server itself; elsewhere, `bams user add NAME --admin` on the server does it."""
        if not same_origin(request):
            raise HTTPException(403, "Refused: the request came from another site.")
        if not auth.is_loopback(_client(request)):
            raise HTTPException(403, "The first account can only be created on the server itself (open BAMS at "
                                     "http://localhost:8484 there), or with `bams user add NAME --admin`.")
        with Tx(con):
            if auth.user_count(con):
                raise HTTPException(409, "BAMS already has an admin. Sign in instead.")
            try:
                uid = auth.create_user(con, body.name, body.password, is_admin=True)
            except auth.AuthError as e:
                raise HTTPException(400, str(e)) from None
        sec.forget_name(body.name)
        ua = request.headers.get("user-agent")
        sec.log("sign-in", "ok", name=body.name, user_id=uid, ip=_client(request), reason="first admin created",
                user_agent=ua)
        _set_cookie(response, request, auth.new_session(con, uid, ua))
        return auth.public(auth.get_user(con, uid))

    def _wait_text(s: float) -> str:
        s = max(1, round(s))
        return f"{s} second{'s' if s != 1 else ''}" if s < 120 else f"{round(s / 60)} minutes"

    @app.post("/api/auth/login")
    def auth_login(body: LoginIn, request: Request, response: Response, con=Depends(db)):
        """Sign in. Each wrong password makes the account wait (1 s, then doubling) and enough of them in a row
        lock it (Settings -> Security). Every attempt goes into the sign-in log."""
        if not same_origin(request):
            raise HTTPException(403, "Refused: the request came from another site.")
        u = _sign_in(body, request, con)
        _set_cookie(response, request, auth.new_session(con, u["id"], request.headers.get("user-agent")))
        return auth.public(u)

    @app.post("/api/auth/token")
    def auth_token(body: TokenLoginIn, request: Request, con=Depends(db)):
        """Sign in from an app (the TV app): the same checks as the web sign-in, but the session token comes back
        in the body, for `Authorization: Bearer`. No cookie is set, so it can't be used by another site."""
        u = _sign_in(body, request, con)
        if u["must_change_password"]:
            # apps have no "set your new password" screen
            raise HTTPException(403, f"{u['name']} must set a new password first: sign in to "
                                     f"{server_name(con)['name']} in a web browser, then try again.")
        return {"token": auth.new_session(con, u["id"], _tv_agent(body.device)), "user": auth.public(u)}

    def _tv_agent(device: str) -> str:
        name = " ".join((device or "TV").split())[:100] or "TV"
        return f"{devices.TV_AGENT} · {name}"

    def _sign_in(body: LoginIn, request: Request, con: sqlite3.Connection) -> sqlite3.Row:
        """Check a name and password (waits, lockout, sign-in log); the user's row, or an HTTPException."""
        ip, ua, name = _client(request), request.headers.get("user-agent"), body.name.strip()

        def refuse(status: int, why: str, msg: str, uid: int | None = None, headers: dict | None = None):
            sec.log("sign-in", "failed", name=name, user_id=uid, ip=ip, reason=why, user_agent=ua)
            raise HTTPException(status, msg, headers=headers)

        if throttle.blocked(ip):
            refuse(429, "too many wrong passwords from this address",
                   "Too many wrong passwords. Wait ten minutes and try again.")
        known = auth.get_user(con, name)
        uid = known["id"] if known else None
        key = security.account_key(uid, name)
        with sec.attempt(key):
            stop = sec.refusal(key)
            if stop and stop[0] == "locked":
                refuse(403, "account locked", "This account is locked. Ask an admin to unlock it.", uid)
            if stop:
                refuse(429, "tried again too soon", f"Wait {_wait_text(stop[1])} before trying again.", uid,
                       {"Retry-After": str(max(1, round(stop[1])))})
            u = auth.authenticate(con, name, body.password)
            if not u:
                throttle.fail(ip)
                n, locked = sec.failed(key, security.threshold(con))
                log.warning("failed sign-in for %r from %s", name[:40], ip)
                why = "wrong password" if known else "no such account"
                if locked:
                    refuse(403, f"{why}; locked after {n} in a row",
                           "Wrong name or password. That was too many: the account is now locked. Ask an admin "
                           "to unlock it.", uid)
                refuse(401, why, f"Wrong name or password. Wait {_wait_text(security.wait_after(n))} before "
                                 "trying again.", uid)
            if u["totp_secret"]:
                # the password alone neither counts as a failure nor resets the count: otherwise someone who knows
                # it could try codes forever
                if not (body.code or "").strip():
                    raise CodeNeeded("Enter the 6-digit code from your authenticator app.")
                if not auth.check_code(con, u, body.code):
                    throttle.fail(ip)
                    n, locked = sec.failed(key, security.threshold(con))
                    log.warning("wrong two-step code for %r from %s", name[:40], ip)
                    if locked:
                        refuse(403, f"wrong two-step code; locked after {n} in a row",
                               "Wrong code. That was too many: the account is now locked. Ask an admin to unlock "
                               "it.", uid)
                    sec.log("sign-in", "failed", name=name, user_id=uid, ip=ip, reason="wrong two-step code",
                            user_agent=ua)
                    raise CodeNeeded(f"That code isn't right (or was already used). Wait "
                                     f"{_wait_text(security.wait_after(n))} and try again with the code the app "
                                     "shows now.")
            sec.succeeded(key)
        throttle.ok(ip)
        sec.log("sign-in", "ok", name=name, user_id=u["id"], ip=ip, user_agent=ua)
        return u

    @app.post("/api/auth/logout", status_code=204)
    def auth_logout(request: Request, response: Response, con=Depends(db)):
        auth.end_session(con, request_token(request))
        forget_sessions()
        response.delete_cookie(auth.COOKIE, path="/")

    # -- apps on other devices (devices.py): finding the server, linking with a code, media tickets
    @app.get("/api/hello")
    def hello():
        """Public: tells an app looking around the network that this is a BAMS server, and which."""
        con = connect(paths.db)
        try:
            return {"app": "bams", "version": VERSION, "name": server_name(con)["name"]}
        finally:
            con.close()

    @app.post("/api/devices/link")
    def link_start(body: LinkStartIn):
        """Public: a TV asks for a code to show. Someone signed in enters it (POST /api/devices/approve or the
        web page /link); the TV polls with `secret` until then."""
        try:
            return link_codes.start(" ".join(body.name.split())[:100] or "TV")
        except devices.LinkError as e:
            raise HTTPException(429, str(e)) from None

    @app.post("/api/devices/link/poll")
    def link_poll(body: LinkPollIn, request: Request, con=Depends(db)):
        """Public: {status: waiting|expired} or, once the code was entered, {status: linked, token, user}
        (once; the token is a session like any other)."""
        status, uid, name = link_codes.poll(body.secret)
        if status != "linked":
            return {"status": status}
        u = auth.get_user(con, uid)
        if not u:  # removed in the meantime
            return {"status": "expired"}
        sec.log("sign-in", "ok", name=u["name"], user_id=uid, ip=_client(request), reason=f"TV linked: {name}",
                user_agent=request.headers.get("user-agent"))
        return {"status": "linked", "token": auth.new_session(con, uid, _tv_agent(name)), "user": auth.public(u)}

    @app.post("/api/devices/approve")
    def link_approve(body: LinkCodeIn, request: Request, me=Depends(current_user)):
        """Link the TV showing `code` to your account."""
        who = f"u{me['id']}"
        if link_throttle.blocked(who):
            raise HTTPException(429, "Too many wrong codes. Wait ten minutes and try again.")
        try:
            name = link_codes.approve(body.code, me["id"])
        except devices.LinkError as e:
            link_throttle.fail(who)
            raise HTTPException(400, str(e)) from None
        return {"name": name}

    @app.get("/api/devices")
    def list_devices(con=Depends(db), me=Depends(current_user)):
        """Your linked TVs (their sessions), newest first."""
        rows = con.execute("""SELECT token, created_at, last_seen_at, user_agent FROM sessions
                              WHERE user_id=? AND user_agent LIKE ? ORDER BY created_at DESC""",
                           (me["id"], devices.TV_AGENT + "%")).fetchall()
        return [{"id": r["token"][:16], "name": r["user_agent"][len(devices.TV_AGENT):].lstrip(" ·") or "TV",
                 "created_at": r["created_at"], "last_seen_at": r["last_seen_at"]} for r in rows]

    @app.delete("/api/devices/{device_id}", status_code=204)
    def remove_device(device_id: str, con=Depends(db), me=Depends(current_user)):
        """Sign one of your TVs out."""
        if not (len(device_id) == 16 and all(c in "0123456789abcdef" for c in device_id)):
            raise HTTPException(404, "no such TV")
        n = con.execute("DELETE FROM sessions WHERE user_id=? AND substr(token, 1, 16)=? AND user_agent LIKE ?",
                        (me["id"], device_id, devices.TV_AGENT + "%")).rowcount
        if not n:
            raise HTTPException(404, "no such TV")
        forget_sessions()

    @app.get("/api/media-ticket")
    def media_ticket(request: Request):
        """A path prefix that opens this session's media (files, HLS, images) without headers, for players and
        <img> tags that can't send any: replace "/api/" in a media URL with `prefix` + "/"."""
        return {"prefix": f"/api/t/{tickets.make(request.state.session)}", "expires_in": devices.TICKET_TTL}

    @app.put("/api/auth/password")
    def change_password(body: PasswordIn, request: Request, response: Response, con=Depends(db),
                        me=Depends(current_user)):
        """Change your own password (also the one an admin asked you to change). Signs you out everywhere else."""
        try:
            with Tx(con):
                auth.change_own_password(con, me["id"], body.current, body.new)
        except auth.AuthError as e:
            raise HTTPException(400, str(e)) from None
        forget_sessions()
        _set_cookie(response, request, auth.new_session(con, me["id"], request.headers.get("user-agent")))
        return auth.public(auth.get_user(con, me["id"]))

    # -- two-step sign-in (auth.py): codes from an authenticator app such as Google Authenticator
    @app.post("/api/auth/2fa/setup")
    def two_factor_setup(con=Depends(db), me=Depends(current_user)):
        """A new secret to show as a QR code; nothing changes until POST /api/auth/2fa confirms a code from it."""
        secret = auth.new_totp_secret()
        return {"secret": secret, "uri": auth.totp_uri(secret, me["name"], server_name(con)["name"])}

    @app.post("/api/auth/2fa")
    def two_factor_on(body: TwoFactorIn, request: Request, con=Depends(db), me=Depends(current_user)):
        """Turn on two-step sign-in: your password, the secret from /setup and a code the app shows for it."""
        u = auth.get_user(con, me["id"])
        if not auth.verify_password(body.password, u["password"]):
            raise HTTPException(400, "Your password isn't right.")
        try:
            auth.enable_two_factor(con, me["id"], body.secret, body.code)
        except auth.AuthError as e:
            raise HTTPException(400, str(e)) from None
        sec.log("2fa", "ok", name=me["name"], user_id=me["id"], ip=_client(request), reason="two-step sign-in on",
                user_agent=request.headers.get("user-agent"))
        return auth.public(auth.get_user(con, me["id"]))

    @app.post("/api/auth/2fa/off")
    def two_factor_off(body: PasswordCheckIn, request: Request, con=Depends(db), me=Depends(current_user)):
        """Turn off your own two-step sign-in (needs your password)."""
        u = auth.get_user(con, me["id"])
        if not auth.verify_password(body.password, u["password"]):
            raise HTTPException(400, "Your password isn't right.")
        auth.disable_two_factor(con, me["id"])
        sec.log("2fa", "ok", name=me["name"], user_id=me["id"], ip=_client(request), reason="two-step sign-in off",
                user_agent=request.headers.get("user-agent"))
        return auth.public(auth.get_user(con, me["id"]))

    @app.delete("/api/users/{user_id}/2fa", dependencies=ADMIN)
    def two_factor_reset(user_id: int, request: Request, con=Depends(db), me=Depends(current_user)):
        """Admins: turn off someone's two-step sign-in (a lost phone). They can sign in with their password again."""
        u = auth.get_user(con, user_id)
        if not u:
            raise HTTPException(404, "No such user.")
        auth.disable_two_factor(con, user_id)
        sec.log("2fa", "admin", name=u["name"], user_id=user_id, ip=_client(request),
                reason=f"two-step sign-in turned off by {me['name']}", user_agent=request.headers.get("user-agent"))
        return auth.public(auth.get_user(con, user_id))

    @app.put("/api/me/prefs")
    def put_prefs(body: PrefsIn, con=Depends(db), me=Depends(current_user)):
        """Your own display preferences (each account has its own). Only the fields sent change."""
        return auth.set_prefs(con, me["id"], body.model_dump(exclude_none=True))

    @app.get("/api/users", dependencies=ADMIN)
    def list_users(con=Depends(db)):
        return [auth.public(u) for u in con.execute("SELECT * FROM users ORDER BY name COLLATE NOCASE")]

    @app.post("/api/users", status_code=201, dependencies=ADMIN)
    def add_user(body: UserIn, con=Depends(db)):
        try:
            uid = auth.create_user(con, body.name, body.password, body.is_admin, body.must_change_password)
        except auth.AuthError as e:
            raise HTTPException(400, str(e)) from None
        sec.forget_name(body.name)
        return auth.public(auth.get_user(con, uid))

    @app.patch("/api/users/{user_id}", dependencies=ADMIN)
    def patch_user(user_id: int, body: UserPatch, con=Depends(db)):
        """Rename, reset the password (signs them out), make/unmake an admin, or make them set a new password at
        their next sign-in (signs them out)."""
        try:
            with Tx(con):
                auth.update_user(con, user_id, **body.model_dump())
        except auth.AuthError as e:
            raise HTTPException(400, str(e)) from None
        forget_sessions()
        return auth.public(auth.get_user(con, user_id))

    @app.delete("/api/users/{user_id}", status_code=204, dependencies=ADMIN)
    def remove_user(user_id: int, me=Depends(current_user), con=Depends(db)):
        if user_id == me["id"]:
            raise HTTPException(400, "You can't remove your own account.")
        try:
            with Tx(con):
                auth.delete_user(con, user_id)
        except auth.AuthError as e:
            raise HTTPException(400, str(e)) from None
        sec.forget(user_id)
        forget_sessions()

    # -- security (admins): sign-in lockout and log, IP lists, traffic log
    def _netflow_status(con) -> dict:
        return {"folder": str(flows.folder), "default_folder": str(paths.netflow),
                "custom": bool(get_setting(con, "netflow_dir")), "max_bytes": flows.max_bytes, **flows.usage()}

    @app.get("/api/security", dependencies=ADMIN)
    def get_security(request: Request, con=Depends(db)):
        p = sec.load_policy()
        return {"lockout_threshold": security.threshold(con), "ip": p.public(), "your_ip": _client(request),
                "netflow": _netflow_status(con)}

    @app.put("/api/security/lockout", dependencies=ADMIN)
    def put_lockout(body: LockoutIn, con=Depends(db)):
        """Wrong passwords in a row that lock an account."""
        set_setting(con, "lockout_threshold", str(body.threshold))
        return {"lockout_threshold": body.threshold}

    @app.put("/api/security/ip", dependencies=ADMIN)
    def put_ip_lists(body: IpListsIn, request: Request, con=Depends(db)):
        """The allow and block lists and which one rules. Refused if it would shut out the admin saving it."""
        try:
            security.save_policy(con, body.mode, [e.model_dump() for e in body.allow],
                                 [e.model_dump() for e in body.block], _client(request))
        except security.SecurityError as e:
            raise HTTPException(400, str(e)) from None
        return sec.load_policy().public()

    @app.put("/api/security/netflow", dependencies=ADMIN)
    def put_netflow(body: NetflowIn, con=Depends(db)):
        """Where the traffic log goes ("" = the default folder) and how big it may grow."""
        folder = None
        if body.folder is not None:
            if body.folder.strip():
                try:
                    folder = netflow.check_folder(body.folder, [paths.transcode])
                except ValueError as e:
                    raise HTTPException(400, str(e)) from None
            else:
                folder = paths.netflow
        flows.configure(folder, body.max_bytes)
        if body.folder is not None:
            set_setting(con, "netflow_dir", str(folder) if body.folder.strip() else None)
        if body.max_bytes is not None:
            set_setting(con, "netflow_max_bytes", str(body.max_bytes))
        return _netflow_status(con)

    @app.get("/api/security/netflow/entries", dependencies=ADMIN)
    def netflow_entries(q: str | None = Query(None, max_length=200), before: str | None = Query(None, max_length=200),
                        limit: int = Query(200, ge=1, le=1000)):
        """Newest requests first; `q` keeps lines containing it (an address, a path, a name...)."""
        flows.flush(1.0)
        try:
            return flows.read(q, before, limit)
        except ValueError:
            raise HTTPException(400, "Bad cursor.") from None

    @app.get("/api/security/auth-log", dependencies=ADMIN)
    def auth_log(result: str | None = Query(None, pattern="^(ok|failed|admin)$"), before: int | None = None,
                 limit: int = Query(100, ge=1, le=500)):
        return sec.auth_log(result, before, limit)

    @app.get("/api/security/accounts", dependencies=ADMIN)
    def security_accounts(con=Depends(db)):
        return sec.accounts(list(con.execute("SELECT * FROM users ORDER BY name COLLATE NOCASE")))

    @app.put("/api/security/accounts/{user_id}/lock", dependencies=ADMIN)
    def lock_account(user_id: int, body: LockIn, request: Request, me=Depends(current_user), con=Depends(db)):
        """Lock (signs them out everywhere; they can't sign in until unlocked) or unlock an account."""
        u = auth.get_user(con, user_id)
        if not u:
            raise HTTPException(404, "No such user.")
        if body.locked and user_id == me["id"]:
            raise HTTPException(400, "You can't lock your own account.")
        if body.locked:
            sec.lock(user_id, me["name"])
            con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            forget_sessions()
        else:
            sec.unlock(user_id)
        sec.log("lock" if body.locked else "unlock", "admin", name=u["name"], user_id=user_id, ip=_client(request),
                reason=f"by {me['name']}", user_agent=request.headers.get("user-agent"))
        return next(a for a in sec.accounts([u]))

    # -- status & settings
    @app.get("/api/status")
    def status(con=Depends(db), me=Depends(current_user)):
        key = get_setting(con, "tmdb_key")
        enc = stream.video_encoder()
        adm = me["is_admin"]  # where things live on the server is for admins
        return {
            "version": VERSION, "data_dir": str(paths.root) if adm else None,
            "ffprobe": (probe.ffprobe_path() if adm else bool(probe.ffprobe_path())) or None,
            "ffmpeg": (stream.ffmpeg_path() if adm else bool(stream.ffmpeg_path())) or None,
            "tmdb_configured": bool(key),
            "video_encoder": {"id": enc, "name": stream.ENCODER_NAMES[enc], "hardware": enc in stream.HARDWARE,
                              "hw_decode": bool(stream.hwaccel_args(enc))} if enc else None,
            "transcodes": {"running": transcodes.running(), "limit": transcode_limit()},
            "read_only_guard": {"installed": True, "protected_roots": len(readonly.protected_roots())},
            "scans": scheduler.status(),
        }

    # -- updates (Settings -> About): the newest release on GitHub, downloaded and checked, installed on Windows
    @app.get("/api/update", dependencies=ADMIN)
    def update_status(refresh: bool = False):
        return {**updates.status(force=refresh), "updates_dir": str(paths.root / "updates")}

    @app.post("/api/update/download", dependencies=ADMIN)
    def update_download():
        try:
            updates.start_download(paths.root / "updates")
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        return update_status()

    @app.post("/api/update/install", dependencies=ADMIN)
    def update_install():
        try:
            updates.install(paths.root / "updates")
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        except RuntimeError as e:
            raise HTTPException(500, str(e)) from None
        return update_status()

    def _tmdb_status(con) -> dict:
        key = get_setting(con, "tmdb_key")
        return {"configured": bool(key), "kind": key_kind(key) if key else None,
                "last4": key[-4:] if key else None, "verified_at": get_setting(con, "tmdb_verified_at")}

    @app.get("/api/settings")
    def get_settings(con=Depends(db)):
        return {"tmdb": _tmdb_status(con), "language": get_setting(con, "language", "en-US"),
                "music_lookup": music_lookup_enabled(con), "music_output": music_output(con),
                "autofill": identify.autofill_enabled(con),
                "max_transcodes": int(get_setting(con, "max_transcodes", "0") or 0),
                "max_transcodes_auto": auto_transcode_limit(), "watch": watch.thresholds(con),
                "server_name": server_name(con)}

    @app.put("/api/settings/server-name", dependencies=ADMIN)
    def put_server_name(body: ServerNameIn, con=Depends(db)):
        """What this server is called where apps list servers (the TV's server list, other browsers' sidebars).
        An empty name goes back to the default."""
        set_setting(con, "server_name", " ".join(body.name.split()) or None)
        return server_name(con)

    @app.put("/api/settings/transcoding", dependencies=ADMIN)
    def put_transcoding(body: TranscodingIn, con=Depends(db)):
        """How many videos may be converted at once (0 = automatic: 4 on a GPU encoder, 2 on the CPU)."""
        set_setting(con, "max_transcodes", str(body.max_transcodes))
        return {"max_transcodes": body.max_transcodes, "limit": transcode_limit()}

    @app.put("/api/settings/watch", dependencies=ADMIN)
    def put_watch_settings(body: WatchSettingsIn, con=Depends(db)):
        """When a title counts as watched (% of its length) and as started (seconds in), for everyone."""
        set_setting(con, "watched_percent", str(body.watched_percent))
        set_setting(con, "resume_after", str(body.resume_after))
        return watch.thresholds(con)

    def _encoders() -> dict:
        auto = None
        if not stream.encoder_forced():  # what "Automatic" means here: the best working one
            auto = next(iter(stream.available_encoders()), None)
        return {
            "choice": stream.preferred(), "active": stream.video_encoder(), "automatic": auto,
            "forced": stream.encoder_forced(),
            "options": [{"id": e, "name": stream.ENCODER_NAMES[e], "hardware": e in stream.HARDWARE}
                        for e in stream.available_encoders()],
        }

    @app.get("/api/settings/encoders", dependencies=ADMIN)
    def get_encoders():
        """Which H.264 encoders work on this machine (each test-encoded once), and which one conversions use."""
        return _encoders()

    @app.put("/api/settings/encoder", dependencies=ADMIN)
    def put_encoder(body: EncoderIn, con=Depends(db)):
        """Convert on the CPU or a GPU (None = automatic: the best one that works). New conversions use it."""
        if body.encoder is not None and body.encoder not in stream.available_encoders():
            raise HTTPException(400, f"{body.encoder} doesn't work on this server.")
        set_setting(con, "video_encoder", body.encoder)
        stream.set_preferred(body.encoder)
        return _encoders()

    @app.put("/api/settings/music-lookup", dependencies=ADMIN)
    def put_music_lookup(body: ToggleIn, con=Depends(db)):
        """Turn online music identification (MusicBrainz, Cover Art Archive, Wikipedia) on or off."""
        set_setting(con, "music_lookup", "1" if body.enabled else "0")
        return {"music_lookup": body.enabled}

    @app.put("/api/settings/autofill", dependencies=ADMIN)
    def put_autofill(body: ToggleIn, con=Depends(db)):
        """Auto fill on or off: files the naming rules can't place are placed by a best guess (or not). Takes effect
        at once; a scan of each TV/Movies library follows so newly placed titles are matched on TMDB."""
        set_setting(con, "autofill", "1" if body.enabled else "0")
        with Tx(con):
            identify.replace_unplaced(con)
        if body.enabled:
            for r in con.execute("SELECT id FROM libraries WHERE type IN ('show', 'movie')").fetchall():
                scheduler.request(r["id"], "autofill")
        return {"autofill": body.enabled}

    @app.put("/api/settings/music-output", dependencies=ADMIN)
    def put_music_output(body: MusicOutputIn, con=Depends(db)):
        """What music browsers can't play (ALAC, AIFF, WMA, APE, DSD...) is converted to: AAC 256k or lossless FLAC."""
        set_setting(con, "music_output", body.output)
        return {"music_output": body.output}

    @app.put("/api/settings/tmdb-key", dependencies=ADMIN)
    def put_key(body: KeyIn, con=Depends(db)):
        """Checked with TMDB before saving. A rejected key is not saved; the full key is never returned."""
        try:
            t = Tmdb(body.key)
        except InvalidKey as e:
            raise HTTPException(400, str(e)) from None
        verified = None
        try:
            t.check()
            verified = str(int(time.time()))
        except InvalidKey as e:
            raise HTTPException(400, str(e)) from None
        except TmdbError as e:
            log.warning("saving TMDB key unverified: %s", e)
        finally:
            t.close()
        set_setting(con, "tmdb_key", body.key.strip())
        set_setting(con, "tmdb_verified_at", verified)
        # titles scanned before the key existed get their posters now, not at the next scheduled scan
        for r in con.execute("SELECT id FROM libraries WHERE type IN ('show', 'movie')").fetchall():
            scheduler.request(r["id"], "tmdb-key", retry_unmatched=True)
        return _tmdb_status(con)

    @app.delete("/api/settings/tmdb-key", dependencies=ADMIN)
    def delete_key(con=Depends(db)):
        set_setting(con, "tmdb_key", None)
        set_setting(con, "tmdb_verified_at", None)
        return _tmdb_status(con)

    @app.post("/api/settings/tmdb-key/test", dependencies=ADMIN)
    def test_key(con=Depends(db)):
        """Check the saved key with TMDB right now."""
        key = get_setting(con, "tmdb_key")
        if not key:
            raise HTTPException(409, "no TMDB key configured")
        try:
            t = Tmdb(key)
            t.check()
            t.close()
        except InvalidKey as e:
            return {"ok": False, "message": str(e)}
        except TmdbError as e:
            return {"ok": False, "message": f"couldn't reach TMDB: {e}"}
        set_setting(con, "tmdb_verified_at", str(int(time.time())))
        return {"ok": True, "message": "Key works."}

    @app.get("/api/fs/browse", dependencies=ADMIN)
    def fs_browse(path: str | None = None):
        """List folders on the server, for picking library folders. Names only; nothing is changed."""
        try:
            return fsbrowse.browse(path)
        except fsbrowse.BrowseError as e:
            raise HTTPException(400, str(e)) from None

    # -- libraries
    @app.get("/api/libraries")
    def list_libraries(con=Depends(db)):
        return [library.describe(con, r) for r in library.listed(con)]

    @app.put("/api/libraries/order", dependencies=ADMIN)
    def order_libraries(body: OrderIn, con=Depends(db)):
        """The order libraries are listed in (sidebar, Home, Settings): ids first to last."""
        library.reorder(con, body.ids)
        return [r["id"] for r in library.listed(con)]

    @app.post("/api/libraries", status_code=201, dependencies=ADMIN)
    def create_library(body: LibraryIn, con=Depends(db)):
        lib_id = library.create(con, paths.root, body.name, body.type, body.paths, body.scan_interval_hours)
        scheduler.request(lib_id, "manual")
        return library.describe(con, library.get(con, lib_id))

    @app.get("/api/libraries/{lib_id}")
    def get_library(lib_id: int, con=Depends(db)):
        return library.describe(con, library.get(con, lib_id))

    @app.patch("/api/libraries/{lib_id}", dependencies=ADMIN)
    def patch_library(lib_id: int, body: LibraryPatch, con=Depends(db)):
        library.update(con, paths.root, lib_id, **body.model_dump())
        if body.add_paths or body.remove_paths:
            scheduler.request(lib_id, "manual")  # index the new folder (or drop the removed one's items) now
        return library.describe(con, library.get(con, lib_id))

    @app.delete("/api/libraries/{lib_id}", status_code=204, dependencies=ADMIN)
    def delete_library(lib_id: int, con=Depends(db)):
        """Removes BAMS's records only. Media files are never touched."""
        library.delete(con, lib_id)

    @app.post("/api/libraries/{lib_id}/scan", status_code=202, dependencies=ADMIN)
    def scan_library(lib_id: int, rematch: bool = False, con=Depends(db)):
        library.get(con, lib_id)
        accepted = scheduler.request(lib_id, "manual", retry_unmatched=rematch)  # False: already queued/running
        return {"accepted": accepted, **scheduler.status()}

    @app.get("/api/scans", dependencies=ADMIN)
    def list_scans(library_id: int | None = None, limit: int = Query(20, le=200), con=Depends(db)):
        q = "SELECT * FROM scans" + (" WHERE library_id=?" if library_id else "") + " ORDER BY id DESC LIMIT ?"
        rows = con.execute(q, ((library_id,) if library_id else ()) + (limit,)).fetchall()
        return {"current": scheduler.status(),
                "history": [{**dict(r), "stats": jload(r["stats"])} for r in rows]}

    # -- items
    _SORTS = {"title": "COALESCE(sort_title, title) COLLATE NOCASE", "year": "year DESC, title COLLATE NOCASE",
              "added": "added_at DESC", "rating": "rating DESC",
              # newest first, a show counting from its newest episode (new episodes bring it back up)
              "recent": """COALESCE((SELECT MAX(e.added_at) FROM items s JOIN items e ON e.parent_id = s.id
                                     WHERE s.parent_id = items.id AND items.kind = 'show'), added_at) DESC""",
              "random": "RANDOM()",
              "artist": "parent_title COLLATE NOCASE, year IS NULL, year, title COLLATE NOCASE"}
    _LIB_KINDS = {"show": ("show",), "movie": ("movie",), "music": MUSIC_KINDS}

    @app.get("/api/libraries/{lib_id}/items")
    def library_items(lib_id: int, sort: str = "title", kind: str | None = None, match_status: str | None = None,
                      q: str | None = None, limit: int = Query(500, le=5000), offset: int = 0, con=Depends(db),
                      me=Depends(current_user)):
        """Top-level items of a library: shows, movies, or (music, `kind=artist|album|track`) artists by default."""
        lib = library.get(con, lib_id)
        allowed = _LIB_KINDS[lib["type"]]
        if kind is not None and kind not in allowed:
            raise HTTPException(400, f"a {lib['type']} library has no {kind!r} items")
        where, args = ["library_id=?", "kind=?"], [lib_id, kind or allowed[0]]
        if match_status:
            where.append("match_status=?")
            args.append(match_status)
        if q:
            where.append("title LIKE ?")
            args.append(f"%{q}%")
        rows = con.execute(f"{ITEM_SELECT} WHERE {' AND '.join(where)} ORDER BY {_SORTS.get(sort, _SORTS['title'])} "
                           "LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
        return watch.annotate(con, me["id"], [item_summary(r) for r in rows])

    @app.get("/api/items")
    def all_items(kind: str = Query("show,movie", pattern="^(show|movie|artist|album|track)(,(show|movie|artist|album|track))*$"),
                  sort: str = "added", q: str | None = None, genre: str | None = None,
                  min_rating: float | None = None, limit: int = Query(100, le=5000), con=Depends(db),
                  me=Depends(current_user)):
        """Shows/movies (default) or artists/albums/tracks across every library (Home rows, search)."""
        kinds = kind.split(",")
        where, args = [f"kind IN ({','.join('?' * len(kinds))})"], list(kinds)
        if q:
            where.append("(title LIKE ? OR parsed_title LIKE ?)")
            args += [f"%{q}%", f"%{q}%"]
        if genre:
            where.append("genres LIKE ?")
            args.append(f'%"{genre}"%')
        if min_rating is not None:
            where.append("rating >= ?")
            args.append(min_rating)
        rows = con.execute(f"{ITEM_SELECT} WHERE {' AND '.join(where)} ORDER BY {_SORTS.get(sort, _SORTS['added'])} LIMIT ?",
                           (*args, limit)).fetchall()
        return watch.annotate(con, me["id"], [item_summary(r) for r in rows])

    @app.get("/api/genres")
    def all_genres(con=Depends(db)):
        """Every genre of the shows/movies in any library, most titles first (Home's genre rows)."""
        n: dict[str, int] = {}
        for r in con.execute("SELECT genres FROM items WHERE kind IN ('show','movie') AND genres IS NOT NULL"):
            for g in jload(r["genres"]) or []:
                n[g] = n.get(g, 0) + 1
        return [{"name": g, "count": c} for g, c in sorted(n.items(), key=lambda x: (-x[1], x[0].lower()))]

    @app.get("/api/items/{item_id}")
    def get_item(item_id: int, con=Depends(db), me=Depends(current_user)):
        r = con.execute(f"{ITEM_SELECT} WHERE id=?", (item_id,)).fetchone()
        if not r:
            raise HTTPException(404, "no such item")
        d = item_detail(r)
        # the show / season this belongs to, top-down, so an episode page can show "Show · Season 2"
        d["ancestors"], p = [], r["parent_id"]
        while p:
            a = con.execute(f"{ITEM_SELECT} WHERE id=?", (p,)).fetchone()
            d["ancestors"].insert(0, item_summary(a))
            p = a["parent_id"]
        order = {"show": "season_number", "artist": "year IS NULL, year, title COLLATE NOCASE",
                 "album": "COALESCE(disc_number, 1), track_number IS NULL, track_number, title COLLATE NOCASE",
                 }.get(r["kind"], "episode_number IS NULL, episode_number, title COLLATE NOCASE")  # unnumbered last
        d["children"] = [item_summary(c) for c in con.execute(
            f"{ITEM_SELECT} WHERE parent_id=? ORDER BY {order}", (item_id,))]
        playable = r["kind"] in watch.PLAYABLE
        mo = music_output(con) if r["kind"] in MUSIC_KINDS else "aac"
        files_sql = """SELECT f.*, lr.path AS root FROM files f JOIN file_items fi ON fi.file_id=f.id
                       JOIN library_roots lr ON lr.id=f.root_id WHERE fi.item_id=? ORDER BY f.rel_path"""
        rows = con.execute(files_sql, (item_id,)).fetchall()
        if playable and _probe_now(con, rows):
            rows = con.execute(files_sql, (item_id,)).fetchall()
        d["files"] = [file_info(f, with_subtitles=playable, music_out=mo) for f in rows]
        watch.annotate(con, me["id"], [d, *d["children"], *d["ancestors"]])
        if r["kind"] == "episode":
            d["next_id"] = watch.next_episode(con, item_id)
        return d

    # -- watch state (per user)
    def _playable(con, item_id: int) -> None:
        r = con.execute("SELECT kind FROM items WHERE id=?", (item_id,)).fetchone()
        if not r or r["kind"] not in watch.PLAYABLE:
            raise HTTPException(404, "no such movie/episode")

    @app.put("/api/items/{item_id}/progress")
    def put_progress(item_id: int, body: ProgressIn, con=Depends(db), me=Depends(current_user)):
        """The player's position in a movie/episode (sent every few seconds while playing). Past 90% it counts
        as watched."""
        _playable(con, item_id)
        return watch.record_progress(con, me["id"], item_id, body.position, body.duration)

    @app.put("/api/items/{item_id}/watched")
    def put_watched(item_id: int, body: WatchedIn, con=Depends(db), me=Depends(current_user)):
        """Mark a movie/episode, or every episode of a season or show, watched or not."""
        n = watch.set_watched(con, me["id"], item_id, body.watched)
        if not n:
            raise HTTPException(404, "nothing to mark: not a movie, episode, season or show")
        return {"items": n, "watched": body.watched}

    @app.get("/api/continue")
    def continue_watching(limit: int = Query(20, le=100), con=Depends(db), me=Depends(current_user)):
        """Continue Watching: titles stopped part-way ("resume"), and the next episode of shows whose last
        watched episode was finished ("next"). Episodes carry their show's title and art."""
        picks = watch.continue_watching(con, me["id"], limit)
        out = []
        for item_id, why, at in picks:
            r = con.execute(f"{ITEM_SELECT} WHERE id=?", (item_id,)).fetchone()
            if not r:
                continue
            d = item_summary(r)
            d["reason"] = why
            d["last_watched_at"] = at  # when, for apps that merge several servers' rows (web/src/everywhere.ts)
            if r["kind"] == "episode":
                show = con.execute("""SELECT sh.id, sh.title, sh.poster, sh.backdrop FROM items s
                                      JOIN items sh ON sh.id=s.parent_id WHERE s.id=?""", (r["parent_id"],)).fetchone()
                d["show"] = {"id": show["id"], "title": show["title"], "poster": _img(show["poster"]),
                             "backdrop": _img(show["backdrop"])}
                d["season_id"] = r["parent_id"]  # the card's episode line opens that season
            out.append(d)
        return watch.annotate(con, me["id"], out)

    @app.get("/api/items/{item_id}/tracks")
    def item_tracks(item_id: int, con=Depends(db)):
        """Every playable track of an artist, album or track, in play order: what a music queue needs."""
        r = con.execute("SELECT kind FROM items WHERE id=?", (item_id,)).fetchone()
        if not r or r["kind"] not in MUSIC_KINDS:
            raise HTTPException(404, "no such artist/album/track")
        where = {"track": "t.id=?", "album": "al.id=?", "artist": "ar.id=?"}[r["kind"]]
        ids = [x[0] for x in con.execute(f"""
            SELECT t.id FROM items t JOIN items al ON al.id=t.parent_id JOIN items ar ON ar.id=al.parent_id
            WHERE t.kind='track' AND {where}
            ORDER BY al.year IS NULL, al.year, al.title COLLATE NOCASE, COALESCE(t.disc_number, 1),
                     t.track_number IS NULL, t.track_number, t.title COLLATE NOCASE""", (item_id,))]
        return _queue(con, ids)

    def _queue(con, ids: list[int]) -> list[dict]:
        """Tracks as a play queue, in the order of `ids` (a playlist may repeat one). A track with several files
        (merged copies of one album) plays the best: available, then playable as-is, then the biggest (lossless).
        CUE tracks carry `start`/`end`: the stretch of their file to play (seconds; end None = to its end)."""
        out_fmt = music_output(con)
        best: dict[int, tuple] = {}
        uniq = list(dict.fromkeys(ids))
        for i in range(0, len(uniq), 500):
            chunk = uniq[i:i + 500]
            for t in con.execute(f"""
                    SELECT t.id, t.title, t.artist, t.track_number, t.disc_number, t.duration,
                           al.id album_id, al.title album, al.poster, ar.id artist_id, ar.title album_artist,
                           f.id file_id, f.rel_path, f.probe, f.size, f.available, fi.cue_start, fi.cue_end
                    FROM items t JOIN items al ON al.id=t.parent_id JOIN items ar ON ar.id=al.parent_id
                    JOIN file_items fi ON fi.item_id=t.id JOIN files f ON f.id=fi.file_id
                    WHERE t.kind='track' AND t.id IN ({','.join('?' * len(chunk))})""", chunk):
                pb = stream.plan_audio(jload(t["probe"]), t["rel_path"], out_fmt)
                rank = (bool(t["available"]), pb["mode"] == "file", t["size"])
                if t["id"] not in best or rank > best[t["id"]][0]:
                    best[t["id"]] = (rank, t, pb)
        out = []
        for i in ids:
            if i not in best:
                continue
            _, t, pb = best[i]
            pb = {**pb, "url": f"/api/files/{t['file_id']}/{'audio' if pb['mode'] == 'transcode' else 'stream'}"}
            span = t["cue_end"] - t["cue_start"] if t["cue_end"] is not None and t["cue_start"] is not None else None
            out.append({
                "id": t["id"], "title": t["title"], "artist": t["artist"] or t["album_artist"],
                "album": t["album"], "album_id": t["album_id"], "artist_id": t["artist_id"],
                "album_artist": t["album_artist"], "poster": _img(t["poster"]),
                "track_number": t["track_number"], "disc_number": t["disc_number"],
                "duration": t["duration"] or span or pb["duration"], "file_id": t["file_id"],
                "start": t["cue_start"], "end": t["cue_end"],
                "available": bool(t["available"]), "playback": pb,
            })
        return out

    # -- playlists (imported from .m3u/.m3u8/.pls files in music libraries; see playlists.py)
    def _playlist_summary(con, r: sqlite3.Row) -> dict:
        covers = [_img(c[0]) for c in con.execute(
            """SELECT al.poster FROM playlist_items pi JOIN items t ON t.id=pi.item_id JOIN items al ON al.id=t.parent_id
               WHERE pi.playlist_id=? AND al.poster IS NOT NULL GROUP BY al.id ORDER BY MIN(pi.position) LIMIT 4""",
            (r["id"],))]
        n, length = con.execute("""SELECT COUNT(*), SUM(t.duration) FROM playlist_items pi JOIN items t ON t.id=pi.item_id
                                   WHERE pi.playlist_id=?""", (r["id"],)).fetchone()
        return {"id": r["id"], "library_id": r["library_id"], "name": r["name"], "path": r["rel_path"],
                "track_count": n, "duration": length, "missing": r["missing"], "covers": covers,
                "updated_at": r["updated_at"]}

    @app.get("/api/libraries/{lib_id}/playlists")
    def library_playlists(lib_id: int, con=Depends(db)):
        """A music library's playlists (imported from playlist files in its folders), by name."""
        library.get(con, lib_id)
        return [_playlist_summary(con, r) for r in con.execute(
            "SELECT * FROM playlists WHERE library_id=? ORDER BY name COLLATE NOCASE", (lib_id,))]

    @app.get("/api/playlists/{playlist_id}")
    def get_playlist(playlist_id: int, con=Depends(db)):
        """One playlist with its tracks, in its own order, ready to queue."""
        r = con.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,)).fetchone()
        if not r:
            raise HTTPException(404, "no such playlist")
        ids = [x[0] for x in con.execute(
            "SELECT item_id FROM playlist_items WHERE playlist_id=? ORDER BY position", (playlist_id,))]
        return {**_playlist_summary(con, r), "library_name": library.get(con, r["library_id"])["name"],
                "tracks": _queue(con, ids)}

    def _unrecognized(con, lib_id: int | None) -> list[dict]:
        """Files the parser couldn't place (each with a hint about why), files placed by a best guess (auto fill,
        `guessed`: to review), and files identified by hand."""
        rows = con.execute(f"""SELECT f.*, lr.path AS root, l.name AS library_name, l.type AS library_type
                               FROM files f JOIN library_roots lr ON lr.id=f.root_id JOIN libraries l ON l.id=f.library_id
                               WHERE (f.id NOT IN (SELECT file_id FROM file_items) OR f.manual IS NOT NULL
                                      OR json_extract(f.parse, '$.guessed'))
                               {"AND f.library_id=?" if lib_id is not None else ""}
                               ORDER BY l.name COLLATE NOCASE, f.rel_path""", (() if lib_id is None else (lib_id,)))
        out = []
        for r in rows:
            manual = jload(r["manual"])
            parsed = jload(r["parse"]) or {}
            guessed = not manual and bool(parsed.get("guessed"))
            out.append({**file_info(r), "library_id": r["library_id"], "library_name": r["library_name"],
                        "library_type": r["library_type"], "manual": manual, "guessed": guessed,
                        "hint": None if manual or guessed else unrecognized_hint(r["rel_path"], r["library_type"]),
                        "guess": {k: parsed.get(k) for k in ("title", "year", "season", "episodes", "episode_title")}})
        return out

    @app.get("/api/libraries/{lib_id}/unrecognized", dependencies=ADMIN)
    def unrecognized(lib_id: int, con=Depends(db)):
        library.get(con, lib_id)
        return _unrecognized(con, lib_id)

    @app.get("/api/unrecognized", dependencies=ADMIN)
    def all_unrecognized(con=Depends(db)):
        """Every library's unrecognised (and hand-identified) files: Settings → Unrecognized files."""
        return _unrecognized(con, None)

    @app.get("/api/libraries/{lib_id}/names", dependencies=ADMIN)
    def library_names(lib_id: int, con=Depends(db)):
        """Shows (with seasons and episodes) or movies already in a library, for the identify form's suggestions."""
        lib = library.get(con, lib_id)
        return identify.names(con, lib_id, lib["type"])

    @app.post("/api/identify/lookup", dependencies=ADMIN)
    def identify_lookup(body: LinkIn, con=Depends(db)):
        """A pasted TMDB / IMDb link -> the identify form's fields."""
        lib = library.get(con, body.library_id)
        t = tmdb_client(con)
        if not t:
            raise HTTPException(409, "Links need a TMDB key (Settings → Metadata). You can still fill the fields in by hand.")
        try:
            return identify.lookup(t, body.link, lib["type"])
        except identify.LinkError as e:
            raise HTTPException(400, str(e)) from None
        except TmdbError as e:
            raise HTTPException(502, f"TMDB: {e}") from None
        finally:
            t.close()

    @app.put("/api/files/{file_id}/identify", dependencies=ADMIN)
    def identify_file(file_id: int, body: IdentifyIn, con=Depends(db)):
        """Say what a file is. Kept across rescans. With a TMDB id the title is matched to it right away."""
        f = con.execute("SELECT f.id, l.type FROM files f JOIN libraries l ON l.id=f.library_id WHERE f.id=?",
                        (file_id,)).fetchone()
        if not f:
            raise HTTPException(404, "no such file")
        if f["type"] == "music":
            raise HTTPException(400, "Music is identified from its tags.")
        if f["type"] == "show" and body.season is None:
            raise HTTPException(422, "Which season? (0 = Specials)")
        manual = body.model_dump(exclude_none=True)
        manual["title"] = manual["title"].strip()
        for k in (("season", "episodes", "episode_title") if f["type"] == "movie" else ("edition",)):
            manual.pop(k, None)
        with Tx(con):
            [target, *_] = identify.store(con, file_id, manual)
        title_id = identify.title_of(con, target)
        note = None
        it = con.execute("SELECT match_status FROM items WHERE id=?", (title_id,)).fetchone()
        t = tmdb_client(con)
        if t and (body.tmdb_id or it["match_status"] == "pending"):
            try:
                matcher.match_title(con, t, paths.images, title_id, tmdb_id=body.tmdb_id, manual=bool(body.tmdb_id))
            except TmdbError as e:
                note = f"Saved, but TMDB couldn't be reached ({e}). The next scan will try again."
            finally:
                t.close()
        elif t:
            t.close()
        # a merge on matching may have folded the title into another one
        target = con.execute("SELECT item_id FROM file_items WHERE file_id=? ORDER BY item_id LIMIT 1",
                             (file_id,)).fetchone()["item_id"]
        return {"item_id": target, "title_id": identify.title_of(con, target), "note": note}

    @app.get("/api/files/{file_id}/guess", dependencies=ADMIN)
    def guess_file(file_id: int, con=Depends(db)):
        """The identify form's "Best guess" button: Auto fill's guess for one file, forced (also where auto fill holds
        back, e.g. a movie in its own folder in a TV library). Only fills the form; nothing is saved."""
        f = con.execute("SELECT f.rel_path, l.type FROM files f JOIN libraries l ON l.id=f.library_id WHERE f.id=?",
                        (file_id,)).fetchone()
        if not f:
            raise HTTPException(404, "no such file")
        if f["type"] == "music":
            raise HTTPException(400, "Music is identified from its tags.")
        g = guess(f["rel_path"], f["type"], force=True)
        if not g:
            raise HTTPException(422, "Nothing in this file's name or folders to guess from.")
        out = {"title": g.title, "year": g.year}
        if f["type"] == "show":
            out |= {"season": g.season, "episodes": g.episodes, "episode_title": g.episode_title}
        else:
            out["edition"] = g.edition
        return out

    @app.put("/api/files/{file_id}/skip", dependencies=ADMIN)
    def skip_file(file_id: int, con=Depends(db)):
        """Don't place this file (an auto fill guess that's wrong, a sample, junk). Kept like a hand identification;
        DELETE /identify undoes it."""
        f = con.execute("SELECT l.type FROM files f JOIN libraries l ON l.id=f.library_id WHERE f.id=?",
                        (file_id,)).fetchone()
        if not f:
            raise HTTPException(404, "no such file")
        if f["type"] == "music":
            raise HTTPException(400, "Music is identified from its tags.")
        with Tx(con):
            identify.store(con, file_id, {"skip": True})
        return {"recognized": False}

    @app.delete("/api/files/{file_id}/identify", dependencies=ADMIN)
    def unidentify_file(file_id: int, con=Depends(db)):
        """Forget a hand identification: the file is placed by its name again (maybe unrecognised)."""
        if not con.execute("SELECT 1 FROM files WHERE id=?", (file_id,)).fetchone():
            raise HTTPException(404, "no such file")
        with Tx(con):
            targets = identify.store(con, file_id, None)
        return {"recognized": bool(targets)}

    @app.get("/api/tmdb/search", dependencies=ADMIN)
    def tmdb_search(q: str, kind: str = Query(pattern="^(show|movie)$"), year: int | None = None, con=Depends(db)):
        t = tmdb_client(con)
        if not t:
            raise HTTPException(409, "TMDB key not configured")
        try:
            res = t.search_tv(q, year) if kind == "show" else t.search_movie(q, year)
        except TmdbError as e:
            raise HTTPException(502, str(e)) from None
        finally:
            t.close()
        return [{"tmdb_id": x["id"], "title": x.get("name") or x.get("title"),
                 "year": matcher._year(x.get("first_air_date") or x.get("release_date")),
                 "overview": x.get("overview"), "poster_path": x.get("poster_path")} for x in res[:20]]

    @app.post("/api/items/{item_id}/match", dependencies=ADMIN)
    def fix_match(item_id: int, body: MatchIn, con=Depends(db), me=Depends(current_user)):
        """Fix match: pin a show/movie to a specific TMDB id."""
        r = con.execute("SELECT kind FROM items WHERE id=?", (item_id,)).fetchone()
        if not r or r["kind"] not in ("show", "movie"):
            raise HTTPException(404, "no such show/movie")
        t = tmdb_client(con)
        if not t:
            raise HTTPException(409, "TMDB key not configured")
        try:
            matcher.match_title(con, t, paths.images, item_id, tmdb_id=body.tmdb_id, manual=True)
        except TmdbError as e:
            raise HTTPException(502, str(e)) from None
        finally:
            t.close()
        keep = con.execute("SELECT id FROM items WHERE tmdb_id=? AND kind=? ORDER BY id LIMIT 1",
                           (body.tmdb_id, r["kind"])).fetchone()
        return get_item(keep["id"], con, me)

    @app.get("/api/musicbrainz/search", dependencies=ADMIN)
    def musicbrainz_search(kind: str = Query(pattern="^(album|artist)$"), q: str = Query(min_length=1),
                           artist: str | None = None):
        """Fix match for music: candidate releases (albums) or artists on MusicBrainz."""
        try:
            with MusicBrainz() as mb:
                if kind == "artist":
                    return [{"mbid": a["id"], "title": a.get("name"), "sort_name": a.get("sort-name"),
                             "type": a.get("type"), "country": a.get("country"),
                             "disambiguation": a.get("disambiguation") or None,
                             "years": "–".join(filter(None, [(a.get("life-span") or {}).get("begin", "")[:4],
                                                            (a.get("life-span") or {}).get("end", "")[:4]])) or None}
                            for a in mb.search_artists(q, limit=15)]
                rels = mb.search_releases(q, artist or None, limit=25)
        except MusicLookupError as e:
            raise HTTPException(502, str(e)) from None
        return [{"mbid": r["id"], "title": r.get("title"), "artist": music_match.credit_name(r.get("artist-credit")),
                 "date": r.get("date"), "country": r.get("country"), "track_count": r.get("track-count"),
                 "format": ", ".join(dict.fromkeys(m.get("format") or "?" for m in r.get("media") or [])) or None,
                 "type": (r.get("release-group") or {}).get("primary-type"), "status": r.get("status"),
                 "disambiguation": r.get("disambiguation") or None} for r in rels]

    @app.post("/api/items/{item_id}/music-match", dependencies=ADMIN)
    def music_fix_match(item_id: int, body: MusicMatchIn, con=Depends(db), me=Depends(current_user)):
        """Fix match for music: pin an album to a MusicBrainz release, or an artist to a MusicBrainz artist."""
        r = con.execute("SELECT kind, library_id FROM items WHERE id=?", (item_id,)).fetchone()
        if not r or r["kind"] not in ("album", "artist"):
            raise HTTPException(404, "no such album/artist")
        fn = music_match.match_album if r["kind"] == "album" else music_match.match_artist
        try:
            with MusicBrainz() as mb:
                fn(con, mb, paths.images, item_id, mbid=body.mbid.lower(), manual=True, lang=language(con))
        except MusicLookupError as e:
            raise HTTPException(502, str(e)) from None
        if r["kind"] == "album" and not con.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone():
            # merged into the library's other album pinned to the same release: that one is the album now
            item_id = con.execute("SELECT id FROM items WHERE library_id=? AND kind='album' AND mbid=? ORDER BY id",
                                  (r["library_id"], body.mbid.lower())).fetchone()["id"]
        return get_item(item_id, con, me)

    # -- files & images
    def _file_path(con, file_id: int) -> tuple[Path, str]:
        r = con.execute("""SELECT f.rel_path, f.available, lr.path root FROM files f
                           JOIN library_roots lr ON lr.id=f.root_id WHERE f.id=?""", (file_id,)).fetchone()
        if not r:
            raise HTTPException(404, "no such file")
        root = Path(r["root"])
        p = (root / r["rel_path"]).resolve()
        if os.path.commonpath([str(p), str(root.resolve())]) != str(root.resolve()):
            raise HTTPException(400, "file path escapes its library folder")
        if not r["available"] or not p.is_file():
            raise HTTPException(410, "file is not available (moved, deleted, or drive offline)")
        return p, Path(r["rel_path"]).name

    @app.get("/api/files/{file_id}/stream")
    def stream_file(file_id: int, con=Depends(db)):
        """Original file with HTTP Range support (seeking), for playing. Opened read-only. No file name is sent:
        BAMS offers no downloads (owner's decision), so nothing suggests saving it."""
        p, name = _file_path(con, file_id)
        return FileResponse(p, media_type=mimetypes.guess_type(name)[0] or "application/octet-stream")

    @app.get("/api/files/{file_id}/seek")
    def seek_point(file_id: int, t: float = Query(0, ge=0), con=Depends(db)):
        """Where a remux asked to start at `t` will really start (the keyframe at/before t).
        Transcodes start exactly at `t`, so they don't need this."""
        p, _ = _file_path(con, file_id)
        return {"t": stream.remux_start(p, t)}

    @app.get("/api/files/{file_id}/subtitles/{track}.vtt")
    def subtitle(file_id: int, track: str, shift: float = Query(0, ge=0), con=Depends(db)):
        """A text subtitle track (embedded "e{n}" or sidecar file "x{n}") as WebVTT. `shift`: the live stream's
        start, for players of the remux/plain transcode streams, whose clock starts at 0 there."""
        p, _ = _file_path(con, file_id)
        row = con.execute("SELECT probe, mtime_ns FROM files WHERE id=?", (file_id,)).fetchone()
        tr = next((x for x in subtitles.tracks(jload(row["probe"]), p, file_id) if x["id"] == track), None)
        if not tr:
            raise HTTPException(404, "no such subtitle track")
        if tr["image"]:
            raise HTTPException(400, "This is a picture-based subtitle track; it's burned into a converted video "
                                     "instead.")
        try:
            vtt = subtitles.webvtt(p, tr, paths.cache / "subtitles", row["mtime_ns"])
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            log.warning("subtitle %s of file %s: %s", track, file_id, e)
            raise HTTPException(500, f"Couldn't convert these subtitles: {e}") from None
        return Response(subtitles.shift(vtt, shift), media_type="text/vtt; charset=utf-8",
                        headers={"cache-control": "private, max-age=300"})

    def _probe_of(file_id: int) -> tuple[Path, dict]:
        con = connect(paths.db)
        try:
            p, _ = _file_path(con, file_id)
            row = con.execute("SELECT probe, parse FROM files WHERE id=?", (file_id,)).fetchone()
        finally:
            con.close()
        return p, {"probe": jload(row["probe"]) or {}, "parse": jload(row["parse"])}

    def _channels(pr: dict, audio: int, want: int) -> int:
        tracks = pr.get("audio") or []
        return stream.audio_channels(tracks[audio] if audio < len(tracks) else None, want)

    def _copy_audio(pr: dict, audio: int, passthrough: bool) -> bool:
        """Whether a remux copies the audio track as-is: the player asked (its device decodes Dolby) and it's
        AC3/EAC3. Anything else is converted to AAC as usual."""
        tracks = pr.get("audio") or []
        return passthrough and audio < len(tracks) and tracks[audio].get("codec") in stream.PASSTHROUGH_AUDIO

    def _burn(pr: dict, p: Path, file_id: int, burn: int | str | None):
        """The picture subtitles to paint on, for `stream`: an embedded stream number, or a track id."""
        if burn is None or burn == "":
            return None
        if isinstance(burn, int) or burn.isdigit():
            if not 0 <= int(burn) <= 99:
                raise HTTPException(422, "burn: no such subtitle stream")
            return int(burn)
        tr = next((x for x in subtitles.tracks(pr, p, file_id) if x["id"] == burn), None)
        if not tr or not tr["image"]:
            raise HTTPException(422, "burn: no such picture subtitle track")
        return subtitles.burn_source(tr, p)

    def _video(p: Path, pr: dict, encoder: str | None) -> dict | None:
        """The probe's video summary, plus pixel shape and scan type when an all-GPU Quick Sync / AMF / VAAPI run
        needs them and the file was probed before BAMS recorded them (a quick ffprobe of the stream header)."""
        v = pr.get("video")
        if v and "sar" not in v and encoder in ("h264_qsv", "h264_amf", "h264_vaapi"):
            if g := probe.video_geometry(p):
                v = {**v, **g}
        return v

    @app.get("/api/files/{file_id}/remux")
    async def remux_file(file_id: int, t: float = Query(0, ge=0), audio: int = Query(0, ge=0, le=31),
                         ch: int = Query(2, ge=1, le=8), passthrough: bool = Query(False)):
        """Video copied as-is, audio converted to AAC (`ch=6`: 5.1 when the track has it), as fragmented MP4
        starting at `t` seconds. For files whose audio browsers can't decode (AC3/EAC3/DTS/TrueHD), or another
        audio track than the first. `passthrough`: the player's device decodes Dolby, so AC3/EAC3 is copied too.
        Seek = request again with ?t=. (The player prefers HLS: POST /hls copy.)"""
        p, info = await anyio.to_thread.run_sync(_probe_of, file_id)
        pr = info["probe"]
        vcodec = stream.plan(pr, info["parse"])["video_codec"]
        return _pipe(stream.remux_cmd, (p, t, vcodec, audio, _channels(pr, audio, ch),
                                        _copy_audio(pr, audio, passthrough)), "video/mp4")

    @app.get("/api/files/{file_id}/transcode")
    async def transcode_file(file_id: int, t: float = Query(0, ge=0), audio: int = Query(0, ge=0, le=31),
                             h: int | None = Query(None, ge=144, le=4320), ch: int = Query(2, ge=1, le=8),
                             sub: str | None = Query(None, max_length=20)):
        """Video converted to H.264 (GPU when available) and audio to AAC, as fragmented MP4 starting
        exactly at `t` seconds, at most `h` pixels high. For codecs the browser can't decode (Xvid, MPEG-2,
        VC-1, HEVC in Firefox...) when it can't use HLS (`POST /hls`). Seek = request again with ?t=.
        `sub`: picture subtitles to burn in (a track id, or an embedded subtitle stream number)."""
        p, info = await anyio.to_thread.run_sync(_probe_of, file_id)
        pr = info["probe"]
        burn = await anyio.to_thread.run_sync(_burn, pr, p, file_id, sub)
        try:
            transcodes.check()
        except hls.Busy as e:
            raise HTTPException(503, str(e)) from None
        return _pipe(stream.transcode_cmd, (p, t, pr.get("video"), audio, None, h, _channels(pr, audio, ch), burn),
                     "video/mp4", on_start=transcodes.add_pipe)

    @app.post("/api/files/{file_id}/hls")
    def hls_start(file_id: int, body: HlsIn, con=Depends(db)):
        """Start an HLS session for a video. Converted (H.264 + AAC, 4-second segments made on demand; `auto`
        lists several sizes for the player to choose between, `height` caps the size, `burn` paints an image
        subtitle track on) or, with `remux`, the video copied and only the audio converted (segments at the
        file's own keyframes). The player loads `playlist` and seeks by itself. Close it with
        DELETE /api/hls/{id} (or it closes when idle)."""
        p, _ = _file_path(con, file_id)
        row = con.execute("SELECT probe, parse, size, mtime_ns FROM files WHERE id=?", (file_id,)).fetchone()
        pr = jload(row["probe"]) or {}
        if not pr.get("duration"):
            raise HTTPException(409, "This file hasn't been probed yet, so its length isn't known and it can't be "
                                     "split into segments.")
        if not stream.ffmpeg_path():
            raise HTTPException(503, "The server can't convert video: FFmpeg wasn't found.")
        ch = _channels(pr, body.audio, body.channels)
        copy_audio = False
        if body.remux:
            kf = keyframes.get(file_id, p, row["size"], row["mtime_ns"])
            if not kf:
                raise HTTPException(409, "Couldn't list this file's keyframes, so it can't be split without "
                                         "converting the video.")
            copy_audio = _copy_audio(pr, body.audio, body.passthrough)
            s = transcodes.create(file_id, p, pr.get("video"), pr["duration"], body.audio, channels=ch,
                                  keyframes=kf, start=body.start, bitrate=pr.get("bitrate"), copy_audio=copy_audio,
                                  ts=body.ts,
                                  video_codec=stream.plan(pr, jload(row["parse"]))["video_codec"])
        else:
            enc = stream.video_encoder()
            if not enc:
                raise HTTPException(503, "The server can't convert video: FFmpeg has no working H.264 encoder.")
            burn = _burn(pr, p, file_id, body.burn)
            video = _video(p, pr, enc)
            heights = hls.ladder(video, enc) if body.auto and not body.height else [body.height]
            try:
                s = transcodes.create(file_id, p, video, pr["duration"], body.audio, heights, channels=ch,
                                      burn=burn, start=body.start, encoder=enc)
            except hls.Busy as e:
                raise HTTPException(503, str(e)) from None
        return {"id": s.id, "playlist": f"/api/hls/{s.id}/index.m3u8", "duration": s.duration,
                "variants": [{"height": v.resolution[1] if v.resolution else v.height, "bandwidth": v.bandwidth}
                             for v in s.variants], "copy": body.remux, "channels": ch, "passthrough": copy_audio}

    def _session(sid: str) -> hls.Session:
        try:
            return transcodes.get(sid)
        except KeyError:
            raise HTTPException(404, "no such conversion (it was closed, or the server restarted)") from None

    _M3U8 = {"media_type": "application/vnd.apple.mpegurl", "headers": {"cache-control": "no-store"}}

    @app.get("/api/hls/{sid}/index.m3u8")
    def hls_master(sid: str):
        return Response(_session(sid).playlist(), **_M3U8)

    @app.get("/api/hls/{sid}/{v}/index.m3u8")
    def hls_playlist(sid: str, v: int):
        s = _session(sid)
        try:
            return Response(transcodes.variant(s, v).playlist(), **_M3U8)
        except KeyError:
            raise HTTPException(404, "no such variant") from None

    def _segment_errors(fn):
        try:
            return fn()
        except KeyError:
            raise HTTPException(404, "no such segment") from None
        except hls.SegmentGone:
            raise HTTPException(409, "the player moved on") from None
        except hls.Busy as e:
            raise HTTPException(503, str(e)) from None
        except TimeoutError:
            raise HTTPException(504, "the segment took too long to make") from None
        except (RuntimeError, OSError) as e:
            raise HTTPException(500, str(e)) from None

    @app.get("/api/hls/{sid}/{v}/init.mp4")
    def hls_init(sid: str, v: int):
        s = _session(sid)
        f = _segment_errors(lambda: transcodes.init(s, v))
        return FileResponse(f, media_type="video/mp4", headers={"cache-control": "no-store"})

    @app.get("/api/hls/{sid}/{v}/{seg}")
    def hls_segment(sid: str, v: int, seg: str):
        """One segment (`{k}.ts` converted, `{k}.m4s` copied), made first if needed (waits up to a minute).
        Sync: runs in the thread pool."""
        k, _, ext = seg.partition(".")
        if not k.isdigit() or ext not in ("ts", "m4s"):
            raise HTTPException(404, "no such segment")
        s = _session(sid)
        f = _segment_errors(lambda: transcodes.segment(s, v, int(k)))
        return FileResponse(f, media_type="video/mp2t" if ext == "ts" else "video/iso.segment",
                            headers={"cache-control": "no-store"})

    @app.delete("/api/hls/{sid}", status_code=204)
    def hls_stop(sid: str):
        transcodes.close(sid)

    @app.get("/api/files/{file_id}/audio")
    async def audio_file(file_id: int, t: float = Query(0, ge=0)):
        """Music in a format browsers can't play (ALAC, AIFF, WMA, APE, DSD...), converted to AAC (fragmented
        MP4) or, when Settings say so, lossless FLAC, starting at `t` seconds. Seek = request again with ?t=."""
        con = connect(paths.db)
        try:
            p, _ = _file_path(con, file_id)
            row = con.execute("SELECT probe FROM files WHERE id=?", (file_id,)).fetchone()
            out = music_output(con)
        finally:
            con.close()
        audio = (jload(row["probe"]) or {}).get("audio") or [{}]
        return _pipe(stream.audio_cmd, (p, t, audio[0], out), "audio/flac" if out == "flac" else "audio/mp4")

    def _pipe(make_cmd, args: tuple, media_type: str, on_start=None) -> StreamingResponse:
        """Run FFmpeg and stream its stdout; it's killed as soon as the client goes away."""
        try:
            proc = stream.spawn(make_cmd(*args))
        except (RuntimeError, OSError) as e:
            raise HTTPException(503, f"can't start FFmpeg: {e}") from None
        if on_start:
            on_start(proc)

        async def body():
            try:
                while True:
                    chunk = await anyio.to_thread.run_sync(proc.stdout.read, 256 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:  # client went away (seek, stop, closed tab) or stream ended
                if proc.poll() is None:
                    proc.kill()
                proc.wait()

        return StreamingResponse(body(), media_type=media_type, headers={"cache-control": "no-store"})

    @app.get("/api/images/{rel:path}")
    def image(rel: str):
        base = paths.images.resolve()
        p = (base / rel).resolve()
        if os.path.commonpath([str(p), str(base)]) != str(base) or not p.is_file():
            raise HTTPException(404, "no such image")
        return FileResponse(p, headers={"cache-control": "public, max-age=604800"})

    # -- web UI (the built React app), if present
    if web_dir and (web_dir / "index.html").is_file():
        app.mount("/", SpaFiles(directory=web_dir, html=True), name="web")

    return app
