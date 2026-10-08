"""Music follow-ups: CUE-sheet albums, playlist import, a cover.jpg added later, merging albums pinned to the
same MusicBrainz release, refreshing identified music, and lossless (FLAC) conversion."""

import os
import subprocess
import time
from pathlib import Path

import pytest

from bams import app as app_module
from bams import cue, jobs, library, music, music_match, playlists, probe, readonly, stream
from bams.app import create_app
from bams.db import jdump, jload
from bams.musicbrainz import MusicBrainz
from bams.scanner import scan_library
from conftest import make_tree, signed_in
from test_music_match import JPEG, REL_ID, fake
from test_readonly import snapshot

FFMPEG = stream.ffmpeg_path()
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and probe.ffprobe_path()), reason="FFmpeg/ffprobe not installed")

SHEET = '''REM GENRE "Progressive Rock"
REM DATE 1979
PERFORMER "Pink Floyd"
TITLE "The Wall"
FILE "The Wall.wav" WAVE
  TRACK 01 AUDIO
    TITLE "In the Flesh?"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "The Thin Ice"
    PERFORMER "Pink Floyd feat. Nobody"
    INDEX 00 03:17:20
    INDEX 01 03:19:40
  TRACK 03 AUDIO
    TITLE "Another Brick in the Wall, Part 1"
    INDEX 01 05:46:00
'''


def tracks_of(con, title):
    return con.execute("""SELECT t.title, t.track_number, t.artist, t.duration, fi.cue_start, fi.cue_end
                          FROM items t JOIN items a ON a.id=t.parent_id JOIN file_items fi ON fi.item_id=t.id
                          WHERE a.title=? ORDER BY t.track_number""", (title,)).fetchall()


# ------------------------------------------------------------------ cue sheets

def test_cue_sheet_parsing():
    sh = cue.parse(SHEET)
    assert (sh.title, sh.performer, sh.date, sh.genre) == ("The Wall", "Pink Floyd", "1979", "Progressive Rock")
    [f] = sh.files
    assert f.name == "The Wall.wav" and [t.number for t in f.tracks] == [1, 2, 3]
    t1, t2, t3 = f.tracks
    assert (t1.start, t1.end) == (0, 3 * 60 + 19 + 40 / 75)  # the pregap (INDEX 00) stays with track 1
    assert t2.performer == "Pink Floyd feat. Nobody" and t3.end is None
    # the sheet was made for a .wav that's now a .flac: matched by name without the extension
    assert cue.file_for(sh, "the wall.FLAC") is f and cue.file_for(sh, "Other.flac") is None
    assert cue.file_for(sh, "Other.flac", only_audio_file=True) is f
    assert cue.splits(f) and not cue.splits(None)
    # damaged / odd input never raises
    assert cue.parse('FILE "x\nTRACK zz AUDIO\nINDEX 01 junk\nTITLE "unbalanced').files[0].tracks == []
    two = cue.parse('FILE "a.flac" WAVE\n TRACK 01 AUDIO\n  INDEX 01 00:00:00\nFILE "b.flac" WAVE\n TRACK 02 AUDIO\n'
                    '  INDEX 01 00:00:00\n TRACK 03 DATA\n  INDEX 01 01:00:00\n')
    assert [len(f.tracks) for f in two.files] == [1, 1] and not cue.splits(cue.file_for(two, "a.flac"))


