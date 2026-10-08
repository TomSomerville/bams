"""Playlists imported from .m3u / .m3u8 / .pls files found in music libraries.

The playlist file stays the source of truth: it's only read (never written), re-read when its size or
modification time changes, and its BAMS playlist goes when the file does. Its entries are kept as written
and matched to tracks after every scan (moved files, CUE images and new music are picked up):

  1. a path relative to the playlist's folder (the usual case: `../Album/01 - Song.flac`)
  2. an absolute path under one of the library's folders (`D:\\Music\\...`, `/srv/music/...`, `file:///...`)
  3. the end of the path: the last three, two, then one parts ("Artist/Album/01.flac"), when exactly one
     file in the library ends that way. Covers playlists made on another computer or before a move.

Entries that match nothing (streams, files not in the library) are counted as missing.
"""

from __future__ import annotations

import logging
import posixpath
import re
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import readonly
from .db import Tx, jdump, jload, now

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_DRIVE_RE = re.compile(r"^/?[a-z]:/", re.IGNORECASE)


def _num(v: str | None) -> float | None:
    try:
        d = float(v) if v is not None else None
    except ValueError:
        return None
    return d if d and d > 0 else None


def parse_m3u(text: str) -> tuple[str | None, list[dict]]:
    """M3U / extended M3U: one path per line; #EXTINF:<seconds>,<Artist - Title> before it; #PLAYLIST:<name>."""
    name, out, info = None, [], None
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.startswith("#"):
            if line.upper().startswith("#EXTINF:"):
                dur, _, title = line[8:].partition(",")
                info = {"duration": _num(dur.split()[0] if dur.split() else None), "title": title.strip() or None}
            elif line.upper().startswith("#PLAYLIST:"):
                name = line[10:].strip() or None
            continue
        out.append({"path": line, **(info or {"title": None, "duration": None})})
        info = None
    return name, out


def parse_pls(text: str) -> tuple[str | None, list[dict]]:
    """PLS: an INI-style [playlist] with FileN=, TitleN=, LengthN=."""
    vals: dict[str, dict[int, str]] = {}
    for raw in text.splitlines():
        k, eq, v = raw.strip().partition("=")
        m = re.match(r"^(file|title|length)(\d+)$", k.strip(), re.IGNORECASE)
        if eq and m:
            vals.setdefault(m.group(1).lower(), {})[int(m.group(2))] = v.strip()
    files = vals.get("file", {})
    return None, [{"path": files[n], "title": vals.get("title", {}).get(n) or None,
                   "duration": _num(vals.get("length", {}).get(n))} for n in sorted(files)]


def parse(filename: str, text: str) -> tuple[str, list[dict]]:
    """(name, entries). The name is the file's own (#PLAYLIST:), else the file name without its extension."""
    is_pls = filename.casefold().endswith(".pls") or text.lstrip("\ufeff").lstrip().lower().startswith("[playlist]")
    name, entries = (parse_pls if is_pls else parse_m3u)(text)
    return name or filename.rsplit(".", 1)[0], entries


