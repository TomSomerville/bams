"""Identify music on MusicBrainz and fill in what the files don't have.

Per album (best first):
  1. a MusicBrainz release id in the files' tags (Picard and most taggers write one) -> used as-is
  2. a search on album title + album artist, scored on title, artist, track count and year;
     accepted only above ACCEPT, otherwise the album is marked 'unmatched' (never guessed)
Then: the release's title and original year, MusicBrainz ids, a description from Wikipedia (via the album's
Wikidata page), a cover from the Cover Art Archive when there's no local art, and titles for tracks
whose names came only from file names.

Per artist: the id found through their albums (or an unambiguous name search), MusicBrainz's sort name,
a Wikipedia summary and a Wikimedia Commons photo when there's no local artist.jpg.

Local art always wins over downloaded art. Genres keep coming from the files' tags (see musicbrainz.py).
"""

from __future__ import annotations

import logging
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from . import music
from .db import Tx, jdump, jload, now
from .musicbrainz import VARIOUS_ARTISTS_MBID, MusicBrainz, MusicLookupError, wikidata_id
from .parse import title_key

log = logging.getLogger(__name__)

ACCEPT = 0.85
_GIVE_UP_AFTER = 5  # consecutive service errors: MusicBrainz is down, try again next scan
_SKIP_ARTISTS = (music.VARIOUS, music.UNKNOWN_ARTIST)


@dataclass
class MusicMatchStats:
    albums_matched: int = 0
    albums_unmatched: int = 0
    artists_matched: int = 0
    artists_unmatched: int = 0
    covers: int = 0
    photos: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _sim(a: str | None, b: str | None) -> float:
    a, b = title_key(a), title_key(b)
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and date[:4].isdigit() else None


def credit_name(credit: list[dict] | None) -> str:
    """MusicBrainz artist credit -> display string ("A feat. B")."""
    return "".join(c.get("name", "") + c.get("joinphrase", "") for c in credit or []).strip()


def score_release(r: dict, album: str, artist: str | None, ntracks: int | None, year: int | None) -> float:
    credit = r.get("artist-credit") or []
    if artist == music.VARIOUS:
        a = 1.0 if any((c.get("artist") or {}).get("id") == VARIOUS_ARTISTS_MBID for c in credit) else 0.4
    elif artist:
        a = max([_sim(artist, credit_name(credit))] + [_sim(artist, c.get("name")) for c in credit])
    else:
        a = 0.7  # unknown artist: rely on the title, track count and year
    s = 0.6 * _sim(album, r.get("title")) + 0.4 * a
    tc = r.get("track-count")
    if ntracks and tc:
        s += 0.08 if tc == ntracks else (-0.03 if abs(tc - ntracks) <= 2 else -0.15)
    ry = _year(r.get("date")) or _year((r.get("release-group") or {}).get("first-release-date"))
    if year and ry and ry == year:
        s += 0.04
    if r.get("status") == "Official":
        s += 0.02
    return s


def best_release(results: list[dict], album: str, artist: str | None, ntracks: int | None,
                 year: int | None) -> tuple[dict | None, float]:
    best, best_s = None, 0.0
    for r in results:
        s = score_release(r, album, artist, ntracks, year)
        if s > best_s + 1e-9:  # ties keep MusicBrainz's own (relevance) order
            best, best_s = r, s
    return best, best_s


def _wiki(mb: MusicBrainz, qid: str | None, lang: str) -> tuple[dict | None, dict | None]:
    """(Wikidata entity, Wikipedia summary in `lang`, else English)."""
    ent = mb.wikidata(qid) if qid else None
    if not ent:
        return None, None
    links = ent.get("sitelinks") or {}
    for lg in dict.fromkeys([lang, "en"]):
        title = (links.get(f"{lg}wiki") or {}).get("title")
        if title and (summary := mb.wikipedia_summary(lg, title)):
            return ent, summary
    return ent, None


def _p18(ent: dict | None) -> str | None:
    """A Wikidata entity's image (P18), if it has one."""
    for claim in ((ent or {}).get("claims") or {}).get("P18", []):
        v = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, str):
            return v
    return None


def _mark_unmatched(con: sqlite3.Connection, item_id: int, score: float | None) -> None:
    with Tx(con):
        con.execute("UPDATE items SET match_status='unmatched', match_score=?, updated_at=? WHERE id=?",
                    (score, now(), item_id))


# ------------------------------------------------------------------ albums

