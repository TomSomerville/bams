"""The item graph: show > season > episode, and movie. Creating, linking files, merging, cleanup."""

from __future__ import annotations

import sqlite3

from .db import now
from .parse import Parsed, title_key


def _insert_item(con: sqlite3.Connection, lib_id: int, kind: str, title: str, **cols) -> int:
    t = now()
    fields = {"library_id": lib_id, "kind": kind, "title": title, "added_at": t, "updated_at": t, **cols}
    keys = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    return con.execute(f"INSERT INTO items ({keys}) VALUES ({marks})", tuple(fields.values())).lastrowid


def get_or_create_title(con: sqlite3.Connection, lib_id: int, kind: str, title: str, year: int | None) -> int:
    """Find the show/movie these files belong to, by normalised title + year, or create it.

    A file without a year joins an existing title with the same name. A file with a year
    adopts a yearless title of the same name, but stays apart from one with a different year
    (remakes and reboots: "Doctor Who (1963)" vs "Doctor Who (2005)").
    """
    key = title_key(title)
    y = year or 0
    rows = con.execute("SELECT item_id, year FROM item_keys WHERE library_id=? AND kind=? AND title_key=?",
                       (lib_id, kind, key)).fetchall()
    exact = [r["item_id"] for r in rows if r["year"] == y]
    if exact:
        return exact[0]
    if y == 0 and rows:
        return rows[0]["item_id"]
    yearless = [r["item_id"] for r in rows if r["year"] == 0]
    if y and yearless:
        item_id = yearless[0]
        con.execute("UPDATE items SET year = COALESCE(year, ?) WHERE id = ?", (year, item_id))
    else:
        item_id = _insert_item(con, lib_id, kind, title, parsed_title=title, title_key=key, year=year)
    con.execute("INSERT OR IGNORE INTO item_keys (library_id, kind, title_key, year, item_id) VALUES (?,?,?,?,?)",
                (lib_id, kind, key, y, item_id))
    return item_id


def season_title(n: int) -> str:
    return "Specials" if n == 0 else f"Season {n}"


def get_or_create_season(con: sqlite3.Connection, lib_id: int, show_id: int, n: int) -> int:
    row = con.execute("SELECT id FROM items WHERE parent_id=? AND kind='season' AND season_number=?",
                      (show_id, n)).fetchone()
    if row:
        return row["id"]
    return _insert_item(con, lib_id, "season", season_title(n), parent_id=show_id, season_number=n)


def get_or_create_episode(con: sqlite3.Connection, lib_id: int, season_id: int, season_n: int, n: int,
                          title: str | None) -> int:
    row = con.execute("SELECT id, match_status FROM items WHERE parent_id=? AND kind='episode' AND episode_number=?",
                      (season_id, n)).fetchone()
    if row:
        if row["match_status"] == "pending":  # title still from the filename: take the (re)parsed one
            con.execute("UPDATE items SET title=?, parsed_title=? WHERE id=?", (title or f"Episode {n}", title, row["id"]))
        return row["id"]
    return _insert_item(con, lib_id, "episode", title or f"Episode {n}", parsed_title=title,
                        parent_id=season_id, season_number=season_n, episode_number=n)


def link_file(con: sqlite3.Connection, lib_id: int, file_id: int, p: Parsed) -> list[int]:
    """(Re)attach a file to the items it contains. Unrecognised files stay indexed but unlinked."""
    con.execute("DELETE FROM file_items WHERE file_id = ?", (file_id,))
    if not p.recognized:
        return []
    if p.kind == "movie":
        targets = [get_or_create_title(con, lib_id, "movie", p.title, p.year)]
    else:
        show = get_or_create_title(con, lib_id, "show", p.title, p.year)
        season = get_or_create_season(con, lib_id, show, p.season)
        targets = [get_or_create_episode(con, lib_id, season, p.season, e, p.episode_title if len(p.episodes) == 1 else None)
                   for e in p.episodes]
    con.executemany("INSERT OR IGNORE INTO file_items (file_id, item_id) VALUES (?, ?)", [(file_id, t) for t in targets])
    return targets


def cleanup_orphans(con: sqlite3.Connection, lib_id: int) -> int:
    """Delete items no file points at any more (episodes/movies/tracks), then empty seasons/albums,
    then empty shows/artists."""
    n = con.execute("""DELETE FROM items WHERE library_id=? AND kind IN ('episode','movie','track')
                       AND id NOT IN (SELECT item_id FROM file_items)""", (lib_id,)).rowcount
    for kinds in ("'season','album'", "'show','artist'"):
        n += con.execute(f"""DELETE FROM items WHERE library_id=? AND kind IN ({kinds})
                             AND id NOT IN (SELECT parent_id FROM items WHERE parent_id IS NOT NULL)""", (lib_id,)).rowcount
    return n


def merge_titles(con: sqlite3.Connection, keep: int, drop: int) -> None:
    """Fold `drop` into `keep` (same TMDB title found under two folder names)."""
    kind = con.execute("SELECT kind FROM items WHERE id=?", (keep,)).fetchone()["kind"]
    con.execute("UPDATE item_keys SET item_id=? WHERE item_id=?", (keep, drop))
    if kind == "movie":
        con.execute("UPDATE OR IGNORE file_items SET item_id=? WHERE item_id=?", (keep, drop))
    else:
        for s in con.execute("SELECT id, season_number FROM items WHERE parent_id=? AND kind='season'", (drop,)).fetchall():
            target = con.execute("SELECT id FROM items WHERE parent_id=? AND kind='season' AND season_number=?",
                                 (keep, s["season_number"])).fetchone()
            if not target:
                con.execute("UPDATE items SET parent_id=? WHERE id=?", (keep, s["id"]))
                continue
            for e in con.execute("SELECT id, episode_number FROM items WHERE parent_id=? AND kind='episode'", (s["id"],)).fetchall():
                te = con.execute("SELECT id FROM items WHERE parent_id=? AND kind='episode' AND episode_number=?",
                                 (target["id"], e["episode_number"])).fetchone()
                if te:
                    con.execute("UPDATE OR IGNORE file_items SET item_id=? WHERE item_id=?", (te["id"], e["id"]))
                else:
                    con.execute("UPDATE items SET parent_id=? WHERE id=?", (target["id"], e["id"]))
    con.execute("DELETE FROM items WHERE id=?", (drop,))
