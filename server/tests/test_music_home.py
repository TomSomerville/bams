"""Music Home (owner 2026-11-18): Recently Added, Released This Week, holiday songs, their Shuffles; albums' release
dates (music.fill_release_dates, match_album) and the holiday data in download manifests."""

import datetime as dt

import pytest

from bams import holidays, library, music, readonly
from bams.app import create_app
from bams.config import Paths
from bams.db import connect, jdump
from bams.scanner import scan_library
from conftest import make_tree, signed_in


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(holidays, "today", lambda: dt.date(2026, 11, 18))  # a Wednesday; Sun 15 .. Sat 21
    paths = Paths(tmp_path / "data")
    media = tmp_path / "media"
    media.mkdir()
    app = create_app(paths, start_scheduler=False)
    con = connect(paths.db)
    yield signed_in(app), con, paths, media
    con.close()
    readonly.set_protected_roots([])


def _scan(con, paths, media, files):
    make_tree(media, files)
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    album = {r["title"]: r["id"] for r in con.execute("SELECT id, title FROM items WHERE kind='album'")}
    return lib_id, album


@pytest.mark.parametrize("text, want", [
    ("Jingle Bell Rock", {"christmas"}),
    ("Silent Night", {"christmas"}),
    ("Rudolph the Red-Nosed Reindeer", {"christmas"}),
    ("Let It Snow! Let It Snow! Let It Snow!", {"christmas"}),
    ("Monster Mash", {"halloween"}),
    ("Santa Monica", set()),                      # a place, not Santa Claus
    ("Noel", set()),                              # a name too
    ("Thriller", set()),
    ("Snow", set()),
])
def test_song_words(text, want):
    assert holidays.song_matches(text) == want


def test_upcoming_holidays():
    got = [(h.id, str(d)) for h, d in holidays.upcoming(dt.date(2026, 11, 18), 45)]
    assert got == [("thanksgiving", "2026-11-26"), ("hanukkah", "2026-12-04"), ("christmas", "2026-12-25"),
                   ("kwanzaa", "2026-12-26"), ("new_year", "2027-01-01")]
    assert [h.id for h, _ in holidays.upcoming(dt.date(2026, 12, 25), 0)] == ["christmas"]  # the day itself counts


def test_release_dates():
    assert music.full_date("1994-11-21") == "1994-11-21"
    assert music.full_date("1994-11-21T00:00:00Z") == "1994-11-21"
    assert music.full_date("1994") is None and music.full_date("1994-11") is None
    assert music.full_date("1994-02-30") is None
    assert music.release_date(1994, "2004-11-21", "1994-11-22") == "1994-11-22"  # a reissue's date is passed over
    assert music.release_date(None, "2004-11-21") == "2004-11-21"


def test_release_dates_from_tags(api):
    _, con, paths, media = api
    lib_id, album = _scan(con, paths, media, ["Band/Record/01 - One.mp3", "Band/Record/02 - Two.mp3",
                                              "Band/Matched/01 - Song.mp3", "Band/Plain/01 - Song.mp3"])
    tags = {"Record": {"date": "2003-11-17", "originaldate": "1993-11-16"}, "Matched": {"date": "1980-11-20"},
            "Plain": {"date": "2001"}}
    for r in con.execute("""SELECT f.id, al.title FROM files f JOIN file_items fi ON fi.file_id=f.id
                            JOIN items t ON t.id=fi.item_id JOIN items al ON al.id=t.parent_id""").fetchall():
        con.execute("UPDATE files SET probe=? WHERE id=?", (jdump({"tags": tags[r["title"]]}), r["id"]))
    con.execute("UPDATE items SET year=1993 WHERE id=?", (album["Record"],))
    # identified, with MusicBrainz's day: the tags don't replace it
    con.execute("UPDATE items SET match_status='matched', air_date='1981-01-02', year=1981 WHERE id=?",
                (album["Matched"],))
    music.fill_release_dates(con, lib_id)
    got = dict(con.execute("SELECT title, air_date FROM items WHERE kind='album'").fetchall())
    assert got == {"Record": "1993-11-16", "Matched": "1981-01-02", "Plain": None}


