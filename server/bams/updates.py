"""Updates: the newest BAMS release on GitHub, downloading it, and installing it (Settings -> About).

Releases are published at github.com/TomSomerville/bams (public): each has BAMS-Setup-<v>.exe, bams_<v>_all.deb and
SHA256SUMS.txt. GitHub lists every asset's SHA-256 ("digest"); a download is checked against it (or against
SHA256SUMS.txt) before anything runs it. How an update is installed depends on how this copy was installed:

- "windows" (the Inno Setup installer, a service as LocalSystem): the downloaded installer runs silently from Task
  Scheduler as SYSTEM. Not as our own child process: the installer stops the BAMS service, and WinSW kills the
  service's process tree when it stops, which would kill the installer half-way.
- "deb" (/opt/bams): the service runs as the desktop user, without root, so it can't install a package. The .deb is
  downloaded into the data dir and the page shows the one `sudo apt install` command to run.
- "source" (a checkout, `python -m bams`): the page links to the release; update with git.

Everything goes in <data dir>/updates, never near the media.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

from .config import VERSION

log = logging.getLogger(__name__)

REPO = "TomSomerville/bams"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
USER_AGENT = f"BAMS/{VERSION} ( https://github.com/{REPO} )"
CHECK_EVERY = 3600  # seconds a check is reused (GitHub allows 60 unauthenticated API calls an hour per address)
TASK = "BAMS update"  # the Task Scheduler task that runs the Windows installer

transport: httpx.BaseTransport | None = None  # tests swap in an httpx.MockTransport
now = time.time

_lock = threading.Lock()
_checked: dict = {"at": 0.0, "release": None, "error": None}
_job: dict = {"state": "idle"}  # idle | downloading | ready | installing | error


def parse_version(v: str) -> tuple[int, ...]:
    """'v0.5.3' -> (0, 5, 3)."""
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def install_kind() -> str:
    """How this copy was installed: "windows", "deb" or "source"."""
    if sys.platform == "win32" and (Path(sys.executable).resolve().parent.parent / "service" / "bams-service.exe").is_file():
        return "windows"
    if Path(__file__).resolve().is_relative_to("/opt/bams"):
        return "deb"
    return "source"


def _client() -> httpx.Client:
    return httpx.Client(timeout=30, headers={"user-agent": USER_AGENT}, transport=transport, follow_redirects=True)


def _asset_kind(name: str) -> str | None:
    if name.startswith("BAMS-Setup-") and name.endswith(".exe"):
        return "windows"
    if name.startswith("bams_") and name.endswith("_all.deb"):
        return "deb"
    return None


def _release(data: dict) -> dict:
    assets = {}
    sums = None
    for a in data.get("assets") or []:
        url = a.get("browser_download_url") or ""
        if not url.startswith(DOWNLOAD_PREFIX):
            continue
        if a.get("name") == "SHA256SUMS.txt":
            sums = url
        elif kind := _asset_kind(a.get("name") or ""):
            digest = a.get("digest") or ""
            assets[kind] = {"name": a["name"], "url": url, "size": a.get("size"),
                            "sha256": digest[7:] if digest.startswith("sha256:") else None}
    return {"version": str(data.get("tag_name") or "").lstrip("v"), "name": data.get("name"),
            "notes": data.get("body") or "", "url": data.get("html_url"), "published": data.get("published_at"),
            "assets": assets, "sums_url": sums}


def check(force: bool = False) -> dict:
    """The latest release (reused for CHECK_EVERY seconds). Never raises: a failure is kept in `error`."""
    with _lock:
        if not force and _checked["at"] and now() - _checked["at"] < CHECK_EVERY:
            return dict(_checked)
    try:
        with _client() as c:
            r = c.get(LATEST_URL, headers={"accept": "application/vnd.github+json"})
            if r.status_code == 404:
                release, error = None, None  # no release published yet
            else:
                r.raise_for_status()
                release, error = _release(r.json()), None
    except (httpx.HTTPError, ValueError) as e:
        log.info("update check failed: %s", e)
        release, error = None, f"Couldn't reach GitHub ({e.__class__.__name__})."
    with _lock:
        _checked.update(at=now(), release=release if not error else _checked["release"], error=error)
        return dict(_checked)


def status(force: bool = False) -> dict:
    c = check(force)
    rel = c["release"]
    kind = install_kind()
    newer = bool(rel and rel["version"] and parse_version(rel["version"]) > parse_version(VERSION))
    with _lock:
        job = dict(_job)
    return {"current": VERSION, "install": kind, "checked_at": c["at"] or None, "error": c["error"],
            "latest": {k: v for k, v in rel.items() if k != "sums_url"} if rel else None, "newer": newer,
            "can_download": newer and kind in rel["assets"] if rel else False, "job": job}


def _expected_sha(c: httpx.Client, asset: dict, sums_url: str | None) -> str:
    if asset["sha256"]:
        return asset["sha256"].lower()
    if sums_url:
        for line in c.get(sums_url).raise_for_status().text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == asset["name"]:
                return parts[0].lower()
    raise RuntimeError("the release doesn't say what the file's SHA-256 should be")


def download(updates_dir: Path, release: dict, kind: str) -> Path:
    """Fetch this install's file of `release` into updates_dir, checked against its SHA-256. Updates _job."""
    asset = release["assets"][kind]
    updates_dir.mkdir(parents=True, exist_ok=True)
    for old in updates_dir.iterdir():  # one update at a time: older downloads go
        if old.is_file() and old.name != "install.log":
            old.unlink(missing_ok=True)
    target = updates_dir / asset["name"]
    part = target.with_name(target.name + ".part")
    h = hashlib.sha256()
    with _client() as c:
        want = _expected_sha(c, asset, release.get("sums_url"))
        with c.stream("GET", asset["url"]) as r, part.open("wb") as f:
            r.raise_for_status()
            size = int(r.headers.get("content-length") or asset.get("size") or 0)
            with _lock:
                _job.update(size=size, got=0)
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                h.update(chunk)
                with _lock:
                    _job["got"] = _job.get("got", 0) + len(chunk)
    if h.hexdigest() != want:
        part.unlink(missing_ok=True)
        raise RuntimeError("the download doesn't match the release's SHA-256, so it was deleted")
    part.replace(target)
    return target


