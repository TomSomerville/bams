"""Identify shows/movies on TMDB and pull their metadata and artwork into the data directory.

Order of preference for each title:
  1. an explicit id in the path ({tmdb-123}, {imdb-tt...}, {tvdb-...})
  2. a TMDB search on the parsed title + year, accepted only above a confidence threshold
Below the threshold the title is marked 'unmatched' (visible in the API) rather than guessed.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from . import items
from .db import Tx, jdump, jload, now
from .parse import title_key
from .tmdb import InvalidKey, Tmdb, TmdbError

log = logging.getLogger(__name__)

ACCEPT = 0.80
REFRESH_AFTER = 150 * 86400  # TMDB terms: cached data no older than 6 months; refresh at ~5
POSTER, BACKDROP, STILL, SEASON_POSTER = "w500", "w1280", "w300", "w342"


@dataclass
class MatchStats:
    matched: int = 0
    unmatched: int = 0
    refreshed: int = 0
    merged: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and date[:4].isdigit() else None


def score(query: str, year: int | None, names: list[str], result_year: int | None, rank: int) -> float:
    q = title_key(query)
    sim = max((SequenceMatcher(None, q, title_key(n)).ratio() for n in names if n), default=0.0)
    s = sim
    if year and result_year:
        if year == result_year:
            s += 0.15
        elif abs(year - result_year) > 1:
            s -= 0.25
    return s - 0.01 * rank  # TMDB already orders by relevance/popularity


def best_match(results: list[dict], query: str, year: int | None, kind: str) -> tuple[dict | None, float]:
    best, best_s = None, 0.0
    for rank, r in enumerate(results[:10]):
        if kind == "show":
            names, ry = [r.get("name"), r.get("original_name")], _year(r.get("first_air_date"))
        else:
            names, ry = [r.get("title"), r.get("original_title")], _year(r.get("release_date"))
        s = score(query, year, names, ry, rank)
        if s > best_s:
            best, best_s = r, s
    return best, best_s


def _path_ids(con: sqlite3.Connection, item_id: int, kind: str) -> dict[str, str]:
    """Id hints from the paths of any file under this show/movie."""
    if kind == "movie":
        q = "SELECT f.parse FROM files f JOIN file_items fi ON fi.file_id=f.id WHERE fi.item_id=?"
    else:
        q = """SELECT f.parse FROM files f JOIN file_items fi ON fi.file_id=f.id JOIN items e ON e.id=fi.item_id
               JOIN items s ON s.id=e.parent_id WHERE s.parent_id=?"""
    for (p,) in con.execute(q, (item_id,)):
        ids = (jload(p) or {}).get("ids") or {}
        if ids:
            return ids
    return {}


def _resolve_id(tmdb: Tmdb, ids: dict[str, str], kind: str) -> int | None:
    if "tmdb" in ids:
        return int(ids["tmdb"])
    key = "tv_results" if kind == "show" else "movie_results"
    for src, val in (("imdb", "imdb_id"), ("tvdb", "tvdb_id")):
        if src in ids:
            try:
                hits = tmdb.find(ids[src], val).get(key) or []
            except TmdbError:
                continue
            if hits:
                return hits[0]["id"]
    return None


def _fetch_title_images(tmdb: Tmdb, images: Path, d: dict) -> dict:
    """Network first, outside any DB transaction."""
    d["_poster"] = tmdb.image(d.get("poster_path"), POSTER, images)
    d["_backdrop"] = tmdb.image(d.get("backdrop_path"), BACKDROP, images)
    return d


def _apply_title(con: sqlite3.Connection, item_id: int, kind: str, d: dict, status: str, s: float | None) -> None:
    ext = d.get("external_ids") or {}
    con.execute("""UPDATE items SET title=?, year=?, overview=?, tagline=?, genres=?, rating=?, runtime=?, air_date=?,
                   tmdb_id=?, imdb_id=?, tvdb_id=?, poster=?, backdrop=?, match_status=?, match_score=?,
                   metadata_at=?, updated_at=? WHERE id=?""", (
        d.get("name") if kind == "show" else d.get("title"),
        _year(d.get("first_air_date") if kind == "show" else d.get("release_date")),
        d.get("overview") or None, d.get("tagline") or None,
        jdump([g["name"] for g in d.get("genres", [])]),
        d.get("vote_average") or None,
        d.get("runtime") or (d.get("episode_run_time") or [None])[0],
        d.get("first_air_date") if kind == "show" else d.get("release_date"),
        d["id"], ext.get("imdb_id") or d.get("imdb_id"), ext.get("tvdb_id"),
        d.get("_poster"), d.get("_backdrop"), status, s, now(), now(), item_id))


def _apply_seasons(con: sqlite3.Connection, tmdb: Tmdb, images: Path, show_id: int, tv_id: int,
                   only_stale: bool) -> None:
    """Per season: fetch from TMDB (and download art) first, then one short transaction."""
    for season in con.execute("SELECT id, season_number, metadata_at FROM items WHERE parent_id=? AND kind='season'",
                              (show_id,)).fetchall():
        pending_eps = con.execute("SELECT 1 FROM items WHERE parent_id=? AND kind='episode' AND match_status='pending'",
                                  (season["id"],)).fetchone()
        stale = not season["metadata_at"] or now() - season["metadata_at"] > REFRESH_AFTER
        if only_stale and not (stale or pending_eps):
            continue
        try:
            sd = tmdb.season(tv_id, season["season_number"])
        except TmdbError as e:
            log.info("no TMDB season %s for tv %s: %s", season["season_number"], tv_id, e)
            continue
        local = con.execute("SELECT id, episode_number FROM items WHERE parent_id=? AND kind='episode'",
                            (season["id"],)).fetchall()
        by_num = {e["episode_number"]: e for e in sd.get("episodes", [])}
        season_poster = tmdb.image(sd.get("poster_path"), SEASON_POSTER, images)
        stills = {ep["id"]: tmdb.image(by_num[ep["episode_number"]].get("still_path"), STILL, images)
                  for ep in local if ep["episode_number"] in by_num}
        with Tx(con):
            con.execute("""UPDATE items SET title=?, overview=?, air_date=?, poster=?, tmdb_id=?, match_status='matched',
                           metadata_at=?, updated_at=? WHERE id=?""", (
                sd.get("name") or items.season_title(season["season_number"]), sd.get("overview") or None,
                sd.get("air_date"), season_poster, sd.get("id"), now(), now(), season["id"]))
            for ep in local:
                e = by_num.get(ep["episode_number"])
                if not e:
                    con.execute("UPDATE items SET match_status='unmatched', updated_at=? WHERE id=?", (now(), ep["id"]))
                    continue
                con.execute("""UPDATE items SET title=?, overview=?, air_date=?, runtime=?, rating=?, still=?, tmdb_id=?,
                               match_status='matched', metadata_at=?, updated_at=? WHERE id=?""", (
                    e.get("name") or f"Episode {ep['episode_number']}", e.get("overview") or None, e.get("air_date"),
                    e.get("runtime"), e.get("vote_average") or None, stills.get(ep["id"]),
                    e.get("id"), now(), now(), ep["id"]))


def _merge_duplicate(con: sqlite3.Connection, lib_id: int, kind: str, item_id: int, tmdb_id: int) -> int:
    """If another title in the library already has this TMDB id, fold this one into it."""
    other = con.execute("SELECT id FROM items WHERE library_id=? AND kind=? AND tmdb_id=? AND id<>? ORDER BY id LIMIT 1",
                        (lib_id, kind, tmdb_id, item_id)).fetchone()
    if not other:
        return item_id
    items.merge_titles(con, other["id"], item_id)
    return other["id"]


def match_title(con: sqlite3.Connection, tmdb: Tmdb, images: Path, item_id: int, *, tmdb_id: int | None = None,
                manual: bool = False) -> bool:
    """Match (or re-match) one show/movie. Returns True if matched."""
    it = con.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    kind, lib_id = it["kind"], it["library_id"]
    query, year = it["parsed_title"] or it["title"], it["year"]
    s: float | None = 1.0
    if tmdb_id is None:
        tmdb_id = _resolve_id(tmdb, _path_ids(con, item_id, kind), kind)
    if tmdb_id is None:
        search = tmdb.search_tv if kind == "show" else tmdb.search_movie
        results = search(query, year) or (search(query) if year else [])
        best, s = best_match(results, query, year, kind)
        if not best or s < ACCEPT:
            with Tx(con):
                con.execute("UPDATE items SET match_status='unmatched', match_score=?, updated_at=? WHERE id=?",
                            (s if best else None, now(), item_id))
            log.info("no confident TMDB match for %s %r (%s), best score %.2f", kind, query, year, s or 0)
            return False
        tmdb_id = best["id"]
    d = _fetch_title_images(tmdb, images, tmdb.tv(tmdb_id) if kind == "show" else tmdb.movie(tmdb_id))
    with Tx(con):
        _apply_title(con, item_id, kind, d, "manual" if manual else "matched", s)
        keep = _merge_duplicate(con, lib_id, kind, item_id, tmdb_id)
    if kind == "show":
        _apply_seasons(con, tmdb, images, keep, tmdb_id, only_stale=False)
    log.info("matched %s %r -> TMDB %s %r", kind, query, tmdb_id, d.get("name") or d.get("title"))
    return True


def match_library(con: sqlite3.Connection, tmdb: Tmdb, images: Path, lib_id: int, *, retry_unmatched: bool = False,
                  progress=None) -> MatchStats:
    stats = MatchStats()
    statuses = ("pending", "unmatched") if retry_unmatched else ("pending",)
    todo = con.execute(f"""SELECT id FROM items WHERE library_id=? AND kind IN ('show','movie')
                           AND match_status IN ({','.join('?' * len(statuses))}) ORDER BY id""",
                       (lib_id, *statuses)).fetchall()
    for i, row in enumerate(todo):
        if progress:
            progress("Matching on TMDB", i, len(todo))
        try:
            if match_title(con, tmdb, images, row["id"]):
                stats.matched += 1
            else:
                stats.unmatched += 1
        except InvalidKey:
            raise
        except TmdbError as e:
            stats.errors += 1
            log.warning("TMDB error on item %s: %s", row["id"], e)

    # Matched shows: fill in seasons/episodes added since, and refresh anything older than ~5 months.
    stale_before = now() - REFRESH_AFTER
    for show in con.execute("""SELECT id, tmdb_id, metadata_at FROM items WHERE library_id=? AND kind IN ('show','movie')
                               AND match_status IN ('matched','manual') AND tmdb_id IS NOT NULL""", (lib_id,)).fetchall():
        try:
            kind = con.execute("SELECT kind FROM items WHERE id=?", (show["id"],)).fetchone()
            if not kind:
                continue  # merged away above
            if (show["metadata_at"] or 0) < stale_before:
                d = _fetch_title_images(tmdb, images, tmdb.tv(show["tmdb_id"]) if kind["kind"] == "show"
                                        else tmdb.movie(show["tmdb_id"]))
                with Tx(con):
                    status = con.execute("SELECT match_status, match_score FROM items WHERE id=?", (show["id"],)).fetchone()
                    _apply_title(con, show["id"], kind["kind"], d, status[0], status[1])
                stats.refreshed += 1
            if kind["kind"] == "show":
                _apply_seasons(con, tmdb, images, show["id"], show["tmdb_id"], only_stale=True)
        except InvalidKey:
            raise
        except TmdbError as e:
            stats.errors += 1
            log.warning("TMDB refresh error on item %s: %s", show["id"], e)
    return stats
