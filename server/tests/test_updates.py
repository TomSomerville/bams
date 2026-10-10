"""Updates (Settings -> About): the newest GitHub release, a checked download, the Windows install via Task Scheduler."""

import hashlib
import subprocess
import time

import httpx
import pytest

from bams import updates
from bams.app import create_app
from bams.config import VERSION, Paths
from conftest import signed_in

PAYLOAD = b"pretend installer" * 1000
DL = updates.DOWNLOAD_PREFIX + "v99.0.0/"


def release(version="99.0.0", digest=True, payload=PAYLOAD):
    sha = hashlib.sha256(payload).hexdigest()
    asset = lambda name: {"name": name, "browser_download_url": DL + name, "size": len(payload),  # noqa: E731
                          "digest": f"sha256:{sha}" if digest else None}
    return {"tag_name": f"v{version}", "name": f"BAMS {version}", "body": "What's new", "html_url": "https://x/rel",
            "published_at": "2026-10-09T00:00:00Z",
            "assets": [asset(f"BAMS-Setup-{version}.exe"), asset(f"bams_{version}_all.deb"),
                       {"name": "SHA256SUMS.txt", "browser_download_url": DL + "SHA256SUMS.txt"},
                       {"name": "evil.exe", "browser_download_url": "https://elsewhere.example/BAMS-Setup-1.exe"}]}


@pytest.fixture
def gh(tmp_path, monkeypatch):
    """A fake GitHub: `state` decides the latest release and what the download serves."""
    state = {"release": release(), "file": PAYLOAD, "calls": 0, "status": 200}

    def handler(req: httpx.Request):
        if req.url.path.endswith("/releases/latest"):
            state["calls"] += 1
            return httpx.Response(state["status"], json=state["release"])
        if req.url.path.endswith("SHA256SUMS.txt"):
            return httpx.Response(200, text=f"{hashlib.sha256(PAYLOAD).hexdigest()}  BAMS-Setup-99.0.0.exe\n")
        return httpx.Response(200, content=state["file"])

    updates.reset()
    monkeypatch.setattr(updates, "transport", httpx.MockTransport(handler))
    app = create_app(Paths(tmp_path / "data"), start_scheduler=False)
    yield state, signed_in(app), app
    updates.reset()


def wait_job(c, until=("ready", "error")):
    for _ in range(100):
        st = c.get("/api/update").json()
        if st["job"]["state"] in until:
            return st
        time.sleep(0.05)
    raise AssertionError(st)


def test_check_finds_a_newer_release(gh):
    state, c, _ = gh
    st = c.get("/api/update").json()
    assert st["current"] == VERSION and st["newer"] and st["latest"]["version"] == "99.0.0"
    assert set(st["latest"]["assets"]) == {"windows", "deb"}  # only files from the project's own releases
    assert st["install"] == "source" and not st["can_download"]  # a checkout updates with git
    c.get("/api/update")
    assert state["calls"] == 1  # reused for an hour...
    c.get("/api/update?refresh=true")
    assert state["calls"] == 2  # ...unless asked again
    state["release"] = release(version="0.0.1")
    assert not c.get("/api/update?refresh=true").json()["newer"]


def test_check_failure_is_reported_not_raised(gh):
    state, c, _ = gh
    state["status"] = 500
    st = c.get("/api/update").json()
    assert st["error"] and st["latest"] is None and not st["newer"]


def test_admins_only(gh):
    _, c, app = gh
    kid = signed_in(app, "Kid", admin=False)
    assert kid.get("/api/update").status_code == 403
    assert kid.post("/api/update/download").status_code == 403
    assert kid.post("/api/update/install").status_code == 403


@pytest.mark.parametrize("digest", [True, False])  # GitHub's digest, else SHA256SUMS.txt
def test_windows_download_and_install(gh, monkeypatch, digest):
    state, c, app = gh
    state["release"] = release(digest=digest)
    monkeypatch.setattr(updates, "install_kind", lambda: "windows")
    ran = []
    monkeypatch.setattr(updates.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    assert c.post("/api/update/install").status_code == 409  # nothing downloaded yet
    assert c.post("/api/update/download").json()["job"]["state"] in ("downloading", "ready")
    st = wait_job(c)
    assert st["job"]["state"] == "ready", st["job"]
    exe = app.state.paths.root / "updates" / "BAMS-Setup-99.0.0.exe"
    assert exe.read_bytes() == PAYLOAD
    r = c.post("/api/update/install")
    assert r.status_code == 200, r.text
    assert r.json()["job"]["state"] == "installing"
    create, run = ran
    assert create[:4] == ["schtasks", "/Create", "/TN", updates.TASK] and "/RU" in create and "SYSTEM" in create
    assert create[create.index("/TR") + 1].startswith(f'"{exe}" /VERYSILENT')
    assert run == ["schtasks", "/Run", "/TN", updates.TASK]


def test_a_download_that_doesnt_match_is_deleted(gh, monkeypatch):
    state, c, app = gh
    monkeypatch.setattr(updates, "install_kind", lambda: "deb")
    state["file"] = b"tampered"
    st = (c.post("/api/update/download"), wait_job(c))[1]
    assert st["job"]["state"] == "error" and "SHA-256" in st["job"]["error"]
    assert not any((app.state.paths.root / "updates").iterdir())
    assert c.post("/api/update/install").status_code == 409  # Linux: the admin runs apt


def test_tidy_keeps_only_newer_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "install_kind", lambda: "deb")
    d = tmp_path / "updates"
    d.mkdir()
    (d / f"bams_{VERSION}_all.deb").write_bytes(b"x")
    (d / "bams_99.0.0_all.deb").write_bytes(b"x")
    updates.tidy(d)
    assert [f.name for f in d.iterdir()] == ["bams_99.0.0_all.deb"]


def test_versions_compare_as_numbers():
    assert updates.parse_version("v0.10.0") > updates.parse_version("0.9.9")
    assert updates.parse_version("0.5.3") == (0, 5, 3)
