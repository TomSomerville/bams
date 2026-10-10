"""Apps on other devices (the TV app): finding the server, linking with a code, bearer tokens, media tickets."""

import pytest
from fastapi.testclient import TestClient

from bams import auth, devices
from bams.app import create_app
from bams.config import Paths
from bams.db import connect
from conftest import PASSWORD, signed_in


@pytest.fixture
def app(tmp_path):
    return create_app(Paths(tmp_path / "data"), start_scheduler=False)


def _tv(app) -> TestClient:
    # a TV: another address, an Origin the server isn't on (the app's own), no cookies
    return TestClient(app, client=("192.168.1.80", 40000), headers={"origin": "file://"})


def _link(app, web: TestClient, name="Living room") -> tuple[TestClient, str]:
    tv = _tv(app)
    r = tv.post("/api/devices/link", json={"name": name})
    assert r.status_code == 200
    code, secret = r.json()["code"], r.json()["secret"]
    assert len(code) == devices.CODE_LEN and not set(code) - set(devices.CODE_CHARS)
    assert tv.post("/api/devices/link/poll", json={"secret": secret}).json() == {"status": "waiting"}
    # typed on a phone: lower case, with a space, is fine
    r = web.post("/api/devices/approve", json={"code": f"{code[:3].lower()} {code[3:]}"})
    assert r.status_code == 200 and r.json() == {"name": name}
    r = tv.post("/api/devices/link/poll", json={"secret": secret}).json()
    assert r["status"] == "linked" and r["user"]["name"] == "Tom"
    # handed out once
    assert tv.post("/api/devices/link/poll", json={"secret": secret}).json() == {"status": "expired"}
    tv.headers["authorization"] = f"Bearer {r['token']}"
    return tv, r["token"]


def test_hello_is_public(app):
    r = TestClient(app).get("/api/hello")
    assert r.status_code == 200 and r.json()["app"] == "bams" and r.json()["version"]


def test_server_name(app):
    """Apps list servers by name: the admin's choice, else "<first admin>'s BAM Server"."""
    bare = TestClient(app)
    assert bare.get("/api/hello").json()["name"]  # no accounts yet: the computer's name
    tom = signed_in(app, "Tom")
    signed_in(app, "Ann")  # a later admin doesn't rename it
    assert bare.get("/api/hello").json()["name"] == "Tom's BAM Server"
    viewer = signed_in(app, "Kid", admin=False)
    assert viewer.put("/api/settings/server-name", json={"name": "Mine"}).status_code == 403
    r = tom.put("/api/settings/server-name", json={"name": "  Living   room  "})
    assert r.json() == {"name": "Living room", "default": "Tom's BAM Server", "custom": True}
    assert bare.get("/api/hello").json()["name"] == "Living room"
    assert viewer.get("/api/settings").json()["server_name"]["name"] == "Living room"
    assert tom.put("/api/settings/server-name", json={"name": ""}).json()["custom"] is False  # back to the default
    assert bare.get("/api/hello").json()["name"] == "Tom's BAM Server"


def test_link_a_tv_with_a_code(app):
    web = signed_in(app, "Tom")
    tv, token = _link(app, web)
    assert tv.get("/api/libraries").status_code == 200
    assert tv.get("/api/auth/state").json()["user"]["name"] == "Tom"
    # a bearer token isn't something a browser attaches by itself: changes from the app's origin are fine
    assert tv.put("/api/me/prefs", json={"home_hero": False}).status_code == 200
    # listed under the account, and can be signed out from there
    listed = web.get("/api/devices").json()
    assert [d["name"] for d in listed] == ["Living room"]
    assert web.delete(f"/api/devices/{listed[0]['id']}").status_code == 204
    assert tv.get("/api/libraries").status_code == 401
    assert web.get("/api/devices").json() == []
    assert web.get("/api/libraries").status_code == 200  # the browser's own session is untouched


def test_wrong_and_used_codes(app):
    web = signed_in(app, "Tom")
    assert web.post("/api/devices/approve", json={"code": "ZZZZZZ"}).status_code == 400
    tv = _tv(app)
    code = tv.post("/api/devices/link", json={"name": "TV"}).json()["code"]
    other = signed_in(app, "Eve", admin=False)
    assert web.post("/api/devices/approve", json={"code": code}).status_code == 200
    assert other.post("/api/devices/approve", json={"code": code}).status_code == 400  # already Tom's
    # nobody signed in can't approve
    assert TestClient(app).post("/api/devices/approve", json={"code": code}).status_code == 401
    # guessing is cut off
    for _ in range(auth.Throttle.MAX):
        other.post("/api/devices/approve", json={"code": "AAAAAA"})
    assert other.post("/api/devices/approve", json={"code": "AAAAAA"}).status_code == 429