def album_facts(con: sqlite3.Connection, album_id: int) -> dict:
    """What we know locally: title, album artist, track count, year, and any release id in the tags."""
    al = con.execute("""SELECT a.*, p.title AS album_artist FROM items a JOIN items p ON p.id=a.parent_id
                        WHERE a.id=?""", (album_id,)).fetchone()
    tag_ids: Counter[str] = Counter()
    years: Counter[int] = Counter()
    n = 0
    for r in con.execute("""SELECT f.probe, t.year FROM items t JOIN file_items fi ON fi.item_id=t.id
                            JOIN files f ON f.id=fi.file_id WHERE t.parent_id=?""", (album_id,)):
        n += 1
        if mbid := ((jload(r["probe"]) or {}).get("tags") or {}).get("musicbrainz_albumid"):
            tag_ids[mbid.strip()] += 1
        if r["year"]:
            years[r["year"]] += 1
    return {"title": al["parsed_title"] or al["title"], "artist": al["album_artist"], "tracks": n,
            "year": years.most_common(1)[0][0] if years else None,
            "tag_mbid": tag_ids.most_common(1)[0][0] if tag_ids else None,
            "artist_id": al["parent_id"], "poster": al["poster"], "status": al["match_status"]}


def match_album(con: sqlite3.Connection, mb: MusicBrainz, images: Path, album_id: int, *, mbid: str | None = None,
                manual: bool = False, lang: str = "en", stats: MusicMatchStats | None = None) -> bool:
    """Identify one album (or pin it to `mbid`). Network first, then one short transaction."""
    f = album_facts(con, album_id)
    score: float | None = 1.0
    mbid = mbid or f["tag_mbid"]
    if not mbid:
        artist = None if f["artist"] == music.UNKNOWN_ARTIST else f["artist"]
        results = mb.search_releases(f["title"], artist)
        if not results and artist:
            results = mb.search_releases(f["title"])  # the artist may be spelled differently there
        best, score = best_release(results, f["title"], artist, f["tracks"], f["year"])
        if not best or score < ACCEPT:
            _mark_unmatched(con, album_id, score if best else None)
            log.info("no confident MusicBrainz match for %r by %r (best %.2f)", f["title"], f["artist"], score or 0)
            return False
        mbid = best["id"]
        score = min(score, 1.0)  # bonuses can push a sure match past 1
    rel = mb.release(mbid)
    if rel is None:  # stale id in the tags, or a typo in Fix match
        if manual:
            raise MusicLookupError(f"MusicBrainz has no release {mbid}")
        _mark_unmatched(con, album_id, None)
        return False

    rg = rel.get("release-group") or {}
    cover = None
    if not f["poster"]:
        data = mb.cover(mbid, rg.get("id"))
        cover = music._store_image(images, data) if data else None  # noqa: SLF001 - shared image store
        if cover and stats:
            stats.covers += 1
    _, wiki = _wiki(mb, wikidata_id(rg), lang)
    extra = {"release_group": rg.get("id"), "type": rg.get("primary-type"),
             "secondary_types": rg.get("secondary-types") or [],
             "country": rel.get("country"), "date": rel.get("date"),
             "musicbrainz_url": f"https://musicbrainz.org/release/{mbid}",
             "wikipedia": {"url": wiki["url"], "title": wiki["title"]} if wiki else None}
    by_pos = {(m.get("position") or 1, t.get("position")): t
              for m in rel.get("media") or [] for t in m.get("tracks") or []}
    credit = rel.get("artist-credit") or []

    with Tx(con):
        con.execute("""UPDATE items SET title=?, year=?, overview=?, mbid=?, extra=?, poster=COALESCE(poster, ?),
                       match_status=?, match_score=?, metadata_at=?, updated_at=? WHERE id=?""", (
            rel.get("title") or f["title"], _year(rg.get("first-release-date")) or _year(rel.get("date")) or f["year"],
            wiki["extract"] if wiki else None, mbid, jdump(extra), cover, "manual" if manual else "matched",
            score, now(), now(), album_id))
        # Tracks: MusicBrainz ids, and real titles for files whose name was all we had.
        for t in con.execute("""SELECT t.id, t.disc_number, t.track_number, f.parse FROM items t
                                JOIN file_items fi ON fi.item_id=t.id JOIN files f ON f.id=fi.file_id
                                WHERE t.parent_id=?""", (album_id,)).fetchall():
            mt = by_pos.get((t["disc_number"] or 1, t["track_number"]))
            if not mt:
                continue
            from_name = (jload(t["parse"]) or {}).get("source") == "path"
            con.execute("""UPDATE items SET mbid=?, title=CASE WHEN ? THEN ? ELSE title END, match_status='matched',
                           updated_at=? WHERE id=?""",
                        ((mt.get("recording") or {}).get("id"), from_name, mt.get("title"), now(), t["id"]))
        # The album artist's MusicBrainz id, for the artist step (only when the credit is clearly them).
        if len(credit) == 1:
            a = credit[0].get("artist") or {}
            artist_row = con.execute("SELECT title, mbid FROM items WHERE id=?", (f["artist_id"],)).fetchone()
            if a.get("id") and not artist_row["mbid"] and a["id"] != VARIOUS_ARTISTS_MBID \
                    and _sim(artist_row["title"], a.get("name")) >= 0.9:
                con.execute("UPDATE items SET mbid=? WHERE id=?", (a["id"], f["artist_id"]))
    log.info("matched album %r -> MusicBrainz %s %r", f["title"], mbid, rel.get("title"))
    return True


