"""Settings -> Security: sign-in waits and lockout, the sign-in log, IP lists, the traffic log."""

import json

import pytest
from fastapi.testclient import TestClient

from bams import netflow, security
from bams.app import create_app
from bams.config import Paths
from bams.db import connect
from conftest import PASSWORD, signed_in


@pytest.fixture
def app(tmp_path):
    return create_app(Paths(tmp_path / "data"), start_scheduler=False)


@pytest.fixture
def clock(monkeypatch):
    """security.now() under the test's control, so waits pass without sleeping."""
    t = {"now": 1_000_000.0}
    monkeypatch.setattr(security, "now", lambda: t["now"])
    return t


def login(c, name, pw):
    return c.post("/api/auth/login", json={"name": name, "password": pw})


def test_waits_double_then_the_account_locks(app, clock):
    admin = signed_in(app, "Tom")
    admin.post("/api/users", json={"name": "Kid", "password": PASSWORD})
    c = TestClient(app, client=("10.0.0.5", 1))
    assert [security.wait_after(n) for n in range(5)] == [0, 1, 2, 4, 8]
    for n in range(1, 5):
        r = login(c, "Kid", "nope")
        assert r.status_code == 401 and f"Wait {int(security.wait_after(n))} second" in r.json()["detail"]
        r = login(c, "Kid", PASSWORD)  # too soon: refused even with the right password, and not counted
        assert r.status_code == 429 and r.headers["retry-after"] == str(int(security.wait_after(n)))
        clock["now"] += security.wait_after(n)
    r = login(c, "Kid", "nope")  # the 5th wrong password in a row locks it
    assert r.status_code == 403 and "locked" in r.json()["detail"]
    clock["now"] += 10**6
    assert login(c, "Kid", PASSWORD).status_code == 403  # locked until an admin unlocks it
    kid = next(a for a in admin.get("/api/security/accounts").json() if a["name"] == "Kid")
    assert kid["locked"] and kid["failures"] == 5 and kid["locked_by"] is None
    assert admin.put(f"/api/security/accounts/{kid['id']}/lock", json={"locked": False}).status_code == 200
    assert login(c, "Kid", PASSWORD).status_code == 200


def test_a_right_password_resets_the_count(app, clock):
    signed_in(app, "Tom")
    c = TestClient(app)
    for _ in range(3):
        assert login(c, "Tom", "nope").status_code == 401
        clock["now"] += 100
    assert login(c, "Tom", PASSWORD).status_code == 200
    assert login(c, "Tom", "nope").json()["detail"].endswith("Wait 1 second before trying again.")


def test_threshold_setting(app, clock):
    admin = signed_in(app, "Tom")
    assert admin.get("/api/security").json()["lockout_threshold"] == 5
    assert admin.put("/api/security/lockout", json={"threshold": 0}).status_code == 422
    assert admin.put("/api/security/lockout", json={"threshold": 2}).status_code == 200
    admin.post("/api/users", json={"name": "Kid", "password": PASSWORD})
    c = TestClient(app)
    assert login(c, "Kid", "nope").status_code == 401
    clock["now"] += 5
    assert login(c, "Kid", "nope").status_code == 403


def test_unknown_names_answer_like_accounts(app, clock):
    signed_in(app, "Tom")
    c = TestClient(app)
    assert login(c, "Nobody", "x").json()["detail"] == login(c, "Tom", "x").json()["detail"]
    assert login(c, "Nobody", "x").status_code == 429 == login(c, "Tom", "x").status_code


def test_admin_lock_signs_out_and_logs(app, clock):
    admin = signed_in(app, "Tom")
    kid = signed_in(app, "Kid", admin=False)
    kid_id = kid.get("/api/auth/state").json()["user"]["id"]
    me = admin.get("/api/auth/state").json()["user"]["id"]
    assert admin.put(f"/api/security/accounts/{me}/lock", json={"locked": True}).status_code == 400  # not yourself
    assert kid.put(f"/api/security/accounts/{kid_id}/lock", json={"locked": False}).status_code == 403  # admins only
    r = admin.put(f"/api/security/accounts/{kid_id}/lock", json={"locked": True})
    assert r.status_code == 200 and r.json()["locked"] and r.json()["locked_by"] == "Tom"
    assert kid.get("/api/libraries").status_code == 401  # signed out
    assert login(kid, "Kid", PASSWORD).status_code == 403
    log = admin.get("/api/security/auth-log").json()["entries"]
    assert [(e["event"], e["result"], e["name"]) for e in log[:2]] == [("sign-in", "failed", "Kid"),
                                                                      ("lock", "admin", "Kid")]
    assert log[0]["reason"] == "account locked"
    oks = admin.get("/api/security/auth-log?result=ok").json()["entries"]
    assert {e["name"] for e in oks} == {"Tom", "Kid"} and all(e["result"] == "ok" for e in oks)
    page = admin.get("/api/security/auth-log?limit=1").json()
    assert len(page["entries"]) == 1 and page["next"]
    older = admin.get(f"/api/security/auth-log?limit=1&before={page['next']}").json()["entries"]
    assert older[0]["id"] < page["entries"][0]["id"]


