"""Music: who an album is filed under (main artist), the Genres tab's routes, and Top Played Songs (ListenBrainz)."""

import httpx
import pytest

from bams import app as app_module
from bams import library, music, readonly
from bams.app import create_app
from bams.config import Paths
from bams.db import connect, jdump, set_setting
from bams.musicbrainz import MusicBrainz
from bams.parse import title_key
from bams.scanner import scan_library
from conftest import make_tree, signed_in


@pytest.mark.parametrize("tag, want", [
    ("Main Act;Guest Star", "Main Act"),
    ("Main Act; Guest Star; Third Name", "Main Act"),
    ("Main Act\x00Guest Star", "Main Act"),
    ("Main Act / Guest Star", "Main Act"),
    ("Main Act feat. Guest Star", "Main Act"),
    ("Main Act ft. Guest Star", "Main Act"),
    ("Main Act Featuring Guest Star", "Main Act"),
    ("Main Act (feat. Guest Star)", "Main Act"),
    ("Main Act [ft Guest Star]", "Main Act"),
    # names, not lists
    ("AC/DC", "AC/DC"),
    ("Simon & Garfunkel", "Simon & Garfunkel"),
    ("Earth, Wind & Fire", "Earth, Wind & Fire"),
    ("Tyler, The Creator", "Tyler, The Creator"),
    ("Little Feat", "Little Feat"),
    ("Various Artists", "Various Artists"),
])
def test_main_artist(tag, want):
    assert music.main_artist(tag) == want


def test_album_is_filed_under_the_main_artist_and_the_song_keeps_its_credit():
    t = music.parse_track("x/y.mp3", {"tags": {"artist": "Main Act;Guest Star", "album": "Night", "title": "One"}})
    assert (t.album_artist, t.artist) == ("Main Act", "Main Act, Guest Star")
    # the album artist tag has several names too
    t = music.parse_track("x/y.mp3", {"tags": {"album_artist": "A;B", "artist": "A", "album": "N"}})
    assert (t.album_artist, t.artist) == ("A", None)
    # a compilation stays one
    t = music.parse_track("x/y.mp3", {"tags": {"artist": "A;B", "compilation": "1", "album": "N"}})
    assert t.album_artist == music.VARIOUS


def test_album_moves_to_its_main_artist_with_its_identification(env):
    """A library scanned by an older parser: the album and the track rows stay, the whole-credit artist goes."""
    paths, media, con = env
    make_tree(media, ["A;B/Album/01 - One.mp3", "A;B/Album/02 - Two.mp3"])
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    # what the old parser left: the whole credit is the artist
    al = con.execute("SELECT id, parent_id FROM items WHERE kind='album'").fetchone()
    con.execute("UPDATE items SET title='A;B', title_key='a b' WHERE id=?", (al["parent_id"],))
    con.execute("UPDATE item_keys SET title_key='a b' WHERE item_id=?", (al["parent_id"],))
    con.execute("UPDATE items SET mbid='release', match_status='manual', poster='cover.jpg' WHERE id=?", (al["id"],))
    tracks = {r[0] for r in con.execute("SELECT id FROM items WHERE kind='track'")}

    con.execute("UPDATE files SET parse=json_set(parse, '$.v', 2)")  # the next scan re-reads the files
    scan_library(con, lib_id, do_probe=False)

    assert [r[0] for r in con.execute("SELECT title FROM items WHERE kind='artist'")] == ["A"]
    moved = con.execute("SELECT id, mbid, match_status, poster FROM items WHERE kind='album'").fetchall()
    assert [tuple(r) for r in moved] == [(al["id"], "release", "manual", "cover.jpg")]
    assert {r[0] for r in con.execute("SELECT id FROM items WHERE kind='track'")} == tracks


def _album(con, lib_id, artist, album, tracks, genres=()):
    """artist > album > tracks, with one fake file each; returns the artist's and the tracks' ids."""
    ar = music._artist(con, lib_id, artist)
    al = music._album(con, lib_id, artist, album)
    ids = []
    root = con.execute("SELECT id FROM library_roots WHERE library_id=?", (lib_id,)).fetchone()[0]
    for n, title in enumerate(tracks, 1):
        i = music._insert(con, lib_id, "track", title, parent_id=al, title_key=title_key(title), track_number=n, duration=100.0,
                          genres=jdump(list(genres)) if genres else None)
        f = con.execute("""INSERT INTO files (library_id, root_id, rel_path, size, mtime_ns, parse, first_seen, last_seen)
                           VALUES (?,?,?,1,1,'{}',0,0)""", (lib_id, root, f"{album}/{title}.mp3")).lastrowid
        con.execute("INSERT INTO file_items (file_id, item_id) VALUES (?,?)", (f, i))
        ids.append(i)
    return ar, ids


