"""Matching against a fake TMDB (httpx.MockTransport): no network, no key needed."""

import httpx

from bams import library, matcher
from bams.scanner import scan_library
from bams.tmdb import Tmdb
from conftest import make_tree

TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.c2lnbmF0dXJl"  # fake, JWT-shaped

SIMPSONS = {"id": 456, "name": "The Simpsons", "original_name": "The Simpsons", "first_air_date": "1989-12-17",
            "overview": "Springfield.", "poster_path": "/simp.jpg", "backdrop_path": "/simp_bd.jpg",
            "genres": [{"name": "Animation"}, {"name": "Comedy"}], "vote_average": 8.0, "episode_run_time": [22],
            "external_ids": {"imdb_id": "tt0096697", "tvdb_id": 71663}}
SIMPSONS_FAKE = {"id": 999, "name": "The Simpsons Movie Behind the Scenes", "first_air_date": "2007-01-01"}


def fake_tmdb(calls: list) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.headers.get("authorization") == f"Bearer {TOKEN}" or req.url.host == "image.tmdb.org"
        path, q = req.url.path, req.url.params
        if req.url.host == "image.tmdb.org":
            assert "authorization" not in req.headers  # key never goes to the image CDN
            return httpx.Response(200, content=b"\xff\xd8jpeg")
        if path == "/3/search/tv":
            if "simpsons" in q["query"].lower():
                return httpx.Response(200, json={"results": [SIMPSONS_FAKE, SIMPSONS]})
            return httpx.Response(200, json={"results": []})
        if path == "/3/tv/456":
            return httpx.Response(200, json=SIMPSONS)
        if path.startswith("/3/tv/456/season/"):
            n = int(path.rsplit("/", 1)[1])
            return httpx.Response(200, json={"id": 4560 + n, "name": f"Season {n}", "poster_path": f"/s{n}.jpg",
                                             "episodes": [{"id": 45600 + n * 100 + e, "episode_number": e,
                                                           "name": f"Real Title {n}x{e}", "overview": "...",
                                                           "air_date": "2023-10-01", "still_path": f"/e{n}{e}.jpg"}
                                                          for e in (1, 2)]})
        return httpx.Response(404, json={})
    return httpx.MockTransport(handler)


