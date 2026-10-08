"""Music libraries: audio files -> artist > album > track, and album/artist artwork.

Where the facts come from, best first:
  1. the file's own tags (ID3, Vorbis comments, MP4 atoms, APE...), read by ffprobe during the scan
  2. the folder layout, Plex's music convention:
       Artist/Album (Year)/01 - Title.ext
       Artist/Album/CD1/01 Title.ext          (disc folders: CD1, Disc 2, Disk 3)
       Artist - Album (Year)/01. Title.ext
       Artist_-_01_-_Title.ext                (FMA/archive.org style; artist/album prefixes are dropped)
Every audio file becomes a track (like Plex): nothing is left "unrecognised".

Artwork, best first: an image next to the music (cover.jpg, folder.jpg... / artist.jpg one folder up),
then the picture embedded in a track. Either way the bytes are READ from the media folder and the
copy goes into the data dir (images/music/); nothing is ever written next to the media.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import readonly, stream
from .config import ALBUM_ART_NAMES, ART_EXTS, ARTIST_ART_NAMES
from .db import Tx, jdump, jload, now
from .parse import title_key

log = logging.getLogger(__name__)

PARSER_VERSION = 1  # bump to make the next scan re-read every music file's tags/path
VARIOUS = "Various Artists"
UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"
_VARIOUS_KEYS = {"variousartists", "various", "va", "compilations", "compilation", "soundtracks"}

_DISC_DIR_RE = re.compile(r"^(?:cd|disc|disk)\s*[-_.]?\s*(\d{1,2})\b", re.IGNORECASE)
_TRAILING_BRACKET_RE = re.compile(r"\s*[\[(]([^\[\]()]*)[\])]\s*$")
_YEAR_RE = re.compile(r"^(1[89]\d\d|2[01]\d\d)$")
# "01 - Title", "01. Title", "01 Title", "1-03 Title" (disc-track), "103 Title" (disc 1, track 3)
_NUM_PREFIX_RE = re.compile(r"^(?:(?P<disc>\d{1,2})[-.](?=\d{2}\D))?(?P<num>\d{1,3})(?:\s*[-._)]\s*|\s+)(?P<rest>\S.*)$")


@dataclass
class Track:
    title: str
    album: str
    album_artist: str
    artist: str | None = None          # the performer, when it isn't the album artist (features, compilations)
    year: int | None = None
    track: int | None = None
    disc: int | None = None
    genres: list[str] = field(default_factory=list)
    duration: float | None = None
    compilation: bool = False
    source: str = "path"               # "tags" if artist/album came from the file's tags

    recognized = True  # every audio file is placed somewhere

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(kind="track", v=PARSER_VERSION)
        return d


def sort_title(title: str) -> str:
    """"The Beatles" sorts under B, like every music app."""
    return re.sub(r"^(the|a|an)\s+(?=\S)", "", title.strip(), flags=re.IGNORECASE)


def _num(v: str | None) -> int | None:
    """'3', '03', '3/12' -> 3. Zero and junk -> None."""
    if not v:
        return None
    m = re.match(r"\s*(\d+)", str(v))
    n = int(m.group(1)) if m else 0
    return n or None


def _year(v: str | None) -> int | None:
    m = re.match(r"\s*(\d{4})", str(v or ""))
    return int(m.group(1)) if m and _YEAR_RE.match(m.group(1)) else None


def _split_dir(name: str) -> tuple[str, int | None]:
    """'Directionless EP (2011) [FLAC]' -> ('Directionless EP', 2011)."""
    year = None
    while (m := _TRAILING_BRACKET_RE.search(name)) and m.start() > 0:
        inner = m.group(1).strip()
        if _YEAR_RE.match(inner):
            year = year or int(inner)
        name = name[: m.start()]
    return name.strip(), year


def _clean_title(stem: str, artist: str | None, album: str | None) -> tuple[str, int | None, int | None]:
    """File name -> (title, track, disc), dropping artist/album prefixes and the track number."""
    if " " not in stem and "_" in stem:
        stem = stem.replace("_", " ")  # Broke_For_Free_-_01_-_Night_Owl
    stem = re.sub(r"\s{2,}", " ", stem).strip()
    drop = {title_key(x) for x in (artist, album) if x}
    parts = [p.strip() for p in stem.split(" - ")]
    track = disc = None
    kept: list[str] = []
    for p in parts:
        if title_key(p) in drop and len(parts) > 1:
            continue
        if track is None and p.isdigit() and len(p) <= 3:
            track = int(p)
            continue
        if track is None and not kept and (m := _NUM_PREFIX_RE.match(p)):
            n = int(m.group("num"))
            if m.group("disc"):
                disc, track = int(m.group("disc")), n
            elif n >= 100:
                disc, track = n // 100, n % 100
            else:
                track = n
            p = m.group("rest").strip()
        kept.append(p)
    title = " - ".join(kept).strip(" -._") or stem
    return title, track or None, disc


def _genres(v: str | None) -> list[str]:
    out: list[str] = []
    for g in re.split(r"[;\x00]", v or ""):
        g = g.strip()
        if g and g not in out:
            out.append(g)
    return out


def parse_track(rel: str, probe: dict | None = None) -> Track:
    """A music file's relative path (and its ffprobe summary, if it's been probed) -> Track."""
    parts = rel.split("/")
    stem = os.path.splitext(parts[-1])[0]
    dirs = parts[:-1]
    disc_dir = None
    if dirs and (m := _DISC_DIR_RE.match(dirs[-1])):
        disc_dir = int(m.group(1))
        dirs = dirs[:-1]
    album_dir, dir_year = _split_dir(dirs[-1]) if dirs else (None, None)
    artist_dir = dirs[-2] if len(dirs) >= 2 else None
    if album_dir and not artist_dir and " - " in album_dir:
        artist_dir, album_dir = (s.strip() for s in album_dir.split(" - ", 1))

    tags = (probe or {}).get("tags") or {}
    compilation = str(tags.get("compilation", "")).strip() in ("1", "true", "yes")
    if artist_dir and title_key(artist_dir) in _VARIOUS_KEYS:
        compilation = True

    t_artist, t_album = tags.get("artist"), tags.get("album")
    album_artist = (tags.get("album_artist") or (VARIOUS if compilation else None) or t_artist
                    or artist_dir or UNKNOWN_ARTIST).strip()
    album = (t_album or album_dir or UNKNOWN_ALBUM).strip()
    name_title, name_track, name_disc = _clean_title(stem, t_artist or artist_dir, t_album or album_dir)
    performer = (t_artist or "").strip() or None
    if performer and title_key(performer) == title_key(album_artist):
        performer = None
    return Track(
        title=(tags.get("title") or "").strip() or name_title,
        album=album, album_artist=album_artist, artist=performer,
        year=_year(tags.get("date")) or _year(tags.get("originaldate")) or dir_year,
        track=_num(tags.get("track")) or name_track,
        disc=_num(tags.get("disc")) or disc_dir or name_disc,
        genres=_genres(tags.get("genre")),
        duration=(probe or {}).get("duration"),
        compilation=compilation,
        source="tags" if (t_artist or t_album or tags.get("album_artist")) else "path",
    )


# ------------------------------------------------------------------ item graph

def _insert(con: sqlite3.Connection, lib_id: int, kind: str, title: str, **cols) -> int:
    t = now()
    fields = {"library_id": lib_id, "kind": kind, "title": title, "added_at": t, "updated_at": t, **cols}
    return con.execute(f"INSERT INTO items ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})",
                       tuple(fields.values())).lastrowid


def _artist(con: sqlite3.Connection, lib_id: int, name: str) -> int:
    key = title_key(name) or name.casefold()
    row = con.execute("SELECT item_id FROM item_keys WHERE library_id=? AND kind='artist' AND title_key=?",
                      (lib_id, key)).fetchone()
    if row:
        return row["item_id"]
    item_id = _insert(con, lib_id, "artist", name, parsed_title=name, title_key=key, sort_title=sort_title(name))
    con.execute("INSERT INTO item_keys (library_id, kind, title_key, year, item_id) VALUES (?, 'artist', ?, 0, ?)",
                (lib_id, key, item_id))
    return item_id


def _album(con: sqlite3.Connection, lib_id: int, artist_id: int, title: str) -> int:
    """Albums group by album artist + album title (so one album split over two folders stays one)."""
    key = title_key(title) or title.casefold()
    row = con.execute("SELECT id FROM items WHERE parent_id=? AND kind='album' AND title_key=?",
                      (artist_id, key)).fetchone()
    if row:
        return row["id"]
    return _insert(con, lib_id, "album", title, parent_id=artist_id, parsed_title=title, title_key=key,
                   sort_title=sort_title(title))


def link_track(con: sqlite3.Connection, lib_id: int, file_id: int, t: Track) -> list[int]:
    """(Re)attach a file to its track, creating the artist/album as needed. The track row is kept
    across re-reads (its id is what play history will hang off), only its fields and album change."""
    prev = con.execute("""SELECT i.id, i.match_status FROM file_items fi JOIN items i ON i.id=fi.item_id
                          WHERE fi.file_id=? AND i.kind='track'""", (file_id,)).fetchone()
    con.execute("DELETE FROM file_items WHERE file_id=?", (file_id,))
    album = _album(con, lib_id, _artist(con, lib_id, t.album_artist), t.album)
    cols = {"parent_id": album, "title": t.title, "parsed_title": t.title, "title_key": title_key(t.title),
            "disc_number": t.disc, "track_number": t.track, "artist": t.artist, "year": t.year,
            "duration": t.duration, "genres": jdump(t.genres) if t.genres else None}
    if prev and prev["match_status"] in ("matched", "manual") and t.source == "path":
        del cols["title"]  # MusicBrainz's title beats one guessed from the file name
    if prev:
        track_id = prev["id"]
        con.execute(f"UPDATE items SET {', '.join(f'{k}=?' for k in cols)}, updated_at=? WHERE id=?",
                    (*cols.values(), now(), track_id))
    else:
        track_id = _insert(con, lib_id, "track", t.title, **{k: v for k, v in cols.items() if k != "title"})
    con.execute("INSERT INTO file_items (file_id, item_id) VALUES (?, ?)", (file_id, track_id))
    return [track_id]


def rollup(con: sqlite3.Connection, lib_id: int) -> None:
    """Album year/duration/genres and artist genres, from their tracks. Recomputed after every scan
    (cheaper to get right than to keep in step track by track)."""
    con.execute("""UPDATE items SET
                     year = CASE WHEN match_status IN ('matched', 'manual') THEN year  -- MusicBrainz's original year
                                 ELSE (SELECT MIN(t.year) FROM items t WHERE t.parent_id = items.id) END,
                     duration = (SELECT SUM(t.duration) FROM items t WHERE t.parent_id = items.id)
                   WHERE library_id=? AND kind='album'""", (lib_id,))
    for parent_kind, child_kind in (("album", "track"), ("artist", "album")):
        genres: dict[int, list[str]] = {}
        for r in con.execute("""SELECT c.parent_id p, c.genres g FROM items c
                                WHERE c.library_id=? AND c.kind=? AND c.genres IS NOT NULL""", (lib_id, child_kind)):
            acc = genres.setdefault(r["p"], [])
            acc.extend(g for g in jload(r["g"]) if g not in acc)
        con.execute("UPDATE items SET genres=NULL WHERE library_id=? AND kind=?", (lib_id, parent_kind))
        con.executemany("UPDATE items SET genres=? WHERE id=?", [(jdump(g[:5]), p) for p, g in genres.items()])


# ------------------------------------------------------------------ artwork

@dataclass
class ArtStats:
    albums_checked: int = 0
    album_covers: int = 0
    artist_images: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _image_ext(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _store_image(images: Path, data: bytes) -> str | None:
    """Save image bytes in the data dir under a content hash; returns the path relative to images/."""
    ext = _image_ext(data)
    if not ext:
        return None
    h = hashlib.sha1(data).hexdigest()
    rel = f"music/{h[:2]}/{h}{ext}"
    dest = images / rel
    if not dest.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    return rel


def _folder_image(folder: Path, names: tuple[str, ...]) -> Path | None:
    """cover.jpg / Folder.JPG / ... in `folder` (case-insensitive), in the order of `names`."""
    try:
        with os.scandir(folder) as it:
            found = {e.name.casefold(): Path(e.path) for e in it
                     if os.path.splitext(e.name)[1].casefold() in ART_EXTS and e.is_file()}
    except OSError:
        return None
    for n in names:
        for ext in ART_EXTS:
            if (p := found.get(n + ext)) is not None:
                return p
    return None


def _read_image(path: Path, limit: int = 20_000_000) -> bytes | None:
    try:
        if path.stat().st_size > limit:
            return None
        with readonly.open_ro(path) as f:
            return f.read()
    except OSError as e:
        log.warning("can't read %s: %s", path, e)
        return None


def embedded_picture(path: Path) -> bytes | None:
    """The cover picture stored inside an audio file, copied out by FFmpeg to a pipe."""
    exe = stream.ffmpeg_path()
    if not exe:
        return None
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
           "-map", "0:v:0", "-c:v", "copy", "-frames:v", "1", "-f", "image2pipe", "pipe:1"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("can't extract cover from %s: %s", path, e)
        return None
    return r.stdout if r.returncode == 0 and r.stdout else None


def fill_artwork(con: sqlite3.Connection, images: Path, lib_id: int) -> ArtStats:
    """Album covers and artist images for albums/artists that don't have one yet.

    An album is looked at again only when one of its tracks changed since the last look
    (metadata_at), so albums without any art don't cost a folder listing every scan."""
    stats = ArtStats()
    roots = {r["id"]: Path(r["path"]) for r in con.execute("SELECT id, path FROM library_roots WHERE library_id=?", (lib_id,))}
    albums = con.execute("""SELECT a.id, a.parent_id FROM items a WHERE a.library_id=? AND a.kind='album' AND a.poster IS NULL
                            AND (a.metadata_at IS NULL OR EXISTS (SELECT 1 FROM items t WHERE t.parent_id=a.id
                                                                  AND t.updated_at > a.metadata_at))""", (lib_id,)).fetchall()
    artist_dirs: dict[int, set[Path]] = {}
    for al in albums:
        stats.albums_checked += 1
        tracks = con.execute("""SELECT f.root_id, f.rel_path, f.probe FROM items t JOIN file_items fi ON fi.item_id=t.id
                                JOIN files f ON f.id=fi.file_id WHERE t.parent_id=? AND f.available=1
                                ORDER BY t.disc_number, t.track_number, t.title""", (al["id"],)).fetchall()
        poster = None
        folders: list[Path] = []
        for t in tracks:
            root = roots.get(t["root_id"])
            if root is None:
                continue
            folder = (root / t["rel_path"]).parent
            if _DISC_DIR_RE.match(folder.name) and folder != root:
                folders += [folder, folder.parent]
            else:
                folders.append(folder)
        folders = list(dict.fromkeys(folders))  # unique, in order
        for folder in folders:
            if (img := _folder_image(folder, ALBUM_ART_NAMES)) and (data := _read_image(img)):
                poster = _store_image(images, data)
                if poster:
                    break
        if not poster:
            for t in tracks:
                if (jload(t["probe"]) or {}).get("cover") and t["root_id"] in roots:
                    data = embedded_picture(roots[t["root_id"]] / t["rel_path"])
                    if data and (poster := _store_image(images, data)):
                        break
        with Tx(con):
            con.execute("UPDATE items SET poster=COALESCE(?, poster), metadata_at=? WHERE id=?", (poster, now(), al["id"]))
        if poster:
            stats.album_covers += 1
        # the artist's folder is the one holding the album folders (never the library root itself)
        for folder in folders[:1]:
            album_folder = folder.parent if _DISC_DIR_RE.match(folder.name) else folder
            parent = album_folder.parent
            if all(parent != r and parent.is_relative_to(r) for r in roots.values() if album_folder.is_relative_to(r)):
                artist_dirs.setdefault(al["parent_id"], set()).add(parent)

    for artist_id, dirs in artist_dirs.items():
        if con.execute("SELECT poster FROM items WHERE id=?", (artist_id,)).fetchone()["poster"]:
            continue
        for d in sorted(dirs):
            if (img := _folder_image(d, ARTIST_ART_NAMES)) and (data := _read_image(img)) and (rel := _store_image(images, data)):
                with Tx(con):
                    con.execute("UPDATE items SET poster=? WHERE id=?", (rel, artist_id))
                stats.artist_images += 1
                break
    return stats
