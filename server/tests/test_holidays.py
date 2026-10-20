"""Holidays (holidays.py): the calendar, which titles are about which holiday, the Home/library routes, admins'
overrides; also the Unidentified filter (`match_status` lists) and TMDB keywords for movies."""

import datetime as dt

import httpx
import pytest

from bams import auth, holidays, jobs, matcher, readonly
from bams.app import create_app
from bams.config import Paths
from bams.db import Tx, connect, jload
from bams.tmdb import Tmdb
from conftest import PASSWORD, make_tree, signed_in
from test_matcher import TOKEN


def test_calendar():
    assert [str(holidays.easter(y)) for y in (2024, 2025, 2026)] == ["2024-03-31", "2025-04-20", "2026-04-05"]
    # Hanukkah begins at sundown on these days
    assert [str(holidays.hanukkah(y)) for y in (2023, 2024, 2025)] == ["2023-12-07", "2024-12-25", "2025-12-14"]
    d = {h.id: h.date(2026) for h in holidays.HOLIDAYS}
    assert str(d["thanksgiving"]) == "2026-11-26" and str(d["memorial_day"]) == "2026-05-25"
    assert str(d["mothers_day"]) == "2026-05-10" and str(d["fathers_day"]) == "2026-06-21"
    assert str(d["labor_day"]) == "2026-09-07" and str(d["lunar_new_year"]) == "2026-02-17"
    (n, nd), (r, rd) = holidays.next_and_recent(dt.date(2026, 10, 19))
    assert (n.id, str(nd), r.id, str(rd)) == ("halloween", "2026-10-31", "labor_day", "2026-09-07")
    (n, _), (r, _) = holidays.next_and_recent(dt.date(2026, 12, 25))  # the day itself is still "upcoming"
    assert (n.id, r.id) == ("christmas", "hanukkah")
    (n, nd), (r, _) = holidays.next_and_recent(dt.date(2026, 12, 31))
    assert (n.id, str(nd), r.id) == ("new_year", "2027-01-01", "kwanzaa")


@pytest.mark.parametrize("text, want", [
    ("Snoopy and the gang on Christmas Eve", {"christmas"}),
    ("Bart goes trick-or-treating", {"halloween"}),
    ("A Hallowe'en party", {"halloween"}),
    ("Fireworks on the Fourth of July", {"independence_day"}),
    ("Valentine’s Day dinner goes wrong", {"valentines"}),
    ("Hanukkah with the family", {"hanukkah"}),
    ("A road trip to Santa Fe", set()),          # not Santa Claus
    ("Shipwrecked on Easter Island", set()),     # not Easter
    ("The Tet Offensive", set()),
    ("A new year at school", set()),             # only New Year's (Eve/Day)
    ("They ring in the new year's eve countdown", {"new_year"}),
])
def test_words(text, want):
    assert holidays.matches(text) == want


@pytest.fixture
def lib(tmp_path, monkeypatch):
    media = tmp_path / "tv"
    make_tree(media, ["Show/Season 01/Show - S01E01.mkv", "Show/Season 01/Show - S01E02.mkv"])
    films = tmp_path / "films"
    make_tree(films, ["Elf (2003)/Elf (2003).mkv", "Heat (1995)/Heat (1995).mkv", "Plain (2010)/Plain (2010).mkv"])
    paths = Paths(tmp_path / "data")
    app = create_app(paths, start_scheduler=False)
    c = signed_in(app, "admin")
    libs = {}
    for name, kind, folder in (("TV", "show", media), ("Films", "movie", films)):
        libs[kind] = c.post("/api/libraries", json={"name": name, "type": kind, "paths": [str(folder)]}).json()["id"]
        jobs.run_scan(paths, libs[kind], do_match=False)
    con = connect(paths.db)
    ids = {r["title"]: r["id"] for r in con.execute("SELECT id, title FROM items WHERE kind='movie'")}
    eps = [r["id"] for r in con.execute("SELECT id FROM items WHERE kind='episode' ORDER BY episode_number")]
    with Tx(con):
        con.execute("UPDATE items SET overview=?, updated_at=updated_at+1 WHERE id=?",
                    ("The family carves a jack-o'-lantern.", eps[0]))
        con.execute("UPDATE items SET overview=?, updated_at=updated_at+1 WHERE id=?", ("Santa Claus is lost.", ids["Elf"]))
        con.execute("UPDATE items SET match_status='matched' WHERE id=?", (ids["Heat"],))
    con.close()
    monkeypatch.setattr(holidays, "today", lambda: dt.date(2026, 10, 19))
    yield app, c, paths, libs, ids, eps
    readonly.set_protected_roots([])