# ------------------------------------------------------------------ artists

def match_artist(con: sqlite3.Connection, mb: MusicBrainz, images: Path, artist_id: int, *, mbid: str | None = None,
                 manual: bool = False, lang: str = "en", stats: MusicMatchStats | None = None) -> bool:
    it = con.execute("SELECT * FROM items WHERE id=?", (artist_id,)).fetchone()
    name = it["title"]
    score: float | None = 1.0
    mbid = mbid or it["mbid"]
    if not mbid:
        # Only an unambiguous exact name: "Nirvana" is several bands, and guessing wrong is worse than nothing.
        exact = [a for a in mb.search_artists(name)
                 if title_key(a.get("name")) == title_key(name)
                 or any(title_key(x.get("name")) == title_key(name) for x in a.get("aliases") or [])]
        if len(exact) != 1:
            _mark_unmatched(con, artist_id, None)
            log.info("artist %r: %s on MusicBrainz", name, "ambiguous" if exact else "not found")
            return False
        mbid = exact[0]["id"]
    a = mb.artist(mbid)
    if a is None:
        if manual:
            raise MusicLookupError(f"MusicBrainz has no artist {mbid}")
        _mark_unmatched(con, artist_id, None)
        return False

    ent, wiki = _wiki(mb, wikidata_id(a), lang)
    photo, credit = None, None
    if not it["poster"] and (fname := _p18(ent)):
        got = mb.commons_image(fname)
        if got and (photo := music._store_image(images, got[0])):  # noqa: SLF001
            credit = got[1]
            if stats:
                stats.photos += 1
    old = jload(it["extra"]) or {}
    extra = {"type": a.get("type"), "country": a.get("country"), "disambiguation": a.get("disambiguation") or None,
             "life_span": a.get("life-span"), "musicbrainz_url": f"https://musicbrainz.org/artist/{mbid}",
             "wikipedia": {"url": wiki["url"], "title": wiki["title"]} if wiki else None,
             # keep the credit of a photo set on an earlier match
             "image_credit": credit or (old.get("image_credit") if it["poster"] else None)}
    with Tx(con):
        con.execute("""UPDATE items SET mbid=?, sort_title=COALESCE(?, sort_title), overview=?, extra=?,
                       poster=COALESCE(poster, ?), match_status=?, match_score=?, metadata_at=?, updated_at=?
                       WHERE id=?""", (
            mbid, a.get("sort-name"), wiki["extract"] if wiki else None, jdump(extra), photo,
            "manual" if manual else "matched", score, now(), now(), artist_id))
    log.info("matched artist %r -> MusicBrainz %s", name, mbid)
    return True


# ------------------------------------------------------------------ library

def match_music_library(con: sqlite3.Connection, mb: MusicBrainz, images: Path, lib_id: int, *,
                        retry_unmatched: bool = False, lang: str = "en",
                        progress: Callable[[str], None] | None = None) -> MusicMatchStats:
    """Albums first (they also find their artists' ids), then artists. Only items not identified yet."""
    stats = MusicMatchStats()
    statuses = ("pending", "unmatched") if retry_unmatched else ("pending",)
    marks = ",".join("?" * len(statuses))
    failures = 0
    for kind, fn in (("album", match_album), ("artist", match_artist)):
        todo = [r["id"] for r in con.execute(
            f"""SELECT id FROM items WHERE library_id=? AND kind=? AND match_status IN ({marks})
                AND NOT (kind='artist' AND title IN (?, ?)) ORDER BY id""", (lib_id, kind, *statuses, *_SKIP_ARTISTS))]
        for i, item_id in enumerate(todo):
            if progress:
                progress(f"identifying {kind}s on MusicBrainz ({i + 1}/{len(todo)})")
            try:
                ok = fn(con, mb, images, item_id, lang=lang, stats=stats)
                failures = 0
            except MusicLookupError as e:
                stats.errors += 1
                failures += 1
                log.warning("MusicBrainz lookup failed for %s %s: %s", kind, item_id, e)
                if failures >= _GIVE_UP_AFTER:
                    log.warning("MusicBrainz keeps failing; the rest waits for the next scan")
                    return stats
                continue
            setattr(stats, f"{kind}s_{'matched' if ok else 'unmatched'}",
                    getattr(stats, f"{kind}s_{'matched' if ok else 'unmatched'}") + 1)
    return stats
