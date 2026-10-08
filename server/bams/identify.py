"""Identifying files by hand: an admin says what a file is when its name doesn't (Settings → Unrecognized files,
or a library's "Unrecognized" tab).

What they enter is kept in `files.manual` and used instead of the file name from then on, so rescans, file
changes and moves keep it. A pasted TMDB or IMDb link fills the fields in: TMDB links carry the id, IMDb ids
go through TMDB's /find (IMDb itself is never fetched). Nothing here touches the media folders.
"""

from __future__ import annotations

import re
import sqlite3

from . import items
from .db import jdump, jload
from .parse import Parsed, parse
from .tmdb import Tmdb

# themoviedb.org/movie/603-the-matrix · /tv/1399-game-of-thrones · /tv/1399/season/1/episode/2
_TMDB_URL = re.compile(r"themoviedb\.org/(?:[a-z]{2}(?:-[A-Z]{2})?/)?(movie|tv)/(\d+)[^/?#\s]*"
                       r"(?:/season/(\d+)(?:/episode/(\d+))?)?", re.I)
_IMDB_ID = re.compile(r"\b(tt\d{7,9})\b")


class LinkError(ValueError):
    """The link isn't one we can read, or doesn't fit this library."""


def manual_parsed(m: dict, lib_type: str) -> Parsed:
    """The Parsed a hand identification stands for."""
    ids = {"tmdb": str(m["tmdb_id"])} if m.get("tmdb_id") else {}
    if lib_type == "show":
        eps = sorted(set(m.get("episodes") or []))
        return Parsed(kind="episode", title=m["title"], year=m.get("year"), season=m.get("season"), episodes=eps,
                      episode_title=m.get("episode_title"), unnumbered=not eps, ids=ids)
    return Parsed(kind="movie", title=m["title"], year=m.get("year"), edition=m.get("edition"), ids=ids)


def parsed_for(con: sqlite3.Connection, file_id: int, rel: str, lib_type: str) -> Parsed:
    """What a file is: the admin's identification if there is one, else what its path says."""
    row = con.execute("SELECT manual FROM files WHERE id=?", (file_id,)).fetchone()
    m = jload(row["manual"]) if row else None
    return manual_parsed(m, lib_type) if m else parse(rel, lib_type)


def store(con: sqlite3.Connection, file_id: int, manual: dict | None) -> list[int]:
    """Save (or with None, clear) a file's identification and re-place it. Call inside a transaction.
    Returns the movie/episode items the file now belongs to (empty: unrecognised again)."""
    f = con.execute("""SELECT f.id, f.rel_path, f.library_id, l.type FROM files f JOIN libraries l ON l.id=f.library_id
                       WHERE f.id=?""", (file_id,)).fetchone()
    con.execute("UPDATE files SET manual=? WHERE id=?", (jdump(manual) if manual else None, file_id))
    p = manual_parsed(manual, f["type"]) if manual else parse(f["rel_path"], f["type"])
    con.execute("UPDATE files SET parse=? WHERE id=?", (jdump({**p.to_dict(), "manual": bool(manual)}), file_id))
    targets = items.link_file(con, f["library_id"], file_id, p)
    items.cleanup_orphans(con, f["library_id"])
    return targets


def title_of(con: sqlite3.Connection, item_id: int) -> int:
    """The show (for an episode) or the movie itself."""
    r = con.execute("SELECT kind, parent_id FROM items WHERE id=?", (item_id,)).fetchone()
    if r["kind"] == "episode":
        return con.execute("SELECT parent_id FROM items WHERE id=?", (r["parent_id"],)).fetchone()["parent_id"]
    return item_id


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and date[:4].isdigit() else None


def lookup(tmdb: Tmdb, text: str, lib_type: str) -> dict:
    """Fields for the identify form from a pasted TMDB or IMDb link (or a bare tt… id)."""
    season = episode = None
    if m := _TMDB_URL.search(text):
        kind, tid = ("movie" if m.group(1).lower() == "movie" else "tv"), int(m.group(2))
        season = int(m.group(3)) if m.group(3) else None
        episode = int(m.group(4)) if m.group(4) else None
    elif m := _IMDB_ID.search(text):
        found = tmdb.find(m.group(1), "imdb_id")
        if hit := (found.get("tv_episode_results") or [None])[0]:
            kind, tid, season, episode = "tv", hit["show_id"], hit.get("season_number"), hit.get("episode_number")
        elif hit := (found.get("tv_results") or [None])[0]:
            kind, tid = "tv", hit["id"]
        elif hit := (found.get("movie_results") or [None])[0]:
            kind, tid = "movie", hit["id"]
        else:
            raise LinkError(f"TMDB doesn't know IMDb title {m.group(1)}.")
    else:
        raise LinkError("Paste a TMDB link (themoviedb.org/movie/… or /tv/…) or an IMDb link (imdb.com/title/tt…).")

    if kind == "movie" and lib_type == "show":
        raise LinkError("That link is a movie, but this is a TV library.")
    if kind == "tv" and lib_type == "movie":
        raise LinkError("That link is a TV show, but this is a Movies library.")
    if kind == "movie":
        d = tmdb.movie(tid)
        return {"tmdb_id": tid, "title": d.get("title"), "year": _year(d.get("release_date"))}
    d = tmdb.tv(tid)
    out = {"tmdb_id": tid, "title": d.get("name"), "year": _year(d.get("first_air_date")),
           "season": season, "episodes": [episode] if episode is not None else [], "episode_title": None}
    if season is not None and episode is not None:
        sd = tmdb.season(tid, season)
        out["episode_title"] = next((e.get("name") for e in sd.get("episodes", []) if e.get("episode_number") == episode), None)
    return out


def names(con: sqlite3.Connection, lib_id: int, lib_type: str) -> list[dict]:
    """Everything already in a library that the identify form can suggest: shows with their seasons and
    episodes, or movies."""
    if lib_type == "movie":
        return [{"title": r["title"], "year": r["year"]} for r in con.execute(
            "SELECT title, year FROM items WHERE library_id=? AND kind='movie' ORDER BY title COLLATE NOCASE", (lib_id,))]
    shows: dict[int, dict] = {}
    for r in con.execute("SELECT id, title, year FROM items WHERE library_id=? AND kind='show' ORDER BY title COLLATE NOCASE",
                         (lib_id,)):
        shows[r["id"]] = {"title": r["title"], "year": r["year"], "seasons": {}}
    for r in con.execute("""SELECT s.parent_id AS show, s.season_number AS season, e.episode_number AS n, e.title
                            FROM items e JOIN items s ON s.id=e.parent_id
                            WHERE e.library_id=? AND e.kind='episode'
                            ORDER BY s.season_number, e.episode_number IS NULL, e.episode_number""", (lib_id,)):
        if r["show"] in shows:
            shows[r["show"]]["seasons"].setdefault(r["season"], []).append({"n": r["n"], "title": r["title"]})
    return [{**s, "seasons": [{"season": n, "episodes": eps} for n, eps in s["seasons"].items()]} for s in shows.values()]
