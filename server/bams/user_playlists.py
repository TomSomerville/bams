"""Playlists people make in BAMS (owner 2026-10-13), as opposed to the ones imported from playlist files
(playlists.py), which stay read-only because media folders are.

Each belongs to one account and only that account sees it (owner's choice: personal and private). It holds tracks
in a chosen order: adding an album or an artist adds its tracks as they are now (later additions to the album
don't follow), a track already in the playlist isn't added twice. A track whose file goes from the library leaves
the playlist with it (foreign key cascade). "Make a copy" of an imported playlist makes one of these.
"""

from __future__ import annotations

import sqlite3

from .db import Tx, now

NAME_MAX = 100
DESCRIPTION_MAX = 500


class PlaylistError(ValueError):
    """Shown to the person: a missing name, an item that isn't music."""


def _name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise PlaylistError("Give the playlist a name.")
    return name[:NAME_MAX]


def _description(text: str | None) -> str:
    return (text or "").strip()[:DESCRIPTION_MAX]


def get(con: sqlite3.Connection, user_id: int, playlist_id: int) -> sqlite3.Row | None:
    """The playlist if it's this account's (someone else's is as good as missing)."""
    return con.execute("SELECT * FROM user_playlists WHERE id=? AND user_id=?", (playlist_id, user_id)).fetchone()


def all_of(con: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM user_playlists WHERE user_id=? ORDER BY name COLLATE NOCASE, id",
                       (user_id,)).fetchall()


def track_ids(con: sqlite3.Connection, item_id: int) -> list[int]:
    """The tracks an item stands for, in play order: an artist's (album by album), an album's, or the track."""
    r = con.execute("SELECT kind FROM items WHERE id=?", (item_id,)).fetchone()
    if not r or r["kind"] not in ("artist", "album", "track"):
        raise PlaylistError("Only songs, albums and artists can go in a playlist.")
    where = {"track": "t.id=?", "album": "al.id=?", "artist": "ar.id=?"}[r["kind"]]
    return [x[0] for x in con.execute(f"""
        SELECT t.id FROM items t JOIN items al ON al.id=t.parent_id JOIN items ar ON ar.id=al.parent_id
        WHERE t.kind='track' AND {where}
        ORDER BY al.year IS NULL, al.year, al.title COLLATE NOCASE, COALESCE(t.disc_number, 1),
                 t.track_number IS NULL, t.track_number, t.title COLLATE NOCASE""", (item_id,))]


def items(con: sqlite3.Connection, playlist_id: int) -> list[int]:
    return [x[0] for x in con.execute(
        "SELECT item_id FROM user_playlist_items WHERE playlist_id=? ORDER BY position", (playlist_id,))]


def create(con: sqlite3.Connection, user_id: int, name: str, description: str | None = None,
           tracks: list[int] | None = None) -> int:
    t = now()
    with Tx(con):
        pid = con.execute("INSERT INTO user_playlists(user_id, name, description, created_at, updated_at) "
                          "VALUES (?,?,?,?,?)", (user_id, _name(name), _description(description), t, t)).lastrowid
        _write(con, pid, list(dict.fromkeys(tracks or [])), t)
    return pid


def update(con: sqlite3.Connection, playlist_id: int, name: str | None = None, description: str | None = None) -> None:
    sets, args = [], []
    if name is not None:
        sets.append("name=?")
        args.append(_name(name))
    if description is not None:
        sets.append("description=?")
        args.append(_description(description))
    if sets:
        con.execute(f"UPDATE user_playlists SET {', '.join(sets)}, updated_at=? WHERE id=?", (*args, now(), playlist_id))


def add(con: sqlite3.Connection, playlist_id: int, item_ids: list[int]) -> tuple[int, int]:
    """Add songs, albums or artists at the end. Returns (tracks added, tracks that were in it already)."""
    wanted: list[int] = []
    for i in item_ids:
        wanted += track_ids(con, i)
    with Tx(con):
        have = items(con, playlist_id)
        seen = set(have)
        new = [t for t in dict.fromkeys(wanted) if t not in seen]
        _write(con, playlist_id, have + new, now())
    return len(new), len(set(wanted)) - len(new)


def set_tracks(con: sqlite3.Connection, playlist_id: int, track_ids_: list[int]) -> None:
    """The playlist's tracks as given (reordered, some taken out). Only tracks it already had: nothing gets in
    this way (adding goes through `add`, which checks they're music)."""
    with Tx(con):
        have = set(items(con, playlist_id))
        _write(con, playlist_id, [t for t in dict.fromkeys(track_ids_) if t in have], now())


def delete(con: sqlite3.Connection, playlist_id: int) -> None:
    con.execute("DELETE FROM user_playlists WHERE id=?", (playlist_id,))


def _write(con: sqlite3.Connection, playlist_id: int, tracks: list[int], t: float) -> None:
    added = {r[0]: r[1] for r in con.execute(
        "SELECT item_id, added_at FROM user_playlist_items WHERE playlist_id=?", (playlist_id,))}
    con.execute("DELETE FROM user_playlist_items WHERE playlist_id=?", (playlist_id,))
    con.executemany("INSERT INTO user_playlist_items(playlist_id, position, item_id, added_at) VALUES (?,?,?,?)",
                    [(playlist_id, n, i, added.get(i, t)) for n, i in enumerate(tracks)])
    con.execute("UPDATE user_playlists SET updated_at=? WHERE id=?", (t, playlist_id))