def test_cli_unlock(app, clock, tmp_path):
    from bams.__main__ import main
    admin = signed_in(app, "Tom")
    kid = admin.post("/api/users", json={"name": "Kid", "password": PASSWORD}).json()
    admin.put(f"/api/security/accounts/{kid['id']}/lock", json={"locked": True})
    assert main(["--data-dir", str(tmp_path / "data"), "user", "unlock", "Kid"]) == 0
    assert login(TestClient(app), "Kid", PASSWORD).status_code == 200


def test_ip_policy_rules():
    p = security.IpPolicy("allow_all", [], [{"cidr": "10.0.0.0/8"}, {"cidr": "2001:db8::/32"}])
    assert p.allowed("192.168.1.2") and not p.allowed("10.1.2.3") and not p.allowed("2001:db8::5")
    assert not p.allowed("::ffff:10.1.2.3")  # IPv4 written the IPv6 way
    assert p.allowed("127.0.0.1") and p.allowed("::1")  # the server itself, always
    p = security.IpPolicy("allowlist", [{"cidr": "192.168.1.0/24"}], [{"cidr": "192.168.1.66"}])
    assert p.allowed("192.168.1.7") and not p.allowed("192.168.2.7") and not p.allowed("192.168.1.66")  # block wins
    assert not p.allowed("testclient") and p.allowed("127.0.0.1")
    assert security.clean_entries([{"cidr": "192.168.1.7/24"}, {"cidr": " 10.0.0.1 "}, {"cidr": "10.0.0.1/32"}]) == [
        {"cidr": "192.168.1.0/24", "note": ""}, {"cidr": "10.0.0.1", "note": ""}]
    with pytest.raises(security.SecurityError):
        security.clean_entries([{"cidr": "not an address"}])


def test_ip_lists_through_the_api(app):
    admin = signed_in(app, "Tom")
    lan = TestClient(app, client=("192.168.1.20", 1))
    other = TestClient(app, client=("192.168.1.30", 1))
    assert lan.get("/api/auth/state").status_code == 200
    r = admin.put("/api/security/ip", json={"mode": "allow_all", "block": [{"cidr": "192.168.1.30", "note": "x"}]})
    assert r.status_code == 200 and r.json()["block"] == [{"cidr": "192.168.1.30", "note": "x"}]
    assert other.get("/").status_code == 403 and other.get("/api/auth/state").status_code == 403
    assert lan.get("/api/auth/state").status_code == 200
    # admin's own address ("testclient", not an IP) would be shut out by an allow list without it
    r = admin.put("/api/security/ip", json={"mode": "allowlist", "allow": [{"cidr": "192.168.1.20"}]})
    assert r.status_code == 400 and "your own address" in r.json()["detail"]
    local = TestClient(app, client=("127.0.0.1", 1))
    local.post("/api/auth/login", json={"name": "Tom", "password": PASSWORD})
    r = local.put("/api/security/ip", json={"mode": "allowlist", "allow": [{"cidr": "192.168.1.0/24"}],
                                            "block": [{"cidr": "192.168.1.30"}]})
    assert r.status_code == 200
    assert lan.get("/api/auth/state").status_code == 200 and other.get("/api/auth/state").status_code == 403
    assert TestClient(app, client=("10.9.9.9", 1)).get("/api/auth/state").status_code == 403
    assert admin.get("/api/auth/state").status_code == 403  # "testclient" isn't on the allow list
    assert local.put("/api/security/ip", json={"mode": "allow_all"}).status_code == 200
    assert TestClient(app, client=("10.9.9.9", 1)).get("/api/auth/state").status_code == 200


def test_cli_allow_all(app, tmp_path):
    from bams.__main__ import main
    local = TestClient(app, client=("127.0.0.1", 1))
    signed_in(app, "Tom")
    local.post("/api/auth/login", json={"name": "Tom", "password": PASSWORD})
    local.put("/api/security/ip", json={"mode": "allowlist", "allow": [{"cidr": "192.168.1.0/24"}]})
    assert main(["--data-dir", str(tmp_path / "data"), "security", "allow-all"]) == 0
    app.state.security._policy_at = -1e9  # a running server re-reads within 10 s
    assert TestClient(app, client=("10.9.9.9", 1)).get("/api/auth/state").status_code == 200


