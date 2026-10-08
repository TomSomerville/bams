"""HTTP API (FastAPI). Interactive docs at /docs while the server runs."""

from __future__ import annotations

import logging
import mimetypes
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
import anyio
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import fsbrowse, hls, library, matcher, music_match, probe, readonly, stream
from .config import VERSION, Paths
from .db import connect, get_setting, jload, migrate, set_setting
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


def file_info(r: sqlite3.Row) -> dict:
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
    return {
        "id": r["id"], "path": r["rel_path"], "root": r["root"], "size": r["size"],
        "available": bool(r["available"]), "probe": pr,
        "release": (pa or {}).get("release"), "playback": pb,
        "stream_url": f"/api/files/{r['id']}/stream", "download_url": f"/api/files/{r['id']}/download",
    }


def unrecognized_hint(rel: str, lib_type: str) -> str:
    """Why a file wasn't placed. Most often: a movie in a TV library or vice versa."""
    if lib_type == "music":
        return "Couldn't read this file's tags or name."
    if lib_type == "show":
        m = parse_movie(rel)
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


class MusicMatchIn(BaseModel):
    mbid: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")


class ToggleIn(BaseModel):
    enabled: bool


class TranscodingIn(BaseModel):
    max_transcodes: int = Field(ge=0, le=32)  # 0 = automatic


class HlsIn(BaseModel):
    audio: int = Field(0, ge=0, le=31)
    height: int | None = Field(None, ge=144, le=4320)  # quality picker; None = as large as the encoder allows


# ------------------------------------------------------------------ app

