"""HTTP API (FastAPI). Interactive docs at /docs while the server runs."""

from __future__ import annotations

import logging
import mimetypes
import os
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
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, fsbrowse, hls, identify, library, matcher, music_match, probe, readonly, stream, subtitles, watch
from .config import VERSION, Paths
from .db import Tx, connect, get_setting, jload, migrate, set_setting
from .jobs import Scheduler, language, music_lookup_enabled, tmdb_client
from .musicbrainz import MusicBrainz, MusicLookupError
from .parse import parse_episode, parse_movie
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


def file_info(r: sqlite3.Row, with_subtitles: bool = False) -> dict:
    """A file as the API returns it. `with_subtitles` also lists sidecar subtitle files, which means listing
    the file's folder (fine for one title's files, not for long lists)."""
    pr, pa = jload(r["probe"]), jload(r["parse"])
    if (pa or {}).get("kind") == "track":  # music
        pb = stream.plan_audio(pr, r["rel_path"])
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
        "stream_url": f"/api/files/{r['id']}/stream", "download_url": f"/api/files/{r['id']}/download",
    }
    if (pa or {}).get("kind") != "track":
        d["audio_tracks"] = audio_tracks(pr)
        if with_subtitles:
            video = Path(r["root"]) / r["rel_path"] if r["available"] else None
            d["subtitles"] = subtitles.tracks(pr, video, r["id"])
    return d


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


class TranscodingIn(BaseModel):
    max_transcodes: int = Field(ge=0, le=32)  # 0 = automatic


class OrderIn(BaseModel):
    ids: list[int] = Field(max_length=1000)


class EncoderIn(BaseModel):
    encoder: str | None = None  # an id from stream.ENCODERS that works here; None = automatic


class WatchSettingsIn(BaseModel):
    watched_percent: int = Field(ge=50, le=100)   # a title counts as watched past this share of its length
    resume_after: int = Field(ge=0, le=600)       # seconds before it counts as started (saved, Continue Watching)


class PrefsIn(BaseModel):
    home_hero: bool | None = None


class HlsIn(BaseModel):
    audio: int = Field(0, ge=0, le=31)
    height: int | None = Field(None, ge=144, le=4320)  # quality picker; None = as large as the encoder allows
    auto: bool = False       # automatic quality: several sizes, the player picks by throughput
    remux: bool = False      # audio-only remux: the video is copied, only the audio converted
    channels: int = Field(2, ge=1, le=8)  # 6 = keep 5.1 when the source has it
    burn: int | None = Field(None, ge=0, le=99)  # image subtitle stream to paint onto the picture
    start: float = Field(0, ge=0)  # where the player starts, so the first FFmpeg run starts there


class LoginIn(BaseModel):
    name: str = Field(max_length=100)
    password: str = Field(max_length=1024)


class PasswordIn(BaseModel):
    current: str = Field(max_length=1024)
    new: str = Field(max_length=1024)


class UserIn(BaseModel):
    name: str = Field(max_length=100)
    password: str = Field(max_length=1024)
    is_admin: bool = False


class UserPatch(BaseModel):
    name: str | None = Field(None, max_length=100)
    password: str | None = Field(None, max_length=1024)
    is_admin: bool | None = None


class ProgressIn(BaseModel):
    position: float = Field(ge=0)
    duration: float | None = Field(None, gt=0)


class WatchedIn(BaseModel):
    watched: bool


# ------------------------------------------------------------------ login