def test_music_home(api):
    client, con, paths, media = api
    lib_id, album = _scan(con, paths, media, [
        "Band/Old Record/01 - Song.mp3", "Band/Old Record/02 - Other.mp3",
        "Band/This Week/01 - A.mp3", "Band/This Week/02 - B.mp3",
        "Band/Last Year Too/01 - C.mp3",
        "Band/Not This Week/01 - D.mp3",
        "Crooner/A Christmas Record/01 - Song One.mp3", "Crooner/A Christmas Record/02 - Song Two.mp3",
        "Crooner/Standards/01 - Silent Night.mp3", "Crooner/Standards/02 - Fly Me.mp3",
        "Crooner/Standards/03 - Monster Mash.mp3",
    ])
    dates = {"This Week": "1984-11-15", "Last Year Too": "2025-11-21", "Not This Week": "1999-11-22",
             "Old Record": "1970-01-01"}
    for title, d in dates.items():
        con.execute("UPDATE items SET air_date=? WHERE id=?", (d, album[title]))
    for i, title in enumerate(["Old Record", "This Week", "Last Year Too", "Not This Week", "A Christmas Record",
                               "Standards"]):
        con.execute("UPDATE items SET added_at=? WHERE id=?", (1000 + i, album[title]))
    con.commit()

    home = client.get(f"/api/libraries/{lib_id}/music-home").json()
    assert [a["title"] for a in home["recent"]] == ["Standards", "A Christmas Record", "Not This Week", "Last Year Too",
                                                    "This Week", "Old Record"]
    assert (home["week"]["start"], home["week"]["end"]) == ("2026-11-15", "2026-11-21")
    assert [(a["title"], a["released"]) for a in home["week"]["albums"]] == [
        ("This Week", "1984-11-15"), ("Last Year Too", "2025-11-21")]
    # Halloween is past; Christmas is coming: its album's songs and its carols. No songs, no section (Thanksgiving).
    assert [(h["id"], h["date"], [t["title"] for t in h["tracks"]]) for h in home["holidays"]] == [
        ("christmas", "2026-12-25", ["Song One", "Song Two", "Silent Night"])]

    shuffled = client.get(f"/api/libraries/{lib_id}/music-home/christmas/random").json()
    assert shuffled["type"] == "music"
    assert sorted(t["title"] for t in shuffled["tracks"]) == ["Silent Night", "Song One", "Song Two"]
    week = client.get(f"/api/libraries/{lib_id}/music-home/week/random").json()
    assert sorted(t["title"] for t in week["tracks"]) == ["A", "B", "C"]
    recent = client.get(f"/api/libraries/{lib_id}/music-home/recent/random").json()
    assert len(recent["tracks"]) == 11
    assert client.get(f"/api/libraries/{lib_id}/music-home/nope/random").status_code == 404


def test_recently_added_keeps_twenty(api):
    client, con, paths, media = api
    lib_id, _ = _scan(con, paths, media, [f"Band/Record {n:02}/01 - Song.mp3" for n in range(25)])
    con.execute("UPDATE items SET added_at=id WHERE kind='album'")
    con.commit()
    recent = client.get(f"/api/libraries/{lib_id}/music-home").json()["recent"]
    assert len(recent) == 20 and recent[0]["title"] == "Record 24"


def test_week_includes_leap_day_in_other_years(api, monkeypatch):
    client, con, paths, media = api
    monkeypatch.setattr(holidays, "today", lambda: dt.date(2027, 3, 1))  # Mon; the week has 28 Feb, no 29 Feb
    lib_id, album = _scan(con, paths, media, ["Band/Leap/01 - Song.mp3"])
    con.execute("UPDATE items SET air_date='1996-02-29' WHERE id=?", (album["Leap"],))
    con.commit()
    assert [a["title"] for a in client.get(f"/api/libraries/{lib_id}/music-home").json()["week"]["albums"]] == ["Leap"]


def test_not_a_music_library(api, tmp_path):
    client, con, paths, _ = api
    films = tmp_path / "films"
    make_tree(films, ["Elf (2003)/Elf (2003).mkv"])
    lib_id = library.create(con, paths.root, "Films", "movie", [str(films)])
    assert client.get(f"/api/libraries/{lib_id}/music-home").status_code == 400


def test_manifest_has_holidays(api):
    client, con, paths, media = api
    con.execute("UPDATE users SET can_download=1")
    con.commit()
    _, album = _scan(con, paths, media, ["Crooner/Standards/01 - Silent Night.mp3", "Crooner/Standards/02 - Fly Me.mp3"])
    m = client.get(f"/api/items/{album['Standards']}/download").json()
    assert {t["title"]: t["holidays"] for t in m["tracks"]} == {"Silent Night": ["christmas"], "Fly Me": []}
    assert m["holidays"]["christmas"]["name"] == "Christmas"
    assert m["holidays"]["christmas"]["dates"][:2] == ["2026-12-25", "2027-12-25"]
    assert "released" in next(i for i in m["items"] if i["kind"] == "album")
