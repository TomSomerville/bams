"""Playlists people make (owner 2026-10-13): private to their account, songs/albums/artists added once each,
reordered and trimmed, renamed, deleted, copied from an imported playlist, downloaded to the Android app; and the
quality details every track carries for the players' quality line."""

from bams import jobs, readonly
from bams.app import create_app
from bams.config import Paths
from conftest import PASSWORD, make_tree, signed_in


def _login(c, name):
    c.cookies.clear()
    assert c.post("/api/auth/login", json={"name": name, "password": PASSWORD}).status_code == 200


def _music(tmp_path):
    media = tmp_path / "media"
    make_tree(media, ["Daft Punk/Discovery/01 - One More Time.mp3", "Daft Punk/Discovery/02 - Aerodynamic.mp3",
                      "Daft Punk/Homework/01 - Daftendirekt.mp3", "Air/Moon Safari/01 - La femme d'argent.mp3"])
    (media / "Playlists").mkdir()
    (media / "Playlists/Mix.m3u").write_text("../Air/Moon Safari/01 - La femme d'argent.mp3\n"
                                             "../Daft Punk/Discovery/02 - Aerodynamic.mp3\n")
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    lib = c.post("/api/libraries", json={"name": "Music", "type": "music", "paths": [str(media)]}).json()
    jobs.run_scan(paths, lib["id"], do_match=False)
    by = {a["title"]: a for a in c.get(f"/api/libraries/{lib['id']}/items").json()}
    albums = {a["title"]: a for a in c.get(f"/api/libraries/{lib['id']}/items?kind=album").json()}
    return c, lib, by, albums


def titles(pl):
    return [t["title"] for t in pl["tracks"]]


def test_make_fill_edit_and_delete_a_playlist(tmp_path):
    c, lib, artists, albums = _music(tmp_path)
    try:
        assert c.post("/api/user-playlists", json={"name": "   "}).status_code == 400
        pl = c.post("/api/user-playlists", json={"name": " Running ", "description": "Fast ones"}).json()
        assert (pl["name"], pl["description"], pl["track_count"], pl["user"]) == ("Running", "Fast ones", 0, True)

        r = c.post(f"/api/user-playlists/{pl['id']}/items", json={"items": [albums["Discovery"]["id"]]}).json()
        assert (r["added"], r["skipped"], r["track_count"]) == (2, 0, 2)
        # the artist: Discovery's tracks are in already, Homework's is added
        r = c.post(f"/api/user-playlists/{pl['id']}/items", json={"items": [artists["Daft Punk"]["id"]]}).json()
        assert (r["added"], r["skipped"]) == (1, 2)
        one = c.get(f"/api/user-playlists/{pl['id']}").json()
        assert titles(one) == ["One More Time", "Aerodynamic", "Daftendirekt"]
        assert c.post(f"/api/user-playlists/{pl['id']}/items", json={"items": [lib["id"] + 9999]}).status_code == 400

        ids = [t["id"] for t in one["tracks"]]
        one = c.put(f"/api/user-playlists/{pl['id']}/tracks", json={"tracks": [ids[2], ids[0], 424242]}).json()
        assert titles(one) == ["Daftendirekt", "One More Time"]  # reordered, one taken out, a stranger ignored

        r = c.patch(f"/api/user-playlists/{pl['id']}", json={"name": "Runs", "description": ""}).json()
        assert (r["name"], r["description"]) == ("Runs", "")
        assert [p["name"] for p in c.get("/api/user-playlists").json()] == ["Runs"]
        assert c.delete(f"/api/user-playlists/{pl['id']}").status_code == 204
        assert c.get("/api/user-playlists").json() == []
    finally:
        readonly.set_protected_roots([])


def test_playlists_are_private(tmp_path):
    c, lib, artists, albums = _music(tmp_path)
    try:
        mine = c.post("/api/user-playlists", json={"name": "Mine", "items": [artists["Air"]["id"]]}).json()
        assert mine["track_count"] == 1
        c.post("/api/users", json={"name": "kid", "password": PASSWORD})
        _login(c, "kid")
        assert c.get("/api/user-playlists").json() == []
        for r in (c.get(f"/api/user-playlists/{mine['id']}"),
                  c.patch(f"/api/user-playlists/{mine['id']}", json={"name": "x"}),
                  c.post(f"/api/user-playlists/{mine['id']}/items", json={"items": [artists["Air"]["id"]]}),
                  c.put(f"/api/user-playlists/{mine['id']}/tracks", json={"tracks": []}),
                  c.delete(f"/api/user-playlists/{mine['id']}"),
                  c.get(f"/api/user-playlists/{mine['id']}/download")):
            assert r.status_code in (403, 404), r.status_code  # the download: no rights *and* not theirs
        _login(c, "admin")
        assert c.get(f"/api/user-playlists/{mine['id']}").json()["track_count"] == 1  # untouched
    finally:
        readonly.set_protected_roots([])


def test_copy_of_an_imported_playlist_and_download(tmp_path):
    c, lib, artists, albums = _music(tmp_path)
    try:
        mix = c.get(f"/api/libraries/{lib['id']}/playlists").json()[0]
        copy = c.post("/api/user-playlists", json={"name": "Mix (copy)", "copy_of": mix["id"]}).json()
        one = c.get(f"/api/user-playlists/{copy['id']}").json()
        assert titles(one) == ["La femme d'argent", "Aerodynamic"]
        assert c.post("/api/user-playlists", json={"name": "x", "copy_of": 999}).status_code == 404

        m = c.get(f"/api/user-playlists/{copy['id']}/download").json()
        assert m["root"] == {"kind": "user_playlist", "id": copy["id"], "title": "Mix (copy)"}
        assert m["playlist"]["user"] and len(m["files"]) == 2 and titles(m) == titles(one)
    finally:
        readonly.set_protected_roots([])


def test_tracks_carry_their_quality(tmp_path):
    c, lib, artists, albums = _music(tmp_path)
    try:
        t = c.get(f"/api/items/{albums['Discovery']['id']}/tracks").json()[0]
        assert {"sample_rate", "bit_depth", "bitrate", "channels"} <= set(t["playback"])
    finally:
        readonly.set_protected_roots([])


def test_quality_of_a_real_flac(tmp_path):
    import subprocess

    import pytest

    from bams import probe, stream
    ff = stream.ffmpeg_path()
    if not (ff and probe.ffprobe_path()):
        pytest.skip("FFmpeg/ffprobe not installed")
    media = tmp_path / "media"
    (media / "Artist/Album").mkdir(parents=True)
    subprocess.run([ff, "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2",
                    "-sample_fmt", "s32", "-c:a", "flac", str(media / "Artist/Album/01 - Tone.flac")], check=True)
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Music", "type": "music", "paths": [str(media)]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        album = c.get(f"/api/libraries/{lib['id']}/items?kind=album").json()[0]
        pb = c.get(f"/api/items/{album['id']}/tracks").json()[0]["playback"]
        assert (pb["audio_codec"], pb["sample_rate"], pb["bit_depth"], pb["channels"]) == ("FLAC", 48000, 24, 1)
        assert pb["bitrate"] and pb["bitrate"] > 0
    finally:
        readonly.set_protected_roots([])
