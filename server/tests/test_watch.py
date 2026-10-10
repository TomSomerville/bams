"""Watch state: resume positions, watched flags, Continue Watching, per user."""

import pytest
from fastapi.testclient import TestClient

from bams import items, jobs, readonly, watch
from bams.app import create_app
from bams.config import Paths
from bams.db import connect
from conftest import PASSWORD, make_tree, signed_in


@pytest.fixture
def tv(tmp_path):
    media = tmp_path / "media"
    make_tree(media, [f"Show/Season 01/Show - S01E0{n}.mkv" for n in (1, 2, 3)]
              + ["Show/Season 02/Show - S02E01.mkv", "Show/Specials/Show - S00E01.mkv",
                 "Other/Season 01/Other - S01E01.mkv", "Film (2001)/Film (2001).mkv"])
    paths = Paths(tmp_path / "data")
    app = create_app(paths, start_scheduler=False)
    c = signed_in(app, "Tom")
    tvlib = c.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(media)]}).json()
    jobs.run_scan(paths, tvlib["id"], do_match=False)
    con = connect(paths.db)
    ep = {(r["season_number"], r["episode_number"]): r["id"] for r in con.execute(
        """SELECT e.id, e.episode_number, s.season_number FROM items e JOIN items s ON s.id=e.parent_id
           JOIN items sh ON sh.id=s.parent_id WHERE e.kind='episode' AND sh.title='Show'""")}
    show = con.execute("SELECT id FROM items WHERE kind='show' AND title='Show'").fetchone()["id"]
    con.close()
    yield app, c, ep, show
    readonly.set_protected_roots([])


def test_progress_resume_and_watched(tv):
    app, c, ep, _ = tv
    e = ep[(1, 1)]
    assert c.get(f"/api/items/{e}").json()["progress"] == {"position": 0.0, "duration": None, "watched": False}
    assert c.put(f"/api/items/{e}/progress", json={"position": 600, "duration": 1300}).json()["position"] == 600
    assert c.get(f"/api/items/{e}").json()["progress"]["position"] == 600
    st = c.put(f"/api/items/{e}/progress", json={"position": 1200, "duration": 1300}).json()  # > 90%
    assert st == {"position": 0.0, "duration": 1300, "watched": True}
    c.put(f"/api/items/{e}/progress", json={"position": 1250, "duration": 1300})  # the credits keep reporting
    con = connect(app.state.paths.db)
    assert con.execute("SELECT play_count FROM watch_state WHERE item_id=?", (e,)).fetchone()[0] == 1
    c.put(f"/api/items/{e}/progress", json={"position": 300, "duration": 1300})   # watching it again...
    c.put(f"/api/items/{e}/progress", json={"position": 1280, "duration": 1300})  # ...to the end
    assert con.execute("SELECT play_count FROM watch_state WHERE item_id=?", (e,)).fetchone()[0] == 2
    con.close()
    season = c.get(f"/api/items/{e}").json()["ancestors"][1]
    assert season["kind"] == "season" and season["episodes"] == 3 and season["unwatched"] == 2
    assert c.put("/api/items/999999/progress", json={"position": 1}).status_code == 404


def test_mark_show_watched_and_unwatched(tv):
    _, c, ep, show = tv
    assert c.put(f"/api/items/{show}/watched", json={"watched": True}).json()["items"] == 5
    s = c.get(f"/api/items/{show}").json()
    assert s["unwatched"] == 0 and all(x["unwatched"] == 0 for x in s["children"])
    c.put(f"/api/items/{ep[(1, 2)]}/watched", json={"watched": False})
    lib_show = next(i for i in c.get("/api/items?kind=show").json() if i["id"] == show)
    assert lib_show["episodes"] == 5 and lib_show["unwatched"] == 1


