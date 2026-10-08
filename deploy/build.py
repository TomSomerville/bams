"""Build the BAMS installers.

    python deploy/build.py windows      -> dist/BAMS-Setup-<version>.exe   (run on Windows)
    python deploy/build.py deb          -> dist/bams_<version>_all.deb     (runs anywhere)
    python deploy/build.py all
    --skip-web                          use the existing web/dist instead of rebuilding the UI

Needs uv and Node 20+ (npm); the Windows installer also needs Inno Setup 6 (`winget install
JRSoftware.InnoSetup`). The version comes from server/bams/config.py VERSION: bump it before building an
update, then hand people the new installer. It installs over the old one and keeps their data.

What goes in (see deploy/README.md):
  Windows: Python (embeddable, pinned in pins.json), the locked Python packages (requirements.txt, hashes
           checked), BAMS + the built UI, WinSW (runs BAMS as a Windows service). FFmpeg is NOT bundled: the
           installer downloads the pinned build from its publisher and checks its SHA-256.
  .deb:    BAMS + the built UI, a wheelhouse of the locked packages for Python 3.11-3.14 on x86_64 and
           aarch64 (installed into a venv by postinst, offline), the systemd unit. apt pulls Python and FFmpeg.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
BUILD = ROOT / "build"
CACHE = BUILD / "cache"
DIST = ROOT / "dist"
PINS = json.loads((DEPLOY / "pins.json").read_text(encoding="utf-8"))
REQUIREMENTS = DEPLOY / "requirements.txt"


VERSION_OVERRIDE: str | None = None


def version() -> str:
    if VERSION_OVERRIDE:
        return VERSION_OVERRIDE
    text = (ROOT / "server" / "bams" / "config.py").read_text(encoding="utf-8")
    return re.search(r'^VERSION = "([^"]+)"', text, re.M).group(1)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    # npm/npx are .cmd files on Windows: they need the shell to start
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True, shell=sys.platform == "win32" and cmd[0] in ("npm", "npx"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(pin: dict) -> Path:
    """Download a pinned file once into build/cache and check its hash."""
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / pin["url"].rsplit("/", 1)[1]
    if not dest.is_file() or sha256(dest) != pin["sha256"]:
        print(f"  downloading {pin['url']}", flush=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(pin["url"]) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        if (got := sha256(tmp)) != pin["sha256"]:
            tmp.unlink()
            sys.exit(f"error: {pin['url']} has SHA-256 {got}, pins.json expects {pin['sha256']}")
        tmp.replace(dest)
    return dest


def build_web(skip: bool) -> Path:
    web = ROOT / "web"
    if not skip:
        print("== web UI")
        if not (web / "node_modules").is_dir():
            run(["npm", "ci"], cwd=web)
        run(["npx", "tsc", "-p", "."], cwd=web)
        run(["npm", "run", "build"], cwd=web)
    dist = web / "dist"
    if not (dist / "index.html").is_file():
        sys.exit("error: web/dist is missing: build the UI (drop --skip-web)")
    return dist


def copy_app(dest: Path, web_dist: Path) -> None:
    """server/bams -> dest/bams, the built UI -> dest/bams/web (where __main__._web_dir looks)."""
    shutil.copytree(ROOT / "server" / "bams", dest / "bams",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "web"))
    shutil.copytree(web_dist, dest / "bams" / "web")


# ------------------------------------------------------------------ licences

def _python_licences(dist_infos: list[Path]) -> list[tuple[str, str, str]]:
    out = {}
    for d in dist_infos:
        meta = (d / "METADATA").read_text(encoding="utf-8", errors="replace")
        head = meta.split("\n\n", 1)[0]
        field = lambda k: next((m.group(1).strip() for m in re.finditer(rf"^{k}: (.*)$", head, re.M)), "")
        lic = field("License-Expression") or field("License")
        if not lic or len(lic) > 60:
            classifiers = re.findall(r"^Classifier: License :: (?:OSI Approved :: )?(.*)$", head, re.M)
            lic = ", ".join(classifiers) or lic.splitlines()[0][:60] if (classifiers or lic) else "see package"
        out[field("Name").lower()] = (field("Name"), field("Version"), lic)
    return sorted(out.values(), key=lambda t: t[0].lower())


def _web_licences() -> list[tuple[str, str, str]]:
    lock = json.loads((ROOT / "web" / "package-lock.json").read_text(encoding="utf-8"))
    out = []
    for path, p in lock.get("packages", {}).items():
        if path and not p.get("dev") and not p.get("optional") and "node_modules/" in path:
            out.append((path.rsplit("node_modules/", 1)[1], p.get("version", ""), p.get("license", "see package")))
    return sorted(out)


def notices(python_pkgs: list[tuple[str, str, str]], extra: list[tuple[str, str, str]]) -> str:
    lines = [f"BAMS {version()} - third-party software",
             "",
             "BAMS itself is MIT licensed (see LICENSE). It includes the following open-source software,",
             "each under its own licence. The full licence texts of the Python packages are in their",
             "*.dist-info folders next to them.",
             ""]
    for title, rows in (("Bundled programs", extra), ("Python packages", python_pkgs),
                        ("Web UI libraries (compiled into the UI)", _web_licences())):
        if not rows:
            continue
        lines += [title, "-" * len(title)]
        lines += [f"  {n} {v}: {lic}" for n, v, lic in rows]
        lines.append("")
    lines += ["Not included: FFmpeg. BAMS uses the FFmpeg installed on the computer. The Windows installer",
              "downloads a build published by gyan.dev (GPL-3.0) from https://github.com/GyanD/codexffmpeg;",
              "on Linux it comes from the distribution (apt install ffmpeg).",
              "",
              "BAMS uses the TMDB API but is not endorsed or certified by TMDB."]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ Windows

def find_iscc() -> Path:
    for c in (os.environ.get("ISCC"), shutil.which("iscc"),
              Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
              Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
              Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe"):
        if c and Path(c).is_file():
            return Path(c)
    sys.exit("error: Inno Setup 6 not found (winget install JRSoftware.InnoSetup, or set ISCC=path\\to\\ISCC.exe)")


def build_windows(web_dist: Path) -> Path:
    if sys.platform != "win32":
        sys.exit("error: the Windows installer is built on Windows (Inno Setup)")
    iscc = find_iscc()
    ver = version()
    print(f"== Windows installer {ver}")
    stage = BUILD / "windows" / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)

    # Python, embeddable distribution. Its ._pth file is the whole sys.path: no site-packages, no user site,
    # no PYTHONPATH, so nothing else installed on the computer can leak in.
    py = PINS["python_embed"]
    with zipfile.ZipFile(fetch(py)) as z:
        z.extractall(stage / "python")
    pth = next((stage / "python").glob("python3*._pth"))
    pth.write_text(f"{pth.stem}.zip\n.\n..\\lib\n..\\app\n", encoding="ascii")
    pyver = ".".join(py["version"].split(".")[:2])

    print("== Python packages")
    run(["uv", "pip", "install", "--quiet", "--target", stage / "lib", "--python-version", pyver,
         "--python-platform", "x86_64-pc-windows-msvc", "--only-binary", ":all:", "--require-hashes",
         "-r", REQUIREMENTS])
    copy_app(stage / "app", web_dist)
    run([stage / "python" / "python.exe", "-m", "compileall", "-q", "-j", "0", stage / "lib", stage / "app"])

    (stage / "service").mkdir()
    shutil.copy2(fetch(PINS["winsw"]), stage / "service" / "bams-service.exe")
    shutil.copy2(DEPLOY / "windows" / "bams.ico", stage / "bams.ico")
    shutil.copy2(DEPLOY / "windows" / "bams.cmd", stage / "bams.cmd")
    shutil.copy2(ROOT / "LICENSE", stage / "LICENSE.txt")
    pkgs = _python_licences(sorted((stage / "lib").glob("*.dist-info")))
    (stage / "THIRD-PARTY-NOTICES.txt").write_text(notices(pkgs, [
        ("Python (embeddable)", py["version"], py["licence"]),
        ("WinSW", PINS["winsw"]["version"], PINS["winsw"]["licence"]),
    ]), encoding="utf-8")

    ff = PINS["ffmpeg_windows"]
    DIST.mkdir(exist_ok=True)
    run([iscc, "/Q", f"/DAppVersion={ver}", f"/DStage={stage}", f"/DOutputDir={DIST}",
         f"/DFFmpegUrl={ff['url']}", f"/DFFmpegSha256={ff['sha256']}", f"/DFFmpegFolder={ff['folder']}",
         f"/DFFmpegVersion={ff['version']}", f"/DFFmpegSizeMB={ff['size_mb']}",
         DEPLOY / "windows" / "bams.iss"])
    out = DIST / f"BAMS-Setup-{ver}.exe"
    print(f"   -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


# ------------------------------------------------------------------ .deb

def linux_wheels() -> Path:
    """Wheels for every locked package, for each Python/CPU the .deb supports (pure-Python ones once)."""
    whl = CACHE / "linux-wheels"
    whl.mkdir(parents=True, exist_ok=True)
    lw = PINS["linux_wheels"]
    for arch in lw["platforms"]:
        for pyv in lw["python"]:
            cmd = ["uvx", "--quiet", "--from", "pip", "pip", "download", "--quiet", "--disable-pip-version-check",
                   "--only-binary=:all:", "--require-hashes", "--no-deps", "-r", REQUIREMENTS, "-d", whl,
                   "--implementation", "cp", "--python-version", pyv,
                   "--platform", f"manylinux2014_{arch}", "--platform", f"manylinux_2_17_{arch}",
                   "--platform", f"manylinux_2_28_{arch}"]
            print(f"  wheels: Python {pyv} {arch}", flush=True)
            if subprocess.run([str(c) for c in cmd]).returncode:
                print(f"  warning: no complete wheel set for Python {pyv} {arch}: postinst will download "
                      "the missing ones on such a system", flush=True)
    return whl


class _Tar:
    """A tar with root-owned entries and explicit modes, buildable on Windows."""

    def __init__(self) -> None:
        self.buf = io.BytesIO()
        self.tar = tarfile.open(fileobj=self.buf, mode="w", format=tarfile.GNU_FORMAT)
        self.dirs: set[str] = set()
        self.mtime = int(time.time())
        self.size = 0
        self.md5: list[str] = []

    def _dir(self, path: str) -> None:
        parts = path.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            d = "./" + "/".join(parts[:i]) + "/"
            if d not in self.dirs:
                self.dirs.add(d)
                ti = tarfile.TarInfo(d)
                ti.type, ti.mode, ti.mtime, ti.uname, ti.gname = tarfile.DIRTYPE, 0o755, self.mtime, "root", "root"
                self.tar.addfile(ti)

    def add(self, path: str, data: bytes, mode: int = 0o644) -> None:
        path = path.strip("/")
        if "/" in path:
            self._dir(path.rsplit("/", 1)[0])
        ti = tarfile.TarInfo("./" + path)
        ti.size, ti.mode, ti.mtime, ti.uname, ti.gname = len(data), mode, self.mtime, "root", "root"
        self.tar.addfile(ti, io.BytesIO(data))
        self.size += len(data)
        self.md5.append(f"{hashlib.md5(data).hexdigest()}  {path}")

    def add_tree(self, src: Path, dest: str) -> None:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                self.add(f"{dest}/{p.relative_to(src).as_posix()}", p.read_bytes())

    def gz(self) -> bytes:
        self.tar.close()
        return gzip.compress(self.buf.getvalue(), 9, mtime=self.mtime)


def _ar(members: list[tuple[str, bytes]]) -> bytes:
    out = bytearray(b"!<arch>\n")
    for name, data in members:
        out += f"{name:<16}{int(time.time()):<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n".encode("ascii")
        out += data + (b"\n" if len(data) % 2 else b"")
    return bytes(out)


def build_deb(web_dist: Path) -> Path:
    ver = version()
    print(f"== .deb {ver}")
    lin = DEPLOY / "linux"
    stage = BUILD / "deb"
    shutil.rmtree(stage, ignore_errors=True)
    copy_app(stage / "lib", web_dist)
    wheels = linux_wheels()

    data = _Tar()
    data.add_tree(stage / "lib", "opt/bams/lib")
    for w in sorted(wheels.glob("*.whl")):
        data.add(f"opt/bams/wheels/{w.name}", w.read_bytes())
    data.add("opt/bams/requirements.txt", REQUIREMENTS.read_bytes())
    data.add("usr/bin/bams", (lin / "bams").read_bytes().replace(b"\r\n", b"\n"), 0o755)
    data.add("usr/lib/systemd/system/bams.service", (lin / "bams.service").read_bytes().replace(b"\r\n", b"\n"))
    data.add("usr/share/applications/bams.desktop", (lin / "bams.desktop").read_bytes().replace(b"\r\n", b"\n"))
    data.add("usr/share/icons/hicolor/256x256/apps/bams.png", (lin / "bams.png").read_bytes())
    data.add("usr/share/doc/bams/copyright", (ROOT / "LICENSE").read_bytes())
    pkgs = []
    with_meta = BUILD / "deb-meta"
    shutil.rmtree(with_meta, ignore_errors=True)
    for w in sorted(wheels.glob("*.whl")):  # licences from the wheels' METADATA
        with zipfile.ZipFile(w) as z:
            meta = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
            z.extract(meta, with_meta)
    pkgs = _python_licences(sorted(with_meta.glob("*.dist-info")))
    data.add("usr/share/doc/bams/THIRD-PARTY-NOTICES.txt", notices(pkgs, []).encode("utf-8"))
    md5sums = "\n".join(data.md5) + "\n"
    installed_kb = data.size // 1024
    data_gz = data.gz()

    control = (lin / "debian" / "control").read_text(encoding="utf-8").replace("\r\n", "\n")
    control = control.replace("@VERSION@", ver).replace("@SIZE@", str(installed_kb))
    ctl = _Tar()
    ctl.add("control", control.encode("utf-8"))
    ctl.add("md5sums", md5sums.encode("utf-8"))
    for script in ("postinst", "prerm", "postrm"):
        ctl.add(script, (lin / "debian" / script).read_bytes().replace(b"\r\n", b"\n"), 0o755)

    DIST.mkdir(exist_ok=True)
    out = DIST / f"bams_{ver}_all.deb"
    out.write_bytes(_ar([("debian-binary", b"2.0\n"), ("control.tar.gz", ctl.gz()), ("data.tar.gz", data_gz)]))
    print(f"   -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", choices=["windows", "deb", "all"])
    ap.add_argument("--skip-web", action="store_true")
    ap.add_argument("--version", help="package version to stamp (testing updates); default: config.VERSION")
    a = ap.parse_args()
    global VERSION_OVERRIDE
    VERSION_OVERRIDE = a.version
    web = build_web(a.skip_web)
    if a.target in ("windows", "all"):
        build_windows(web)
    if a.target in ("deb", "all"):
        build_deb(web)
    return 0


if __name__ == "__main__":
    sys.exit(main())
