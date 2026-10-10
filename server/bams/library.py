"""Libraries and their root folders. Shared by the API and the CLI."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import readonly
from .db import Tx, now

TYPES = ("movie", "show", "music")


class LibraryError(ValueError):
    pass


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def _overlaps(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return a == b or a.startswith(b.rstrip("\\/") + os.sep) or b.startswith(a.rstrip("\\/") + os.sep)


def validate_root(path: str, data_dir: Path, other_roots: list[str]) -> str:
    if not path or not os.path.isabs(path):
        raise LibraryError(f"folder must be an absolute path: {path!r}")
    p = os.path.abspath(path)
    st = readonly.root_status(Path(p))
    if not st["exists"]:
        raise LibraryError(f"folder not found (or not mounted): {p}")
    if not st["readable"]:
        raise LibraryError(f"BAMS can't list this folder; give its account read access: {p}")
    if _overlaps(p, str(data_dir)):
        raise LibraryError(f"media folder and BAMS data folder ({data_dir}) can't contain each other: {p}")
    for o in other_roots:
        if _overlaps(p, o):
            raise LibraryError(f"overlaps a folder already in a library ({o}): {p}")
    return p


def all_roots(con: sqlite3.Connection) -> list[str]:
    return [r["path"] for r in con.execute("SELECT path FROM library_roots")]


def refresh_guard(con: sqlite3.Connection) -> None:
    """Tell the read-only guard which folders are media folders."""
    readonly.set_protected_roots(all_roots(con))


def get(con: sqlite3.Connection, ref: int | str) -> sqlite3.Row:
    row = (con.execute("SELECT * FROM libraries WHERE id=?", (int(ref),)).fetchone()
           if str(ref).isdigit() else
           con.execute("SELECT * FROM libraries WHERE name=? COLLATE NOCASE", (str(ref),)).fetchone())
    if not row:
        raise LibraryError(f"no library {ref!r}")
    return row


def roots(con: sqlite3.Connection, lib_id: int) -> list[sqlite3.Row]:
    return con.execute("SELECT id, path FROM library_roots WHERE library_id=? ORDER BY id", (lib_id,)).fetchall()


# How libraries are listed everywhere (sidebar, Home, Settings, CLI): the admin's order, new ones last.
ORDER = "sort_order IS NULL, sort_order, name COLLATE NOCASE"


def listed(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(f"SELECT * FROM libraries ORDER BY {ORDER}").fetchall()


def reorder(con: sqlite3.Connection, ids: list[int]) -> None:
    """Put libraries in this order. Ids left out keep their order after the ones given; unknown ids are ignored."""
    current = [r["id"] for r in listed(con)]
    order = [i for i in dict.fromkeys(ids) if i in current] + [i for i in current if i not in ids]
    with Tx(con):
        con.executemany("UPDATE libraries SET sort_order=? WHERE id=?", list(enumerate(order)))


def create(con: sqlite3.Connection, data_dir: Path, name: str, type_: str, paths: list[str],
           scan_interval_hours: float = 6) -> int:
    name = name.strip()
    if not name:
        raise LibraryError("library needs a name")
    if type_ not in TYPES:
        raise LibraryError(f"type must be one of {', '.join(TYPES)}")
    if not paths:
        raise LibraryError("add at least one folder")
    if not 0.25 <= scan_interval_hours <= 24 * 7:
        raise LibraryError("scan interval must be between 0.25 and 168 hours")
    if con.execute("SELECT 1 FROM libraries WHERE name=? COLLATE NOCASE", (name,)).fetchone():
        raise LibraryError(f"a library called {name!r} already exists")
    existing = all_roots(con)
    clean: list[str] = []
    for p in paths:
        clean.append(validate_root(p, data_dir, existing + clean))
    with Tx(con):
        last = con.execute("SELECT COALESCE(MAX(sort_order), -1) FROM libraries").fetchone()[0]
        lib_id = con.execute("""INSERT INTO libraries (name, type, scan_interval_hours, created_at, sort_order)
                                VALUES (?,?,?,?,?)""", (name, type_, scan_interval_hours, now(), last + 1)).lastrowid
        con.executemany("INSERT INTO library_roots (library_id, path) VALUES (?, ?)", [(lib_id, p) for p in clean])
    refresh_guard(con)
    return lib_id


def update(con: sqlite3.Connection, data_dir: Path, lib_id: int, *, name: str | None = None,
           scan_interval_hours: float | None = None, add_paths: list[str] | None = None,
           remove_paths: list[str] | None = None) -> None:
    get(con, lib_id)
    with Tx(con):
        if name is not None:
            con.execute("UPDATE libraries SET name=? WHERE id=?", (name.strip(), lib_id))
        if scan_interval_hours is not None:
            if not 0.25 <= scan_interval_hours <= 24 * 7:
                raise LibraryError("scan interval must be between 0.25 and 168 hours")
            con.execute("UPDATE libraries SET scan_interval_hours=? WHERE id=?", (scan_interval_hours, lib_id))
        for p in remove_paths or []:
            con.execute("DELETE FROM library_roots WHERE library_id=? AND path=?", (lib_id, p))
        for p in add_paths or []:
            clean = validate_root(p, data_dir, all_roots(con))
            con.execute("INSERT INTO library_roots (library_id, path) VALUES (?, ?)", (lib_id, clean))
    refresh_guard(con)


def delete(con: sqlite3.Connection, lib_id: int) -> None:
    """Forget a library. Only BAMS's own records are removed; the media files are never touched."""
    get(con, lib_id)
    con.execute("DELETE FROM libraries WHERE id=?", (lib_id,))
    refresh_guard(con)


def describe(con: sqlite3.Connection, row: sqlite3.Row) -> dict:
    lib_id = row["id"]
    counts = {r["kind"]: r["n"] for r in con.execute(
        "SELECT kind, COUNT(*) n FROM items WHERE library_id=? GROUP BY kind", (lib_id,))}
    files = con.execute("SELECT COUNT(*) n, SUM(available) a, COALESCE(SUM(size),0) s FROM files WHERE library_id=?",
                        (lib_id,)).fetchone()
    unrecognized = con.execute("""SELECT COUNT(*) FROM files WHERE library_id=? AND id NOT IN (SELECT file_id FROM file_items)
                                  AND json_extract(manual, '$.skip') IS NULL""",  # left out on purpose: not to do
                               (lib_id,)).fetchone()[0]
    guessed = con.execute("SELECT COUNT(*) FROM files WHERE library_id=? AND manual IS NULL AND json_extract(parse, '$.guessed')",
                          (lib_id,)).fetchone()[0]  # placed by auto fill: to review
    return {
        "id": lib_id, "name": row["name"], "type": row["type"],
        "scan_interval_hours": row["scan_interval_hours"],
        "last_scan_at": row["last_scan_at"], "last_scan_status": row["last_scan_status"],
        "roots": [{"path": r["path"], **readonly.root_status(Path(r["path"]))} for r in roots(con, lib_id)],
        "counts": counts,
        "files": {"total": files["n"], "available": files["a"] or 0, "bytes": files["s"], "unrecognized": unrecognized,
                  "guessed": guessed},
    }