def test_home_row_sorts(tv):
    """Home: a show with a newly added episode comes before newer shows ("recent"); random order; top rated."""
    app, c, ep, show = tv
    con = connect(app.state.paths.db)
    con.execute("UPDATE items SET added_at=100")
    con.execute("UPDATE items SET added_at=200 WHERE kind='show' AND title='Other'")
    con.execute("UPDATE items SET added_at=300, rating=8.1 WHERE id=?", (ep[(2, 1)],))  # a new Show episode
    con.execute("UPDATE items SET rating=7.5 WHERE kind='show' AND title='Other'")
    con.execute("UPDATE items SET rating=6.0 WHERE id=?", (show,))
    con.commit()
    con.close()
    lib = c.get("/api/libraries").json()[0]["id"]
    assert [i["title"] for i in c.get(f"/api/libraries/{lib}/items?sort=recent").json()][:2] == ["Show", "Other"]
    assert [i["title"] for i in c.get(f"/api/libraries/{lib}/items?sort=added").json()][0] == "Other"
    assert {i["title"] for i in c.get("/api/items?sort=random&min_rating=7").json()} == {"Other"}  # shows/movies only
    assert len(c.get("/api/items?sort=random&limit=1").json()) == 1


def test_continue_watching(tv):
    app, c, ep, show = tv
    assert c.get("/api/continue").json() == []
    c.put(f"/api/items/{ep[(1, 1)]}/progress", json={"position": 1200, "duration": 1300})  # finished
    [nxt] = c.get("/api/continue").json()
    assert nxt["id"] == ep[(1, 2)] and nxt["reason"] == "next" and nxt["show"]["title"] == "Show"
    c.put(f"/api/items/{ep[(1, 2)]}/watched", json={"watched": True})
    c.put(f"/api/items/{ep[(1, 3)]}/watched", json={"watched": True})
    c.put(f"/api/items/{ep[(1, 3)]}/progress", json={"position": 1290, "duration": 1300})
    assert c.get("/api/continue").json()[0]["id"] == ep[(2, 1)]  # on to the next season, not the special
    c.put(f"/api/items/{ep[(2, 1)]}/progress", json={"position": 400, "duration": 1300})
    [r] = c.get("/api/continue").json()
    assert r["id"] == ep[(2, 1)] and r["reason"] == "resume" and r["progress"]["position"] == 400
    season2 = c.get(f"/api/items/{ep[(2, 1)]}").json()["ancestors"][-1]
    assert season2["kind"] == "season" and r["season_id"] == season2["id"]  # the card's episode line opens it
    c.put(f"/api/items/{ep[(2, 1)]}/progress", json={"position": 1250, "duration": 1300})
    assert c.get("/api/continue").json() == []  # the show is finished (the special isn't offered)
    assert c.get(f"/api/items/{ep[(1, 3)]}").json()["next_id"] == ep[(2, 1)]
    assert c.get(f"/api/items/{ep[(2, 1)]}").json()["next_id"] is None


def test_watch_state_is_per_user(tv):
    app, c, ep, _ = tv
    c.put(f"/api/items/{ep[(1, 1)]}/progress", json={"position": 500, "duration": 1300})
    kid = signed_in(app, "Kid", admin=False)
    assert kid.get(f"/api/items/{ep[(1, 1)]}").json()["progress"]["position"] == 0
    assert kid.get("/api/continue").json() == []
    kid.put(f"/api/items/{ep[(1, 1)]}/watched", json={"watched": True})
    assert c.get(f"/api/items/{ep[(1, 1)]}").json()["progress"] == {"position": 500, "duration": 1300, "watched": False}


def test_merged_titles_keep_watch_state(tv):
    app, c, ep, show = tv
    c.put(f"/api/items/{ep[(1, 1)]}/progress", json={"position": 500, "duration": 1300})
    con = connect(app.state.paths.db)
    other = con.execute("SELECT id FROM items WHERE kind='show' AND title='Other'").fetchone()["id"]
    other_ep = con.execute("""SELECT e.id FROM items e JOIN items s ON s.id=e.parent_id
                              WHERE s.parent_id=?""", (other,)).fetchone()["id"]
    c.put(f"/api/items/{other_ep}/watched", json={"watched": True})
    kid = signed_in(app, "Kid", admin=False)
    kid.put(f"/api/items/{other_ep}/watched", json={"watched": True})
    items.merge_titles(con, show, other)  # same TMDB title found under two names: S01E01 is in both
    con.close()
    assert c.get(f"/api/items/{ep[(1, 1)]}").json()["progress"]["position"] == 500  # the kept one's state wins
    assert kid.get(f"/api/items/{ep[(1, 1)]}").json()["progress"]["watched"] is True  # moved over
    me = c.get("/api/auth/state").json()["user"]["id"]
    con = connect(app.state.paths.db)
    assert watch.state(con, me, other_ep)["watched"] is False  # the merged-away episode is gone
    con.close()