def test_cue_image_becomes_tracks_and_follows_the_sheet(env, unguarded):
    paths, media, con = env
    make_tree(media, ["Pink Floyd/The Wall/The Wall.flac", "Pink Floyd/Animals/01 - Dogs.flac"])
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    st = scan_library(con, lib_id, do_probe=False)
    assert st.cue_files == 0 and len(tracks_of(con, "The Wall")) == 1  # no sheet yet: one long track

    with unguarded:
        (media / "Pink Floyd/The Wall/The Wall.cue").write_text(SHEET, encoding="cp1252")
    st = scan_library(con, lib_id, do_probe=False)
    assert st.cue_files == 1 and st.reparsed == 1  # the audio didn't change; the new sheet re-read it
    rows = tracks_of(con, "The Wall")
    assert [r["title"] for r in rows] == ["In the Flesh?", "The Thin Ice", "Another Brick in the Wall, Part 1"]
    assert rows[1]["artist"] == "Pink Floyd feat. Nobody" and rows[0]["artist"] is None
    assert rows[0]["cue_start"] == 0 and rows[1]["cue_start"] == pytest.approx(199.533, abs=1e-3)
    assert rows[2]["cue_end"] is None and rows[2]["duration"] is None  # not probed: length of the file unknown
    al = con.execute("SELECT * FROM items WHERE kind='album' AND title='The Wall'").fetchone()
    assert al["year"] == 1979 and jload(al["genres"]) == ["Progressive Rock"]
    ids = [r[0] for r in con.execute("SELECT item_id FROM file_items fi JOIN files f ON f.id=fi.file_id "
                                     "WHERE f.rel_path LIKE '%The Wall.flac' ORDER BY cue_start")]

    # editing the sheet keeps the track rows (matched up by number)
    with unguarded:
        (media / "Pink Floyd/The Wall/The Wall.cue").write_text(SHEET.replace("The Thin Ice", "Thin Ice"))
        p = media / "Pink Floyd/The Wall/The Wall.cue"
        os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 10_000_000))  # same size: make sure it's newer
    scan_library(con, lib_id, do_probe=False)
    assert [r[0] for r in con.execute("SELECT item_id FROM file_items fi JOIN files f ON f.id=fi.file_id "
                                      "WHERE f.rel_path LIKE '%The Wall.flac' ORDER BY cue_start")] == ids
    assert tracks_of(con, "The Wall")[1]["title"] == "Thin Ice"

    # sheet gone: one track again
    with unguarded:
        (media / "Pink Floyd/The Wall/The Wall.cue").unlink()
    scan_library(con, lib_id, do_probe=False)
    assert len(tracks_of(con, "The Wall")) == 1


def test_cue_tracks_in_the_play_queue(tmp_path):
    media = tmp_path / "media"
    make_tree(media, ["Pink Floyd/The Wall/The Wall.ape"])
    (media / "Pink Floyd/The Wall/The Wall.cue").write_text(SHEET)
    c = signed_in(create_app(app_module.Paths(tmp_path / "data"), start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Music", "type": "music", "paths": [str(media)]}).json()
        jobs.run_scan(c.app.state.paths, lib["id"], do_match=False)
        album = c.get(f"/api/libraries/{lib['id']}/items?kind=album").json()[0]
        q = c.get(f"/api/items/{album['id']}/tracks").json()
        assert [(t["track_number"], t["start"], t["end"] is None) for t in q] == [
            (1, 0, False), (2, pytest.approx(199.533, abs=1e-3), False), (3, 346, True)]
        assert len({t["file_id"] for t in q}) == 1 and q[0]["duration"] == pytest.approx(199.533, abs=1e-3)
    finally:
        readonly.set_protected_roots([])


@needs_ffmpeg
def test_embedded_cue_sheet_in_a_real_flac(env):
    paths, media, con = env
    folder = media / "Artist" / "Live"
    folder.mkdir(parents=True)
    sheet = ('PERFORMER "Artist"\nTITLE "Live"\nFILE "live.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "Intro"\n'
             '    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "Song"\n    INDEX 01 00:02:00\n')
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=440:d=5",
                    "-metadata", f"CUESHEET={sheet}", "-c:a", "flac", str(folder / "live.flac")], check=True)
    before = snapshot(media)
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    st = scan_library(con, lib_id)
    assert st.cue_files == 1
    rows = tracks_of(con, "Live")
    assert [(r["title"], r["cue_start"]) for r in rows] == [("Intro", 0), ("Song", 2)]
    assert rows[1]["duration"] == pytest.approx(3, abs=0.1)  # to the end of the 5 s file
    assert snapshot(media) == before


# ------------------------------------------------------------------ playlists

def test_playlist_parsing():
    name, e = playlists.parse("Road trip.m3u8", "\ufeff#EXTM3U\n#PLAYLIST:Summer\n#EXTINF:215,Daft Punk - One More Time\n"
                                                "../Daft Punk/01.flac\n\nhttp://radio/stream\n")
    assert name == "Summer" and e == [{"path": "../Daft Punk/01.flac", "title": "Daft Punk - One More Time", "duration": 215},
                                      {"path": "http://radio/stream", "title": None, "duration": None}]
    name, e = playlists.parse("Mix.pls", "[playlist]\nFile2=b.mp3\nFile1=a.mp3\nTitle1=A\nLength1=-1\nNumberOfEntries=2\n")
    assert name == "Mix" and [x["path"] for x in e] == ["a.mp3", "b.mp3"] and e[0]["title"] == "A"
    assert e[0]["duration"] is None


