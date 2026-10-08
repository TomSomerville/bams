"""Music libraries: tag/path parsing, the artist > album > track graph, artwork, playback, schema v2."""

import sqlite3
import subprocess

import pytest
from fastapi.testclient import TestClient

from bams import db, library, music, probe, readonly, stream
from bams.app import create_app
from bams.config import Paths
from bams.jobs import run_scan
from bams.scanner import scan_library
from conftest import make_tree, signed_in
from test_readonly import snapshot

FFMPEG = stream.ffmpeg_path()
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and probe.ffprobe_path()), reason="FFmpeg/ffprobe not installed")


# ------------------------------------------------------------------ parsing

@pytest.mark.parametrize("rel, want", [
    # Plex layout
    ("Daft Punk/Discovery (2001)/01 - One More Time.flac",
     dict(album_artist="Daft Punk", album="Discovery", year=2001, track=1, title="One More Time")),
    ("Daft Punk/Discovery/03. Digital Love.mp3", dict(album="Discovery", track=3, title="Digital Love")),
    ("Daft Punk/Discovery/07 Superheroes.mp3", dict(track=7, title="Superheroes")),
    # disc folders, and disc-track prefixes
    ("Pink Floyd/The Wall/CD2/04 Comfortably Numb.flac",
     dict(album_artist="Pink Floyd", album="The Wall", disc=2, track=4, title="Comfortably Numb")),
    ("Pink Floyd/The Wall/Disc 1/1-02 In the Flesh.flac", dict(album="The Wall", disc=1, track=2)),
    ("Pink Floyd/The Wall/203 Hey You.flac", dict(disc=2, track=3, title="Hey You")),
    # "Artist - Album" folder, no artist folder; bracket noise after the year
    ("Radiohead - OK Computer (1997) [FLAC]/02 Paranoid Android.flac",
     dict(album_artist="Radiohead", album="OK Computer", year=1997, track=2, title="Paranoid Android")),
    # archive.org / FMA style names: artist and album prefixes dropped
    ("Broke For Free/Slam Funk (2010)/Broke_For_Free_-_01_-_Nothing_Like_Captain_Crunch.mp3",
     dict(album_artist="Broke For Free", album="Slam Funk", track=1, title="Nothing Like Captain Crunch")),
    ("Chris Zabriskie/Thoughtless (2015)/Chris Zabriskie - Thoughtless - 02 Another Version of You.mp3",
     dict(track=2, title="Another Version of You")),
    ("Kevin MacLeod/Oddities/Kevin_MacLeod_-_Fluffing_a_Duck.mp3", dict(track=None, title="Fluffing a Duck")),
    # compilations folder
    ("Various Artists/Now 10/01 Song.mp3", dict(album_artist=music.VARIOUS, compilation=True)),
    # loose file at the root
    ("01 - Mystery.mp3", dict(album_artist=music.UNKNOWN_ARTIST, album=music.UNKNOWN_ALBUM, track=1, title="Mystery")),
])
def test_parse_from_path(rel, want):
    t = music.parse_track(rel)
    for k, v in want.items():
        assert getattr(t, k) == v, (rel, k, getattr(t, k))
    assert t.source == "path"


def test_tags_win_over_the_path():
    probe_info = {"duration": 201.5, "tags": {
        "title": "Get Lucky", "artist": "Daft Punk feat. Pharrell Williams", "album_artist": "Daft Punk",
        "album": "Random Access Memories", "track": "8/13", "disc": "1/1", "date": "2013-05-17",
        "genre": "Disco;Funk;Disco"}}
    t = music.parse_track("misc/stuff/track08.mp3", probe_info)
    assert (t.album_artist, t.album, t.title, t.track, t.disc, t.year) == (
        "Daft Punk", "Random Access Memories", "Get Lucky", 8, 1, 2013)
    assert t.artist == "Daft Punk feat. Pharrell Williams"  # performer kept: differs from the album artist
    assert t.genres == ["Disco", "Funk"] and t.duration == 201.5 and t.source == "tags"


