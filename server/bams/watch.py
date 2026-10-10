"""Each user's watch state: where they stopped in a movie/episode, what they've watched, what's next.

Positions are reported by the player while it plays (`record_progress`). Past the "watched at" share of the
running time (an admin setting, 90% by default) a title counts as watched and its position goes back to 0 (like Plex). Shows and seasons have no state of their
own: they're summed up from their episodes.
"""

from __future__ import annotations

import sqlite3

from .db import Tx, get_setting, now

WATCHED_PERCENT = 90   # default: share of the running time after which a title counts as watched
RESUME_AFTER = 30      # default: seconds watched before a title is "started" (saved, in Continue Watching)


def thresholds(con: sqlite3.Connection) -> dict:
    """The admin's watch settings: `watched_percent` (50-100) and `resume_after` (seconds)."""
    def num(key: str, default: int) -> int:
        try:
            return int(get_setting(con, key) or default)
        except ValueError:
            return default
    return {"watched_percent": num("watched_percent", WATCHED_PERCENT), "resume_after": num("resume_after", RESUME_AFTER)}
PLAYABLE = ("movie", "episode")


def record_progress(con: sqlite3.Connection, user_id: int, item_id: int, position: float,
                    duration: float | None) -> dict:
    """The player is at `position` seconds of `duration`. Returns the item's new state."""
    t = now()
    th = thresholds(con)
    prev = con.execute("SELECT * FROM watch_state WHERE user_id=? AND item_id=?", (user_id, item_id)).fetchone()
    finished = bool(duration and duration > 0 and position >= duration * th["watched_percent"] / 100)
    with Tx(con):
        if finished:
            # count a viewing once: a finished title stays at 0 while the credits keep reporting progress,
            # but a re-watch (position moved past 0 again) counts again
            again = prev is None or not prev["watched"] or prev["position"] > 0
            con.execute("""INSERT INTO watch_state(user_id, item_id, position, duration, watched, play_count,
                               last_watched_at, updated_at) VALUES (?,?,0,?,1,1,?,?)
                           ON CONFLICT(user_id, item_id) DO UPDATE SET position=0, duration=excluded.duration,
                               watched=1, play_count=play_count+?, last_watched_at=CASE WHEN ? THEN excluded.last_watched_at
                               ELSE last_watched_at END, updated_at=excluded.updated_at""",
                        (user_id, item_id, duration, t, t, int(again), int(again)))
        else:
            pos = position if position >= max(th["resume_after"], 1) else 0.0
            con.execute("""INSERT INTO watch_state(user_id, item_id, position, duration, updated_at)
                           VALUES (?,?,?,?,?)
                           ON CONFLICT(user_id, item_id) DO UPDATE SET position=excluded.position,
                               duration=COALESCE(excluded.duration, duration), updated_at=excluded.updated_at""",
                        (user_id, item_id, pos, duration, t))
    return state(con, user_id, item_id)


def episodes_under(con: sqlite3.Connection, item_id: int) -> list[int]:
    """The movie/episode itself, or every episode of a season or show."""
    r = con.execute("SELECT kind FROM items WHERE id=?", (item_id,)).fetchone()
    if not r:
        return []
    if r["kind"] in PLAYABLE:
        return [item_id]
    if r["kind"] == "season":
        return [x[0] for x in con.execute("SELECT id FROM items WHERE parent_id=? AND kind='episode'", (item_id,))]
    if r["kind"] == "show":
        return [x[0] for x in con.execute("""SELECT e.id FROM items e JOIN items s ON s.id=e.parent_id
                                             WHERE s.parent_id=? AND e.kind='episode'""", (item_id,))]
    return []


def set_watched(con: sqlite3.Connection, user_id: int, item_id: int, watched: bool) -> int:
    """Mark a movie/episode, or every episode of a season/show, watched or unwatched. Returns how many."""
    ids = episodes_under(con, item_id)
    t = now()
    with Tx(con):
        for i in ids:
            if watched:
                con.execute("""INSERT INTO watch_state(user_id, item_id, position, watched, play_count, last_watched_at,
                                   updated_at) VALUES (?,?,0,1,1,?,?)
                               ON CONFLICT(user_id, item_id) DO UPDATE SET position=0, watched=1,
                                   play_count=MAX(play_count, 1), last_watched_at=COALESCE(last_watched_at, excluded.last_watched_at),
                                   updated_at=excluded.updated_at""", (user_id, i, t, t))
            else:
                con.execute("DELETE FROM watch_state WHERE user_id=? AND item_id=?", (user_id, i))
    return len(ids)


def state(con: sqlite3.Connection, user_id: int, item_id: int) -> dict:
    r = con.execute("SELECT position, duration, watched FROM watch_state WHERE user_id=? AND item_id=?",
                    (user_id, item_id)).fetchone()
    return _state(r)


def _state(r) -> dict:
    if not r:
        return {"position": 0.0, "duration": None, "watched": False}
    return {"position": r["position"], "duration": r["duration"], "watched": bool(r["watched"])}


