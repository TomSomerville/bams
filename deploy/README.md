# Building the BAMS installers

```bash
server\.venv\Scripts\python deploy\build.py all      # Windows: both installers into dist\
python3 deploy/build.py deb                          # Linux/macOS: the .deb only
```

Output: `dist/BAMS-Setup-<version>.exe` (~18 MB) and `dist/bams_<version>_all.deb` (~20 MB). User-facing
instructions are in [docs/INSTALL.md](../docs/INSTALL.md).

Needs **uv**, **Node 20+** (the UI is rebuilt unless `--skip-web`) and, for the `.exe`, **Inno Setup 6** on Windows
(`winget install JRSoftware.InnoSetup`; `ISCC=` points at another copy). The `.deb` is assembled in Python, so it
builds on Windows too. `--version X` stamps a different package version (for testing updates).

## Releasing an update

1. Bump `VERSION` in `server/bams/config.py` (the installers, the `.deb` and `bams --help` all read it). Windows
   doesn't strictly need a higher version, but apt only upgrades to a higher one.
2. If dependencies changed: `uv pip compile server/pyproject.toml --universal --generate-hashes --python-version 3.11 -o deploy/requirements.txt`, then run the tests against it.
3. `deploy\build.py all`, test, then commit, tag and publish (the README's download link points at the latest
   release):
   ```bash
   git tag -a v0.2.0 -m "BAMS 0.2.0" && git push origin main v0.2.0
   cd dist && sha256sum * > SHA256SUMS.txt && cd ..
   gh release create v0.2.0 dist/BAMS-Setup-0.2.0.exe dist/bams_0.2.0_all.deb dist/SHA256SUMS.txt --title "BAMS 0.2.0" --notes "..."
   ```
   People run the new installer over the old one.

## What's inside

| | Windows `.exe` (Inno Setup) | `.deb` |
|---|---|---|
| Python | embeddable CPython (pinned in `pins.json`), in `{app}\python`; its `._pth` file is the whole `sys.path` | the distribution's `python3` (3.11+), a venv in `/opt/bams/venv` built by `postinst` |
| Python packages | `requirements.txt` (locked, hash-checked), installed at build time into `{app}\lib` | wheels for Python 3.11–3.14 × x86_64/aarch64 in `/opt/bams/wheels`, installed offline by `postinst` (PyPI only as a fallback) |
| BAMS + UI | `{app}\app\bams`, UI in `bams\web` (found by `__main__._web_dir`) | `/opt/bams/lib/bams` (+ `web`), on the venv's path via `bams.pth` |
| FFmpeg | **not bundled**: the installer downloads the pinned gyan.dev build (`pins.json`, SHA-256 checked) into `{app}\ffmpeg`, found by `probe.app_ffmpeg_dir` | apt dependency `ffmpeg` |
| Runs as | Windows service `BAMS` (WinSW, LocalSystem, automatic start, restarts on failure) | systemd `bams.service` as the desktop user (`/etc/default/bams` → drop-in), `ProtectSystem=strict` |
| Data | `C:\ProgramData\BAMS` (ACL: SYSTEM + Administrators only) | `/var/lib/bams` |
| Network | task "home network" → `--host 0.0.0.0` + firewall rule (private/domain profiles) | `BAMS_HOST=0.0.0.0`; `ufw allow 8484/tcp` when ufw is active |
| CLI | `{app}\bams.cmd` | `/usr/bin/bams` (runs as the service account) |

Pinned downloads (`pins.json`) are checked against their SHA-256 by `build.py`, and FFmpeg by the installer
itself. To move to a newer one, change `url`, `version` and `sha256` together.

## How updates keep everything

- **Windows:** one `AppId`, so a newer installer is an update. It skips the questions (`UsePreviousTasks`), stops
  the service in `PrepareToInstall`, wipes only `python\`, `lib\` and `app\` (`[InstallDelete]`, so no stale
  modules), installs the new files, rewrites the WinSW XML (read at every start, so the service registration stays),
  keeps FFmpeg unless `pins.json` names a newer version, and starts the service. `C:\ProgramData\BAMS` is never in
  the installer's file list.
- **Linux:** `prerm upgrade` stops the service, dpkg swaps `/opt/bams/lib`, `postinst configure` rebuilds the venv
  and restarts it. `/etc/default/bams` is created once by `postinst` and deliberately **not** a conffile, so an
  update can never stop to ask about it. `remove` keeps `/var/lib/bams`; only `purge` deletes it.
- **Both:** database migrations run when the new version starts (`db.MIGRATIONS`, with a backup first).

## Tested (2026-10-08)

- `.deb` in Docker: Debian 12 (Python 3.11) and Ubuntu 24.04 (3.12) install → first-admin setup → UI and guide
  served → reinstall over the top → login still works → remove keeps data → purge removes it. Debian 12 with real
  systemd: service enabled and running as the desktop user, `/home` read-only to it, 0.1.0 → 0.1.1 upgrade restarted
  it with the account intact.
- Windows 11 (the owner's PC): silent install → FFmpeg downloaded and checked, service `BAMS` running as LocalSystem
  (automatic), listening on 0.0.0.0, firewall rule added, data dir closed to non-admins, first-admin setup, status
  shows the installer's FFmpeg and NVENC. Same version again over the top, then 0.1.0 → 0.1.1 while running: service
  stopped and restarted, no second FFmpeg download, earlier choices reused, login kept. Uninstall: service, firewall
  rule and program files gone, data kept.
  Bug found and fixed on the way: `icacls /inheritance:r … /T` left the existing database and logs with an empty
  ACL, so an update couldn't start (now: folder only + `/reset` on its contents, which also repairs that).
