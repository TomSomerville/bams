"""Music identification against fake MusicBrainz / Cover Art Archive / Wikimedia (httpx.MockTransport):
no network, no waiting for the real 1-request-per-second limit."""

import httpx
import pytest
from fastapi.testclient import TestClient

from bams import app as app_module
from bams import jobs, library, music, music_match, readonly
from bams.app import create_app
from bams.config import Paths
from bams.db import jdump, jload
from bams.musicbrainz import USER_AGENT, MusicBrainz
from bams.scanner import scan_library
from conftest import make_tree, signed_in

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
ARTIST_ID = "11111111-1111-1111-1111-111111111111"
REL_ID = "22222222-2222-2222-2222-222222222222"
RG_ID = "33333333-3333-3333-3333-333333333333"
TAGGED_ID = "44444444-4444-4444-4444-444444444444"


def _credit(name=" Real Artist", aid=ARTIST_ID):
    return [{"name": name.strip(), "joinphrase": "", "artist": {"id": aid, "name": name.strip()}}]


REAL_ALBUM_SEARCH = {"id": REL_ID, "score": 100, "title": "Real Album", "status": "Official", "date": "2019-03-01",
                     "track-count": 2, "artist-credit": _credit()}
DECOY = {"id": "99999999-9999-9999-9999-999999999999", "score": 90, "title": "Real Album (Live)",
         "date": "2020", "track-count": 14, "artist-credit": _credit("Someone Else", "x")}
REAL_ALBUM = {
    "id": REL_ID, "title": "Real Album", "date": "2019-03-01", "country": "XW", "artist-credit": _credit(),
    "release-group": {"id": RG_ID, "primary-type": "Album", "first-release-date": "2018-11-30",
                      "relations": [{"type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q200"}}]},
    "media": [{"position": 1, "tracks": [
        {"position": 1, "title": "Track One (Remastered)", "recording": {"id": "rec-1"}},
        {"position": 2, "title": "Track Two", "recording": {"id": "rec-2"}}]}],
}
TAGGED = {"id": TAGGED_ID, "title": "Tagged Album", "artist-credit": _credit(),
          "release-group": {"id": "rg-t", "first-release-date": "2001"}, "media": []}
ARTIST = {"id": ARTIST_ID, "name": "Real Artist", "sort-name": "Artist, Real", "type": "Group", "country": "GB",
          "life-span": {"begin": "1990"},
          "relations": [{"type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q100"}}]}