def test_playlists_are_imported_and_follow_their_files(tmp_path, unguarded):
    media = tmp_path / "media"
    make_tree(media, ["Daft Punk/Discovery/01 - One More Time.mp3", "Daft Punk/Discovery/02 - Aerodynamic.mp3",
                      "Pink Floyd/The Wall/The Wall.flac"])
    (media / "Pink Floyd/The Wall/The Wall.cue").write_text(SHEET)
    pl = media / "Playlists"
    pl.mkdir()
    (pl / "Mix.m3u").write_text(
        "#EXTM3U\n../Daft Punk/Discovery/02 - Aerodynamic.mp3\n"              # relative
        "D:\\Old PC\\Music\\Daft Punk\\Discovery\\01 - One More Time.mp3\n"  # made on another computer
        f"{(media / 'Pink Floyd/The Wall/The Wall.flac').as_uri()}\n"        # file:// URL of a CUE image: its tracks
        "http://radio.example/stream\n../Nope/missing.mp3\n")
    (pl / "Two.pls").write_text("[playlist]\nFile1=../Daft Punk/Discovery/01 - One More Time.mp3\n")
    c = signed_in(create_app(app_module.Paths(tmp_path / "data"), start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Music", "type": "music", "paths": [str(media)]}).json()
        res = jobs.run_scan(c.app.state.paths, lib["id"], do_match=False)
        assert res["scan"]["playlists"] == 2
        lists = c.get(f"/api/libraries/{lib['id']}/playlists").json()
        assert [(p["name"], p["track_count"], p["missing"]) for p in lists] == [("Mix", 5, 2), ("Two", 1, 0)]
        mix = c.get(f"/api/playlists/{lists[0]['id']}").json()
        assert [t["title"] for t in mix["tracks"]] == ["Aerodynamic", "One More Time", "In the Flesh?", "The Thin Ice",
                                                       "Another Brick in the Wall, Part 1"]
        assert mix["path"] == "Playlists/Mix.m3u" and c.get("/api/playlists/999").status_code == 404

        # the file is the source: edited -> re-read, deleted -> gone. Nothing is ever written to it.
        with unguarded:
            (pl / "Mix.m3u").write_text("../Daft Punk/Discovery/01 - One More Time.mp3\n")
            (pl / "Two.pls").unlink()
        res = jobs.run_scan(c.app.state.paths, lib["id"], do_match=False)
        lists = c.get(f"/api/libraries/{lib['id']}/playlists").json()
        assert [(p["name"], p["track_count"], p["missing"]) for p in lists] == [("Mix", 1, 0)]
    finally:
        readonly.set_protected_roots([])


# ------------------------------------------------------------------ artwork

def test_cover_added_later_replaces_embedded_or_downloaded_art(env, unguarded):
    paths, media, con = env
    make_tree(media, ["Artist/Album/01 - a.mp3", "Artist/Other/01 - b.mp3"])
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    st = scan_library(con, lib_id, do_probe=False)
    assert music.fill_artwork(con, paths.images, lib_id, st.side).album_covers == 0
    # pretend the Cover Art Archive gave it a cover and Commons gave the artist a photo
    con.execute("""UPDATE items SET poster='music/caa.jpg', poster_src=? WHERE kind='album' AND title='Album'""",
                (jdump({"from": "caa"}),))
    con.execute("UPDATE items SET poster='music/commons.jpg', poster_src=?, extra=? WHERE kind='artist'",
                (jdump({"from": "commons"}), jdump({"image_credit": {"author": "Someone"}})))

    with unguarded:
        (media / "Artist/Album/cover.jpg").write_bytes(JPEG + b"1")
        (media / "Artist/artist.jpg").write_bytes(JPEG + b"artist")
    st = scan_library(con, lib_id, do_probe=False)
    art = music.fill_artwork(con, paths.images, lib_id, st.side)
    assert (art.album_covers, art.artist_images) == (1, 1)
    al = con.execute("SELECT poster, poster_src FROM items WHERE kind='album' AND title='Album'").fetchone()
    assert al["poster"] != "music/caa.jpg" and jload(al["poster_src"])["from"] == "folder"
    ar = con.execute("SELECT poster, extra FROM items WHERE kind='artist'").fetchone()
    assert (paths.images / ar["poster"]).read_bytes() == JPEG + b"artist" and jload(ar["extra"]) is None

    # unchanged: nothing re-read; replaced: picked up again
    assert music.fill_artwork(con, paths.images, lib_id, scan_library(con, lib_id, do_probe=False).side).album_covers == 0
    with unguarded:
        (media / "Artist/Album/cover.jpg").write_bytes(JPEG + b"22")
    st = scan_library(con, lib_id, do_probe=False)
    assert music.fill_artwork(con, paths.images, lib_id, st.side).album_covers == 1
    poster = con.execute("SELECT poster FROM items WHERE kind='album' AND title='Album'").fetchone()[0]
    assert (paths.images / poster).read_bytes() == JPEG + b"22"
    # without the walk's list (folders listed instead) it's the same answer
    assert music.fill_artwork(con, paths.images, lib_id).album_covers in (0, 1)

    # a refresh doesn't replace the owner's cover with a download
    con.execute("UPDATE items SET mbid=?, match_status='matched', metadata_at=0 WHERE kind='album' AND title='Album'",
                (REL_ID,))
    with MusicBrainz(transport=fake([]), min_interval=0) as mb:
        music_match.match_music_library(con, mb, paths.images, lib_id)
    assert con.execute("SELECT poster FROM items WHERE kind='album' AND mbid=?", (REL_ID,)).fetchone()[0] == poster


# ------------------------------------------------------------------ merging and refreshing

def _two_copies(env):
    paths, media, con = env
    make_tree(media, ["Real Artist/Real Album [FLAC]/01 - Track One.flac", "Real Artist/Real Album [FLAC]/02 - Track Two.flac",
                      "Real Artist/Real Album [MP3]/01 - Track One.mp3", "Real Artist/Real Album [MP3]/02 - Track Two.mp3",
                      "Real Artist/Real Album [MP3]/03 - Bonus.mp3"])
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    # the tags carry the folder's album name, and a MusicBrainz release id (as Picard writes them)
    for f in con.execute("SELECT id, rel_path FROM files").fetchall():
        album = f["rel_path"].split("/")[1]
        con.execute("UPDATE files SET probe=?, probed_at=1 WHERE id=?", (jdump({"audio": [{"codec": "MP3"}], "tags": {
            "album": album, "artist": "Real Artist", "musicbrainz_albumid": REL_ID}}), f["id"]))
    con.execute("UPDATE files SET parse=json_set(parse, '$.v', 0)")  # re-read with those tags
    scan_library(con, lib_id, do_probe=False)
    return paths, con, lib_id


def test_albums_pinned_to_the_same_release_are_merged(env, monkeypatch):
    paths, con, lib_id = _two_copies(env)
    assert con.execute("SELECT COUNT(*) FROM items WHERE kind='album'").fetchone()[0] == 2
    with MusicBrainz(transport=fake([]), min_interval=0) as mb:
        st = music_match.match_music_library(con, mb, paths.images, lib_id)
    assert st.merged == 1
    [al] = con.execute("SELECT * FROM items WHERE kind='album'").fetchall()
    assert al["mbid"] == REL_ID
    rows = con.execute("""SELECT t.id, t.title, COUNT(fi.file_id) n FROM items t JOIN file_items fi ON fi.item_id=t.id
                          WHERE t.parent_id=? GROUP BY t.id ORDER BY t.track_number""", (al["id"],)).fetchall()
    assert [(r["title"], r["n"]) for r in rows] == [("Track One", 2), ("Track Two", 2), ("Bonus", 1)]

    # later scans keep them together (the alias), even when every file is re-read
    monkeypatch.setattr(music, "PARSER_VERSION", music.PARSER_VERSION + 1)
    scan_library(con, lib_id, do_probe=False)
    assert con.execute("SELECT COUNT(*) FROM items WHERE kind='album'").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM items WHERE kind='track'").fetchone()[0] == 3

    # the play queue plays one file per track: the bigger one (here the FLAC; both play as-is)
    con.execute("UPDATE files SET size=size*10 WHERE rel_path LIKE '%.flac'")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        q = c.get(f"/api/items/{al['id']}/tracks").json()
        assert len(q) == 3 and all(t["file_id"] for t in q)
        flac = {r[0] for r in con.execute("SELECT id FROM files WHERE rel_path LIKE '%.flac'")}
        assert {t["file_id"] for t in q[:2]} <= flac
    finally:
        readonly.set_protected_roots([])


def test_unsure_matches_are_not_merged(env):
    paths, con, lib_id = _two_copies(env)
    a, b = [r[0] for r in con.execute("SELECT id FROM items WHERE kind='album' ORDER BY id")]
    for x in (a, b):
        con.execute("UPDATE items SET mbid=?, match_status='matched', match_score=0.9, extra=? WHERE id=?",
                    (REL_ID, jdump({"matched_by": "search"}), x))
    assert music_match.merge_same_release(con, b) == b
    con.execute("UPDATE items SET match_status='manual' WHERE id=?", (b,))  # Fix match: one side pinned isn't enough
    assert music_match.merge_same_release(con, b) == b
    con.execute("UPDATE items SET match_status='manual' WHERE id=?", (a,))
    assert music_match.merge_same_release(con, b) == a


def test_identified_music_is_refreshed_after_a_while(env):
    paths, media, con = env
    make_tree(media, ["Real Artist/Real Album/01 - Track One.mp3", "Real Artist/Real Album/02 - Track Two.mp3"])
    lib_id = library.create(con, paths.root, "Music", "music", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    calls: list = []
    with MusicBrainz(transport=fake(calls), min_interval=0) as mb:
        music_match.match_music_library(con, mb, paths.images, lib_id)
    al = con.execute("SELECT * FROM items WHERE kind='album'").fetchone()
    assert al["match_status"] == "matched" and jload(al["extra"])["matched_by"] == "search"
    score = al["match_score"]

    calls.clear()
    with MusicBrainz(transport=fake(calls), min_interval=0) as mb:
        st = music_match.match_music_library(con, mb, paths.images, lib_id)
    assert st.refreshed == 0 and calls == []  # fresh: left alone

    old = time.time() - music_match.REFRESH_AFTER - 10
    con.execute("UPDATE items SET metadata_at=?, overview=NULL WHERE kind IN ('album', 'artist')", (old,))
    with MusicBrainz(transport=fake(calls), min_interval=0) as mb:
        st = music_match.match_music_library(con, mb, paths.images, lib_id)
    assert st.refreshed == 2  # the album and its artist
    al = con.execute("SELECT * FROM items WHERE kind='album'").fetchone()
    assert al["overview"] == "About Real Album." and al["metadata_at"] > old
    assert al["match_score"] == score and jload(al["extra"])["matched_by"] == "search"  # how it was found is kept
    # the downloaded cover is fetched again (a better scan may have been uploaded); the owner's art never is
    assert jload(al["poster_src"]) == {"from": "caa"}
    assert any(c.url.host == "coverartarchive.org" for c in calls)


# ------------------------------------------------------------------ lossless conversion

def test_flac_output_command():
    cmd = stream.audio_cmd(Path("x.wv"), 12.5, {"codec": "WavPack", "sample_rate": 192000,
                                                                     "bit_depth": 24}, "flac")
    s = " ".join(cmd)
    assert "-c:a flac" in s and "-sample_fmt s32 -bits_per_raw_sample 24" in s and "-ar 96000" in s
    assert cmd[-3:] == ["-f", "flac", "pipe:1"] and "-ac" not in cmd  # channels kept
    s = " ".join(stream.audio_cmd(Path("x.dsf"), 0, {"codec": "DSD", "sample_rate": 2822400}, "flac"))
    assert "-sample_fmt s32" in s and "-ar 88200" in s
    s = " ".join(stream.audio_cmd(Path("x.m4a"), 0, {"codec": "ALAC", "sample_rate": 44100}, "flac"))
    assert "-sample_fmt s16" in s and "-ar" not in s
    assert "-c:a aac" in " ".join(stream.audio_cmd(Path("x.m4a"), 0, None))
    pb = stream.plan_audio({"container": "MP4", "audio": [{"codec": "ALAC"}]}, "x.m4a", "flac")
    assert pb["mode"] == "transcode" and pb["output"] == "flac"
    assert stream.plan_audio({"container": "FLAC", "audio": [{"codec": "FLAC"}]}, "x.flac", "flac")["output"] is None


@needs_ffmpeg
def test_flac_output_through_the_api(tmp_path):
    media = tmp_path / "media"
    (media / "A" / "B").mkdir(parents=True)
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=440:d=3",
                    "-c:a", "alac", str(media / "A" / "B" / "01 - x.m4a")], check=True)
    c = signed_in(create_app(app_module.Paths(tmp_path / "data"), start_scheduler=False))
    try:
        assert c.get("/api/settings").json()["music_output"] == "aac"
        lib = c.post("/api/libraries", json={"name": "Music", "type": "music", "paths": [str(media)]}).json()
        jobs.run_scan(c.app.state.paths, lib["id"], do_match=False)
        album = c.get(f"/api/libraries/{lib['id']}/items?kind=album").json()[0]
        [t] = c.get(f"/api/items/{album['id']}/tracks").json()
        assert t["playback"]["mode"] == "transcode" and t["playback"]["output"] == "aac"
        assert c.put("/api/settings/music-output", json={"output": "wav"}).status_code == 422
        assert c.put("/api/settings/music-output", json={"output": "flac"}).json() == {"music_output": "flac"}
        [t] = c.get(f"/api/items/{album['id']}/tracks").json()
        assert t["playback"]["output"] == "flac"
        r = c.get(t["playback"]["url"] + "?t=1")
        assert r.status_code == 200 and r.headers["content-type"] == "audio/flac" and r.content[:4] == b"fLaC"
    finally:
        readonly.set_protected_roots([])
