"""Library scan: walk -> diff -> parse -> link -> probe. Read-only on the media folders.

Music libraries go walk -> diff -> probe -> parse -> link instead: a track's artist/album/title
come mostly from its tags, which ffprobe reads, so files are linked after they're probed. Their walk also
notes cue sheets, cover images and playlists (same directory listings): a file with a cue sheet becomes
several tracks, and playlists are imported (playlists.py).

Everything a scan learns is written to the database in the data directory; nothing is ever
written next to the media.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, fields
from pathlib import Path

from . import cue, identify, items, library, music, playlists, probe, readonly
from .config import ART_EXTS, AUDIO_EXTS, CUE_EXTS, EXTRAS_DIRS, PLAYLIST_EXTS, SKIP_DIRS, VIDEO_EXTS
from .db import Tx, jdump, jload, now
from .parse import PARSER_VERSION

log = logging.getLogger(__name__)
BATCH = 200  # commit every N files so a long scan never holds the write lock for long
# progress(step, done=None, total=None, bytes_done=None, bytes_total=None): what the scan is doing and how far it
# is, for Settings ("Reading file details: 120 of 505 files, 12 of 48 GB"). Plain progress("text") works too.
Progress = Callable[..., None]


@dataclass
class ScanStats:
    files_seen: int = 0
    added: int = 0
    changed: int = 0
    moved: int = 0
    missing: int = 0
    unrecognized: int = 0
    busy: int = 0                      # couldn't open (mid-copy?); retried next scan
    reparsed: int = 0                  # unchanged files re-read with a newer parser
    probed: int = 0
    orphans_removed: int = 0
    cue_files: int = 0                 # files split into tracks by a cue sheet (music)
    playlists: int = 0                 # playlists imported or updated (music)
    roots_offline: list[str] = field(default_factory=list)
    # music: cue sheets / images / playlists the walk saw, by folder (for the artwork step; not in as_dict)
    side: dict[Path, list[readonly.FileEntry]] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "side"}


def _store_parse(con: sqlite3.Connection, lib_id: int, lib_type: str, file_id: int, rel: str, stats: ScanStats,
                 probe_info: dict | None = None, sheet: tuple | None = None, cues: list | None = None) -> None:
    if lib_type == "music":
        if sheet:  # (CueSheet, its FILE block for this file, where the sheet is: a rel path or "embedded")
            tracks = music.parse_cue_tracks(rel, probe_info, sheet[0], sheet[1])
            p = {**tracks[0].to_dict(), "title": None, "track": None, "start": None, "end": None, "duration": None,
                 "source": "cue" if any(t.source == "cue" for t in tracks) else "path",
                 "cue": {"sheet": sheet[2], "tracks": len(tracks)}}
            stats.cue_files += 1
        else:
            tracks = [music.parse_track(rel, probe_info)]
            p = tracks[0].to_dict()
        p["cues"] = cues or []
        con.execute("UPDATE files SET parse=? WHERE id=?", (jdump(p), file_id))
        music.link_tracks(con, lib_id, file_id, tracks)
        return
    p = identify.parsed_for(con, file_id, rel, lib_type)  # identified by hand, else by its name
    con.execute("UPDATE files SET parse=? WHERE id=?", (jdump(p.to_dict()), file_id))
    if not items.link_file(con, lib_id, file_id, p):
        stats.unrecognized += 1
        log.info("unrecognised: %s", rel)


def scan_library(con: sqlite3.Connection, lib_id: int, *, do_probe: bool = True,
                 progress: Progress | None = None) -> ScanStats:
    lib = library.get(con, lib_id)
    report: Progress = progress or (lambda *a, **k: None)
    seen_bytes = 0
    lib_type = lib["type"]
    is_music = lib_type == "music"
    exts, nested_skip = (AUDIO_EXTS, frozenset()) if is_music else (VIDEO_EXTS, EXTRAS_DIRS)
    parser_version = music.PARSER_VERSION if is_music else PARSER_VERSION
    relink: list[tuple[int, str]] = []  # music: (file_id, rel) to parse + link once probed
    stats = ScanStats()
    side: list[readonly.FileEntry] = []          # music: cue sheets, images, playlists seen by the walk
    side_exts = CUE_EXTS | frozenset(ART_EXTS) | PLAYLIST_EXTS if is_music else frozenset()
    audio_in: Counter[Path] = Counter()          # music: audio files per folder
    sheets: dict[Path, cue.CueSheet] = {}        # cue sheets read this scan

    def cues_near(path: Path) -> list[list]:
        """The cue sheets in a file's folder, as [rel, size, mtime]: when they change, its tracks are re-read."""
        return sorted([e.rel, e.size, e.mtime_ns] for e in stats.side.get(path.parent, ())
                      if e.path.suffix.casefold() in CUE_EXTS)

    def sheet_for(path: Path, probe_info: dict | None) -> tuple | None:
        """The cue sheet that cuts this file into tracks: a .cue next to it naming it, else one in its tags."""
        for e in sorted((e for e in stats.side.get(path.parent, ()) if e.path.suffix.casefold() in CUE_EXTS),
                        key=lambda e: e.rel):
            if e.path not in sheets:
                sheets[e.path] = cue.parse(readonly.read_text(e.path) or "")
            block = cue.file_for(sheets[e.path], path.name, only_audio_file=audio_in[path.parent] == 1)
            if cue.splits(block):
                return sheets[e.path], block, e.rel
        if text := (probe_info or {}).get("cuesheet"):
            sh = cue.parse(text)
            block = sh.files[0] if len(sh.files) == 1 else cue.file_for(sh, path.name)
            if cue.splits(block):
                return sh, block, "embedded"
        return None

    def store(file_id: int, path: Path, rel: str, probe_info: dict | None = None) -> None:
        if is_music:
            _store_parse(con, lib_id, lib_type, file_id, rel, stats, probe_info, sheet_for(path, probe_info),
                         cues_near(path))
        else:
            _store_parse(con, lib_id, lib_type, file_id, rel, stats, probe_info)

    to_probe: list[tuple[int, Path]] = []
    new_files: list[tuple[int, readonly.FileEntry]] = []   # (root_id, entry)
    seen_ids: set[int] = set()
    online_roots: list[int] = []

    for root in library.roots(con, lib_id):
        root_path = Path(root["path"])
        st = readonly.root_status(root_path)
        if not (st["exists"] and st["readable"]):
            # Unmounted drive / offline share: don't mark its files missing, just skip it.
            stats.roots_offline.append(root["path"])
            log.warning("library %s: root offline, skipped: %s", lib["name"], root_path)
            continue
        online_roots.append(root["id"])
        known = {r["rel_path"]: r for r in con.execute(
            "SELECT id, rel_path, size, mtime_ns, json_extract(parse, '$.v') AS pv, "
            + ("probe, json_extract(parse, '$.cues') AS cues, json_extract(probe, '$.pv') AS ppv, "
               "json_extract(probe, '$.duration') AS pdur " if is_music else
               "NULL AS probe, NULL AS cues, NULL AS ppv, NULL AS pdur ")
            + "FROM files WHERE root_id=?", (root["id"],))}
        report("Looking for files", stats.files_seen, None, seen_bytes)
        # Walk first, with no transaction open: listing a big (network) tree can take minutes, and holding the
        # write lock meanwhile made every other write (logins, adding a library) fail with "database is locked".
        known_entries: list[tuple[sqlite3.Row, readonly.FileEntry]] = []
        side.clear()
        for entry in readonly.walk(root_path, exts, SKIP_DIRS, nested_skip, side_exts, side):
            stats.files_seen += 1
            if is_music:
                audio_in[entry.path.parent] += 1
            seen_bytes += entry.size
            if stats.files_seen % 50 == 0:
                report("Looking for files", stats.files_seen, None, seen_bytes)
            row = known.get(entry.rel)
            if row is None:
                new_files.append((root["id"], entry))
            else:
                seen_ids.add(row["id"])
                known_entries.append((row, entry))
        for e in side:
            stats.side.setdefault(e.path.parent, []).append(e)
        if is_music:
            stats.playlists += playlists.import_files(con, lib_id, root["id"],
                                                      [e for e in side if e.path.suffix.casefold() in PLAYLIST_EXTS])
        for i in range(0, len(known_entries), BATCH):
            with Tx(con):
                for row, entry in known_entries[i:i + BATCH]:
                    t = now()
                    if row["size"] == entry.size and row["mtime_ns"] == entry.mtime_ns:
                        con.execute("UPDATE files SET last_seen=?, available=1, missing_since=NULL WHERE id=?", (t, row["id"]))
                        if is_music and row["pdur"] and row["pdur"] >= 600 and (row["ppv"] or 0) < probe.PROBE_VERSION:
                            # a long file probed before embedded cue sheets were read: probe it again, then re-read
                            con.execute("UPDATE files SET probed_at=NULL WHERE id=?", (row["id"],))
                            relink.append((row["id"], entry.rel))
                        elif (row["pv"] or 0) < parser_version or (
                                is_music and json.loads(row["cues"] or "[]") != cues_near(entry.path)):
                            stats.reparsed += 1
                            store(row["id"], entry.path, entry.rel, jload(row["probe"]))
                    else:
                        stats.changed += 1
                        con.execute("""UPDATE files SET size=?, mtime_ns=?, quick_hash=NULL, probe=NULL, probed_at=NULL,
                                       last_seen=?, available=1, missing_since=NULL WHERE id=?""",
                                    (entry.size, entry.mtime_ns, t, row["id"]))
                        if is_music:
                            relink.append((row["id"], entry.rel))  # tags may have changed: re-read after probing
                        else:
                            store(row["id"], entry.path, entry.rel)
                        to_probe.append((row["id"], entry.path))

    # Files the DB knows (in online roots) that weren't seen: candidates for "moved" or "missing".
    gone = [r for r in con.execute(
        f"SELECT id, size, quick_hash FROM files WHERE library_id=? AND root_id IN ({','.join('?' * len(online_roots)) or 'NULL'})",
        (lib_id, *online_roots)) if r["id"] not in seen_ids]
    gone_by_size: dict[int, list[sqlite3.Row]] = {}
    for r in gone:
        gone_by_size.setdefault(r["size"], []).append(r)
    moved_ids: set[int] = set()

    new_bytes, hashed_n, hashed_bytes = sum(e.size for _, e in new_files), 0, 0
    for i in range(0, len(new_files), BATCH):
        # Read the files' fingerprints before taking the write lock (slow on a network share).
        hashed: list[tuple[int, readonly.FileEntry, str]] = []
        for root_id, entry in new_files[i:i + BATCH]:
            report("Adding new files", hashed_n, len(new_files), hashed_bytes, new_bytes)
            hashed_n, hashed_bytes = hashed_n + 1, hashed_bytes + entry.size
            try:
                hashed.append((root_id, entry, readonly.quick_hash(entry.path, entry.size)))
            except OSError as e:
                # Usually a file still being copied in (the copier holds it locked). Leave it for the
                # next scan rather than indexing a half-written file.
                stats.busy += 1
                log.info("skipped for now (in use / still copying?): %s (%s)", entry.rel, e.strerror or e)
        with Tx(con):
            for root_id, entry, qh in hashed:
                t = now()
                twin = next((g for g in gone_by_size.get(entry.size, [])
                             if g["id"] not in moved_ids and qh and g["quick_hash"] == qh), None)
                if twin:  # same bytes, new place: keep the row (and so its links/watch state)
                    moved_ids.add(twin["id"])
                    stats.moved += 1
                    con.execute("""UPDATE files SET root_id=?, rel_path=?, mtime_ns=?, last_seen=?, available=1,
                                   missing_since=NULL WHERE id=?""", (root_id, entry.rel, entry.mtime_ns, t, twin["id"]))
                    if is_music:
                        relink.append((twin["id"], entry.rel))
                    else:
                        store(twin["id"], entry.path, entry.rel)
                    continue
                stats.added += 1
                fid = con.execute("""INSERT INTO files (library_id, root_id, rel_path, size, mtime_ns, quick_hash,
                                     first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)""",
                                  (lib_id, root_id, entry.rel, entry.size, entry.mtime_ns, qh, t, t)).lastrowid
                if is_music:
                    relink.append((fid, entry.rel))
                else:
                    store(fid, entry.path, entry.rel)
                to_probe.append((fid, entry.path))

    with Tx(con):
        t = now()
        for r in gone:
            if r["id"] not in moved_ids:
                stats.missing += 1
                # Kept, flagged unavailable: the share may just be half-mounted. Never auto-deleted.
                con.execute("UPDATE files SET available=0, missing_since=COALESCE(missing_since, ?) WHERE id=?", (t, r["id"]))
        stats.orphans_removed = items.cleanup_orphans(con, lib_id)

    # Files never probed (new, changed, or ffprobe was missing on an earlier scan).
    if do_probe and probe.ffprobe_path():
        unprobed = con.execute("""SELECT f.id, r.path root, f.rel_path, f.size FROM files f
                                  JOIN library_roots r ON r.id=f.root_id
                                  WHERE f.library_id=? AND f.available=1 AND f.probed_at IS NULL""", (lib_id,)).fetchall()
        to_probe = [(r["id"], Path(r["root"]) / r["rel_path"], r["size"]) for r in unprobed]
        total_bytes, done_bytes, done = sum(s for *_, s in to_probe), 0, 0
        pending: list[tuple[int, dict]] = []

        def save() -> None:  # in batches as results come in: a long probe shows (and keeps) its progress
            with Tx(con):
                t = now()
                for fid, info in pending:
                    stats.probed += 1
                    con.execute("UPDATE files SET probe=?, probed_at=? WHERE id=?", (jdump(info), t, fid))
            pending.clear()

        if to_probe:
            report("Reading file details", 0, len(to_probe), 0, total_bytes)
            with ThreadPoolExecutor(max_workers=8 if is_music else 4) as pool:
                for fid, info, size in pool.map(lambda fp: (fp[0], probe.probe(fp[1]), fp[2]), to_probe):
                    done, done_bytes = done + 1, done_bytes + size
                    report("Reading file details", done, len(to_probe), done_bytes, total_bytes)
                    if info is not None:
                        pending.append((fid, info))
                    if len(pending) >= BATCH:
                        save()
            save()

    if is_music:
        # Now the tags are known (or ffprobe is missing and the folder layout has to do).
        for i in range(0, len(relink), BATCH):
            report("Reading tags", i, len(relink))
            with Tx(con):
                for fid, rel in relink[i:i + BATCH]:
                    row = con.execute("""SELECT f.probe, r.path root FROM files f JOIN library_roots r ON r.id=f.root_id
                                         WHERE f.id=?""", (fid,)).fetchone()
                    store(fid, Path(row["root"]) / rel, rel, jload(row["probe"]))
        with Tx(con):
            stats.orphans_removed += items.cleanup_orphans(con, lib_id)  # albums/artists emptied by re-reads
            music.rollup(con, lib_id)
            playlists.resolve(con, lib_id)  # entries -> tracks, now that every file is linked
    return stats