def test_codes_run_out():
    t = [0.0]
    codes = devices.LinkCodes(clock=lambda: t[0])
    c = codes.start("TV")
    t[0] += devices.CODE_TTL + 1
    with pytest.raises(devices.LinkError):
        codes.approve(c["code"], 1)
    assert codes.poll(c["secret"])[0] == "expired"


def test_token_sign_in(app):
    signed_in(app, "Tom")
    tv = _tv(app)
    assert tv.post("/api/auth/token", json={"name": "Nobody", "password": "wrong-password"}).status_code == 401
    r = tv.post("/api/auth/token", json={"name": "tom", "password": PASSWORD, "device": "QN50LS03B"})
    assert r.status_code == 200 and "set-cookie" not in r.headers
    tv.headers["authorization"] = f"Bearer {r.json()['token']}"
    assert tv.get("/api/continue").status_code == 200
    assert tv.post("/api/auth/logout").status_code == 204
    assert tv.get("/api/continue").status_code == 401


def test_cookie_requests_from_other_sites_are_still_refused(app):
    web = signed_in(app, "Tom")
    r = web.put("/api/me/prefs", json={"home_hero": False}, headers={"origin": "http://evil.example"})
    assert r.status_code == 403


def test_cors_for_apps_never_for_cookies(app):
    c = TestClient(app)
    pre = c.options("/api/libraries", headers={"origin": "file://", "access-control-request-method": "GET",
                                               "access-control-request-headers": "authorization"})
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == "*"
    assert "authorization" in pre.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in pre.headers
    r = c.get("/api/hello", headers={"origin": "file://"})
    assert r.headers["access-control-allow-origin"] == "*"


def test_media_tickets(app, tmp_path):
    web = signed_in(app, "Tom")
    tv, token = _link(app, web)
    paths = app.state.paths
    (paths.images / "tmdb").mkdir(parents=True, exist_ok=True)
    (paths.images / "tmdb" / "p.jpg").write_bytes(b"jpeg")
    prefix = tv.get("/api/media-ticket").json()["prefix"]
    assert prefix.startswith("/api/t/") and token not in prefix
    bare = TestClient(app)  # an <img> tag or the TV's video player: no headers, no cookie
    assert bare.get(f"{prefix}/images/tmdb/p.jpg").content == b"jpeg"
    # media only, and only reading
    assert bare.get(f"{prefix}/libraries").status_code == 401
    assert bare.get(f"{prefix}/../libraries").status_code in (401, 404)
    assert bare.delete(f"{prefix}/hls/abc").status_code == 401
    # ...but with the session itself, a client can use a ticket link as it is (the web app keeps another server's
    # media links as ticket URLs and opens/closes HLS sessions on them)
    assert tv.delete(f"{prefix}/hls/abc").status_code in (204, 404)
    other_ticket = "/api/t/nonsense/hls/abc"
    assert tv.delete(other_ticket).status_code in (204, 404)  # the token decides, not the ticket
    assert tv.get(other_ticket + "/index.m3u8").status_code == 401  # reading takes a valid ticket
    # forged or altered tickets
    t = prefix.split("/")[3]
    digest, exp, sig = t.split(".")
    assert bare.get(f"/api/t/{digest}.{int(exp) + 999}.{sig}/images/tmdb/p.jpg").status_code == 401
    assert bare.get("/api/t/nonsense/images/tmdb/p.jpg").status_code == 401
    # signing the TV out ends its tickets too
    tv.post("/api/auth/logout")
    assert bare.get(f"{prefix}/images/tmdb/p.jpg").status_code == 401


def test_tickets_expire():
    now = [1000.0]
    tk = devices.Tickets(clock=lambda: now[0])
    t = tk.make("a" * 64, ttl=60)
    assert tk.check(t) == "a" * 64
    now[0] += 61
    assert tk.check(t) is None
    assert devices.Tickets().check(t) is None  # another process's key


def test_ticket_paths():
    assert devices.split_ticket_path("/api/t/x/files/3/stream") == ("x", "/api/files/3/stream")
    assert devices.split_ticket_path("/api/t/x/hls/s/0/1.ts") == ("x", "/api/hls/s/0/1.ts")
    assert devices.split_ticket_path("/api/t/x/users") is None
    assert devices.split_ticket_path("/api/t/x/images/../users") is None
    assert devices.split_ticket_path("/api/files/3/stream") is None


def test_traffic_log_shows_the_real_path_not_the_ticket(app):
    web = signed_in(app, "Tom")
    tv, _ = _link(app, web)
    prefix = tv.get("/api/media-ticket").json()["prefix"]
    TestClient(app).get(f"{prefix}/images/none.jpg")
    entries = web.get("/api/security/netflow/entries").json()["entries"]
    assert not any(e["path"].startswith("/api/t/") for e in entries)
    hit = next(e for e in entries if e["path"] == "/api/images/none.jpg")
    assert hit["user"] == "Tom" and hit["status"] == 404
