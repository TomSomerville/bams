"""The watch list: movies, shows, seasons and episodes each user means to watch, kept on the server per account."""

import sqlite3

import pytest

from bams import db, items, jobs, readonly
from bams.app import create_app
from bams.config import Paths
from bams.db import connect
from conftest import make_tree, signed_in


@pytest.fixture
def lib(tmp_path):
    media = tmp_path / "media"
    make_tree(media, [f"Show/Season 01/Show - S01E0{n}.mkv" for n in (1, 2)]
              + ["Show/Season 02/Show - S02E01.mkv", "Other/Season 01/Other - S01E01.mkv"])
    films = tmp_path / "films"
    make_tree(films, ["Film (2001)/Film (2001).mkv"])
    music = tmp_path / "music"
    make_tree(music, ["Band/Album/01 - Song.mp3"])
    paths = Paths(tmp_path / "data")
    app = create_app(paths, start_scheduler=False)
    c = signed_in(app, "Tom")
    for name, kind, folder in (("TV", "show", media), ("Films", "movie", films), ("Music", "music", music)):
        made = c.post("/api/libraries", json={"name": name, "type": kind, "paths": [str(folder)]}).json()
        jobs.run_scan(paths, made["id"], do_match=False)
    con = connect(paths.db)
    ids = {r["kind"] + ":" + r["title"]: r["id"] for r in con.execute("SELECT id, kind, title FROM items")}
    ids["ep"] = con.execute("""SELECT e.id FROM items e JOIN items s ON s.id=e.parent_id JOIN items sh ON sh.id=s.parent_id
                               WHERE sh.title='Show' AND s.season_number=1 AND e.episode_number=2""").fetchone()[0]
    ids["season"] = con.execute("""SELECT s.id FROM items s JOIN items sh ON sh.id=s.parent_id
                                   WHERE sh.title='Show' AND s.season_number=2""").fetchone()[0]
    con.close()
    yield app, c, ids
    readonly.set_protected_roots([])


def test_add_list_remove(lib):
    app, c, ids = lib
    assert c.get("/api/watchlist").json() == []
    for k in ("movie:Film", "show:Show", "season", "ep"):
        r = c.put(f"/api/watchlist/{ids[k]}")
        assert r.status_code == 200 and r.json()["watchlist"] is True
    got = c.get("/api/watchlist").json()
    assert [i["id"] for i in got] == [ids["ep"], ids["season"], ids["show:Show"], ids["movie:Film"]]  # newest first
    assert all(i["watchlist"] is True and isinstance(i["listed_at"], float) for i in got)
    ep, season = got[0], got[1]
    assert ep["kind"] == "episode" and ep["show"]["title"] == "Show" and ep["season_id"] and ep["episode_number"] == 2
    assert ep["progress"] == {"position": 0.0, "duration": None, "watched": False}  # watch state comes along
    assert season["show"]["id"] == ids["show:Show"] and "season_id" not in season
    # adding again changes nothing (the first date stays)
    first = got[3]["listed_at"]
    assert c.put(f"/api/watchlist/{ids['movie:Film']}").json()["listed_at"] == first
    assert len(c.get("/api/watchlist").json()) == 4
    # off again; removing what isn't there is fine too
    assert c.delete(f"/api/watchlist/{ids['show:Show']}").json() == {"watchlist": False, "removed": True}
    assert c.delete(f"/api/watchlist/{ids['show:Show']}").json() == {"watchlist": False, "removed": False}
    assert ids["show:Show"] not in [i["id"] for i in c.get("/api/watchlist").json()]
    assert c.get("/api/watchlist?limit=1").json()[0]["id"] == ids["ep"]


def test_only_video_items(lib):
    _, c, ids = lib
    for k in ("artist:Band", "album:Album", "track:Song"):
        assert c.put(f"/api/watchlist/{ids[k]}").status_code == 404
    assert c.put("/api/watchlist/999999").status_code == 404
    assert c.get("/api/watchlist").json() == []


def test_items_say_whether_they_are_listed(lib):
    """Every item list and item page says `watchlist` for the signed-in user, so apps can show the button's state."""
    _, c, ids = lib
    c.put(f"/api/watchlist/{ids['ep']}")
    c.put(f"/api/watchlist/{ids['movie:Film']}")
    show = c.get(f"/api/items/{ids['show:Show']}").json()
    assert show["watchlist"] is False and [s["watchlist"] for s in show["children"]] == [False, False]
    season1 = c.get(f"/api/items/{show['children'][0]['id']}").json()
    assert {e["episode_number"]: e["watchlist"] for e in season1["children"]} == {1: False, 2: True}
    ep = c.get(f"/api/items/{ids['ep']}").json()
    assert ep["watchlist"] is True and [a["watchlist"] for a in ep["ancestors"]] == [False, False]
    assert {i["title"]: i["watchlist"] for i in c.get("/api/items?kind=show,movie").json()} == \
        {"Show": False, "Other": False, "Film": True}
    films = next(x for x in c.get("/api/libraries").json() if x["name"] == "Films")
    assert c.get(f"/api/libraries/{films['id']}/items").json()[0]["watchlist"] is True
    assert "watchlist" not in c.get(f"/api/items/{ids['album:Album']}").json()  # music has no list


