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

Two local albums pinned to the same release (say a FLAC and an MP3 copy, or one album in two folders) are
merged into one, when both identifications are sure: a release id in the tags, Fix match, or a search
scoring MERGE_SCORE. Identified albums and artists are looked up again after REFRESH_AFTER (MusicBrainz
corrections, new Wikipedia text, a better cover), a few per scan.

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
MERGE_SCORE = 0.95  # a search match this sure can be merged with another album pinned to the same release
REFRESH_AFTER = 120 * 86400  # look identified albums/artists up again after ~4 months
REFRESH_PER_SCAN = 50  # at most this many per scan (MusicBrainz allows 1 request/second)
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
    refreshed: int = 0
    merged: int = 0
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
            "artist_id": al["parent_id"], "poster": al["poster"], "status": al["match_status"],
            "score": al["match_score"], "poster_src": jload(al["poster_src"]) or {}, "extra": jload(al["extra"]) or {}}


def match_album(con: sqlite3.Connection, mb: MusicBrainz, images: Path, album_id: int, *, mbid: str | None = None,
                manual: bool = False, refresh: bool = False, lang: str = "en",
                stats: MusicMatchStats | None = None) -> bool:
    """Identify one album (or pin it to `mbid`; `refresh`: look its release up again, keeping how it was
    identified). Network first, then one short transaction. May merge it into another album pinned to the
    same release (see merge_same_release)."""
    f = album_facts(con, album_id)
    score: float | None = f["score"] if refresh else 1.0
    matched_by = f["extra"].get("matched_by") if refresh else ("manual" if manual else "tag")
    mbid = mbid or f["tag_mbid"]
    if not mbid:
        matched_by = "search"
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
    if rel is None:  # stale id in the tags, a typo in Fix match, or a release since deleted
        if manual:
            raise MusicLookupError(f"MusicBrainz has no release {mbid}")
        if refresh:  # keep what we have; try again after another REFRESH_AFTER
            with Tx(con):
                con.execute("UPDATE items SET metadata_at=? WHERE id=?", (now(), album_id))
            return False
        _mark_unmatched(con, album_id, None)
        return False
    mbid = rel.get("id") or mbid  # MusicBrainz answers a merged-away id with the release it went into

    rg = rel.get("release-group") or {}
    cover = None
    if not f["poster"] or (refresh and f["poster_src"].get("from") == "caa"):
        data = mb.cover(mbid, rg.get("id"))
        cover = music._store_image(images, data) if data else None  # noqa: SLF001 - shared image store
        if cover and stats and cover != f["poster"]:
            stats.covers += 1
    _, wiki = _wiki(mb, wikidata_id(rg), lang)
    extra = {"release_group": rg.get("id"), "type": rg.get("primary-type"),
             "secondary_types": rg.get("secondary-types") or [],
             "country": rel.get("country"), "date": rel.get("date"),
             "musicbrainz_url": f"https://musicbrainz.org/release/{mbid}",
             "wikipedia": {"url": wiki["url"], "title": wiki["title"]} if wiki else None,
             "matched_by": matched_by}
    by_pos = {(m.get("position") or 1, t.get("position")): t
              for m in rel.get("media") or [] for t in m.get("tracks") or []}
    credit = rel.get("artist-credit") or []

    with Tx(con):
        con.execute("""UPDATE items SET title=?, year=?, overview=?, mbid=?, extra=?, poster=COALESCE(?, poster),
                       poster_src=CASE WHEN ? IS NULL THEN poster_src ELSE ? END,
                       match_status=?, match_score=?, metadata_at=?, updated_at=? WHERE id=?""", (
            rel.get("title") or f["title"], _year(rg.get("first-release-date")) or _year(rel.get("date")) or f["year"],
            wiki["extract"] if wiki else None, mbid, jdump(extra), cover, cover, jdump({"from": "caa"}),
            "manual" if manual else "matched", score, now(), now(), album_id))
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
    log.info("%s album %r -> MusicBrainz %s %r", "refreshed" if refresh else "matched", f["title"], mbid,
             rel.get("title"))
    if merge_same_release(con, album_id) != album_id and stats:
        stats.merged += 1
    return True


# ------------------------------------------------------------------ merging

def _pinned(r: sqlite3.Row) -> bool:
    """Sure enough of this album's release to merge it with another album on the same release."""
    by = (jload(r["extra"]) or {}).get("matched_by")
    return r["match_status"] == "manual" or by in ("tag", "manual") or (r["match_score"] or 0) >= MERGE_SCORE


def merge_same_release(con: sqlite3.Connection, album_id: int) -> int:
    """Merge this album with other albums of its library pinned to the same release (the oldest is kept).
    Returns the id of the album it now is."""
    me = con.execute("SELECT * FROM items WHERE id=?", (album_id,)).fetchone()
    if not me or not me["mbid"] or not _pinned(me):
        return album_id
    keep = album_id
    for o in con.execute("""SELECT * FROM items WHERE library_id=? AND kind='album' AND mbid=? AND id<>?
                            ORDER BY id""", (me["library_id"], me["mbid"], album_id)).fetchall():
        if _pinned(o):
            a, b = sorted((keep, o["id"]))
            with Tx(con):
                merge_albums(con, a, b)
            keep = a
    return keep


