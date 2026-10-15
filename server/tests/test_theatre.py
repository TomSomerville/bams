"""Theatre mode: the TV app's page served at /theatre/ for PCs at a TV, next to the web UI at /."""

from fastapi.testclient import TestClient

from bams.app import create_app
from bams.config import Paths
from conftest import PASSWORD


def _app(tmp_path, theatre=True):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<p>web</p>")
    tv = tmp_path / "tv"
    (tv / "assets").mkdir(parents=True)
    (tv / "index.html").write_text("<p>theatre</p>")
    (tv / "assets" / "index-1.js").write_text("1")
    return create_app(Paths(tmp_path / "data"), start_scheduler=False, web_dir=web,
                      theatre_dir=tv if theatre else None)


def test_theatre_page_next_to_the_web_ui(tmp_path):
    c = TestClient(_app(tmp_path), follow_redirects=False)
    r = c.get("/theatre/")
    assert r.status_code == 200 and "theatre" in r.text
    assert r.headers["cache-control"] == "no-cache"  # a cached page would name scripts that no longer exist
    assert c.get("/theatre/assets/index-1.js").text == "1"
    assert c.get("/theatre/assets/gone.js").status_code == 404  # no fallback to the page
    assert c.get("/theatre/settings").status_code == 404        # the TV page has no URL routes
    # without the slash the page's ./assets paths wouldn't resolve, and the mount alone would hand it to the web UI
    r = c.get("/theatre")
    assert r.status_code == 308 and r.headers["location"] == "/theatre/"
    assert "web" in c.get("/").text and "web" in c.get("/settings").text and "web" in c.get("/theatrex").text


def test_no_theatre_build(tmp_path):
    c = TestClient(_app(tmp_path, theatre=False), follow_redirects=False)
    assert "web" in c.get("/theatre/").text  # just the web UI's own fallback, as before


def test_link_from_the_same_origin_with_the_web_cookie(tmp_path):
    """The theatre page can link itself with the web UI's sign-in (it sends the cookie only for approve), and the
    token works on its own: what "Use <name>'s account" on the theatre Link screen does."""
    from bams import auth
    from bams.db import connect
    app = _app(tmp_path)
    con = connect(app.state.paths.db)
    auth.create_user(con, "alice", PASSWORD, False)
    con.close()
    origin = {"origin": "http://testserver"}
    web = TestClient(app)
    assert web.post("/api/auth/login", json={"name": "alice", "password": PASSWORD}).status_code == 200
    page = TestClient(app, headers=origin)  # fetches with credentials: "omit": no cookie
    s = page.post("/api/devices/link", json={"name": "Theatre · Chrome on Linux"}).json()
    assert web.post("/api/devices/approve", json={"code": s["code"]}, headers=origin).status_code == 200
    r = page.post("/api/devices/link/poll", json={"secret": s["secret"]}).json()
    assert r["status"] == "linked" and r["user"]["name"] == "alice"
    me = page.get("/api/auth/state", headers={"authorization": f"Bearer {r['token']}"}).json()["user"]
    assert me["name"] == "alice"
    assert [d["name"] for d in web.get("/api/devices").json()] == ["Theatre · Chrome on Linux"]