def test_tag_edge_cases():
    # track "0" means none; the album artist falls back to the artist; compilation flag
    t = music.parse_track("x/y/a.mp3", {"tags": {"title": "A", "artist": "Kevin MacLeod", "album": "Oddities",
                                                  "track": "0", "date": "2014-11-19T16:55:16"}})
    assert t.track is None and t.album_artist == "Kevin MacLeod" and t.artist is None and t.year == 2014
    t = music.parse_track("x/y/a.mp3", {"tags": {"title": "A", "artist": "Someone", "album": "Hits",
                                                  "compilation": "1"}})
    assert t.album_artist == music.VARIOUS and t.artist == "Someone"


def test_music_tags_normalised():
    # Vorbis-comment spellings (FLAC/Ogg from other taggers) and tags on the stream (Ogg/Opus)
    data = {"format": {"format_name": "ogg", "duration": "3.0"},
            "streams": [{"codec_type": "audio", "codec_name": "opus", "sample_rate": "48000",
                         "tags": {"TITLE": "T", "ARTIST": "A", "ALBUMARTIST": "AA", "TRACKNUMBER": "4",
                                  "DISCNUMBER": "2", "encoder": "x", "comment": "long text"}},
                        {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}}]}
    s = probe.summarize(data)
    assert s["tags"] == {"title": "T", "artist": "A", "album_artist": "AA", "track": "4", "disc": "2"}
    assert s["cover"] is True and s["video"] is None
    assert s["container"] == "OGG" and s["audio"][0]["codec"] == "Opus" and s["audio"][0]["sample_rate"] == 48000


@pytest.mark.parametrize("fmt, codec, container, label", [
    ("wav", "pcm_s24le", "WAV", "PCM"), ("aiff", "pcm_s16be", "AIFF", "PCM"), ("mov,mp4,m4a,3gp,3g2,mj2", "alac", "MP4", "ALAC"),
    ("flac", "flac", "FLAC", "FLAC"), ("mp3", "mp3", "MP3", "MP3"), ("asf", "wmav2", "WMV", "WMA"), ("ape", "ape", "APE", "APE"),
])
def test_audio_codec_and_container_names(fmt, codec, container, label):
    s = probe.summarize({"format": {"format_name": fmt}, "streams": [{"codec_type": "audio", "codec_name": codec}]})
    assert (s["container"], s["audio"][0]["codec"]) == (container, label)


def test_sort_title():
    assert music.sort_title("The Beatles") == "Beatles"
    assert music.sort_title("A Tribe Called Quest") == "Tribe Called Quest"
    assert music.sort_title("Theory of a Deadman") == "Theory of a Deadman"


# ------------------------------------------------------------------ scanning (folder layout only)

LAYOUT = [
    "Artist One/First Album (2001)/01 - Alpha.mp3",
    "Artist One/First Album (2001)/02 - Beta.mp3",
    "Artist One/Second Album (2005)/CD1/01 Gamma.flac",
    "Artist One/Second Album (2005)/CD2/01 Delta.flac",
    "Artist Two - Solo (2010)/01. Epsilon.ogg",
    "Artist Two - Solo (2010)/cover.jpg",          # not audio: not indexed
    "Artist One/First Album (2001)/notes.txt",
]


@pytest.fixture
def music_lib(env):
    paths, media, con = env
    make_tree(media, LAYOUT)
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    return paths, media, con, lib_id


def _graph(con, lib_id):
    out = {}
    for ar in con.execute("SELECT id, title FROM items WHERE library_id=? AND kind='artist'", (lib_id,)):
        for al in con.execute("SELECT id, title, year FROM items WHERE parent_id=?", (ar["id"],)):
            out[(ar["title"], al["title"], al["year"])] = sorted(
                (t["disc_number"], t["track_number"], t["title"])
                for t in con.execute("SELECT * FROM items WHERE parent_id=?", (al["id"],)))
    return out