@pytest.fixture
def api(tmp_path):
    paths = Paths(tmp_path / "data")
    (tmp_path / "media").mkdir()
    app = create_app(paths, start_scheduler=False)
    con = connect(paths.db)
    lib_id = library.create(con, paths.root, "Music", "music", [str(tmp_path / "media")])
    yield signed_in(app), con, lib_id
    con.close()
    readonly.set_protected_roots([])


def test_genres_list_every_genre_and_their_artists(api):
    c, con, lib_id = api
    a, _ = _album(con, lib_id, "Alpha", "A1", ["x"], ["Rock", "Pop", "Funk", "Soul", "Jazz", "Blues", "Metal"])
    b, _ = _album(con, lib_id, "Beta", "B1", ["y", "z"], ["rock"])
    _album(con, lib_id, "Gamma", "G1", ["w"])  # no genre
    assert c.get(f"/api/libraries/{lib_id}/genres").json()[-3:] == [
        {"name": "Pop", "count": 1}, {"name": "Rock", "count": 2}, {"name": "Soul", "count": 1}]
    names = lambda g: [i["title"] for i in c.get(f"/api/libraries/{lib_id}/items", params={"kind": "artist", "genre": g}).json()]
    assert names("Rock") == ["Alpha", "Beta"]
    assert names("Metal") == ["Alpha"]  # past the five kept on the artist
    assert names("Nothing") == []
    assert c.get(f"/api/libraries/{lib_id}/items", params={"kind": "album", "genre": "Rock"}).status_code == 400


def lb(monkeypatch, answer, calls=None):
    """ListenBrainz stood in for: `answer` = (status, recordings)."""
    def handle(req):
        if calls is not None:
            calls.append(req.url.path)
        return httpx.Response(answer[0], json=answer[1])
    monkeypatch.setattr(app_module, "MusicBrainz", lambda: MusicBrainz(transport=httpx.MockTransport(handle), min_interval=0))


def rec(title, listens, mbid=None):
    return {"recording_mbid": mbid or f"m-{title}", "recording_name": title, "total_listen_count": listens}


def test_top_played_songs_come_from_listenbrainz(api, monkeypatch):
    c, con, lib_id = api
    ar, (one, two, three) = _album(con, lib_id, "Alpha", "A1", ["One", "Two", "Three"])
    con.execute("UPDATE items SET mbid='artist-id' WHERE id=?", (ar,))
    con.execute("UPDATE items SET mbid='rec-1', title='One (Remastered)', title_key='oneremastered' WHERE id=?", (one,))
    calls = []
    lb(monkeypatch, (200, [rec("Not Owned", 900), rec("Two!", 500), rec("Two", 400), rec("Uno", 300, "rec-1"), rec("Three", 100)]), calls)
    url = f"/api/items/{ar}/top-tracks"

    r = c.get(url).json()  # by title without its punctuation, by recording id, a song's second recording left out
    assert [(t["id"], t["listens"]) for t in r["tracks"]] == [(two, 500), (one, 300), (three, 100)] and r["total"] == 3
    assert calls == ["/1/popularity/top-recordings-for-artist/artist-id"]
    assert r["tracks"][0]["album"] == "A1" and r["tracks"][0]["playback"]["url"]  # a play queue
    r = c.get(url, params={"limit": 2}).json()
    assert [t["id"] for t in r["tracks"]] == [two, one] and r["total"] == 3
    assert len(calls) == 1  # kept: not asked again

    con.execute("UPDATE artist_popularity SET fetched_at = fetched_at - ?", (music.POPULAR_REFRESH + 1,))
    lb(monkeypatch, (503, {}), calls)
    assert c.get(url).json()["total"] == 3 and len(calls) == 2  # asked again; a failure keeps what we had

    assert c.get(f"/api/items/{one}/top-tracks").status_code == 404


def test_top_played_songs_without_an_identified_artist_or_lookups(api, monkeypatch):
    c, con, lib_id = api
    ar, _ = _album(con, lib_id, "Alpha", "A1", ["One"])
    calls = []
    lb(monkeypatch, (200, [rec("One", 5)]), calls)
    assert c.get(f"/api/items/{ar}/top-tracks").json() == {"tracks": [], "total": 0, "token": None}  # no id yet
    con.execute("UPDATE items SET mbid='artist-id' WHERE id=?", (ar,))
    set_setting(con, "music_lookup", "0")
    assert c.get(f"/api/items/{ar}/top-tracks").json()["total"] == 0
    assert calls == []  # the owner turned lookups off


