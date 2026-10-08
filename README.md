<p align="center"><img src="branding/logo/bams-wordmark.png" alt="BAMS — Bad Ass Media Server" width="420"></p>

# BAMS — Bad Ass Media Server

A self-hosted, Netflix/Plex-style server for **your own** movies, TV shows and music.
Point it at folders on a local or mounted drive. It finds and identifies your media, pulls posters and
descriptions, and streams to any browser. It runs on **Windows** and **Debian / Ubuntu / Linux Mint**.

> **Status: early.** The server (Python) indexes and identifies TV/movie folders (matched on TMDB) and
> music folders (tags, then MusicBrainz), and streams files. See [server/README.md](server/README.md). The web UI shows your real
> libraries and plays anything: the server converts what the browser can't decode, with subtitles, audio
> tracks, and per-person accounts with resume and Continue Watching.
> The full plan is in [docs/PLAN.md](docs/PLAN.md).
>
> Your media folders are **read-only** to BAMS, enforced in code and by the OS: [docs/READ-ONLY.md](docs/READ-ONLY.md).

## Install

Download the installer for your computer from the
**[latest release](https://github.com/TomSomerville/bams/releases/latest)**:

| Your computer | Download | Then |
|---|---|---|
| Windows 10 / 11 (64-bit) | `BAMS-Setup-<version>.exe` | Double-click it. If Windows says *"Windows protected your PC"*, click **More info → Run anyway** (the installer isn't code-signed). Click **Yes**, then **Install**. It downloads FFmpeg, installs BAMS as a service that starts with the computer, and opens it in your browser. |
| Debian 12+, Ubuntu 24.04+, Linux Mint 22+ | `bams_<version>_all.deb` | Double-click it and click **Install** (or run `sudo apt install ./bams_<version>_all.deb`). Python and FFmpeg come along automatically. Then open **BAMS** from the applications menu. |

### Set it up (5 minutes, once)

1. **Open BAMS on the computer you installed it on:** http://localhost:8484. Create your **admin account** (this
   only works on that computer, so nobody else on the network can grab it).
2. **Add your free TMDB key**, where posters and descriptions come from. Click the orange bar at the top; BAMS has a
   step-by-step guide with pictures (also at http://localhost:8484/help/tmdb.html).
3. **Add your folders:** Settings → **Add library** → TV Shows, Movies or Music → pick the folder. BAMS scans it
   right away. Network shares on Windows: type the path as `\\NAS\Videos`.
4. **Add the people in your house:** Settings → Accounts. Each person gets their own watch history and Continue
   Watching.
5. **Watch on other devices** (TV, phone, laptop): open `http://<computer-name>:8484` in their browser.

### Updates

Download the newer installer and run it the same way. It installs over the old version and keeps your libraries,
accounts, watch history and settings. No uninstalling, nothing to set up again.

More detail (uninstalling, where data lives, forgotten passwords, troubleshooting): [docs/INSTALL.md](docs/INSTALL.md).
Building the installers: [deploy/README.md](deploy/README.md).

## Run it (development)

Start the server (see [server/README.md](server/README.md)). It serves the UI at http://127.0.0.1:8484; the first
visit, on the server itself, creates the admin account.
After changing the UI, rebuild it (Node 20+):

```bash
cd web && npm install && npm run build
```

For UI development with hot reload, run `npm run dev` in `web/` and open http://localhost:5173.
It proxies `/api` to the server.

## Layout

| Path | What |
|---|---|
| `CLAUDE.md` | Rules and pitfalls for AI coding sessions (read first) |
| `docs/STATUS.md` | What's built, requirements, decisions log, dev environment |
| `docs/CODEBASE.md` | Codebase map: every file, data flow, DB schema, API, "where to change X" |
| `docs/FORMATS.md` | Every video/audio/subtitle/music format and how BAMS handles it |
| `docs/PLAN.md` | Architecture, how Plex works, metadata/licensing decisions, phases |
| `docs/READ-ONLY.md` | How media folders are kept read-only (code guard + OS setup) |
| `server/` | Python server: scanner, TMDB and MusicBrainz matchers, API, CLI, tests |
| `docs/INSTALL.md` | Installing, updating and uninstalling (Windows and Linux) |
| `deploy/` | Installer builds: `build.py`, pinned downloads, locked Python packages, Inno Setup script, `.deb` scripts |
| `deploy/linux/bams.service` | Hardened systemd unit (media read-only at the kernel level) |
| `web/public/help/tmdb.html` | Step-by-step TMDB key guide with screenshots, served by BAMS at `/help/tmdb.html` |
| `web/` | React + Vite + TypeScript UI, served by the server from `web/dist` |
| `branding/logo/` | Logo files. `*-transparent.png` are cut-outs for dark backgrounds |
| `tools/brand_art/rework.py` | Redraws the logo set through local ComfyUI (Qwen Image 2.1 edit) and rebuilds the cut-outs |

## License

[MIT](LICENSE). Metadata providers have their own terms (see PLAN.md §5). BAMS uses the TMDB API but is not
endorsed or certified by TMDB. Plex is a trademark of Plex, Inc. BAMS is not affiliated with or endorsed by Plex.
