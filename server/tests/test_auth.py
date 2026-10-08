"""Accounts, signing in, and who may do what."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from bams import auth
from bams.app import create_app
from bams.config import Paths
from bams.db import connect
from conftest import PASSWORD, signed_in


@pytest.fixture
def app(tmp_path):
    return create_app(Paths(tmp_path / "data"), start_scheduler=False)


def test_passwords_are_hashed():
    h = auth.hash_password("hunter2hunter2")
    assert h.startswith("scrypt$") and "hunter2" not in h
    assert auth.verify_password("hunter2hunter2", h) and not auth.verify_password("hunter2hunter3", h)
    assert h != auth.hash_password("hunter2hunter2")  # salted
    assert not auth.verify_password("x", "garbage")


def test_everything_needs_signing_in(app):
    c = TestClient(app)
    for path in ("/api/libraries", "/api/items", "/api/status", "/api/images/x.jpg", "/api/files/1/stream",
                 "/api/hls/abc/index.m3u8", "/api/continue"):
        assert c.get(path).status_code == 401, path
    assert c.get("/api/auth/state").json() == {"user": None, "setup": True, "setup_here": False}


def test_first_admin_only_from_the_server_itself(app):
    remote = TestClient(app, client=("192.168.1.50", 5000))
    r = remote.post("/api/auth/setup", json={"name": "Tom", "password": PASSWORD})
    assert r.status_code == 403 and "bams user add" in r.json()["detail"]
    local = TestClient(app, client=("127.0.0.1", 5000))
    assert local.get("/api/auth/state").json()["setup_here"] is True
    assert local.post("/api/auth/setup", json={"name": "Tom", "password": "short"}).status_code == 400
    r = local.post("/api/auth/setup", json={"name": "Tom", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["is_admin"] is True
    assert local.get("/api/libraries").status_code == 200  # signed in by the setup
    again = TestClient(app, client=("127.0.0.1", 5001))
    assert again.post("/api/auth/setup", json={"name": "Eve", "password": PASSWORD}).status_code == 409


def test_sign_in_and_out(app):
    c = signed_in(app, "Tom")
    assert c.get("/api/auth/state").json()["user"]["name"] == "Tom"
    cookie = c.cookies.get(auth.COOKIE)
    con = connect(app.state.paths.db)
    stored = con.execute("SELECT token FROM sessions").fetchone()["token"]
    assert stored != cookie and len(stored) == 64  # only a hash of the cookie is kept
    con.close()
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/libraries").status_code == 401
    other = TestClient(app)
    assert other.post("/api/auth/login", json={"name": "tom", "password": PASSWORD}).status_code == 200  # any case
    assert other.post("/api/auth/login", json={"name": "Tom", "password": "wrong"}).status_code == 401
    assert other.post("/api/auth/login", json={"name": "Nobody", "password": PASSWORD}).status_code == 401


def test_wrong_passwords_are_throttled(app):
    signed_in(app, "Tom")
    c = TestClient(app, client=("10.0.0.9", 1))
    for _ in range(auth.Throttle.MAX):
        assert c.post("/api/auth/login", json={"name": "Tom", "password": "nope"}).status_code == 401
    r = c.post("/api/auth/login", json={"name": "Tom", "password": PASSWORD})
    assert r.status_code == 429  # even the right password waits
    assert TestClient(app, client=("10.0.0.10", 1)).post(
        "/api/auth/login", json={"name": "Tom", "password": PASSWORD}).status_code == 200  # others aren't affected


def test_viewers_cant_manage(app, tmp_path):
    admin = signed_in(app, "Tom")
    viewer = signed_in(app, "Kid", admin=False)
    for method, path, body in (("post", "/api/libraries", {"name": "x", "type": "show", "paths": [str(tmp_path)]}),
                               ("put", "/api/settings/transcoding", {"max_transcodes": 1}),
                               ("get", "/api/fs/browse", None), ("get", "/api/users", None),
                               ("post", "/api/users", {"name": "x", "password": PASSWORD}),
                               ("delete", "/api/settings/tmdb-key", None)):
        r = getattr(viewer, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 403, (method, path)
    st = viewer.get("/api/status").json()
    assert st["data_dir"] is None and st["ffmpeg"] in (True, None)  # no server paths for viewers
    assert admin.get("/api/status").json()["data_dir"]
    assert viewer.get("/api/libraries").status_code == 200 and viewer.get("/api/settings").status_code == 200


def test_user_management(app):
    c = signed_in(app, "Tom")
    me = c.get("/api/auth/state").json()["user"]
    kid = c.post("/api/users", json={"name": "Kid", "password": PASSWORD}).json()
    assert c.post("/api/users", json={"name": "kid", "password": PASSWORD}).status_code == 400  # taken
    assert [u["name"] for u in c.get("/api/users").json()] == ["Kid", "Tom"]
    k = TestClient(app)
    assert k.post("/api/auth/login", json={"name": "Kid", "password": PASSWORD}).status_code == 200
    assert c.patch(f"/api/users/{kid['id']}", json={"password": "a new password"}).status_code == 200
    assert k.get("/api/libraries").status_code == 401  # a reset password signs them out
    assert c.patch(f"/api/users/{me['id']}", json={"is_admin": False}).status_code == 400  # the last admin
    assert c.delete(f"/api/users/{me['id']}").status_code == 400  # not yourself
    assert c.delete(f"/api/users/{kid['id']}").status_code == 204
    assert [u["name"] for u in c.get("/api/users").json()] == ["Tom"]


def test_change_own_password(app):
    c = signed_in(app, "Tom")
    elsewhere = TestClient(app)
    elsewhere.post("/api/auth/login", json={"name": "Tom", "password": PASSWORD})
    assert c.put("/api/auth/password", json={"current": "wrong", "new": "brand new pw"}).status_code == 400
    assert c.put("/api/auth/password", json={"current": PASSWORD, "new": "brand new pw"}).status_code == 200
    assert c.get("/api/libraries").status_code == 200        # this browser stays signed in
    assert elsewhere.get("/api/libraries").status_code == 401  # the others are signed out


def test_cross_site_changes_are_refused(app):
    c = signed_in(app, "Tom")
    r = c.put("/api/settings/transcoding", json={"max_transcodes": 2}, headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    r = c.put("/api/settings/transcoding", json={"max_transcodes": 2}, headers={"origin": "http://testserver"})
    assert r.status_code == 200


def test_migration_to_v4_keeps_data(tmp_path):
    from bams import db
    p = tmp_path / "old.db"
    con = sqlite3.connect(p, isolation_level=None)
    con.executescript("BEGIN;" + db.SCHEMA + "PRAGMA user_version = 1; COMMIT;")
    con.execute("INSERT INTO settings VALUES ('tmdb_key', 'k')")
    con.close()
    con = connect(p)
    db.migrate(con, backup_dir=tmp_path / "backups")
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION == 6
    assert db.get_setting(con, "tmdb_key") == "k" and auth.user_count(con) == 0
    assert "prefs" in [r[1] for r in con.execute("PRAGMA table_info(users)")]  # v5
    assert "manual" in [r[1] for r in con.execute("PRAGMA table_info(files)")]  # v6
    assert list((tmp_path / "backups").iterdir())