def test_top_played_songs_send_the_admins_listenbrainz_token(api, monkeypatch):
    """ListenBrainz wants a token for its popularity data (401 without): the admin's own, saved in Settings."""
    c, con, lib_id = api
    ar, (one,) = _album(con, lib_id, "Alpha", "A1", ["One"])
    con.execute("UPDATE items SET mbid='artist-id' WHERE id=?", (ar,))
    good = "tok-1234"  # privacy-check: ok (made up)
    seen = []

    def handle(req):
        auth = req.headers.get("authorization")
        seen.append((req.url.path, auth))
        if req.url.path == "/1/validate-token":
            return httpx.Response(200, json={"valid": auth == f"Token {good}", "user_name": "someone"})
        if auth != f"Token {good}":
            return httpx.Response(401, json={"code": 401, "error": "you need to provide an Auth token"})
        return httpx.Response(200, json=[rec("One", 7)])
    monkeypatch.setattr(app_module, "MusicBrainz", lambda: MusicBrainz(transport=httpx.MockTransport(handle), min_interval=0))
    url = f"/api/items/{ar}/top-tracks"

    r = c.get(url).json()
    assert (r["tracks"], r["token"]) == ([], "missing")  # the page says an admin can add one
    assert seen[-1] == ("/1/popularity/top-recordings-for-artist/artist-id", None)

    bad = c.put("/api/settings/listenbrainz-token", json={"key": "nope-0000"})
    assert bad.status_code == 400 and "isn't valid" in bad.json()["detail"]
    assert c.get("/api/settings").json()["listenbrainz"]["configured"] is False  # not saved
    assert c.put("/api/settings/listenbrainz-token", json={"key": "has space"}).status_code == 400

    saved = c.put("/api/settings/listenbrainz-token", json={"key": f"  {good} "}).json()
    assert saved == {"configured": True, "last4": "1234", "user": "someone", "checked": True}
    assert good not in c.get("/api/settings").text  # never sent back

    r = c.get(url).json()
    assert [(t["id"], t["listens"]) for t in r["tracks"]] == [(one, 7)] and r["token"] is None
    assert seen[-1][1] == f"Token {good}"

    # a token ListenBrainz stops accepting says so
    con.execute("DELETE FROM artist_popularity")
    set_setting(con, "listenbrainz_token", "old-9999")
    assert c.get(url).json()["token"] == "refused"
    assert c.delete("/api/settings/listenbrainz-token").json() == {"configured": False, "last4": None, "user": None}


def test_listenbrainz_token_saved_unchecked_when_listenbrainz_is_down(api, monkeypatch):
    c, con, lib_id = api
    lb(monkeypatch, (503, {}))
    r = c.put("/api/settings/listenbrainz-token", json={"key": "tok-5678"}).json()  # privacy-check: ok (made up)
    assert (r["configured"], r["checked"], r["user"]) == (True, False, None)


@pytest.mark.parametrize("title, key", [
    ("Song - 2011 Remaster", "song"), ("Song (Live)", "song"), ("Song [Remastered] (feat. Guest)", "song"),
    ("Song (Live) - Remastered 2009", "song"), ("(Untitled)", "untitled"), ("Weird Fishes/Arpeggi", "weirdfishesarpeggi"),
])
def test_song_key_drops_version_notes(title, key):
    assert music.song_key(title) == key


def test_top_played_songs_match_titles_with_version_notes(api, monkeypatch):
    """The files say "Song - 2011 Remaster", ListenBrainz says "Song": the same song. A song's exact title still wins."""
    c, con, lib_id = api
    ar, (remaster, live, plain) = _album(con, lib_id, "Alpha", "A1", ["Hit - 2011 Remaster", "Ballad (Live)", "Ballad"])
    con.execute("UPDATE items SET mbid='artist-id' WHERE id=?", (ar,))
    lb(monkeypatch, (200, [rec("Hit", 900), rec("Ballad", 500), rec("Ballad (Live at Somewhere)", 50)]))
    r = c.get(f"/api/items/{ar}/top-tracks").json()
    assert [(t["id"], t["listens"]) for t in r["tracks"]] == [(remaster, 900), (plain, 500)] and r["total"] == 2