def start_download(updates_dir: Path) -> dict:
    """Download the newer release for this install in the background. Returns the job."""
    st = status()
    if not st["can_download"]:
        raise ValueError("There's no newer release for this kind of install.")
    release = _checked["release"]
    kind = st["install"]
    with _lock:
        if _job["state"] in ("downloading", "installing"):
            return dict(_job)
        _job.clear()
        _job.update(state="downloading", version=release["version"], got=0, size=release["assets"][kind]["size"])

    def run():
        try:
            path = download(updates_dir, release, kind)
            with _lock:
                _job.update(state="ready", file=str(path), got=_job.get("size") or 0)
        except Exception as e:  # noqa: BLE001 - shown to the admin, logged here
            log.warning("update download failed: %s", e)
            with _lock:
                _job.update(state="error", error=str(e))

    threading.Thread(target=run, name="update-download", daemon=True).start()
    with _lock:
        return dict(_job)


def install(updates_dir: Path) -> dict:
    """Windows: run the downloaded, checked installer from Task Scheduler (SYSTEM, silent). The service is stopped,
    updated and started again by the installer, so this server goes away shortly after this returns."""
    if install_kind() != "windows":
        raise ValueError("Only the Windows install can update itself; on Linux run the apt command shown.")
    with _lock:
        job = dict(_job)
    path = Path(job.get("file") or "")
    if job["state"] != "ready" or not path.is_file() or path.parent != updates_dir:
        raise ValueError("Download the update first.")
    cmd = f'"{path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART'
    logged = f'{cmd} /LOG="{updates_dir / "install.log"}"'
    cmd = logged if len(logged) <= 261 else cmd  # schtasks' limit for /TR; without a path Inno logs to SYSTEM's TEMP
    if len(cmd) > 261:
        raise ValueError("The data folder's path is too long for Task Scheduler; run the installer by hand: " + str(path))
    run = lambda *a: subprocess.run(["schtasks", *a], capture_output=True, text=True, check=True)  # noqa: E731
    try:
        run("/Create", "/TN", TASK, "/TR", cmd, "/SC", "ONCE", "/ST", "00:00", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F")
        run("/Run", "/TN", TASK)
    except (OSError, subprocess.CalledProcessError) as e:
        detail = getattr(e, "stderr", "") or str(e)
        log.warning("couldn't start the update: %s", detail)
        raise RuntimeError(f"Couldn't start the installer: {detail.strip()}") from e
    with _lock:
        _job["state"] = "installing"
        return dict(_job)


def tidy(updates_dir: Path) -> None:
    """At start-up: remove the finished update task and downloads of versions this one already is (or passed)."""
    if install_kind() == "windows":
        subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], capture_output=True)
    if not updates_dir.is_dir():
        return
    for f in updates_dir.iterdir():
        m = re.search(r"\d+\.\d+\.\d+", f.name)
        if f.is_file() and m and parse_version(m.group()) <= parse_version(VERSION):
            f.unlink(missing_ok=True)


def reset() -> None:
    """Tests: forget checks and jobs."""
    with _lock:
        _checked.update(at=0.0, release=None, error=None)
        _job.clear()
        _job["state"] = "idle"