PUBLIC_API = frozenset({"/api/auth/state", "/api/auth/login", "/api/auth/setup"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class LoginRequired:
    """ASGI middleware: every /api/ route except signing in needs a valid session cookie. The signed-in user
    goes into `request.state.user`. Changes (POST/PUT/PATCH/DELETE) from another site's page are refused.
    Plain ASGI rather than BaseHTTPMiddleware, which would sit between FFmpeg's streams and the client."""

    def __init__(self, app, lookup):
        self.app, self.lookup = app, lookup

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/") or path in PUBLIC_API:
            return await self.app(scope, receive, send)
        req = Request(scope)
        user = await anyio.to_thread.run_sync(self.lookup, req.cookies.get(auth.COOKIE))
        if user is None:
            return await JSONResponse({"detail": "Sign in to BAMS first."}, status_code=401)(scope, receive, send)
        if scope.get("method") not in _SAFE_METHODS and not same_origin(req):
            return await JSONResponse({"detail": "Refused: the request came from another site."},
                                      status_code=403)(scope, receive, send)
        scope.setdefault("state", {})["user"] = user
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

    # Signed-in users by cookie, for a minute: a playing video asks for a segment every few seconds, and
    # each would otherwise be a DB lookup. Signing out / password changes clear it.
    seen: dict[str, tuple[float, dict]] = {}
    seen_lock = threading.Lock()

    def lookup(token: str | None) -> dict | None:
        if not token:
            return None
        t = time.monotonic()
        with seen_lock:
            hit = seen.get(token)
            if hit and t - hit[0] < 60:
                return hit[1]
        con = connect(paths.db)
        try:
            u = auth.session_user(con, token)
        finally:
            con.close()
        user = {"id": u["id"], "name": u["name"], "is_admin": bool(u["is_admin"])} if u else None
        with seen_lock:
            if len(seen) > 1000:
                seen.clear()
            if user:
                seen[token] = (t, user)
            else:
                seen.pop(token, None)
        return user

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
        yield
        scheduler.stop()
        transcodes.shutdown()

    app = FastAPI(title="BAMS", version=VERSION, lifespan=lifespan,
                  description="Bad Ass Media Server API. Media folders are read-only to this server.")
    app.state.paths = paths
    app.state.scheduler = scheduler
    app.state.transcodes = transcodes
    app.add_middleware(LoginRequired, lookup=lookup)

    def db() -> Iterator[sqlite3.Connection]:
        con = connect(paths.db)
        try:
            yield con
        finally:
            con.close()

    @app.exception_handler(library.LibraryError)
    async def _lib_err(_req: Request, e: library.LibraryError):
        return JSONResponse({"detail": str(e)}, status_code=400)

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
        u = lookup(request.cookies.get(auth.COOKIE))
        if u:
            u = {**u, "prefs": auth.prefs(auth.get_user(con, u["id"]))}
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
        _set_cookie(response, request, auth.new_session(con, uid, request.headers.get("user-agent")))
        return auth.public(auth.get_user(con, uid))

    @app.post("/api/auth/login")
    def auth_login(body: LoginIn, request: Request, response: Response, con=Depends(db)):
        if not same_origin(request):
            raise HTTPException(403, "Refused: the request came from another site.")
        ip = _client(request)
        if throttle.blocked(ip):
            raise HTTPException(429, "Too many wrong passwords. Wait ten minutes and try again.")
        u = auth.authenticate(con, body.name, body.password)
        if not u:
            throttle.fail(ip)
            log.warning("failed sign-in for %r from %s", body.name[:40], ip)
            raise HTTPException(401, "Wrong name or password.")
        throttle.ok(ip)
        _set_cookie(response, request, auth.new_session(con, u["id"], request.headers.get("user-agent")))
        return auth.public(u)

    @app.post("/api/auth/logout", status_code=204)
    def auth_logout(request: Request, response: Response, con=Depends(db)):
        auth.end_session(con, request.cookies.get(auth.COOKIE))
        forget_sessions()
        response.delete_cookie(auth.COOKIE, path="/")

    @app.put("/api/auth/password")
    def change_password(body: PasswordIn, request: Request, response: Response, con=Depends(db),
                        me=Depends(current_user)):
        """Change your own password. Signs you out everywhere else."""
        u = auth.get_user(con, me["id"])
        if not auth.verify_password(body.current, u["password"]):
            raise HTTPException(400, "Your current password isn't right.")
        try:
            auth.update_user(con, me["id"], password=body.new)
        except auth.AuthError as e:
            raise HTTPException(400, str(e)) from None
        forget_sessions()
        _set_cookie(response, request, auth.new_session(con, me["id"], request.headers.get("user-agent")))
        return auth.public(auth.get_user(con, me["id"]))

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
            uid = auth.create_user(con, body.name, body.password, body.is_admin)
        except auth.AuthError as e:
            raise HTTPException(400, str(e)) from None
        return auth.public(auth.get_user(con, uid))

    @app.patch("/api/users/{user_id}", dependencies=ADMIN)
    def patch_user(user_id: int, body: UserPatch, con=Depends(db)):
        """Rename, reset the password (signs them out), or make/unmake an admin."""
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
        forget_sessions()

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

    def _tmdb_status(con) -> dict:
        key = get_setting(con, "tmdb_key")
        return {"configured": bool(key), "kind": key_kind(key) if key else None,
                "last4": key[-4:] if key else None, "verified_at": get_setting(con, "tmdb_verified_at")}

    @app.get("/api/settings")
    def get_settings(con=Depends(db)):
        return {"tmdb": _tmdb_status(con), "language": get_setting(con, "language", "en-US"),
                "music_lookup": music_lookup_enabled(con),
                "max_transcodes": int(get_setting(con, "max_transcodes", "0") or 0),
                "max_transcodes_auto": auto_transcode_limit(), "watch": watch.thresholds(con)}

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
                  limit: int = Query(100, le=5000), con=Depends(db), me=Depends(current_user)):
        """Shows/movies (default) or artists/albums/tracks across every library (Home rows, search)."""
        kinds = kind.split(",")
        where, args = [f"kind IN ({','.join('?' * len(kinds))})"], list(kinds)
        if q:
            where.append("(title LIKE ? OR parsed_title LIKE ?)")
            args += [f"%{q}%", f"%{q}%"]
        if genre:
            where.append("genres LIKE ?")
            args.append(f'%"{genre}"%')
        rows = con.execute(f"{ITEM_SELECT} WHERE {' AND '.join(where)} ORDER BY {_SORTS.get(sort, _SORTS['added'])} LIMIT ?",
                           (*args, limit)).fetchall()
        return watch.annotate(con, me["id"], [item_summary(r) for r in rows])

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
        d["files"] = [file_info(f, with_subtitles=playable) for f in con.execute(
            """SELECT f.*, lr.path AS root FROM files f JOIN file_items fi ON fi.file_id=f.id
               JOIN library_roots lr ON lr.id=f.root_id WHERE fi.item_id=? ORDER BY f.rel_path""", (item_id,))]
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
        for item_id, why in picks:
            r = con.execute(f"{ITEM_SELECT} WHERE id=?", (item_id,)).fetchone()
            if not r:
                continue
            d = item_summary(r)
            d["reason"] = why
            if r["kind"] == "episode":
                show = con.execute("""SELECT sh.id, sh.title, sh.poster, sh.backdrop FROM items s
                                      JOIN items sh ON sh.id=s.parent_id WHERE s.id=?""", (r["parent_id"],)).fetchone()
                d["show"] = {"id": show["id"], "title": show["title"], "poster": _img(show["poster"]),
                             "backdrop": _img(show["backdrop"])}
            out.append(d)
        return watch.annotate(con, me["id"], out)

    @app.get("/api/items/{item_id}/tracks")
    def item_tracks(item_id: int, con=Depends(db)):
        """Every playable track of an artist, album or track, in play order: what a music queue needs."""
        r = con.execute("SELECT kind FROM items WHERE id=?", (item_id,)).fetchone()
        if not r or r["kind"] not in MUSIC_KINDS:
            raise HTTPException(404, "no such artist/album/track")
        where = {"track": "t.id=?", "album": "al.id=?", "artist": "ar.id=?"}[r["kind"]]
        rows = con.execute(f"""
            SELECT t.id, t.title, t.artist, t.track_number, t.disc_number, t.duration,
                   al.id album_id, al.title album, al.poster, ar.id artist_id, ar.title album_artist,
                   f.id file_id, f.rel_path, f.probe, f.parse, f.available
            FROM items t JOIN items al ON al.id=t.parent_id JOIN items ar ON ar.id=al.parent_id
            JOIN file_items fi ON fi.item_id=t.id JOIN files f ON f.id=fi.file_id
            WHERE t.kind='track' AND {where}
            GROUP BY t.id
            ORDER BY al.year IS NULL, al.year, al.title COLLATE NOCASE, COALESCE(t.disc_number, 1),
                     t.track_number IS NULL, t.track_number, t.title COLLATE NOCASE""", (item_id,)).fetchall()
        out = []
        for t in rows:
            pb = stream.plan_audio(jload(t["probe"]), t["rel_path"])
            pb["url"] = f"/api/files/{t['file_id']}/{'audio' if pb['mode'] == 'transcode' else 'stream'}"
            out.append({
                "id": t["id"], "title": t["title"], "artist": t["artist"] or t["album_artist"],
                "album": t["album"], "album_id": t["album_id"], "artist_id": t["artist_id"],
                "album_artist": t["album_artist"], "poster": _img(t["poster"]),
                "track_number": t["track_number"], "disc_number": t["disc_number"],
                "duration": t["duration"] or pb["duration"], "file_id": t["file_id"],
                "available": bool(t["available"]), "playback": pb,
                "download_url": f"/api/files/{t['file_id']}/download",
            })
        return out

    def _unrecognized(con, lib_id: int | None) -> list[dict]:
        """Files the parser couldn't place (each with a hint about why), and files identified by hand."""
        rows = con.execute(f"""SELECT f.*, lr.path AS root, l.name AS library_name, l.type AS library_type
                               FROM files f JOIN library_roots lr ON lr.id=f.root_id JOIN libraries l ON l.id=f.library_id
                               WHERE (f.id NOT IN (SELECT file_id FROM file_items) OR f.manual IS NOT NULL)
                               {"AND f.library_id=?" if lib_id is not None else ""}
                               ORDER BY l.name COLLATE NOCASE, f.rel_path""", (() if lib_id is None else (lib_id,)))
        out = []
        for r in rows:
            manual = jload(r["manual"])
            guess = jload(r["parse"]) or {}
            out.append({**file_info(r), "library_id": r["library_id"], "library_name": r["library_name"],
                        "library_type": r["library_type"], "manual": manual,
                        "hint": None if manual else unrecognized_hint(r["rel_path"], r["library_type"]),
                        "guess": {k: guess.get(k) for k in ("title", "year", "season", "episodes", "episode_title")}})
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
        r = con.execute("SELECT kind FROM items WHERE id=?", (item_id,)).fetchone()
        if not r or r["kind"] not in ("album", "artist"):
            raise HTTPException(404, "no such album/artist")
        fn = music_match.match_album if r["kind"] == "album" else music_match.match_artist
        try:
            with MusicBrainz() as mb:
                fn(con, mb, paths.images, item_id, mbid=body.mbid.lower(), manual=True, lang=language(con))
        except MusicLookupError as e:
            raise HTTPException(502, str(e)) from None
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
        """Original file with HTTP Range support (seeking). Opened read-only."""
        p, name = _file_path(con, file_id)
        return FileResponse(p, media_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                            content_disposition_type="inline", filename=name)

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

    @app.get("/api/files/{file_id}/remux")
    async def remux_file(file_id: int, t: float = Query(0, ge=0), audio: int = Query(0, ge=0, le=31),
                         ch: int = Query(2, ge=1, le=8)):
        """Video copied as-is, audio converted to AAC (`ch=6`: 5.1 when the track has it), as fragmented MP4
        starting at `t` seconds. For files whose audio browsers can't decode (AC3/EAC3/DTS/TrueHD), or another
        audio track than the first. Seek = request again with ?t=. (The player prefers HLS: POST /hls copy.)"""
        p, info = await anyio.to_thread.run_sync(_probe_of, file_id)
        vcodec = stream.plan(info["probe"], info["parse"])["video_codec"]
        return _pipe(stream.remux_cmd, (p, t, vcodec, audio, _channels(info["probe"], audio, ch)), "video/mp4")

    @app.get("/api/files/{file_id}/transcode")
    async def transcode_file(file_id: int, t: float = Query(0, ge=0), audio: int = Query(0, ge=0, le=31),
                             h: int | None = Query(None, ge=144, le=4320), ch: int = Query(2, ge=1, le=8),
                             sub: int | None = Query(None, ge=0, le=99)):
        """Video converted to H.264 (GPU when available) and audio to AAC, as fragmented MP4 starting
        exactly at `t` seconds, at most `h` pixels high. For codecs the browser can't decode (Xvid, MPEG-2,
        VC-1, HEVC in Firefox...) when it can't use HLS (`POST /hls`). Seek = request again with ?t=.
        `sub`: an image subtitle stream to burn in."""
        p, info = await anyio.to_thread.run_sync(_probe_of, file_id)
        pr = info["probe"]
        try:
            transcodes.check()
        except hls.Busy as e:
            raise HTTPException(503, str(e)) from None
        return _pipe(stream.transcode_cmd, (p, t, pr.get("video"), audio, None, h, _channels(pr, audio, ch), sub),
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
        if body.remux:
            kf = keyframes.get(file_id, p, row["size"], row["mtime_ns"])
            if not kf:
                raise HTTPException(409, "Couldn't list this file's keyframes, so it can't be split without "
                                         "converting the video.")
            s = transcodes.create(file_id, p, pr.get("video"), pr["duration"], body.audio, channels=ch,
                                  keyframes=kf, start=body.start, bitrate=pr.get("bitrate"),
                                  video_codec=stream.plan(pr, jload(row["parse"]))["video_codec"])
        else:
            enc = stream.video_encoder()
            if not enc:
                raise HTTPException(503, "The server can't convert video: FFmpeg has no working H.264 encoder.")
            heights = hls.ladder(pr.get("video"), enc) if body.auto and not body.height else [body.height]
            try:
                s = transcodes.create(file_id, p, pr.get("video"), pr["duration"], body.audio, heights, channels=ch,
                                      burn=body.burn, start=body.start, encoder=enc)
            except hls.Busy as e:
                raise HTTPException(503, str(e)) from None
        return {"id": s.id, "playlist": f"/api/hls/{s.id}/index.m3u8", "duration": s.duration,
                "variants": [{"height": v.resolution[1] if v.resolution else v.height, "bandwidth": v.bandwidth}
                             for v in s.variants], "copy": body.remux, "channels": ch}

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
        """Music in a format browsers can't play (ALAC, AIFF, WMA, APE, DSD...), converted to AAC as
        fragmented MP4 starting at `t` seconds. Seek = request again with ?t=."""
        con = connect(paths.db)
        try:
            p, _ = _file_path(con, file_id)
            row = con.execute("SELECT probe FROM files WHERE id=?", (file_id,)).fetchone()
        finally:
            con.close()
        audio = (jload(row["probe"]) or {}).get("audio") or [{}]
        return _pipe(stream.audio_cmd, (p, t, audio[0].get("sample_rate")), "audio/mp4")

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

    @app.get("/api/files/{file_id}/download")
    def download_file(file_id: int, con=Depends(db)):
        p, name = _file_path(con, file_id)
        return FileResponse(p, media_type="application/octet-stream", filename=name)

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