def test_every_request_is_in_the_traffic_log(app):
    admin = signed_in(app, "Tom")
    admin.get("/api/libraries?x=1")
    TestClient(app, client=("192.168.1.99", 4242)).get("/api/libraries")
    entries = admin.get("/api/security/netflow/entries").json()["entries"]
    lib = [e for e in entries if e["path"] == "/api/libraries"]
    assert lib[0]["client"] == "192.168.1.99" and lib[0]["client_port"] == 4242 and lib[0]["status"] == 401
    assert lib[0]["user"] is None and lib[0]["action"] == "allow"
    assert lib[1]["user"] == "Tom" and lib[1]["status"] == 200 and lib[1]["query"] == "x=1"
    assert lib[1]["bytes_out"] > 0 and lib[1]["duration_ms"] >= 0
    login = next(e for e in entries if e["path"] == "/api/auth/login")
    assert login["method"] == "POST" and login["bytes_in"] > 0
    hits = admin.get("/api/security/netflow/entries?q=192.168.1.99").json()["entries"]
    assert [e["client"] for e in hits] == ["192.168.1.99"]
    status = admin.get("/api/security").json()["netflow"]
    assert status["files"] == 1 and status["bytes"] > 0 and status["max_bytes"] == netflow.DEFAULT_MAX_BYTES


def test_blocked_requests_are_logged(app):
    admin = signed_in(app, "Tom")
    admin.put("/api/security/ip", json={"mode": "allow_all", "block": [{"cidr": "203.0.113.0/24"}]})
    TestClient(app, client=("203.0.113.9", 1)).get("/whatever")
    e = admin.get("/api/security/netflow/entries?q=203.0.113.9").json()["entries"][0]
    assert e["action"] == "block" and e["status"] == 403 and e["path"] == "/whatever"


def test_traffic_log_size_cap_and_paging(tmp_path, monkeypatch):
    n = netflow.Netflow(tmp_path / "flows", max_bytes=netflow.MIN_MAX_BYTES)
    monkeypatch.setattr(netflow, "segment_size", lambda _m: 50_000)
    pad = "x" * 400
    for i in range(3000):  # ~1.3 MB: many 50 kB files, but the cap is 10 MB, so nothing trimmed yet
        n.record({"i": i, "pad": pad})
    n.flush()
    assert len(n.files()) > 10 and n.usage()["bytes"] > 1_000_000
    n.configure(max_bytes=300_000)  # a smaller cap trims the oldest files at once
    assert n.usage()["bytes"] <= 300_000 + 50_000
    # read it all back, newest first, a page at a time, with nothing skipped or repeated
    seen, cur = [], None
    while True:
        page = n.read(before=cur, limit=97)
        seen += [e["i"] for e in page["entries"]]
        if not page["next"]:
            break
        cur = page["next"]
    assert seen == list(range(2999, 2999 - len(seen), -1)) and len(seen) > 500
    assert [e["i"] for e in n.read(q='"i":2998,')["entries"]] == [2998]


def test_traffic_log_folder_and_size_settings(app, tmp_path):
    admin = signed_in(app, "Tom")
    admin.get("/api/libraries")
    new = tmp_path / "elsewhere" / "flows"
    r = admin.put("/api/security/netflow", json={"folder": str(new), "max_bytes": 50 * 1024**2})
    assert r.status_code == 200 and r.json()["folder"] == str(new) and r.json()["custom"]
    assert r.json()["max_bytes"] == 50 * 1024**2
    admin.get("/api/libraries")
    app.state.netflow.flush()
    assert any(new.glob("netflow-*.jsonl"))
    assert admin.put("/api/security/netflow", json={"folder": "relative/path"}).status_code == 400
    assert admin.put("/api/security/netflow", json={"max_bytes": 5}).status_code == 422
    t = app.state.paths.transcode
    assert admin.put("/api/security/netflow", json={"folder": str(t / "x")}).status_code == 400
    lib = tmp_path / "media"
    lib.mkdir()
    admin.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(lib)]})
    r = admin.put("/api/security/netflow", json={"folder": str(lib / "logs")})
    assert r.status_code == 400 and "media library" in r.json()["detail"]
    r = admin.put("/api/security/netflow", json={"folder": ""})
    assert r.json()["folder"] == str(app.state.paths.netflow) and not r.json()["custom"]
    con = connect(app.state.paths.db)
    assert json.loads(json.dumps(dict(con.execute("SELECT * FROM settings WHERE key='netflow_max_bytes'")
                                      .fetchone())))["value"] == str(50 * 1024**2)
    con.close()
