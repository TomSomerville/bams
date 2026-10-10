<p align="center"><img src="branding/logo/bams-wordmark.png" alt="BAMS — Bad Ass Media Server" width="420"></p>

# BAMS — Bad Ass Media Server

A self-hosted, Netflix/Plex-style server for **your own** movies, TV shows and music.
Point it at folders on a local or mounted drive. It finds and identifies your media, pulls posters and
descriptions, and streams to any browser. It runs on **Windows** and **Debian / Ubuntu / Linux Mint**.

> **Status: early.** The server (Python) indexes and identifies TV/movie folders (matched on TMDB) and
> music folders (tags, then MusicBrainz), and streams files. See [server/README.md](server/README.md). The web UI shows your real
> libraries and plays anything: the server converts what the browser can't decode, with subtitles, audio
> tracks, and per-person accounts with resume and Continue Watching. Files it can't identify from their names
> can be identified by hand (paste a TMDB/IMDb link, or pick the show, season and episode).
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
5. **Watch on other devices** (TV, phone, laptop): open `http://<computer-name>:8484` in their browser. Samsung TVs
   can also run the BAMS TV app, driven with the TV remote: see [Samsung TV app](#samsung-tv-app-the-frame) below.

### Updates

Download the newer installer and run it the same way. It installs over the old version and keeps your libraries,
accounts, watch history and settings. No uninstalling, nothing to set up again. What's new in each version:
[CHANGELOG.md](CHANGELOG.md).

More detail (uninstalling, where data lives, forgotten passwords, troubleshooting): [docs/INSTALL.md](docs/INSTALL.md).
Building the installers: [deploy/README.md](deploy/README.md).

## Layout

| Path | What |
|---|---|
| `CLAUDE.md` | Rules and pitfalls for AI coding sessions (read first) |
| `CHANGELOG.md` | What changed in each release |
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
| `tv/` | Samsung TV app (Tizen web app): build, sign and install notes in `tv/README.md` |
| `branding/logo/` | Logo files. `*-transparent.png` are cut-outs for dark backgrounds |
| `tools/brand_art/rework.py` | Redraws the logo set through local ComfyUI (Qwen Image 2.1 edit) and rebuilds the cut-outs |

## License

[MIT](LICENSE). Metadata providers have their own terms (see PLAN.md §5). BAMS uses the TMDB API but is not
endorsed or certified by TMDB. Plex is a trademark of Plex, Inc. BAMS is not affiliated with or endorsed by Plex.

## Samsung TV app (The Frame)

BAMS has an app for Samsung smart TVs, used with the TV remote. It was made on a **2022 The Frame (QN50LS03BAFXZA,
Tizen 6.5)**; other Samsung TVs from about 2020 on should work but haven't been tested. Samsung only lets home-made apps
on a TV in **Developer Mode**, so it's a one-time setup with a PC, about 30 minutes. After that the app stays installed
and opens from the TV's Apps like any other.

You need: BAMS **0.6.1 or newer** running on a computer on the same network (the Windows installer already lets the
network in on port 8484), a Windows PC for the setup (it can be the same one), and a free **Samsung account**.

### 1. Tizen Studio on the PC

1. Download Tizen Studio's IDE installer from <https://download.tizen.org/sdk/Installer/> (folder `tizen-studio_6.1`,
   file `web-ide_Tizen_Studio_6.1_windows-64.exe`, ~660 MB) and run it. Install to `C:	izen-studio`.
2. Start **Package Manager** (Start menu → Tizen Studio) **as administrator**. On the **Extension SDK** tab install
   **TV Extensions** (*Web app. development* and *Tools* are enough; skip the emulator) and **Samsung Certificate
   Extension**.

### 2. Developer Mode on the TV

These steps are for the current Samsung home screen (2024 and later software, also on 2022 TVs that were updated).
Older software has the **Apps** icon in the bar along the bottom instead.