def test_routes(lib):
    app, c, paths, libs, ids, eps = lib
    h = c.get("/api/holidays").json()
    assert h["next"] == {"id": "halloween", "name": "Halloween", "date": "2026-10-31", "count": 1}
    assert h["recent"]["id"] == "labor_day" and len(h["all"]) == len(holidays.HOLIDAYS)
    items = c.get("/api/holidays/next/items").json()
    assert [i["id"] for i in items] == [eps[0]]
    assert items[0]["show"]["title"] == "Show" and items[0]["season_id"]  # shown under its show, like watch list entries
    assert [i["title"] for i in c.get("/api/holidays/christmas/items").json()] == ["Elf"]
    # a library's own: a show library gives its episodes, a movie library its movies
    assert len(c.get(f"/api/holidays/next/items?library={libs['show']}").json()) == 1
    assert c.get(f"/api/holidays/next/items?library={libs['movie']}").json() == []
    assert c.get("/api/holidays/nope/items").status_code == 404


def test_admin_override(lib):
    app, c, paths, libs, ids, eps = lib
    # Heat isn't a Christmas film by its words: an admin puts it in; Elf is, and is taken out
    resp = c.put(f"/api/items/{ids['Heat']}/holidays/christmas", json={"tagged": True})
    assert resp.status_code == 200, resp.text
    r = resp.json()
    assert next(x for x in r if x["id"] == "christmas") == {"id": "christmas", "name": "Christmas", "on": True, "tagged": True}
    c.put(f"/api/items/{ids['Elf']}/holidays/christmas", json={"tagged": False})
    assert [i["title"] for i in c.get("/api/holidays/christmas/items").json()] == ["Heat"]
    c.put(f"/api/items/{ids['Elf']}/holidays/christmas", json={"tagged": None})  # back to automatic
    assert sorted(i["title"] for i in c.get("/api/holidays/christmas/items").json()) == ["Elf", "Heat"]
    show = c.get("/api/libraries").json()  # any non-movie/episode: refused
    assert c.put(f"/api/items/{ids['Elf']}/holidays/diwali", json={"tagged": True}).status_code == 404
    # viewers may look but not tag
    con = connect(paths.db)
    auth.create_user(con, "kid", PASSWORD, False)
    con.close()
    v = signed_in_as(app, "kid")
    assert v.get("/api/holidays").status_code == 200
    assert v.put(f"/api/items/{ids['Heat']}/holidays/christmas", json={"tagged": False}).status_code == 403
    assert show


def signed_in_as(app, name):
    from fastapi.testclient import TestClient
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"name": name, "password": PASSWORD}).status_code == 200
    return c


def test_unidentified_filter(lib):
    app, c, paths, libs, ids, eps = lib
    got = c.get(f"/api/libraries/{libs['movie']}/items?match_status=pending,unmatched").json()
    assert sorted(i["title"] for i in got) == ["Elf", "Plain"]  # Heat is identified
    assert [i["title"] for i in c.get(f"/api/libraries/{libs['movie']}/items?match_status=matched").json()] == ["Heat"]


def test_movie_keywords(lib):
    """A movie's TMDB keywords are kept (identifying it, or a few per scan for older ones) and count for holidays."""
    app, c, paths, libs, ids, eps = lib

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/3/movie/949/keywords":
            return httpx.Response(200, json={"id": 949, "keywords": [{"id": 1, "name": "christmas party"}]})
        return httpx.Response(404, json={})

    con = connect(paths.db)
    with Tx(con):
        con.execute("UPDATE items SET tmdb_id=949 WHERE id=?", (ids["Heat"],))
    tmdb = Tmdb(TOKEN, transport=httpx.MockTransport(handler))
    assert matcher.fill_keywords(con, tmdb, libs["movie"]) == 1
    assert jload(con.execute("SELECT json_extract(extra, '$.keywords') FROM items WHERE id=?", (ids["Heat"],)).fetchone()[0]) \
        == ["christmas party"]
    assert matcher.fill_keywords(con, tmdb, libs["movie"]) == 0  # once
    con.close()
    assert sorted(i["title"] for i in c.get("/api/holidays/christmas/items").json()) == ["Elf", "Heat"]
