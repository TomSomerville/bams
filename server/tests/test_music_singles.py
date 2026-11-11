"""Music: an artist's singles, told apart from albums (music.single_sql) and listed on their own."""

import pytest

from bams import library, readonly
from bams.app import create_app
from bams.config import Paths
from bams.db import connect, jdump
from conftest import make_tree, signed_in
from bams.scanner import scan_library


@pytest.fixture
def api(tmp_path):
    paths = Paths(tmp_path / "data")
    media = tmp_path / "media"
    media.mkdir()
    app = create_app(paths, start_scheduler=False)
    con = connect(paths.db)
    yield signed_in(app), con, paths, media
    con.close()
    readonly.set_protected_roots([])


def test_singles_are_counted_and_listed_apart_from_albums(api):
    client, con, paths, media = api
    make_tree(media, [
        *[f"Band/Big Record/0{n} - Song {n}.mp3" for n in range(1, 6)],     # 5 tracks: an album
        "Band/Hit/01 - Hit Song.mp3", "Band/Hit/02 - B Side.mp3",                  # 2 tracks: a single
        *[f"Band/Short EP/0{n} - EP {n}.mp3" for n in range(1, 3)],         # 2 tracks, but MusicBrainz says EP
        *[f"Band/Odd One/0{n} - Odd {n}.mp3" for n in range(1, 5)],         # 4 tracks, MusicBrainz says Single
        *[f"Band/Unknown/0{n} - Unknown {n}.mp3" for n in range(1, 4)],     # 3 tracks, not identified: an album
    ])
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    album = {r["title"]: r["id"] for r in con.execute("SELECT id, title FROM items WHERE kind='album'")}
    con.execute("UPDATE items SET extra=?, year=2001 WHERE id=?", (jdump({"type": "EP"}), album["Short EP"]))
    con.execute("UPDATE items SET extra=?, year=1999 WHERE id=?", (jdump({"type": "Single"}), album["Odd One"]))
    con.execute("UPDATE items SET year=2005 WHERE id=?", (album["Hit"],))
    con.commit()

    artists = client.get(f"/api/libraries/{lib_id}/items?kind=artist").json()
    assert [(a["title"], a["child_count"], a["single_count"]) for a in artists] == [("Band", 5, 2)]

    band = client.get(f"/api/items/{artists[0]['id']}").json()
    assert band["single_count"] == 2
    assert {a["title"]: a["single"] for a in band["children"]} == {
        "Big Record": False, "Hit": True, "Short EP": False, "Odd One": True, "Unknown": False}

    songs = client.get(f"/api/items/{band['id']}/singles").json()
    assert [(s["title"], s["album"], s["year"]) for s in songs] == [
        ("Odd 1", "Odd One", 1999), ("Odd 2", "Odd One", 1999), ("Odd 3", "Odd One", 1999), ("Odd 4", "Odd One", 1999),
        ("Hit Song", "Hit", 2005), ("B Side", "Hit", 2005)]
    assert client.get(f"/api/items/{album['Hit']}/singles").status_code == 404