def import_files(con: sqlite3.Connection, lib_id: int, root_id: int, found: list[readonly.FileEntry]) -> int:
    """Bring a library folder's playlists in step with the playlist files the scan saw there. Returns how
    many were added or re-read. Reads first, then one short write."""
    known = {r["rel_path"]: r for r in con.execute(
        "SELECT id, rel_path, size, mtime_ns FROM playlists WHERE root_id=?", (root_id,))}
    changed = []
    for e in found:
        old = known.pop(e.rel, None)
        if old and old["size"] == e.size and old["mtime_ns"] == e.mtime_ns:
            continue
        text = readonly.read_text(e.path, 5_000_000)
        if text is None:  # unreadable right now: keep what we had (it's out of `known`, so not deleted below)
            continue
        name, entries = parse(e.path.name, text)
        changed.append((old, e, name, entries))
    if not changed and not known:
        return 0
    with Tx(con):
        t = now()
        for old, e, name, entries in changed:
            if old:
                con.execute("UPDATE playlists SET name=?, size=?, mtime_ns=?, entries=?, updated_at=? WHERE id=?",
                            (name, e.size, e.mtime_ns, jdump(entries), t, old["id"]))
            else:
                con.execute("""INSERT INTO playlists (library_id, root_id, rel_path, name, size, mtime_ns, entries,
                               added_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                            (lib_id, root_id, e.rel, name, e.size, e.mtime_ns, jdump(entries), t, t))
            log.info("playlist %s: %s (%d entries)", "updated" if old else "imported", e.rel, len(entries))
        for gone in known.values():  # the file was deleted or moved away
            con.execute("DELETE FROM playlists WHERE id=?", (gone["id"],))
    return len(changed)


def _local_path(entry: str) -> str | None:
    """An entry as a '/'-separated path, or None for a stream (http://...)."""
    if entry.lower().startswith("file:"):
        p = unquote(urlparse(entry).path or "")
        if urlparse(entry).netloc:  # file://server/share/x -> //server/share/x
            p = f"//{urlparse(entry).netloc}{p}"
        entry = p[1:] if _DRIVE_RE.match(p) and p.startswith("/") else p
    elif _URL_RE.match(entry):
        return None
    return entry.replace("\\", "/")


def _is_absolute(p: str) -> bool:
    return p.startswith("/") or bool(_DRIVE_RE.match(p))


def resolve(con: sqlite3.Connection, lib_id: int) -> None:
    """Match every playlist of the library to its tracks again (call inside a transaction)."""
    pls = con.execute("SELECT id, root_id, rel_path, entries FROM playlists WHERE library_id=?", (lib_id,)).fetchall()
    if not pls:
        return
    roots = {r["id"]: Path(r["path"]).as_posix().rstrip("/").casefold()
             for r in con.execute("SELECT id, path FROM library_roots WHERE library_id=?", (lib_id,))}
    by_rel: dict[tuple[int, str], int] = {}
    by_tail: dict[str, int | None] = {}  # None = more than one file ends that way
    for f in con.execute("SELECT id, root_id, rel_path FROM files WHERE library_id=?", (lib_id,)):
        rel = f["rel_path"].casefold()
        by_rel[(f["root_id"], rel)] = f["id"]
        parts = rel.split("/")
        for k in (1, 2, 3):
            if len(parts) >= k:
                tail = "/".join(parts[-k:])
                by_tail[tail] = f["id"] if tail not in by_tail else None
    tracks_of: dict[int, list[int]] = {}
    for r in con.execute("""SELECT fi.file_id, fi.item_id FROM file_items fi JOIN files f ON f.id=fi.file_id
                            JOIN items i ON i.id=fi.item_id WHERE f.library_id=? AND i.kind='track'
                            ORDER BY fi.file_id, fi.cue_start""", (lib_id,)):
        tracks_of.setdefault(r["file_id"], []).append(r["item_id"])

    def find(root_id: int, folder: str, entry: str) -> int | None:
        p = _local_path(entry)
        if not p:
            return None
        if _is_absolute(p):
            low = p.casefold()
            for rid, rp in roots.items():
                if low.startswith(rp + "/") and (fid := by_rel.get((rid, low[len(rp) + 1:]))):
                    return fid
        else:
            rel = posixpath.normpath(posixpath.join(folder, p)).casefold()
            if not rel.startswith("../") and (fid := by_rel.get((root_id, rel))):
                return fid
        parts = [x for x in p.casefold().split("/") if x and x != "."]
        for k in (3, 2, 1):
            if len(parts) >= k and (fid := by_tail.get("/".join(parts[-k:]))):
                return fid
        return None

    for pl in pls:
        folder = posixpath.dirname(pl["rel_path"] or "")
        ids: list[int] = []
        missing = 0
        for e in jload(pl["entries"]) or []:
            fid = find(pl["root_id"], folder, e.get("path") or "")
            got = tracks_of.get(fid, []) if fid else []
            if not got:
                missing += 1
            ids.extend(got)
        con.execute("DELETE FROM playlist_items WHERE playlist_id=?", (pl["id"],))
        con.executemany("INSERT INTO playlist_items (playlist_id, position, item_id) VALUES (?,?,?)",
                        [(pl["id"], n, i) for n, i in enumerate(ids)])
        con.execute("UPDATE playlists SET missing=? WHERE id=?", (missing, pl["id"]))
