"""Library scan: walk -> diff -> parse -> link -> probe. Read-only on the media folders.

Music libraries go walk -> diff -> probe -> parse -> link instead: a track's artist/album/title
come mostly from its tags, which ffprobe reads, so files are linked after they're probed.

Everything a scan learns is written to the database in the data directory; nothing is ever
written next to the media.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import items, library, music, probe, readonly
from .config import AUDIO_EXTS, EXTRAS_DIRS, SKIP_DIRS, VIDEO_EXTS
from .db import Tx, jdump, jload, now
from .parse import PARSER_VERSION, parse

log = logging.getLogger(__name__)
BATCH = 200  # commit every N files so a long scan never holds the write lock for long


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
    roots_offline: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _store_parse(con: sqlite3.Connection, lib_id: int, lib_type: str, file_id: int, rel: str, stats: ScanStats,
                 probe_info: dict | None = None) -> None:
    if lib_type == "music":
        t = music.parse_track(rel, probe_info)
        con.execute("UPDATE files SET parse=? WHERE id=?", (jdump(t.to_dict()), file_id))
        music.link_track(con, lib_id, file_id, t)
        return
    p = parse(rel, lib_type)
    con.execute("UPDATE files SET parse=? WHERE id=?", (jdump(p.to_dict()), file_id))
    if not items.link_file(con, lib_id, file_id, p):
        stats.unrecognized += 1
        log.info("unrecognised: %s", rel)


def scan_library(con: sqlite3.Connection, lib_id: int, *, do_probe: bool = True,
                 progress: Callable[[str], None] | None = None) -> ScanStats:
    lib = library.get(con, lib_id)
    lib_type = lib["type"]
    is_music = lib_type == "music"
    exts, nested_skip = (AUDIO_EXTS, frozenset()) if is_music else (VIDEO_EXTS, EXTRAS_DIRS)
    parser_version = music.PARSER_VERSION if is_music else PARSER_VERSION
    relink: list[tuple[int, str]] = []  # music: (file_id, rel) to parse + link once probed
    stats = ScanStats()
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
            f"{'probe' if is_music else 'NULL AS probe'} FROM files WHERE root_id=?", (root["id"],))}
        if progress:
            progress(f"walking {root_path}")
        pending = 0
        con.execute("BEGIN IMMEDIATE")
        try:
            for entry in readonly.walk(root_path, exts, SKIP_DIRS, nested_skip):
                stats.files_seen += 1
                row = known.get(entry.rel)
                t = now()
                if row is None:
                    new_files.append((root["id"], entry))
                    continue
                seen_ids.add(row["id"])
                if row["size"] == entry.size and row["mtime_ns"] == entry.mtime_ns:
                    con.execute("UPDATE files SET last_seen=?, available=1, missing_since=NULL WHERE id=?", (t, row["id"]))
                    if (row["pv"] or 0) < parser_version:
                        stats.reparsed += 1
                        _store_parse(con, lib_id, lib_type, row["id"], entry.rel, stats, jload(row["probe"]))
                else:
                    stats.changed += 1
                    con.execute("""UPDATE files SET size=?, mtime_ns=?, quick_hash=NULL, probe=NULL, probed_at=NULL,
                                   last_seen=?, available=1, missing_since=NULL WHERE id=?""",
                                (entry.size, entry.mtime_ns, t, row["id"]))
                    if is_music:
                        relink.append((row["id"], entry.rel))  # tags may have changed: re-read after probing
                    else:
                        _store_parse(con, lib_id, lib_type, row["id"], entry.rel, stats)
                    to_probe.append((row["id"], entry.path))
                pending += 1
                if pending >= BATCH:
                    con.execute("COMMIT")
                    con.execute("BEGIN IMMEDIATE")
                    pending = 0
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise

    # Files the DB knows (in online roots) that weren't seen: candidates for "moved" or "missing".
    gone = [r for r in con.execute(
        f"SELECT id, size, quick_hash FROM files WHERE library_id=? AND root_id IN ({','.join('?' * len(online_roots)) or 'NULL'})",
        (lib_id, *online_roots)) if r["id"] not in seen_ids]
    gone_by_size: dict[int, list[sqlite3.Row]] = {}
    for r in gone:
        gone_by_size.setdefault(r["size"], []).append(r)
    moved_ids: set[int] = set()

    if progress and new_files:
        progress(f"adding {len(new_files)} new files")
    for i in range(0, len(new_files), BATCH):
        with Tx(con):
            for root_id, entry in new_files[i:i + BATCH]:
                try:
                    qh = readonly.quick_hash(entry.path, entry.size)
                except OSError as e:
                    # Usually a file still being copied in (the copier holds it locked). Leave it for the
                    # next scan rather than indexing a half-written file.
                    stats.busy += 1
                    log.info("skipped for now (in use / still copying?): %s (%s)", entry.rel, e.strerror or e)
                    continue
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
                        _store_parse(con, lib_id, lib_type, twin["id"], entry.rel, stats)
                    continue
                stats.added += 1
                fid = con.execute("""INSERT INTO files (library_id, root_id, rel_path, size, mtime_ns, quick_hash,
                                     first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)""",
                                  (lib_id, root_id, entry.rel, entry.size, entry.mtime_ns, qh, t, t)).lastrowid
                if is_music:
                    relink.append((fid, entry.rel))
                else:
                    _store_parse(con, lib_id, lib_type, fid, entry.rel, stats)
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
        unprobed = con.execute("""SELECT f.id, r.path root, f.rel_path FROM files f JOIN library_roots r ON r.id=f.root_id
                                  WHERE f.library_id=? AND f.available=1 AND f.probed_at IS NULL""", (lib_id,)).fetchall()
        to_probe = [(r["id"], Path(r["root"]) / r["rel_path"]) for r in unprobed]
        if to_probe:
            if progress:
                progress(f"probing {len(to_probe)} files")
            with ThreadPoolExecutor(max_workers=8 if is_music else 4) as pool:
                results = list(pool.map(lambda fp: (fp[0], probe.probe(fp[1])), to_probe))
            with Tx(con):
                t = now()
                for fid, info in results:
                    if info is not None:
                        stats.probed += 1
                        con.execute("UPDATE files SET probe=?, probed_at=? WHERE id=?", (jdump(info), t, fid))

    if is_music:
        # Now the tags are known (or ffprobe is missing and the folder layout has to do).
        if progress and relink:
            progress(f"reading tags of {len(relink)} tracks")
        for i in range(0, len(relink), BATCH):
            with Tx(con):
                for fid, rel in relink[i:i + BATCH]:
                    row = con.execute("SELECT probe FROM files WHERE id=?", (fid,)).fetchone()
                    _store_parse(con, lib_id, lib_type, fid, rel, stats, jload(row["probe"]))
        with Tx(con):
            stats.orphans_removed += items.cleanup_orphans(con, lib_id)  # albums/artists emptied by re-reads
            music.rollup(con, lib_id)
    return stats
