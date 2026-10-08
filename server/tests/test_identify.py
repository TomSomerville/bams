"""Identifying unrecognised files by hand (Settings → Unrecognized files / a library's Unrecognized tab)."""

import httpx
import pytest

from bams import identify, jobs, readonly
from bams.app import create_app
from bams.config import Paths
from bams.db import connect
from bams.tmdb import Tmdb
from conftest import make_tree, signed_in
from test_matcher import TOKEN


@pytest.fixture
def tv(tmp_path):
    media = tmp_path / "media"
    make_tree(media, ["Show (2010)/Season 01/Show - S01E01 - Pilot.mkv",
                      "Show (2010)/clip0042.mkv",   # no season folder, no number: unrecognised
                      "random stuff.mkv"])          # nothing to go on
    paths = Paths(tmp_path / "data")
    app = create_app(paths, start_scheduler=False)
    c = signed_in(app, "Tom")
    lib = c.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(media)]}).json()
    jobs.run_scan(paths, lib["id"], do_match=False)
    yield app, c, lib["id"], paths
    readonly.set_protected_roots([])


def _file(c, name):
    return next(f for f in c.get("/api/unrecognized").json() if f["path"].endswith(name))


def test_identify_unrecognised_file_and_keep_it(tv):
    app, c, lib_id, paths = tv
    files = c.get("/api/unrecognized").json()
    assert sorted(f["path"].rsplit("/", 1)[-1] for f in files) == ["clip0042.mkv", "random stuff.mkv"]
    clip = _file(c, "clip0042.mkv")
    assert clip["hint"] and clip["manual"] is None and clip["library_name"] == "TV" and clip["guess"]["title"] == "Show"
    assert c.get(f"/api/libraries/{lib_id}/names").json() == [{"title": "Show", "year": 2010, "seasons": [
        {"season": 1, "episodes": [{"n": 1, "title": "Pilot"}]}]}]

    r = c.put(f"/api/files/{clip['id']}/identify",
              json={"title": "Show", "year": 2010, "season": 1, "episodes": [2], "episode_title": "The Second One"})
    assert r.status_code == 200, r.text
    ep = c.get(f"/api/items/{r.json()['item_id']}").json()
    assert (ep["kind"], ep["season_number"], ep["episode_number"], ep["title"]) == ("episode", 1, 2, "The Second One")
    assert ep["ancestors"][0]["title"] == "Show"  # joined the existing show, not a new one
    assert c.get(f"/api/libraries/{lib_id}").json()["files"]["unrecognized"] == 1
    assert _file(c, "clip0042.mkv")["manual"]["episodes"] == [2]  # still listed, as identified by hand

    # an extra (no episode number), then a rescan that re-reads every file: both identifications stay
    rnd = _file(c, "random stuff.mkv")
    assert c.put(f"/api/files/{rnd['id']}/identify",
                 json={"title": "Show", "year": 2010, "season": 0, "episode_title": "Gag Reel"}).status_code == 200

    con = connect(paths.db)
    con.execute("UPDATE files SET parse=json_set(parse, '$.v', 0)")
    con.close()
    jobs.run_scan(paths, lib_id, do_match=False)
    names = c.get(f"/api/libraries/{lib_id}/names").json()[0]["seasons"]
    assert names == [{"season": 0, "episodes": [{"n": None, "title": "Gag Reel"}]},
                     {"season": 1, "episodes": [{"n": 1, "title": "Pilot"}, {"n": 2, "title": "The Second One"}]}]
    assert c.get(f"/api/libraries/{lib_id}").json()["files"]["unrecognized"] == 0

    # undo: unrecognised again, and the extra it made is gone
    assert c.delete(f"/api/files/{rnd['id']}/identify").json() == {"recognized": False}
    assert c.get(f"/api/libraries/{lib_id}").json()["files"]["unrecognized"] == 1
    assert [s["season"] for s in c.get(f"/api/libraries/{lib_id}/names").json()[0]["seasons"]] == [1]


def test_identify_rules(tv):
    app, c, lib_id, _ = tv
    clip = _file(c, "clip0042.mkv")
    assert c.put(f"/api/files/{clip['id']}/identify", json={"title": "Show"}).status_code == 422  # season needed
    assert c.put(f"/api/files/{clip['id']}/identify", json={"title": "", "season": 1}).status_code == 422
    assert c.put("/api/files/99999/identify", json={"title": "Show", "season": 1}).status_code == 404
    assert c.post("/api/identify/lookup", json={"link": "https://www.themoviedb.org/tv/456", "library_id": lib_id}
                  ).status_code == 409  # no TMDB key
    kid = signed_in(app, "Kid", admin=False)
    assert kid.get("/api/unrecognized").status_code == 403
    assert kid.put(f"/api/files/{clip['id']}/identify", json={"title": "Show", "season": 1}).status_code == 403


def fake_tmdb() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/3/find/tt0133093":
            return httpx.Response(200, json={"movie_results": [{"id": 603}], "tv_results": [], "tv_episode_results": []})
        if path == "/3/find/tt1480055":
            return httpx.Response(200, json={"movie_results": [], "tv_results": [],
                                             "tv_episode_results": [{"show_id": 1399, "season_number": 1, "episode_number": 1}]})
        if path == "/3/find/tt0000001":
            return httpx.Response(200, json={"movie_results": [], "tv_results": [], "tv_episode_results": []})
        if path == "/3/movie/603":
            return httpx.Response(200, json={"id": 603, "title": "The Matrix", "release_date": "1999-03-31"})
        if path == "/3/tv/1399":
            return httpx.Response(200, json={"id": 1399, "name": "Game of Thrones", "first_air_date": "2011-04-17"})
        if path == "/3/tv/1399/season/1":
            return httpx.Response(200, json={"episodes": [{"episode_number": 1, "name": "Winter Is Coming"},
                                                          {"episode_number": 2, "name": "The Kingsroad"}]})
        return httpx.Response(404, json={})
    return httpx.MockTransport(handler)


def test_lookup_reads_tmdb_and_imdb_links():
    t = Tmdb(TOKEN, transport=fake_tmdb())
    assert identify.lookup(t, "https://www.themoviedb.org/movie/603-the-matrix", "movie") == \
        {"tmdb_id": 603, "title": "The Matrix", "year": 1999}
    assert identify.lookup(t, "https://www.imdb.com/title/tt0133093/?ref_=x", "movie")["tmdb_id"] == 603
    assert identify.lookup(t, "https://www.themoviedb.org/tv/1399-game-of-thrones/season/1/episode/2", "show") == \
        {"tmdb_id": 1399, "title": "Game of Thrones", "year": 2011, "season": 1, "episodes": [2],
         "episode_title": "The Kingsroad"}
    assert identify.lookup(t, "imdb.com/title/tt1480055/", "show")["episode_title"] == "Winter Is Coming"
    show = identify.lookup(t, "https://www.themoviedb.org/tv/1399", "show")
    assert (show["title"], show["season"], show["episodes"]) == ("Game of Thrones", None, [])
    for link, lib, msg in [("https://www.themoviedb.org/movie/603", "show", "movie, but this is a TV library"),
                           ("https://www.themoviedb.org/tv/1399", "movie", "TV show, but this is a Movies library"),
                           ("tt0000001", "movie", "doesn't know"), ("https://example.com/x", "movie", "Paste a TMDB link")]:
        with pytest.raises(identify.LinkError, match=msg):
            identify.lookup(t, link, lib)