def test_progress_needs_a_signed_in_user(tv):
    app, _, ep, _ = tv
    assert TestClient(app).put(f"/api/items/{ep[(1, 1)]}/progress", json={"position": 5}).status_code == 401


def test_watch_thresholds_are_settings(tv):
    """Tester request: started after 10 s, watched at 95%. Admins set them; viewers can't."""
    app, c, ep, _ = tv
    assert c.get("/api/settings").json()["watch"] == {"watched_percent": 90, "resume_after": 30}
    e = ep[(1, 1)]
    c.put(f"/api/items/{e}/progress", json={"position": 15, "duration": 1000})
    assert c.get(f"/api/items/{e}").json()["progress"]["position"] == 0  # under 30 s: not started
    assert c.put("/api/settings/watch", json={"watched_percent": 95, "resume_after": 10}).json() == \
        {"watched_percent": 95, "resume_after": 10}
    c.put(f"/api/items/{e}/progress", json={"position": 15, "duration": 1000})
    assert c.get("/api/continue").json()[0]["id"] == e  # 15 s in: saved and in Continue Watching
    assert not c.put(f"/api/items/{e}/progress", json={"position": 920, "duration": 1000}).json()["watched"]
    assert c.put(f"/api/items/{e}/progress", json={"position": 950, "duration": 1000}).json()["watched"]
    assert c.put("/api/settings/watch", json={"watched_percent": 40, "resume_after": 10}).status_code == 422
    kid = signed_in(app, "Kid", admin=False)
    assert kid.put("/api/settings/watch", json={"watched_percent": 95, "resume_after": 10}).status_code == 403


def test_prefs_are_per_user(tv):
    app, c, _, _ = tv
    assert c.get("/api/auth/state").json()["user"]["prefs"] == {"home_hero": True, "home_rows": []}
    assert c.put("/api/me/prefs", json={"home_hero": False}).json() == {"home_hero": False, "home_rows": []}
    assert c.get("/api/auth/state").json()["user"]["prefs"] == {"home_hero": False, "home_rows": []}
    kid = signed_in(app, "Kid", admin=False)
    assert kid.get("/api/auth/state").json()["user"]["prefs"] == {"home_hero": True, "home_rows": []}
    assert kid.put("/api/me/prefs", json={"nonsense": 1}).json() == {"home_hero": True, "home_rows": []}


def test_home_rows_pref(tv):
    app, c, _, _ = tv
    rows = [{"id": "genres", "show": True}, {"id": "continue", "show": False}, {"id": "lib:1", "show": True}]
    assert c.put("/api/me/prefs", json={"home_rows": rows}).json()["home_rows"] == rows
    # the other pref is untouched, and changing it keeps the rows
    assert c.put("/api/me/prefs", json={"home_hero": False}).json() == {"home_hero": False, "home_rows": rows}
    assert c.get("/api/auth/state").json()["user"]["prefs"]["home_rows"] == rows
    # duplicates are dropped (first wins); bad shapes are refused
    dup = c.put("/api/me/prefs", json={"home_rows": rows + [{"id": "genres", "show": False}]}).json()
    assert dup["home_rows"] == rows
    assert c.put("/api/me/prefs", json={"home_rows": [{"id": "", "show": True}]}).status_code == 422
    assert c.put("/api/me/prefs", json={"home_rows": [{"id": "x"}]}).status_code == 422
    assert c.put("/api/me/prefs", json={"home_rows": [{"id": f"r{i}", "show": True} for i in range(201)]}).status_code == 422
    # each account has its own
    kid = signed_in(app, "Kid", admin=False)
    assert kid.get("/api/auth/state").json()["user"]["prefs"]["home_rows"] == []
    assert c.put("/api/me/prefs", json={"home_rows": []}).json()["home_rows"] == []  # back to the default


def test_an_episode_only_opened_doesnt_hide_the_show(tv):
    """Opening the next episode for a few seconds (or a play that failed) leaves position 0: Continue Watching
    still offers where you really were."""
    app, c, ep, show = tv
    c.put(f"/api/items/{ep[(1, 1)]}/progress", json={"position": 400, "duration": 1300})
    c.put(f"/api/items/{ep[(1, 2)]}/progress", json={"position": 5, "duration": 1300})  # stored as 0
    [r] = c.get("/api/continue").json()
    assert r["id"] == ep[(1, 1)] and r["reason"] == "resume"