def test_each_account_has_its_own(lib):
    app, c, ids = lib
    c.put(f"/api/watchlist/{ids['movie:Film']}")
    kid = signed_in(app, "Kid", admin=False)
    assert kid.get("/api/watchlist").json() == []
    assert kid.get(f"/api/items/{ids['movie:Film']}").json()["watchlist"] is False
    kid.put(f"/api/watchlist/{ids['ep']}")
    assert [i["id"] for i in c.get("/api/watchlist").json()] == [ids["movie:Film"]]
    assert [i["id"] for i in kid.get("/api/watchlist").json()] == [ids["ep"]]
    # removing an account removes its list
    con = connect(app.state.paths.db)
    kid_id = con.execute("SELECT id FROM users WHERE name='Kid'").fetchone()[0]
    assert c.delete(f"/api/users/{kid_id}").status_code == 204
    assert con.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 1
    con.close()


def test_needs_a_signed_in_user(lib):
    from fastapi.testclient import TestClient
    app, _, ids = lib
    anon = TestClient(app)
    assert anon.get("/api/watchlist").status_code == 401
    assert anon.put(f"/api/watchlist/{ids['movie:Film']}").status_code == 401


def test_merged_titles_stay_listed(lib):
    """Two folders turn out to be one show: what was listed under the merged-away one is listed under the kept one."""
    app, c, ids = lib
    con = connect(app.state.paths.db)
    other_season = con.execute("SELECT id FROM items WHERE kind='season' AND parent_id=?", (ids["show:Other"],)).fetchone()[0]
    other_ep = con.execute("SELECT id FROM items WHERE kind='episode' AND parent_id=?", (other_season,)).fetchone()[0]
    for i in (ids["show:Other"], other_season, other_ep):
        c.put(f"/api/watchlist/{i}")
    items.merge_titles(con, ids["show:Show"], ids["show:Other"])  # Other's S01E01 is also Show's S01E01
    con.close()
    s1e1 = c.get(f"/api/items/{ids['show:Show']}").json()["children"][0]
    season1 = c.get(f"/api/items/{s1e1['id']}").json()
    listed = {i["id"] for i in c.get("/api/watchlist").json()}
    assert listed == {ids["show:Show"], season1["id"], season1["children"][0]["id"]}


def test_gone_items_leave_the_list(lib):
    app, c, ids = lib
    c.put(f"/api/watchlist/{ids['movie:Film']}")
    con = connect(app.state.paths.db)
    con.execute("DELETE FROM items WHERE id=?", (ids["movie:Film"],))  # what cleanup_orphans does to a deleted file
    con.commit()
    con.close()
    assert c.get("/api/watchlist").json() == []


def test_list_name_pref(lib):
    app, c, _ = lib
    assert c.get("/api/auth/state").json()["user"]["prefs"]["watchlist_name"] == ""  # "" = "My Watch List"
    assert c.put("/api/me/prefs", json={"watchlist_name": "  Films   to see "}).json()["watchlist_name"] == "Films to see"
    assert c.get("/api/auth/state").json()["user"]["prefs"]["watchlist_name"] == "Films to see"
    assert c.put("/api/me/prefs", json={"watchlist_name": "x" * 61}).status_code == 422
    assert c.put("/api/me/prefs", json={"home_hero": False}).json()["watchlist_name"] == "Films to see"  # kept
    kid = signed_in(app, "Kid", admin=False)
    assert kid.get("/api/auth/state").json()["user"]["prefs"]["watchlist_name"] == ""
    assert c.put("/api/me/prefs", json={"watchlist_name": ""}).json()["watchlist_name"] == ""  # back to the default


def test_migration_to_v12(tmp_path):
    p = tmp_path / "old.db"
    con = sqlite3.connect(p, isolation_level=None)
    con.executescript("BEGIN;" + db.SCHEMA + "PRAGMA user_version = 1; COMMIT;")
    con.close()
    con = connect(p)
    db.migrate(con, backup_dir=tmp_path / "backups")
    assert con.execute("PRAGMA user_version").fetchone()[0] == 12
    assert [r[1] for r in con.execute("PRAGMA table_info(watchlist)")] == ["user_id", "item_id", "added_at"]
    con.close()