class SpaFiles(StaticFiles):
    """Static files, but unknown paths (client-side routes like /settings) get index.html."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code != 404 or path.replace("\\", "/").startswith("api/"):  # OS-normalised path
                raise
            return await super().get_response("index.html", scope)


def create_app(paths: Paths, *, start_scheduler: bool = True, web_dir: Path | None = None) -> FastAPI:
    bootstrap(paths)
    scheduler = Scheduler(paths)

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

    def db() -> Iterator[sqlite3.Connection]:
        con = connect(paths.db)
        try:
            yield con
        finally:
            con.close()

    @app.exception_handler(library.LibraryError)
    async def _lib_err(_req: Request, e: library.LibraryError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    # -- status & settings
    @app.get("/api/status")
    def status(con=Depends(db)):
        key = get_setting(con, "tmdb_key")
        enc = stream.video_encoder()
        return {
            "version": VERSION, "data_dir": str(paths.root),
            "ffprobe": probe.ffprobe_path(), "ffmpeg": stream.ffmpeg_path(), "tmdb_configured": bool(key),
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
                "max_transcodes_auto": auto_transcode_limit()}

    @app.put("/api/settings/transcoding")
    def put_transcoding(body: TranscodingIn, con=Depends(db)):
        """How many videos may be converted at once (0 = automatic: 4 on a GPU encoder, 2 on the CPU)."""
        set_setting(con, "max_transcodes", str(body.max_transcodes))
        return {"max_transcodes": body.max_transcodes, "limit": transcode_limit()}

    @app.put("/api/settings/music-lookup")
    def put_music_lookup(body: ToggleIn, con=Depends(db)):
        """Turn online music identification (MusicBrainz, Cover Art Archive, Wikipedia) on or off."""
        set_setting(con, "music_lookup", "1" if body.enabled else "0")
        return {"music_lookup": body.enabled}

    @app.put("/api/settings/tmdb-key")
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
        return _tmdb_status(con)

    @app.delete("/api/settings/tmdb-key")
    def delete_key(con=Depends(db)):
        set_setting(con, "tmdb_key", None)
        set_setting(con, "tmdb_verified_at", None)
        return _tmdb_status(con)

    @app.post("/api/settings/tmdb-key/test")
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

    @app.get("/api/fs/browse")
    def fs_browse(path: str | None = None):
        """List folders on the server, for picking library folders. Names only; nothing is changed."""
        try:
            return fsbrowse.browse(path)
        except fsbrowse.BrowseError as e:
            raise HTTPException(400, str(e)) from None

    # -- libraries
    @app.get("/api/libraries")
    def list_libraries(con=Depends(db)):
        return [library.describe(con, r) for r in con.execute("SELECT * FROM libraries ORDER BY name")]

    @app.post("/api/libraries", status_code=201)
    def create_library(body: LibraryIn, con=Depends(db)):
        lib_id = library.create(con, paths.root, body.name, body.type, body.paths, body.scan_interval_hours)
        scheduler.request(lib_id, "manual")
        return library.describe(con, library.get(con, lib_id))

    @app.get("/api/libraries/{lib_id}")
    def get_library(lib_id: int, con=Depends(db)):
        return library.describe(con, library.get(con, lib_id))

    @app.patch("/api/libraries/{lib_id}")
    def patch_library(lib_id: int, body: LibraryPatch, con=Depends(db)):
        library.update(con, paths.root, lib_id, **body.model_dump())
        if body.add_paths or body.remove_paths:
            scheduler.request(lib_id, "manual")  # index the new folder (or drop the removed one's items) now
        return library.describe(con, library.get(con, lib_id))

    @app.delete("/api/libraries/{lib_id}", status_code=204)
    def delete_library(lib_id: int, con=Depends(db)):
        """Removes BAMS's records only. Media files are never touched."""
        library.delete(con, lib_id)

    @app.post("/api/libraries/{lib_id}/scan", status_code=202)
    def scan_library(lib_id: int, rematch: bool = False, con=Depends(db)):
        library.get(con, lib_id)
        accepted = scheduler.request(lib_id, "manual", retry_unmatched=rematch)  # False: already queued/running
        return {"accepted": accepted, **scheduler.status()}

    @app.get("/api/scans")
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
                      q: str | None = None, limit: int = Query(500, le=5000), offset: int = 0, con=Depends(db)):
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
        return [item_summary(r) for r in rows]

    @app.get("/api/items")
    def all_items(kind: str = Query("show,movie", pattern="^(show|movie|artist|album|track)(,(show|movie|artist|album|track))*$"),
                  sort: str = "added", q: str | None = None, genre: str | None = None,
                  limit: int = Query(100, le=5000), con=Depends(db)):
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
        return [item_summary(r) for r in rows]

    @app.get("/api/items/{item_id}")
    def get_item(item_id: int, con=Depends(db)):
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
                 }.get(r["kind"], "episode_number")
        d["children"] = [item_summary(c) for c in con.execute(
            f"{ITEM_SELECT} WHERE parent_id=? ORDER BY {order}", (item_id,))]
        d["files"] = [file_info(f) for f in con.execute(
            """SELECT f.*, lr.path AS root FROM files f JOIN file_items fi ON fi.file_id=f.id
               JOIN library_roots lr ON lr.id=f.root_id WHERE fi.item_id=? ORDER BY f.rel_path""", (item_id,))]
        return d

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

    @app.get("/api/libraries/{lib_id}/unrecognized")
    def unrecognized(lib_id: int, con=Depends(db)):
        """Indexed files the parser couldn't place, each with a hint about why."""
        lib = library.get(con, lib_id)
        rows = con.execute("""SELECT f.*, lr.path AS root FROM files f JOIN library_roots lr ON lr.id=f.root_id
                              WHERE f.library_id=? AND f.id NOT IN (SELECT file_id FROM file_items)
                              ORDER BY f.rel_path""", (lib_id,))
        return [{**file_info(r), "hint": unrecognized_hint(r["rel_path"], lib["type"])} for r in rows]

    @app.get("/api/tmdb/search")
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

    @app.post("/api/items/{item_id}/match")
    def fix_match(item_id: int, body: MatchIn, con=Depends(db)):
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
        return get_item(keep["id"], con)

    @app.get("/api/musicbrainz/search")
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

    @app.post("/api/items/{item_id}/music-match")
    def music_fix_match(item_id: int, body: MusicMatchIn, con=Depends(db)):
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
        return get_item(item_id, con)

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

    @app.get("/api/files/{file_id}/remux")
    async def remux_file(file_id: int, t: float = Query(0, ge=0), audio: int = Query(0, ge=0, le=31)):
        """Video copied as-is, audio converted to AAC, as fragmented MP4 starting at `t` seconds.
        For files whose audio browsers can't decode (AC3/EAC3/DTS/TrueHD). Seek = request again with ?t=."""
        con = connect(paths.db)
        try:
            p, _ = _file_path(con, file_id)
            row = con.execute("SELECT probe, parse FROM files WHERE id=?", (file_id,)).fetchone()
        finally:
            con.close()
        vcodec = stream.plan(jload(row["probe"]), jload(row["parse"]))["video_codec"]
        return _pipe(stream.remux_cmd, (p, t, vcodec, audio), "video/mp4")

    @app.get("/api/files/{file_id}/transcode")
    async def transcode_file(file_id: int, t: float = Query(0, ge=0), audio: int = Query(0, ge=0, le=31),
                             h: int | None = Query(None, ge=144, le=4320)):
        """Video converted to H.264 (GPU when available) and audio to AAC, as fragmented MP4 starting
        exactly at `t` seconds, at most `h` pixels high. For codecs the browser can't decode (Xvid, MPEG-2,
        VC-1, HEVC in Firefox...) when it can't use HLS (`POST /hls`). Seek = request again with ?t=."""
        con = connect(paths.db)
        try:
            p, _ = _file_path(con, file_id)
            row = con.execute("SELECT probe FROM files WHERE id=?", (file_id,)).fetchone()
        finally:
            con.close()
        video = (jload(row["probe"]) or {}).get("video")
        try:
            transcodes.check()
        except hls.Busy as e:
            raise HTTPException(503, str(e)) from None
        return _pipe(stream.transcode_cmd, (p, t, video, audio, None, h), "video/mp4", on_start=transcodes.add_pipe)

    @app.post("/api/files/{file_id}/hls")
    def hls_start(file_id: int, body: HlsIn, con=Depends(db)):
        """Start an HLS conversion of a video (H.264 + AAC, 4-second segments made on demand). The player
        loads `playlist` and seeks by itself. Close it with DELETE /api/hls/{id} (or it closes when idle)."""
        p, _ = _file_path(con, file_id)
        pr = jload(con.execute("SELECT probe FROM files WHERE id=?", (file_id,)).fetchone()["probe"]) or {}
        if not pr.get("duration"):
            raise HTTPException(409, "This file hasn't been probed yet, so its length isn't known and it can't be "
                                     "split into segments.")
        if not stream.ffmpeg_path() or not stream.video_encoder():
            raise HTTPException(503, "The server can't convert video: FFmpeg or a working H.264 encoder is missing.")
        try:
            s = transcodes.create(file_id, p, pr.get("video"), pr["duration"], body.audio, body.height)
        except hls.Busy as e:
            raise HTTPException(503, str(e)) from None
        return {"id": s.id, "playlist": f"/api/hls/{s.id}/index.m3u8", "duration": s.duration,
                "segment": stream.SEGMENT}

    def _session(sid: str) -> hls.Session:
        try:
            return transcodes.get(sid)
        except KeyError:
            raise HTTPException(404, "no such conversion (it was closed, or the server restarted)") from None

    @app.get("/api/hls/{sid}/index.m3u8")
    def hls_playlist(sid: str):
        return Response(_session(sid).playlist(), media_type="application/vnd.apple.mpegurl",
                        headers={"cache-control": "no-store"})

    @app.get("/api/hls/{sid}/{k}.ts")
    def hls_segment(sid: str, k: int):
        """One segment, made first if needed (waits up to a minute). Sync: runs in the thread pool."""
        s = _session(sid)
        try:
            f = transcodes.segment(s, k)
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
        return FileResponse(f, media_type="video/mp2t", headers={"cache-control": "no-store"})

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
