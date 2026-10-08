# BAMS — Bad Ass Media Server

A self-hosted Netflix/Plex-style server for your own video (then music) files. Point it at folders on a
local or mounted drive. It finds the files, works out what each one is, fetches posters and descriptions,
and streams to a browser. If a browser can't play a file as-is, BAMS converts it on the fly.

**Decided (2026-10-07):** Python backend (FastAPI) + React web UI · MIT license · runs on Windows and
Debian/Ubuntu/Mint · logo and palette from `branding/logo/` (a play-button arrow with a cyan → blue → violet →
magenta → orange gradient on near-black).

---

## 1. What Plex does, and how

Plex Media Server (PMS) has six main parts. BAMS needs a version of each one.

| Plex piece | What it does | How Plex does it | BAMS equivalent |
|---|---|---|---|
| **Libraries / sections** | A library is a folder (or several) plus a type: Movies, TV Shows, Music | The user picks the type, which decides which scanner and agent run | `libraries` table: name, type, list of root paths |
| **Scanner** | Turns file paths into a structure: *this file is S02E05 of Show X* | Filename/folder regexes tuned to their [naming guide](https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/); no internet lookup | Filename parser (`guessit`) + our own rules for folder layout |
| **Agent (metadata)** | Matches the parsed title to a database and pulls the poster, plot, cast, ratings | Plex's own metadata service, built on TMDB / TheTVDB with IMDb IDs and ratings | TMDB API as the main source. Store the IMDb ID for every item. |
| **Media analysis** | Reads container, codecs, resolution, audio tracks, subtitles, duration | Their fork of FFmpeg (ffprobe-like) | `ffprobe`, results stored per file |
| **Library refresh** | Finds new, changed and deleted files | A filesystem watcher, a scheduled scan, and a manual "Scan Library Files" button | The same three: watcher + scheduler (every N hours) + scan button / API |
| **Playback** | Picks Direct Play, Direct Stream (remux) or Transcode based on what the client can play | Client sends a capability profile; Plex Transcoder (FFmpeg fork) outputs HLS/DASH | The same decision logic; FFmpeg → HLS; NVENC on your RTX 5070 Ti |
| **Extras** | Watch state, Continue Watching, On Deck, users, downloads, remote access | Server DB + plex.tv account relay | Watch state and users in v1; downloads in v1 (friend's request); remote access later |

Plex's internal data model is worth copying because it handles "one movie, three files" cleanly:

```
metadata item (Movie | Show > Season > Episode)   ← what it IS (title, plot, poster, IDs)
  └─ media item (one version: 4K HDR, 1080p...)     ← how it's encoded
       └─ part (the actual file; multi-part movies)  ← path, size, mtime
            └─ stream (video / audio / subtitle)      ← codec, language, channels
```

---

## 2. Requirements (yours + your friend's)

| # | Requirement | Phase | Notes |
|---|---|---|---|
| R1 | Movies, TV Shows, **Music** libraries from local or mounted folders | Video: 1, Music: 3 | Mounted network shares (SMB/NFS) are fine. Watchers are unreliable on them, so the scheduled scan is the safety net. |
| R2 | Identify content correctly, with posters, backdrops and descriptions, "using IMDb and other databases like Plex" | 1 | TMDB for data and images. IMDb ID stored and shown. See §5 for why we can't pull data from IMDb directly. |
| R3 | Understand `Show Name - Season 00 - S00E01 - Episode name` style names | 1 | Season 00 = Specials (same as Plex). Unit-test the parser against a corpus of real names. |
| R4 | Auto refresh every X hours, plus on demand | 1 | Configurable per library; "Scan now" button and `POST /api/libraries/{id}/scan` |
| R5 | Download content | 2 | Download the original file (resumable HTTP range) or an "optimized" transcoded copy for phones/laptops |
| R6 | Formats: **H.264, H.265/HEVC, MKV, MP4, AVI, MP3**, **ISO** if possible | 1 (ISO: 3) | See §6 |

---

## 3. Proposed stack (all open source)

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python 3.12 + FastAPI** (MIT) | Same language as your other tooling. Async file serving. OpenAPI docs for free. |
| Database | **SQLite** (public domain), WAL mode, FTS5 search | One file, no server. Fine up to hundreds of thousands of items. |
| Media probe/transcode | **FFmpeg / ffprobe** called as a separate program | NVENC/NVDEC on the 5070 Ti. Running it as an external process keeps its license separate from ours. |
| Filename parsing | **guessit** (LGPL-3.0) | Handles the messy real-world names (`Show.S01E02.1080p.x265-GRP.mkv`) |
| Scheduling | **APScheduler** (MIT) + **watchdog** (Apache-2.0) | Interval scans + filesystem events |
| Frontend | **React + Vite + TypeScript** (MIT), **hls.js** (Apache-2.0) | Netflix-style poster grid; hls.js plays the HLS streams |
| Packaging | Windows installer + `.deb` (Debian/Ubuntu/Mint) + Docker | See §3a |

A .NET or Go backend would also work (Jellyfin is .NET). I'm recommending Python because it's quickest to iterate on.

### 3a. Windows + Debian / Ubuntu / Linux Mint

Both platforms are first-class from day one. CI runs the test suite on `windows-latest` and `ubuntu-latest`.

| Concern | Windows | Debian / Ubuntu / Mint |
|---|---|---|
| Runs as | Windows service (WinSW wrapper) + optional tray icon | `systemd` unit under a `bams` system user |
| Install | Installer (Inno Setup, open source) or a portable zip | `.deb` package (`apt install ./bams_x.y.deb`); Docker as an alternative |
| FFmpeg | Not bundled. The installer offers to fetch a gyan.dev/BtbN build, or the user points to their own | `Depends: ffmpeg` (the distro package) |
| Config / data dirs | `%ProgramData%\BAMS\` | `/etc/bams/`, `/var/lib/bams/` (DB, image cache, transcode temp) |
| Mounted drives | **Use UNC paths (`\\nas\media`)**: a service can't see the drive letters you mapped as a user. The service account needs share credentials | `/mnt/...` or `/media/...` via `fstab` (cifs/nfs). The `bams` user needs read access. Start the service after `remote-fs.target` |
| File watching | `ReadDirectoryChangesW` (watchdog). Unreliable on SMB shares | inotify. Raise `fs.inotify.max_user_watches` for big libraries. No events from NFS/CIFS at all |
| GPU transcode | NVENC (NVIDIA), QSV (Intel), AMF (AMD) | NVENC (proprietary NVIDIA driver), VAAPI (Intel/AMD), QSV |
| Gotchas | Case-insensitive paths, 260-char path limit (use `\\?\` long paths), files locked while being copied in | Case-sensitive (`Movie.MKV` ≠ `movie.mkv`), symlinks, permissions |

The rules that keep it portable: `pathlib` everywhere, never hard-code `/` or `\`. Store paths in the DB
relative to their library root, so a library can move from `D:\Media` to `/mnt/media`. Probe the hardware
encoders at startup with `ffmpeg -encoders` plus a 1-frame test encode, and fall back to CPU (libx264)
if none work.

---

## 4. The indexer (scanner + matcher)

```
 ┌─ triggers ─────────────────────────────┐
 │  • every N hours (per library)          │
 │  • filesystem event (debounced 30 s)    │──►  scan job queue (one job per library at a time)
 │  • "Scan now" button / API              │
 └─────────────────────────────────────────┘
        │
  1. WALK      list every file under each root; skip non-media extensions, samples, `.partial`
  2. DIFF      compare (path, size, mtime) to the DB → new / changed / missing
               moved file? match by OpenSubtitles-style hash (size + first/last 64 KB) → keep watch state
  3. PARSE     folder + filename → {type, title, year, season, episode(s), edition, imdb/tmdb id hints}
  4. PROBE     ffprobe → container, codecs, resolution, HDR, audio/subtitle tracks, duration
  5. MATCH     search TMDB by title+year (TV: show then episode); score candidates;
               an explicit id in the name ({tmdb-603} / {imdb-tt0133093}) always wins
               low confidence → "Unmatched" queue in the UI with a "Fix match" search box
  6. ENRICH    poster, backdrop, plot, genres, cast, rating, runtime, IMDb id; cache images locally
  7. MISSING   files gone for 2 scans in a row → mark unavailable (don't delete; the drive may just be unmounted)
```

**Naming conventions we'll document (Plex-compatible, so existing libraries just work):**

```
Movies/
  The Matrix (1999)/The Matrix (1999).mkv
  The Matrix (1999) {imdb-tt0133093}/The Matrix (1999) - 2160p.mkv     ← optional id pin + version
TV Shows/
  Breaking Bad (2008)/Season 01/Breaking Bad - S01E01 - Pilot.mkv
  Breaking Bad (2008)/Season 00/Breaking Bad - S00E01 - Special.mkv     ← specials
  Some Show/Some Show - Season 00 - S00E01-Episode name.mkv            ← your friend's style (flat folder)
  Some Show/Season 2/Some.Show.S02E03E04.720p.mkv                       ← multi-episode file
Music/   (phase 3)
  Artist/Album (Year)/01 - Track.mp3
```

Unmatched or wrong matches are expected. Plex has the same problem. That's why the "Fix match" UI is in phase 1.

---

## 5. Metadata sources and the IMDb question

Terms checked 2026-10-07. This is not legal advice.

| Source | Use in BAMS | Terms that matter |
|---|---|---|
| **TMDB** | **Primary**: titles, plots, posters, backdrops, cast, seasons/episodes, IMDb IDs | Free for non-commercial use. Show the TMDB logo (smaller than ours) on the About page plus the line *"This product uses the TMDB API but is not endorsed or certified by TMDB."* **Don't cache data or images longer than 6 months**, so BAMS refreshes anything older than ~5 months. ~40 req/s; back off on HTTP 429. **No AI/LLM use of TMDB data** without a commercial deal. Key handling: see "API keys" below. |
| **IMDb** | IMDb ID shown and linked on every item. Optional: ratings from the datasets | **No free API**: the official API is paid, via AWS Data Exchange. **Scraping imdb.com is prohibited** by its conditions of use. The non-commercial TSV datasets are OK for personal use: each BAMS install downloads its own copy (we never mirror them) and shows *"Information courtesy of IMDb (https://www.imdb.com). Used with permission."* No posters or plots in those datasets. |
| **Wikidata** | Fallback ID cross-walk (IMDb ↔ TMDB ↔ TVDB) | CC0, no restrictions |
| **TheTVDB** | Optional, later (TMDB's TV data is good enough to start) | Per-project key. Its licensing docs contradict each other (free under $50k revenue vs. each end user needs a $12/yr subscription), so email them before adding it |
| **OMDb** | Skip | CC BY-NC data scraped from IMDb, posters for paid supporters only. TMDB covers this better |
| **Fanart.tv** | Optional: logos, clear-art, banners | Project key + optional personal key. Terms page couldn't be verified |
| **Music (phase 3)** | MusicBrainz (CC0 core data) + Cover Art Archive + tags embedded in files | |

**So "use IMDb like Plex does"** works out to the same thing Plex actually does: match against TMDB, store and
display the IMDb ID, and optionally show the IMDb rating from the official datasets.

### API keys: how Plex does it without asking you for one

Plex users never see an API key because **Plex runs its own metadata service** (`metadata.provider.plex.tv`).
Your Plex server asks Plex Inc.'s servers. Plex's servers hold the keys and Plex's commercial licensing deals with
TMDB, TheTVDB, Gracenote and others, and they cache the results for millions of users. That deal is part of
what Plex Pass and ads pay for.

The open-source servers do one of three things:

| Approach | Used by | Good | Bad |
|---|---|---|---|
| **A. Ship one project key inside the app** | Jellyfin, Kodi | No setup for the user | One key shared by every install; if TMDB rate-limits or revokes it, everyone breaks. TMDB's terms don't address it either way. |
| **B. Run our own metadata proxy** (like Plex) | Sonarr / Radarr (their "skyhook" proxies) | No setup; we control caching; one place to fix matching | We'd host and pay for a public service, and serving data to thousands of installs likely needs a TMDB agreement |
| **C. User pastes their own free key** | Many small projects | Clearly compliant; each user has their own rate limit | Setup friction (a 2-minute signup) |

**BAMS plan: A with C as an override.** Register a "BAMS" app with TMDB (non-commercial), ship that key as the
default, and add a Settings field where anyone can paste their own key. That's zero setup, like Plex, with an
escape hatch if the shared key ever gets throttled. Revisit B only if BAMS gets big enough to need it.

---

## 6. Formats and playback

Browsers play only a small set of formats natively. Everything else has to be **remuxed** (repackaged
without re-encoding: fast, lossless, cheap) or **transcoded** (re-encoded: heavier work, done on the GPU via NVENC).

| Input | Browser plays natively? | BAMS does |
|---|---|---|
| MP4 + H.264 + AAC | Yes, everywhere | **Direct Play** (byte-range file serving) |
| MKV + H.264 | No (container) | **Remux** to fMP4/HLS (`-c copy`), no quality loss |
| H.265 / HEVC | Edge/Safari and Chrome with hardware support; Firefox no | Direct play if the client says it can; else **transcode** to H.264 (NVENC) |
| AVI (DivX/Xvid/MPEG-4 ASP) | No | **Transcode** video to H.264 |
| AC3 / DTS / TrueHD audio | Mostly no | Transcode **audio only** to AAC/Opus, copy the video |
| Image subtitles (PGS/VobSub) | No | Burn in when selected; text subtitles (SRT/ASS) → WebVTT |
| MP3 | Yes | Direct play (music phase; also works in video libraries as audio) |
| **ISO** (DVD / Blu-ray) | No | Phase 3: FFmpeg's `dvdvideo` demuxer / `libbluray` to read the main title, then remux/transcode. Plex doesn't support ISO at all, so this would be a BAMS feature. Encrypted (CSS/AACS) discs are out of scope. Decrypting them is legally risky. |

Decision flow per play request: client sends what it can play → server picks
**Direct Play > Direct Stream (remux) > audio-only transcode > full transcode**.

---

## 7. Phases

**Phase 0: skeleton (≈ 1 weekend)**
- Repo, FastAPI app, SQLite schema (libraries, metadata items, media, parts, streams), React shell with the BAMS logo
- Config: library roots, scan interval, TMDB key
- CI running the tests on Windows and Ubuntu from the first commit

**Phase 1: watchable movie & TV library (MVP)**
- Scanner (walk/diff/parse/probe), guessit parser + unit-test corpus incl. your friend's `Season 00` style
- TMDB matcher, image cache, "Unmatched / Fix match" screen
- Scheduler + watcher + Scan Now
- Netflix-style browse: rows, poster grid, show → seasons → episodes, detail page with plot/backdrop
- Player: direct play + remux + NVENC transcode via HLS; resume position, mark watched, Continue Watching

**Phase 2: daily driver**
- Downloads (original + optimized), multi-user + login, search (FTS5), subtitles (external `.srt`, embedded)
- Collections, "Recently Added", trailers/extras folders, thumbnails for scrubbing
- Packaging: Windows service + installer, `.deb` + systemd unit (tested on Debian 12/13, Ubuntu 24.04, Mint 22), Docker image

**Phase 3: beyond video**
- Music library (MusicBrainz/Cover Art Archive, mutagen tags, album/artist views, gapless audio)
- ISO support, intro/credits detection (audio fingerprinting across episodes), remote access, TV/mobile clients (DLNA or a Jellyfin-compatible API so existing apps work)

---

## 8. Legal / licensing guardrails

- BAMS plays **media you own**. No torrent/indexer/"find this movie" features. That's what keeps Plex/Jellyfin
  clear of trouble, and it's also why "download content" means *download from your server to your device*.
- **Don't copy Jellyfin code** (GPL-2.0). Porting it would force BAMS to be GPL-2.0. Reading it for ideas is fine.
- **Plex naming conventions are fine to support.** A file-layout scheme is functional, not copyrightable. Write our
  own docs rather than copying Plex's article. Say "supports Plex-style folder naming". Never put "Plex" in the
  name, domain or logo, and never use their chevron. Add: *"Plex is a trademark of Plex, Inc.; BAMS is not
  affiliated with or endorsed by Plex."*
- **FFmpeg is not bundled.** It's installed separately (apt on Linux, a user-chosen build on Windows) and called
  as a subprocess, so its LGPL/GPL terms don't spread to BAMS.
- **Dependency licenses:** FastAPI, React, Vite, APScheduler, PTN = MIT. hls.js, watchdog = Apache-2.0.
  guessit = LGPL-3.0 (importing it is fine; changes to guessit itself stay LGPL). SQLite = public domain.
  If we use pymediainfo, ship the MediaInfo copyright notice.
- **BAMS' own license: MIT** (decided). It's the most widely used permissive license; the only condition is
  keeping the copyright notice. Everything above is compatible with it.
- **Credits page:** TMDB logo + notice, the IMDb notice (if datasets are enabled), FFmpeg, MediaInfo.
- **Logo:** supplied by the project owner (`branding/logo/`). Do a quick trademark search on "BAMS" before going public.
- **Prototype art:** every title in `web/src/mock/` is fictional and its art was generated locally, so the
  prototype contains no copyrighted posters.