def annotate(con: sqlite3.Connection, user_id: int | None, items: list[dict]) -> list[dict]:
    """Add the user's state to serialised items: `progress` on movies/episodes; `episodes` / `unwatched`
    counts on shows and seasons. Batched: one query per kind, whatever the number of items."""
    if user_id is None or not items:
        return items
    playable = [d["id"] for d in items if d["kind"] in PLAYABLE]
    if playable:
        rows = {r["item_id"]: r for r in _in(con, "SELECT item_id, position, duration, watched FROM watch_state "
                                              "WHERE user_id=? AND item_id IN ({})", [user_id], playable)}
        for d in items:
            if d["kind"] in PLAYABLE:
                d["progress"] = _state(rows.get(d["id"]))
    for kind, sql in (
        ("season", """SELECT e.parent_id AS id, COUNT(*) AS n, COUNT(w.item_id) AS seen FROM items e
                      LEFT JOIN watch_state w ON w.item_id=e.id AND w.user_id=? AND w.watched=1
                      WHERE e.kind='episode' AND e.parent_id IN ({}) GROUP BY e.parent_id"""),
        ("show", """SELECT s.parent_id AS id, COUNT(*) AS n, COUNT(w.item_id) AS seen FROM items e
                    JOIN items s ON s.id=e.parent_id
                    LEFT JOIN watch_state w ON w.item_id=e.id AND w.user_id=? AND w.watched=1
                    WHERE e.kind='episode' AND s.parent_id IN ({}) GROUP BY s.parent_id"""),
    ):
        ids = [d["id"] for d in items if d["kind"] == kind]
        if not ids:
            continue
        counts = {r["id"]: (r["n"], r["seen"]) for r in _in(con, sql, [user_id], ids)}
        for d in items:
            if d["kind"] == kind:
                n, seen = counts.get(d["id"], (0, 0))
                d["episodes"], d["unwatched"] = n, n - seen
    return items


def _in(con: sqlite3.Connection, sql: str, args: list, ids: list[int]):
    out = []
    for i in range(0, len(ids), 500):  # SQLite caps bound parameters
        chunk = ids[i:i + 500]
        out += con.execute(sql.format(",".join("?" * len(chunk))), (*args, *chunk)).fetchall()
    return out


# ------------------------------------------------------------------ what to watch next

_EPISODE_ORDER = "s.season_number = 0, s.season_number, e.episode_number"  # specials last


def next_episode(con: sqlite3.Connection, episode_id: int) -> int | None:
    """The episode after this one in the show (season by season, specials only after a special)."""
    e = con.execute("""SELECT e.episode_number, s.season_number, s.parent_id AS show FROM items e
                       JOIN items s ON s.id=e.parent_id WHERE e.id=? AND e.kind='episode'""", (episode_id,)).fetchone()
    if not e:
        return None
    r = con.execute(f"""SELECT e.id FROM items e JOIN items s ON s.id=e.parent_id
                        WHERE s.parent_id=? AND e.kind='episode' AND (s.season_number=0) = (?=0)
                          AND (s.season_number > ? OR (s.season_number = ? AND e.episode_number > ?))
                          AND EXISTS (SELECT 1 FROM file_items fi JOIN files f ON f.id=fi.file_id
                                      WHERE fi.item_id=e.id AND f.available=1)
                        ORDER BY {_EPISODE_ORDER} LIMIT 1""",
                    (e["show"], e["season_number"], e["season_number"], e["season_number"],
                     e["episode_number"])).fetchone()
    return r["id"] if r else None


def continue_watching(con: sqlite3.Connection, user_id: int, limit: int = 20) -> list[tuple[int, str]]:
    """(item id, why) pairs, most recent first: titles stopped part-way ("resume"), and for shows whose last
    watched episode was finished, the next unwatched one ("next")."""
    recent = con.execute("""
        SELECT w.item_id, w.position, w.watched, w.updated_at, i.kind,
               (SELECT s.parent_id FROM items s WHERE s.id=i.parent_id) AS show
        FROM watch_state w JOIN items i ON i.id=w.item_id
        WHERE w.user_id=? ORDER BY w.updated_at DESC LIMIT 400""", (user_id,)).fetchall()
    out: list[tuple[int, str]] = []
    shows_done: set[int] = set()
    min_resume = max(thresholds(con)["resume_after"], 1)
    for r in recent:
        if len(out) >= limit:
            break
        if r["kind"] == "movie":
            if not r["watched"] and r["position"] >= min_resume:
                out.append((r["item_id"], "resume"))
            continue
        show = r["show"]
        if show in shows_done:
            continue
        if not r["watched"] and r["position"] < min_resume:
            continue  # opened but not really watched (or a play that failed): says nothing about where you are
        shows_done.add(show)  # only the most recent activity of a show decides what it offers
        if not r["watched"] and r["position"] >= min_resume:
            out.append((r["item_id"], "resume"))
            continue
        if not r["watched"]:
            continue
        nxt = r["item_id"]
        while (nxt := next_episode(con, nxt)) is not None:
            w = con.execute("SELECT watched FROM watch_state WHERE user_id=? AND item_id=?", (user_id, nxt)).fetchone()
            if not w or not w["watched"]:
                out.append((nxt, "next"))
                break
    return out