1. If the TV shows art, press the power button once to get to the normal TV screen.
2. Press **Home**. Move **right** into the page, then **up** to the row **For You · Live · Apps**, and open **Apps**.
3. Scroll to the very **bottom** of the Apps page and open **App Settings** (the gear).
4. Press the **123** button on the remote to bring up the number pad, type **1 2 3 4 5** and press **Done**.
   (On the main Apps page the code does nothing; it has to be App Settings.)
5. In the **Developer Mode** window: switch it **On**, enter the PC's address in **Host PC IP** (on the PC:
   `ipconfig`, the IPv4 address, e.g. `192.168.1.40`), then **OK**.
6. **Restart the TV fully**: Settings → General → System Manager → Reboot, or unplug it for 30 seconds. Turning it
   off with the remote isn't enough.
7. Note the TV's address: Settings → General → Network → Network Status → **IP Settings** (e.g. `192.168.1.211`).

### 3. Connect the PC to the TV and make your certificate

1. In a command prompt on the PC: `C:	izen-studio	oolssdb.exe connect 192.168.1.211` (your TV's address). It
   should say *connected*, and `sdb devices` lists your TV's model.
2. Open **Certificate Manager** (Start menu → Tizen Studio). If it doesn't open, edit
   `C:	izen-studio	oolscertificate-managereclipse.ini`, delete the line `--add-modules=ALL-SYSTEM`, and try again.
3. Click **+** → **Samsung** → **TV** → name the profile (e.g. **BAMS**) → **Create a new author certificate**: any
   name, a password you write down → sign in with your Samsung account when asked.
4. **Distributor certificate**: *Create a new distributor certificate*, privilege **Public**. Your connected TV's
   ID (DUID) is filled in by itself; if not, type it (TV: Settings → Support → About This TV → Unique Device ID).
   Click **Finish**. Keep the folder it shows (`C:Users<you>SamsungCertificate<profile>`): updates of the app must
   be signed with the same certificate.

### 4. Install the app

Download **`BAMS-SamsungTV-<version>.wgt`** from the
**[latest release](https://github.com/TomSomerville/bams/releases/latest)**. The file on the release page is signed
for the developer's own TV, so sign it for yours (Samsung's documented way to repackage a `.wgt`):

1. A `.wgt` is a zip file: extract it into a new folder, e.g. `C:ams-tv` (7-Zip, or rename it to `.zip` and
   *Extract all*).
2. In that folder, delete **`author-signature.xml`** and **`signature1.xml`**.
3. Sign it with your profile, then install it on the TV and start it:
   ```bat
   C:	izen-studio	oolsidein	izen.bat package -t wgt -s BAMS -- C:ams-tv
   C:	izen-studio	oolsidein	izen.bat install -n BAMS.wgt -s 192.168.1.211:26101 -- C:ams-tv
   C:	izen-studio	oolsidein	izen.bat run -p BAMSmedia1.BAMS -s 192.168.1.211:26101
   ```
   (`BAMS` = your certificate profile's name, `192.168.1.211` = your TV.)

Or build it from source instead: `cd tv && npm install && npm run build && npm run package -- --install --run`
(`TIZEN_PROFILE=<profile>` if yours isn't called BAMS; see [tv/README.md](tv/README.md)).

### 5. First start

1. Open **BAMS** from the TV's Apps. It looks for your server on the network; pick it, or type its address
   (e.g. `192.168.1.40`).
2. The TV shows a **code** and a **QR code**. Scan the QR code with your phone, or open
   `http://<server>:8484/link` on any computer, sign in **with the account the TV should use**, and enter the code.
   The TV signs in by itself. (Or choose *Sign in with name and password* and type them with the remote.)
3. Remote: arrows move, **OK** selects, **Back** goes back. While watching: ◀ ▶ skip back 10 s / ahead 30 s, OK or
   ⏯ pauses, ▲ shows the controls (Sound, Subtitles, subtitle **Timing**, Next episode).

Linked TVs are listed under **Settings → Your TVs** on the web, where you can sign one out. To update the app later,
repeat step 4 with the new `.wgt` (same certificate, so your sign-in and settings stay).