def test_match_merges_folders_and_fills_episodes(env):
    paths, media, con = env
    make_tree(media, [
        "The Simpsons 1989 S35 1080p DSNP WEBRip DDP 5 1 x265-edge2020/The.Simpsons.S35E01.Homers.Crossing.mkv",
        "Simpsons/Season 36/Simpsons - S36E02.mkv",       # different folder name, same show
        "Nonexistent Show Xyz/Season 1/Nonexistent Show Xyz - S01E01.mkv",
    ])
    lib_id = library.create(con, paths.root, "TV", "show", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    assert con.execute("SELECT COUNT(*) FROM items WHERE kind='show'").fetchone()[0] == 3

    calls: list = []
    t = Tmdb(TOKEN, transport=fake_tmdb(calls))
    st = matcher.match_library(con, t, paths.images, lib_id)
    assert st.matched == 2 and st.unmatched == 1

    shows = con.execute("SELECT * FROM items WHERE kind='show' ORDER BY id").fetchall()
    assert len(shows) == 2  # the two Simpsons folders merged into one
    simpsons = next(s for s in shows if s["tmdb_id"] == 456)
    assert (simpsons["title"], simpsons["year"], simpsons["imdb_id"]) == ("The Simpsons", 1989, "tt0096697")
    assert (paths.images / simpsons["poster"]).is_file()
    seasons = {s["season_number"] for s in con.execute("SELECT * FROM items WHERE parent_id=?", (simpsons["id"],))}
    assert seasons == {35, 36}
    titles = {r["title"] for r in con.execute("SELECT title FROM items WHERE kind='episode' AND match_status='matched'")}
    assert titles == {"Real Title 35x1", "Real Title 36x2"}
    other = next(s for s in shows if s["tmdb_id"] is None)
    assert other["match_status"] == "unmatched"

    # A later scan with a new Simpsons file under the merged-away folder name must not re-create a duplicate.
    from bams import readonly
    saved = readonly.protected_roots()
    readonly.set_protected_roots([])
    make_tree(media, ["Simpsons/Season 36/Simpsons - S36E01.mkv"])
    readonly._roots = saved
    scan_library(con, lib_id, do_probe=False)
    assert con.execute("SELECT COUNT(*) FROM items WHERE kind='show'").fetchone()[0] == 2
    matcher.match_library(con, t, paths.images, lib_id)
    ep = con.execute("SELECT title, match_status FROM items WHERE kind='episode' AND season_number=36 AND episode_number=1").fetchone()
    assert (ep["title"], ep["match_status"]) == ("Real Title 36x1", "matched")


def test_score_prefers_exact_title_and_year():
    best, s = matcher.best_match([SIMPSONS_FAKE, SIMPSONS], "The Simpsons", 1989, "show")
    assert best["id"] == 456 and s >= matcher.ACCEPT


def test_exact_title_beats_a_wrong_year():
    # "Parks.and.Recreation.S07E01.2017" gave the show the air year of one episode; TMDB says 2009
    parks = {"id": 1, "name": "Parks and Recreation", "first_air_date": "2009-04-09"}
    best, s = matcher.best_match([parks], "Parks and Recreation", 2017, "show")
    assert s < matcher.ACCEPT
    best, s = matcher.choose([parks], "Parks and Recreation", 2017, "show")
    assert best is parks and s >= matcher.ACCEPT
    # but a different title with the wrong year still fails
    best, s = matcher.choose([{"id": 2, "name": "Parks and Rec Unofficial", "first_air_date": "2009-01-01"}],
                             "Parks and Recreation", 2017, "show")
    assert s < matcher.ACCEPT


def test_franchise_prefix_matches_tmdb_top_hit():
    andor = {"id": 3, "name": "Andor", "first_air_date": "2022-09-21"}
    best, s = matcher.choose([andor], "Star Wars Andor", None, "show")
    assert best is andor and s >= matcher.ACCEPT
    # only TMDB's first result gets that benefit, and only a real suffix
    best, s = matcher.choose([{"id": 4, "name": "Other"}, andor], "Star Wars Andor", None, "show")
    assert s < matcher.ACCEPT
    best, s = matcher.choose([{"id": 5, "name": "Dor"}], "Star Wars Andor", None, "show")
    assert s < matcher.ACCEPT


def test_unmatched_titles_are_retried_after_a_reparse_or_new_matcher_rules(env):
    """Tester's library: after the parser upgrade (0.5.0) South Park etc. stayed 'unmatched' because only
    'pending' titles were tried. A scan that re-parsed files, or the first after a matcher change, retries them."""
    from bams import jobs
    paths, media, con = env
    make_tree(media, ["The Simpsons/Season 1/The Simpsons - S01E01.mkv"])
    lib_id = library.create(con, paths.root, "TV", "show", [str(media)])
    assert jobs.should_rematch(con, lib_id, requested=False, reparsed=0)        # never matched with these rules
    jobs.note_matched(con, lib_id)
    assert not jobs.should_rematch(con, lib_id, requested=False, reparsed=0)
    assert jobs.should_rematch(con, lib_id, requested=False, reparsed=3)        # parser upgrade re-read names
    assert jobs.should_rematch(con, lib_id, requested=True, reparsed=0)
    con.execute("UPDATE settings SET value='1' WHERE key=?", (f"matcher_version:{lib_id}",))
    assert jobs.should_rematch(con, lib_id, requested=False, reparsed=0)        # rules changed since
    # and match_library really does retry them when asked
    scan_library(con, lib_id, do_probe=False)
    con.execute("UPDATE items SET match_status='unmatched', match_score=0.5 WHERE kind='show'")
    t = Tmdb(TOKEN, transport=fake_tmdb([]))
    assert matcher.match_library(con, t, paths.images, lib_id).matched == 0
    assert matcher.match_library(con, t, paths.images, lib_id, retry_unmatched=True).matched == 1