def merge_albums(con: sqlite3.Connection, keep: int, drop: int) -> None:
    """Fold album `drop` into `keep` (call inside a transaction). Tracks that are the same track (same disc and
    number, a similar title: the FLAC and the MP3 of one song) become one track with both files; the others
    move over. Later scans file `drop`'s music under `keep` (an item_keys alias by artist + album name)."""
    k = con.execute("SELECT * FROM items WHERE id=?", (keep,)).fetchone()
    d = con.execute("""SELECT a.*, p.title AS album_artist FROM items a JOIN items p ON p.id=a.parent_id
                       WHERE a.id=?""", (drop,)).fetchone()
    con.execute("UPDATE item_keys SET item_id=? WHERE item_id=?", (keep, drop))
    con.execute("INSERT OR REPLACE INTO item_keys (library_id, kind, title_key, year, item_id) VALUES (?, 'album', ?, 0, ?)",
                (d["library_id"], music.album_alias(d["album_artist"], d["parsed_title"] or d["title"]), keep))
    mine = con.execute("SELECT id, disc_number, track_number, title FROM items WHERE parent_id=? AND kind='track'",
                       (keep,)).fetchall()
    for t in con.execute("SELECT id, disc_number, track_number, title FROM items WHERE parent_id=? AND kind='track'",
                         (drop,)).fetchall():
        same = next((m for m in mine if t["track_number"] is not None and m["track_number"] == t["track_number"]
                     and (m["disc_number"] or 1) == (t["disc_number"] or 1) and _sim(m["title"], t["title"]) >= 0.8), None)
        if same:
            con.execute("UPDATE OR IGNORE file_items SET item_id=? WHERE item_id=?", (same["id"], t["id"]))
            con.execute("UPDATE playlist_items SET item_id=? WHERE item_id=?", (same["id"], t["id"]))
            con.execute("DELETE FROM items WHERE id=?", (t["id"],))
        else:
            con.execute("UPDATE items SET parent_id=?, updated_at=? WHERE id=?", (keep, now(), t["id"]))
    if not k["poster"] and d["poster"]:
        con.execute("UPDATE items SET poster=?, poster_src=? WHERE id=?", (d["poster"], d["poster_src"], keep))
    con.execute("DELETE FROM items WHERE id=?", (drop,))
    if not con.execute("SELECT 1 FROM items WHERE parent_id=?", (d["parent_id"],)).fetchone():
        con.execute("DELETE FROM items WHERE id=? AND kind='artist'", (d["parent_id"],))  # an artist left empty
    music.rollup(con, d["library_id"])
    log.info("merged album %s into %s (same MusicBrainz release)", drop, keep)


# ------------------------------------------------------------------ artists

def match_artist(con: sqlite3.Connection, mb: MusicBrainz, images: Path, artist_id: int, *, mbid: str | None = None,
                 manual: bool = False, refresh: bool = False, lang: str = "en",
                 stats: MusicMatchStats | None = None) -> bool:
    it = con.execute("SELECT * FROM items WHERE id=?", (artist_id,)).fetchone()
    name = it["title"]
    score: float | None = it["match_score"] if refresh else 1.0
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
        if refresh:
            with Tx(con):
                con.execute("UPDATE items SET metadata_at=? WHERE id=?", (now(), artist_id))
            return False
        _mark_unmatched(con, artist_id, None)
        return False
    mbid = a.get("id") or mbid

    ent, wiki = _wiki(mb, wikidata_id(a), lang)
    photo, credit = None, None
    from_commons = (jload(it["poster_src"]) or {}).get("from") == "commons"
    if (not it["poster"] or (refresh and from_commons)) and (fname := _p18(ent)):
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
                       poster=COALESCE(?, poster), poster_src=CASE WHEN ? IS NULL THEN poster_src ELSE ? END,
                       match_status=?, match_score=?, metadata_at=?, updated_at=? WHERE id=?""", (
            mbid, a.get("sort-name"), wiki["extract"] if wiki else None, jdump(extra), photo, photo,
            jdump({"from": "commons"}), "manual" if manual else "matched", score, now(), now(), artist_id))
    log.info("%s artist %r -> MusicBrainz %s", "refreshed" if refresh else "matched", name, mbid)
    return True


# ------------------------------------------------------------------ library

def match_music_library(con: sqlite3.Connection, mb: MusicBrainz, images: Path, lib_id: int, *,
                        retry_unmatched: bool = False, lang: str = "en",
                        progress: Callable[..., None] | None = None) -> MusicMatchStats:
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
                progress(f"Identifying {kind}s on MusicBrainz", i, len(todo))
            if not con.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone():
                continue  # merged into another album meanwhile
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

    # Identified a while ago: look them up again (oldest first, a few per scan).
    stale = con.execute("""SELECT id, kind, mbid, match_status FROM items WHERE library_id=? AND kind IN ('album', 'artist')
                           AND match_status IN ('matched', 'manual') AND mbid IS NOT NULL
                           AND COALESCE(metadata_at, 0) < ? ORDER BY COALESCE(metadata_at, 0), id LIMIT ?""",
                        (lib_id, now() - REFRESH_AFTER, REFRESH_PER_SCAN)).fetchall()
    for i, r in enumerate(stale):
        if progress:
            progress("Refreshing music details from MusicBrainz", i, len(stale))
        if not con.execute("SELECT 1 FROM items WHERE id=?", (r["id"],)).fetchone():
            continue  # merged away meanwhile
        fn = match_album if r["kind"] == "album" else match_artist
        try:
            if fn(con, mb, images, r["id"], mbid=r["mbid"], manual=r["match_status"] == "manual", refresh=True,
                  lang=lang, stats=stats):
                stats.refreshed += 1
            failures = 0
        except MusicLookupError as e:
            stats.errors += 1
            failures += 1
            log.warning("MusicBrainz refresh failed for %s %s: %s", r["kind"], r["id"], e)
            if failures >= _GIVE_UP_AFTER:
                break
    return stats