def test_scan_builds_artist_album_track(music_lib):
    _, _, con, lib_id = music_lib
    st = scan_library(con, lib_id, do_probe=False)
    assert st.added == 5 and st.unrecognized == 0
    assert _graph(con, lib_id) == {
        ("Artist One", "First Album", 2001): [(None, 1, "Alpha"), (None, 2, "Beta")],
        ("Artist One", "Second Album", 2005): [(1, 1, "Gamma"), (2, 1, "Delta")],
        ("Artist Two", "Solo", 2010): [(None, 1, "Epsilon")],
    }
    d = library.describe(con, library.get(con, lib_id))
    assert d["counts"] == {"artist": 2, "album": 3, "track": 5} and d["files"]["unrecognized"] == 0


def test_rescan_is_stable_and_moves_keep_the_track(music_lib, unguarded):
    _, media, con, lib_id = music_lib
    scan_library(con, lib_id, do_probe=False)
    before = _graph(con, lib_id)
    track_id = con.execute("SELECT id FROM items WHERE kind='track' AND title='Epsilon'").fetchone()[0]
    st = scan_library(con, lib_id, do_probe=False)
    assert st.added == st.changed == 0 and _graph(con, lib_id) == before

    with unguarded:  # the user reorganises: Artist Two gets an artist folder
        (media / "Artist Two" / "Solo (2010)").mkdir(parents=True)
        (media / "Artist Two - Solo (2010)" / "01. Epsilon.ogg").rename(media / "Artist Two" / "Solo (2010)" / "01. Epsilon.ogg")
        (media / "Artist One" / "First Album (2001)" / "02 - Beta.mp3").unlink()
    st = scan_library(con, lib_id, do_probe=False)
    assert st.moved == 1 and st.missing == 1
    assert con.execute("SELECT id FROM items WHERE kind='track' AND title='Epsilon'").fetchone()[0] == track_id
    g = _graph(con, lib_id)
    assert ("Artist Two", "Solo", 2010) in g and len(g) == 3  # the old "Artist Two - Solo" album was cleaned up
    # a vanished file is flagged, never deleted (the drive may just be half-mounted), like video
    assert con.execute("SELECT available FROM files WHERE rel_path LIKE '%Beta.mp3'").fetchone()[0] == 0


def test_unchanged_files_reparsed_after_parser_bump(music_lib, monkeypatch):
    _, _, con, lib_id = music_lib
    scan_library(con, lib_id, do_probe=False)
    monkeypatch.setattr(music, "PARSER_VERSION", music.PARSER_VERSION + 1)
    assert scan_library(con, lib_id, do_probe=False).reparsed == 5


# ------------------------------------------------------------------ real files (FFmpeg)

def _ff(*args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *map(str, args)], check=True, capture_output=True)


def _make_album(media):
    """A small real album: FLAC with an embedded cover, ALAC in M4A, MP3 with a performer tag."""
    d = media / "Folder Name" / "Whatever"
    d.mkdir(parents=True)
    common = ["-metadata", "album=Real Album", "-metadata", "album_artist=Real Artist", "-metadata", "date=2019"]
    art = media.parent / "embedded.jpg"  # outside the library
    _ff("-f", "lavfi", "-i", "color=c=red:s=64x64:d=1", "-frames:v", "1", art)
    _ff("-f", "lavfi", "-i", "sine=f=440:d=3", "-i", art,
        "-map", "0", "-map", "1", "-c:v", "copy", "-disposition:v", "attached_pic",
        *common, "-metadata", "title=First", "-metadata", "track=1/3", "-metadata", "genre=Rock", d / "a.flac")
    _ff("-f", "lavfi", "-i", "sine=f=550:d=3", "-c:a", "alac", *common, "-metadata", "title=Second",
        "-metadata", "track=2/3", d / "b.m4a")
    _ff("-f", "lavfi", "-i", "sine=f=660:d=3", "-c:a", "libmp3lame", *common, "-metadata", "title=Third",
        "-metadata", "track=3/3", "-metadata", "artist=Guest Star", d / "c.mp3")
    return d


