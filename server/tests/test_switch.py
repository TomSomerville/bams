"""Quick account switching on the web: other accounts signed in on this browser keep their sessions in an HttpOnly
cookie (`bams_others`); switching swaps which one is current, with no password."""

import pytest
from fastapi.testclient import TestClient

from bams import auth
from bams.app import create_app
from bams.config import Paths
from bams.db import connect
from conftest import PASSWORD, signed_in

ORIGIN = {"origin": "http://testserver"}


@pytest.fixture
def app(tmp_path):
    a = create_app(Paths(tmp_path / "data"), start_scheduler=False)
    con = connect(a.state.paths.db)
    for n in ("kid", "guest"):
        auth.create_user(con, n, PASSWORD, False)
    con.close()
    return a


def me(c):
    return c.get("/api/auth/state").json()["user"]["name"]


def test_add_switch_remove(app):
    c = signed_in(app, "mum")
    assert [a["name"] for a in c.get("/api/auth/accounts").json()] == ["mum"]
    r = c.post("/api/auth/accounts", json={"name": "kid", "password": PASSWORD}, headers=ORIGIN)
    assert r.status_code == 200 and me(c) == "kid"
    accounts = c.get("/api/auth/accounts").json()
    assert [(a["name"], a["current"]) for a in accounts] == [("kid", True), ("mum", False)]
    # the tokens never reach the page: only HttpOnly cookies
    assert all("httponly" in h.lower() for h in r.headers.get_list("set-cookie"))
    mum = next(a for a in accounts if a["name"] == "mum")
    assert c.post("/api/auth/switch", json={"user_id": mum["id"]}, headers=ORIGIN).status_code == 200
    assert me(c) == "mum"
    assert [(a["name"], a["current"]) for a in c.get("/api/auth/accounts").json()] == [("mum", True), ("kid", False)]
    kid = next(a for a in c.get("/api/auth/accounts").json() if a["name"] == "kid")
    assert c.delete(f"/api/auth/accounts/{kid['id']}", headers=ORIGIN).status_code == 204
    assert [a["name"] for a in c.get("/api/auth/accounts").json()] == ["mum"]
    assert c.post("/api/auth/switch", json={"user_id": kid["id"]}, headers=ORIGIN).status_code == 404


def test_wrong_password_and_other_sites(app):
    c = signed_in(app, "mum")
    assert c.post("/api/auth/accounts", json={"name": "kid", "password": "nope"}, headers=ORIGIN).status_code == 401
    assert me(c) == "mum"
    # another site's page can't add or switch (the cookie would go with it)
    assert c.post("/api/auth/accounts", json={"name": "kid", "password": PASSWORD},
                  headers={"origin": "http://evil.example"}).status_code == 403
    assert c.post("/api/auth/switch", json={"user_id": 1}, headers={"origin": "http://evil.example"}).status_code == 403


def test_sign_out_moves_to_the_next_account(app):
    c = signed_in(app, "mum")
    c.post("/api/auth/accounts", json={"name": "kid", "password": PASSWORD}, headers=ORIGIN)
    c.post("/api/auth/logout", headers=ORIGIN)
    assert me(c) == "mum"  # kid signed out; mum, still signed in here, is current again
    c.post("/api/auth/logout", headers=ORIGIN)
    assert c.get("/api/auth/state").json()["user"] is None


def test_a_session_ended_elsewhere_drops_off(app, monkeypatch):
    c = signed_in(app, "mum")
    c.post("/api/auth/accounts", json={"name": "kid", "password": PASSWORD}, headers=ORIGIN)
    # mum's sessions end elsewhere (signed out on another device, password changed)
    other = TestClient(app)
    other.post("/api/auth/login", json={"name": "mum", "password": PASSWORD})
    con = connect(app.state.paths.db)
    con.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE name='mum')")
    con.commit()
    con.close()
    import time
    import bams.app
    later = time.monotonic() + 120  # past the minute signed-in sessions are remembered for
    monkeypatch.setattr(bams.app.time, "monotonic", lambda: later)
    assert [a["name"] for a in c.get("/api/auth/accounts").json()] == ["kid"]
