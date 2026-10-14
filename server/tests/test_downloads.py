"""Downloads to the Android app (owner 2026-10-13): a per-account switch (admins always), the original file with
its name and Range, and the manifests that say what to fetch for a title, a season, a show, music and playlists."""

from bams import jobs, readonly
from bams.app import create_app
from bams.config import Paths
from conftest import PASSWORD, make_tree, signed_in


def _login(c, name):
    c.cookies.clear()
    r = c.post("/api/auth/login", json={"name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text


def test_downloads_need_the_switch_and_send_the_original(tmp_path):
    media = tmp_path / "media"
    make_tree(media, ["Film (2001)/Film (2001).mkv"], size=100_000)
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Films", "type": "movie", "paths": [str(media)]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        item = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
        assert c.get("/api/auth/state").json()["user"]["can_download"]  # admins always may

        m = c.get(f"/api/items/{item['id']}/download").json()
        assert m["root"] == {"kind": "movie", "id": item["id"], "title": item["title"]}
        assert [f["name"] for f in m["files"]] == ["Film (2001).mkv"] and m["bytes"] == m["files"][0]["size"]
        assert m["files"][0]["items"] == [item["id"]] and m["items"][0]["id"] == item["id"]

        url = m["files"][0]["url"]
        r = c.get(url)
        original = (media / "Film (2001)/Film (2001).mkv").read_bytes()
        assert r.status_code == 200 and r.content == original
        assert r.headers["content-disposition"].startswith("attachment;") and "Film%20%282001%29.mkv" in r.headers["content-disposition"]
        r = c.get(url, headers={"Range": "bytes=1000-"})  # a broken download resumes
        assert r.status_code == 206 and r.content == original[1000:]

        # a viewer can't, until an admin turns it on (and off again)
        viewer = c.post("/api/users", json={"name": "kid", "password": PASSWORD}).json()
        assert viewer["can_download"] is False
        _login(c, "kid")
        assert c.get(url).status_code == 403
        assert c.get(f"/api/items/{item['id']}/download").status_code == 403
        assert c.get(f"/api/files/{m['files'][0]['id']}/stream").status_code == 200  # playing still works
        _login(c, "admin")
        assert c.patch(f"/api/users/{viewer['id']}", json={"can_download": True}).json()["can_download"] is True
        _login(c, "kid")
        assert c.get("/api/auth/state").json()["user"]["can_download"] and c.get(url).status_code == 200
        _login(c, "admin")
        c.patch(f"/api/users/{viewer['id']}", json={"can_download": False})
        _login(c, "kid")
        assert c.get(url).status_code == 403
    finally:
        readonly.set_protected_roots([])


def test_show_season_and_episode_manifests(tmp_path):
    media = tmp_path / "media"
    make_tree(media, ["Show/Season 01/Show - S01E01.mkv", "Show/Season 01/Show - S01E02.mkv",
                      "Show/Season 02/Show - S02E01.mkv"])
    (media / "Show/Season 01/Show - S01E01.en.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(media)]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        show = c.get(f"/api/libraries/{lib['id']}/items").json()[0]

        m = c.get(f"/api/items/{show['id']}/download").json()
        assert sorted(f["name"] for f in m["files"]) == ["Show - S01E01.mkv", "Show - S01E02.mkv", "Show - S02E01.mkv"]
        assert [d["kind"] for d in m["items"]].count("episode") == 3 and m["items"][0]["id"] == show["id"]
        e1 = next(f for f in m["files"] if f["name"] == "Show - S01E01.mkv")
        assert [s["url"] for s in e1["subtitles"]] == [f"/api/files/{e1['id']}/subtitles/x0.vtt"]
        assert c.get(e1["subtitles"][0]["url"]).status_code == 200

        season2 = next(s for s in c.get(f"/api/items/{show['id']}").json()["children"] if s["season_number"] == 2)
        m = c.get(f"/api/items/{season2['id']}/download").json()
        assert [f["name"] for f in m["files"]] == ["Show - S02E01.mkv"]
        assert [d["kind"] for d in m["items"]] == ["show", "season", "episode"]  # listed under its show offline

        ep = next(d for d in m["items"] if d["kind"] == "episode")
        m = c.get(f"/api/items/{ep['id']}/download").json()
        assert [d["kind"] for d in m["items"]] == ["show", "season", "episode"] and len(m["files"]) == 1
    finally:
        readonly.set_protected_roots([])


def test_music_and_playlist_manifests(tmp_path):
    media = tmp_path / "media"
    make_tree(media, ["Daft Punk/Discovery/01 - One More Time.mp3", "Daft Punk/Discovery/02 - Aerodynamic.mp3",
                      "Daft Punk/Homework/01 - Daftendirekt.mp3", "Air/Moon Safari/01 - La femme d'argent.mp3"])
    (media / "Playlists").mkdir()
    (media / "Playlists/Mix.m3u").write_text("../Air/Moon Safari/01 - La femme d'argent.mp3\n"
                                             "../Daft Punk/Discovery/02 - Aerodynamic.mp3\n")
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Music", "type": "music", "paths": [str(media)]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        artists = {a["title"]: a for a in c.get(f"/api/libraries/{lib['id']}/items").json()}

        m = c.get(f"/api/items/{artists['Daft Punk']['id']}/download").json()
        assert sorted(t["title"] for t in m["tracks"]) == ["Aerodynamic", "Daftendirekt", "One More Time"]
        assert len(m["files"]) == 3 and all(f["url"].endswith("/download") for f in m["files"])
        assert [d["kind"] for d in m["items"]] == ["artist", "album", "album"]

        album = next(d for d in m["items"] if d["kind"] == "album" and d["title"] == "Discovery")
        m = c.get(f"/api/items/{album['id']}/download").json()
        assert [d["kind"] for d in m["items"]] == ["artist", "album"] and len(m["tracks"]) == 2

        track = m["tracks"][0]
        m = c.get(f"/api/items/{track['id']}/download").json()
        assert len(m["files"]) == 1 and m["files"][0]["items"] == [track["id"]]

        pl = c.get(f"/api/libraries/{lib['id']}/playlists").json()[0]
        m = c.get(f"/api/playlists/{pl['id']}/download").json()
        assert m["root"]["kind"] == "playlist" and m["playlist"]["name"] == "Mix"
        assert [t["title"] for t in m["tracks"]] == ["La femme d'argent", "Aerodynamic"] and len(m["files"]) == 2
        assert {d["title"] for d in m["items"] if d["kind"] == "artist"} == {"Air", "Daft Punk"}
    finally:
        readonly.set_protected_roots([])