@needs_ffmpeg
def test_real_album_tags_cover_playback_and_media_untouched(tmp_path):
    paths = Paths(tmp_path / "data")
    media = tmp_path / "media"
    _make_album(media)
    before = snapshot(media)
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Music", "type": "music", "paths": [str(media)]}).json()
        res = run_scan(paths, lib["id"], do_match=False)  # offline: identification has its own tests
        assert res["status"] == "ok" and res["artwork"]["album_covers"] == 1, res

        artists = c.get(f"/api/libraries/{lib['id']}/items").json()
        assert [a["title"] for a in artists] == ["Real Artist"]
        assert artists[0]["poster"]  # falls back to the album cover
        albums = c.get(f"/api/libraries/{lib['id']}/items?kind=album").json()
        assert [(a["title"], a["year"], a["parent_title"]) for a in albums] == [("Real Album", 2019, "Real Artist")]
        assert albums[0]["genres"] == ["Rock"] and albums[0]["duration"] > 8
        img = c.get(albums[0]["poster"])
        assert img.status_code == 200 and img.content[:3] == b"\xff\xd8\xff"  # the embedded JPEG, copied out

        album = c.get(f"/api/items/{albums[0]['id']}").json()
        assert [(t["track_number"], t["title"], t["artist"]) for t in album["children"]] == [
            (1, "First", None), (2, "Second", None), (3, "Third", "Guest Star")]

        tracks = c.get(f"/api/items/{artists[0]['id']}/tracks").json()
        modes = {t["title"]: (t["playback"]["mode"], t["playback"]["url"].rsplit("/", 1)[1]) for t in tracks}
        assert modes == {"First": ("file", "stream"), "Second": ("transcode", "audio"), "Third": ("file", "stream")}
        assert tracks[2]["artist"] == "Guest Star" and tracks[0]["artist"] == "Real Artist"

        # ALAC -> AAC in fragmented MP4, from the start and from a seek point
        for t in (0, 1.5):
            r = c.get(f"/api/files/{tracks[1]['file_id']}/audio?t={t}")
            assert r.status_code == 200 and r.headers["content-type"] == "audio/mp4" and b"ftyp" in r.content[:16]
        assert c.get(tracks[0]["playback"]["url"]).status_code == 200

        assert c.get(f"/api/items?kind=album,track&q=Second").json()[0]["kind"] == "track"
        assert c.get(f"/api/libraries/{lib['id']}/items?kind=show").status_code == 400
    finally:
        readonly.set_protected_roots([])
    assert snapshot(media) == before  # scanning, probing, cover extraction and streaming changed nothing


@needs_ffmpeg
def test_folder_cover_and_artist_image_preferred(tmp_path):
    paths = Paths(tmp_path / "data")
    media = tmp_path / "media"
    d = _make_album(media)
    _ff("-f", "lavfi", "-i", "color=c=blue:s=32x32:d=1", "-frames:v", "1", d / "Cover.PNG")
    _ff("-f", "lavfi", "-i", "color=c=green:s=32x32:d=1", "-frames:v", "1", d.parent / "artist.jpg")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Music", "type": "music", "paths": [str(media)]}).json()
        res = run_scan(paths, lib["id"], do_match=False)  # offline: identification has its own tests
        assert res["artwork"] == {"albums_checked": 1, "album_covers": 1, "artist_images": 1, "errors": 0}
        album = c.get(f"/api/libraries/{lib['id']}/items?kind=album").json()[0]
        assert album["poster"].endswith(".png")  # the folder image beat the embedded one
        artist = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
        assert artist["poster"].endswith(".jpg") and artist["poster"] != album["poster"]
        # a second scan doesn't look at albums whose tracks didn't change
        assert run_scan(paths, lib["id"], do_match=False)["artwork"]["albums_checked"] == 0
    finally:
        readonly.set_protected_roots([])