def fake(calls: list, down: bool = False) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.headers["user-agent"] == USER_AGENT
        host, path, q = req.url.host, req.url.path, req.url.params
        if down:
            return httpx.Response(503)
        if host == "musicbrainz.org":
            assert q["fmt"] == "json"
            if path == "/ws/2/release":
                query = q["query"]
                if '"Real Album"' in query:
                    return httpx.Response(200, json={"releases": [DECOY, REAL_ALBUM_SEARCH]})
                if '"Odd Thing"' in query:
                    return httpx.Response(200, json={"releases": [{"id": "x", "title": "Something Else Entirely",
                                                                    "artist-credit": _credit()}]})
                return httpx.Response(200, json={"releases": []})
            if path == f"/ws/2/release/{REL_ID}":
                return httpx.Response(200, json=REAL_ALBUM)
            if path == f"/ws/2/release/{TAGGED_ID}":
                return httpx.Response(200, json=TAGGED)
            if path == "/ws/2/artist":
                if '"Nirvana"' in q["query"]:  # two bands, same name: must not guess
                    return httpx.Response(200, json={"artists": [{"id": "n1", "name": "Nirvana"},
                                                                 {"id": "n2", "name": "Nirvana"}]})
                return httpx.Response(200, json={"artists": []})
            if path == f"/ws/2/artist/{ARTIST_ID}":
                return httpx.Response(200, json=ARTIST)
            return httpx.Response(404)
        if host == "coverartarchive.org":
            return httpx.Response(200, content=JPEG) if REL_ID in path else httpx.Response(404)
        if host == "www.wikidata.org":
            qid = path.rsplit("/", 1)[1].removesuffix(".json")
            ent = {"Q100": {"sitelinks": {"enwiki": {"title": "Real Artist"}},
                            "claims": {"P18": [{"mainsnak": {"datavalue": {"value": "Real Artist 2010.jpg"}}}]}},
                   "Q200": {"sitelinks": {"enwiki": {"title": "Real Album"}}, "claims": {}}}[qid]
            return httpx.Response(200, json={"entities": {qid: ent}})
        if host == "en.wikipedia.org":
            title = path.rsplit("/", 1)[1].replace("_", " ")
            return httpx.Response(200, json={"type": "standard", "title": title, "extract": f"About {title}.",
                                             "content_urls": {"desktop": {"page": f"https://en.wikipedia.org/wiki/{title}"}}})
        if host == "commons.wikimedia.org":
            return httpx.Response(200, json={"query": {"pages": {"1": {"imageinfo": [{
                "url": "https://upload.wikimedia.org/full.jpg", "thumburl": "https://upload.wikimedia.org/thumb.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Real_Artist_2010.jpg",
                "extmetadata": {"Artist": {"value": '<a href="u">Jane Photographer</a>'},
                                "LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}}}})
        if host == "upload.wikimedia.org":
            return httpx.Response(200, content=JPEG)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


LAYOUT = [
    "Real Artist/Real Album (2019)/01 - Track One.mp3",
    "Real Artist/Real Album (2019)/02 - Track Two.mp3",
    "Real Artist/Odd Thing/01 - Whatever.mp3",
    "Real Artist/Tagged Album/01 - Tagged.mp3",
    "Nirvana/Bleach/01 - Blew.mp3",
    "Various Artists/Hits/01 - Song.mp3",
]


@pytest.fixture
def lib(env):
    paths, media, con = env
    make_tree(media, LAYOUT)
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    # pretend ffprobe read a MusicBrainz release id from this file's tags
    con.execute("UPDATE files SET probe=? WHERE rel_path LIKE 'Real Artist/Tagged Album/%'",
                (jdump({"audio": [{"codec": "MP3"}], "tags": {"musicbrainz_albumid": TAGGED_ID}}),))
    return paths, con, lib_id


def item(con, kind, title):
    return con.execute("SELECT * FROM items WHERE kind=? AND (title=? OR parsed_title=?)", (kind, title, title)).fetchone()


def test_identifies_albums_and_artists(lib):
    paths, con, lib_id = lib
    calls: list = []
    with MusicBrainz(transport=fake(calls), min_interval=0) as mb:
        st = music_match.match_music_library(con, mb, paths.images, lib_id)
    assert st.as_dict() == {"albums_matched": 2, "albums_unmatched": 3, "artists_matched": 1,
                            "artists_unmatched": 1, "covers": 1, "photos": 1, "refreshed": 0,
                            "merged": 0, "errors": 0}

    al = item(con, "album", "Real Album")
    assert (al["mbid"], al["match_status"], al["year"]) == (REL_ID, "matched", 2018)  # original release year
    assert al["overview"] == "About Real Album." and al["poster"].startswith("music/")
    extra = jload(al["extra"])
    assert extra["release_group"] == RG_ID and extra["type"] == "Album"
    assert extra["wikipedia"]["url"].endswith("/Real Album")
    # untagged files take MusicBrainz's titles; every track gets its recording id
    tracks = con.execute("SELECT title, mbid FROM items WHERE parent_id=? ORDER BY track_number", (al["id"],)).fetchall()
    assert [tuple(t) for t in tracks] == [("Track One (Remastered)", "rec-1"), ("Track Two", "rec-2")]

    # the release id in the tags is used directly (no search for that album)
    assert item(con, "album", "Tagged Album")["mbid"] == TAGGED_ID
    assert not any('"Tagged Album"' in c.url.params.get("query", "") for c in calls)
    # low score / nothing found: unmatched, never guessed
    assert item(con, "album", "Odd Thing")["match_status"] == "unmatched"
    assert item(con, "album", "Bleach")["match_status"] == "unmatched"

    ar = item(con, "artist", "Real Artist")
    assert (ar["mbid"], ar["sort_title"], ar["overview"]) == (ARTIST_ID, "Artist, Real", "About Real Artist.")
    assert ar["poster"] and jload(ar["extra"])["image_credit"] == {
        "author": "Jane Photographer", "license": "CC BY-SA 4.0",
        "url": "https://commons.wikimedia.org/wiki/File:Real_Artist_2010.jpg"}
    assert not any(c.url.path == "/ws/2/artist" and "Real Artist" in c.url.params["query"] for c in calls)  # id via album
    assert item(con, "artist", "Nirvana")["match_status"] == "unmatched"  # ambiguous name
    assert item(con, "artist", music.VARIOUS)["match_status"] == "pending"  # never looked up

    # a second run only looks at what's new
    calls.clear()
    with MusicBrainz(transport=fake(calls), min_interval=0) as mb:
        st = music_match.match_music_library(con, mb, paths.images, lib_id)
    assert calls == [] and st.albums_matched == 0


def test_identified_data_survives_rescans(lib, monkeypatch):
    paths, con, lib_id = lib
    with MusicBrainz(transport=fake([]), min_interval=0) as mb:
        music_match.match_music_library(con, mb, paths.images, lib_id)
    monkeypatch.setattr(music, "PARSER_VERSION", music.PARSER_VERSION + 1)  # every file re-read and re-linked
    assert scan_library(con, lib_id, do_probe=False).reparsed == len(LAYOUT)
    al = item(con, "album", "Real Album")
    assert al["year"] == 2018 and al["match_status"] == "matched"
    assert [t[0] for t in con.execute("SELECT title FROM items WHERE parent_id=? ORDER BY track_number",
                                      (al["id"],))] == ["Track One (Remastered)", "Track Two"]


def test_local_art_beats_downloaded_art(lib):
    paths, con, lib_id = lib
    al = item(con, "album", "Real Album")
    con.execute("UPDATE items SET poster='music/local.jpg' WHERE id=?", (al["id"],))
    calls: list = []
    with MusicBrainz(transport=fake(calls), min_interval=0) as mb:
        music_match.match_album(con, mb, paths.images, al["id"])
    assert item(con, "album", "Real Album")["poster"] == "music/local.jpg"
    assert not any(c.url.host == "coverartarchive.org" for c in calls)


def test_service_down_leaves_items_pending(lib):
    paths, con, lib_id = lib
    calls: list = []
    with MusicBrainz(transport=fake(calls, down=True), min_interval=0) as mb:
        st = music_match.match_music_library(con, mb, paths.images, lib_id)
    assert st.errors == music_match._GIVE_UP_AFTER  # noqa: SLF001 - stops early instead of hammering
    assert con.execute("SELECT COUNT(*) FROM items WHERE kind='album' AND match_status<>'pending'").fetchone()[0] == 0


def test_scoring_prefers_the_right_release():
    best, s = music_match.best_release([DECOY, REAL_ALBUM_SEARCH], "Real Album", "Real Artist", 2, 2019)
    assert best is REAL_ALBUM_SEARCH and s >= music_match.ACCEPT
    best, s = music_match.best_release([DECOY], "Real Album", "Real Artist", 2, 2019)
    assert s < music_match.ACCEPT  # wrong artist + very different track count


def test_api_toggle_and_fix_match(tmp_path, monkeypatch):
    media = tmp_path / "media"
    make_tree(media, ["Real Artist/Some Folder/01 - a.mp3", "Real Artist/Some Folder/02 - b.mp3"])
    paths = Paths(tmp_path / "data")
    calls: list = []
    monkeypatch.setattr(app_module, "MusicBrainz", lambda: MusicBrainz(transport=fake(calls), min_interval=0))
    monkeypatch.setattr(jobs, "MusicBrainz", lambda: MusicBrainz(transport=fake(calls), min_interval=0))
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        assert c.get("/api/settings").json()["music_lookup"] is True  # on by default
        assert c.put("/api/settings/music-lookup", json={"enabled": False}).json() == {"music_lookup": False}
        lib = c.post("/api/libraries", json={"name": "Music", "type": "music", "paths": [str(media)]}).json()
        res = jobs.run_scan(paths, lib["id"])
        assert res["identify"].startswith("skipped") and calls == []

        c.put("/api/settings/music-lookup", json={"enabled": True})
        res = jobs.run_scan(paths, lib["id"])
        assert res["identify"]["albums_unmatched"] == 1  # "Some Folder" isn't on (fake) MusicBrainz

        album = c.get(f"/api/libraries/{lib['id']}/items?kind=album").json()[0]
        hits = c.get("/api/musicbrainz/search?kind=album&q=Real Album&artist=Real Artist").json()
        assert hits[1]["mbid"] == REL_ID and hits[1]["artist"] == "Real Artist" and hits[1]["track_count"] == 2
        d = c.post(f"/api/items/{album['id']}/music-match", json={"mbid": REL_ID}).json()
        assert (d["title"], d["match_status"], d["ids"]["musicbrainz"]) == ("Real Album", "manual", REL_ID)
        assert d["extra"]["wikipedia"]["title"] == "Real Album" and d["overview"] == "About Real Album."
        assert c.post(f"/api/items/{album['id']}/music-match", json={"mbid": "nope"}).status_code == 422
        unknown = "55555555-5555-5555-5555-555555555555"
        assert c.post(f"/api/items/{album['id']}/music-match", json={"mbid": unknown}).status_code == 502
    finally:
        readonly.set_protected_roots([])