# ------------------------------------------------------------------ playback plan

@pytest.mark.parametrize("container, codec, ok", [
    ("MP3", "MP3", True), ("MP4", "AAC", True), ("FLAC", "FLAC", True), ("OGG", "Opus", True),
    ("OGG", "Vorbis", True), ("WAV", "PCM", True),
    ("MP4", "ALAC", False), ("AIFF", "PCM", False), ("WMV", "WMA", False), ("APE", "APE", False),
    ("WavPack", "WavPack", False), ("DSF", "DSD", False), ("MKV", "FLAC", False), ("AC3", "AC3", False),
])
def test_plan_audio(container, codec, ok, monkeypatch):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    pb = stream.plan_audio({"container": container, "audio": [{"codec": codec}]}, "x")
    assert pb["mode"] == ("file" if ok else "transcode")


def test_plan_audio_before_probe(monkeypatch):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    assert stream.plan_audio(None, "a/b.flac")["mode"] == "file"
    assert stream.plan_audio(None, "a/b.ape")["mode"] == "transcode"
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: None)
    assert stream.plan_audio(None, "a/b.ape")["mode"] == "file"  # best effort without FFmpeg


# ------------------------------------------------------------------ schema migration

def test_v1_database_migrates_keeping_everything(tmp_path):
    path = tmp_path / "old.db"
    con = db.connect(path)
    con.executescript("BEGIN;" + db.SCHEMA + "PRAGMA user_version = 1; COMMIT;")  # a v1 install
    con.execute("INSERT INTO libraries (id, name, type, created_at) VALUES (1, 'TV', 'show', 0)")
    con.execute("INSERT INTO library_roots (id, library_id, path) VALUES (1, 1, '/tv')")
    con.execute("""INSERT INTO items (id, library_id, kind, title, tmdb_id, match_status, added_at, updated_at)
                   VALUES (1, 1, 'show', 'Show', 42, 'matched', 0, 0)""")
    con.execute("""INSERT INTO items (id, library_id, kind, parent_id, title, season_number, added_at, updated_at)
                   VALUES (2, 1, 'season', 1, 'Season 1', 1, 0, 0)""")
    con.execute("""INSERT INTO items (id, library_id, kind, parent_id, title, season_number, episode_number,
                   added_at, updated_at) VALUES (3, 1, 'episode', 2, 'Pilot', 1, 1, 0, 0)""")
    con.execute("INSERT INTO item_keys VALUES (1, 'show', 'show', 0, 1)")
    con.execute("""INSERT INTO files (id, library_id, root_id, rel_path, size, mtime_ns, first_seen, last_seen)
                   VALUES (1, 1, 1, 'Show/S01E01.mkv', 1, 1, 0, 0)""")
    con.execute("INSERT INTO file_items VALUES (1, 3)")

    db.migrate(con, backup_dir=tmp_path / "backups")
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert con.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 3
    assert tuple(con.execute("SELECT tmdb_id, match_status FROM items WHERE id=1").fetchone()) == (42, "matched")
    assert [tuple(r) for r in con.execute("SELECT * FROM file_items")] == [(1, 3)]  # not cascade-deleted by the rebuild
    assert con.execute("SELECT item_id FROM item_keys").fetchone()[0] == 1
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    # the new kinds and columns exist, and cascades still work after the rename
    con.execute("""INSERT INTO items (library_id, kind, title, track_number, added_at, updated_at)
                   VALUES (1, 'track', 't', 1, 0, 0)""")
    con.execute("DELETE FROM items WHERE id=3")
    assert con.execute("SELECT COUNT(*) FROM file_items").fetchone()[0] == 0
    backups = list((tmp_path / "backups").iterdir())
    assert len(backups) == 1
    assert sqlite3.connect(backups[0]).execute("PRAGMA user_version").fetchone()[0] == 1
    con.close()
