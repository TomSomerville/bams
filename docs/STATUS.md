# BAMS: build status, requirements and decisions

The hand-over document for anyone (human or Claude session) picking up the project.
Last updated: **2026-10-08** (release 0.2.0).

> **Several agents work on this repo, often at the same time, and none of them sees everything.** This file
> (especially §8 **Work log**) and [CODEBASE.md](CODEBASE.md) are the shared memory between them. Before planning
> non-trivial work, read the parts that apply. When your work is finished **and signed off by the owner**, add a
> Work log entry and update §4/§5 and CODEBASE.md. See the "Multiple agents" section of [CLAUDE.md](../CLAUDE.md).

---

## 1. What BAMS is

A self-hosted Netflix/Plex-style media server for **your own** files. Point it at folders on local or mounted
drives; it finds the media, identifies it on TMDB (posters, plots, episode titles, IMDb IDs), and streams it to
a browser. Video and music libraries both work. Name: **BAMS — Bad Ass Media Server** (renamed from an earlier
working title on 2026-10-07). Owner: Tom Somerville. A friend contributed requirements.

## 2. Requirements

### From the owner
| # | Requirement | Status |
|---|---|---|
| O1 | Plex/Netflix-like app + service for local video, then audio | Video: working. Music: working (libraries, identification, player) |
| O2 | Media in local/mounted folders; a service crawls and indexes it every N minutes/hours **and on demand** | ✅ per-library interval + Scan now |
| O3 | Identify and categorise media (look it up "like Plex", via naming conventions) | ✅ guessit parser + TMDB matching; music: tags/folders + MusicBrainz |
| O4 | **Everything open-licensed and legal** | ✅ see PLAN.md §5, §8 |
| O5 | **Crawler only uses read-only access** to media folders | ✅ 3 layers, docs/READ-ONLY.md, tests |
| O6 | Runs on **Windows and Debian/Ubuntu/Mint** | ✅ double-click installers: Windows `.exe` (service) and `.deb` (systemd), both update in place (v0.3.0) |
| O12 | Users + login, each with their own watch state; resume, watched, Continue Watching | ✅ |
| O7 | **Each user pastes their own TMDB key**; no shared key; a warning banner links to the setting until it's set | ✅ |
| O8 | Configure libraries (folders) in the UI | ✅ Settings, with a server-side folder picker |
| O9 | UI shows **only real data** (no placeholders) | ✅ |
| O10 | Design docs list every video and audio format | ✅ docs/FORMATS.md |
| O11 | Branding: supplied logo + palette (play-arrow icon, cyan→blue→violet→magenta→orange on near-black) | ✅ used in the UI; GUI mockups still to come from the owner |

### From the friend
| # | Requirement | Status |
|---|---|---|
| F1 | TV Shows / Movies / Music libraries, identified correctly, with posters and descriptions (IMDb and other databases, like Plex) | TV ✅ Movies ✅ Music ✅ (MusicBrainz, Cover Art Archive, Wikipedia bios) |
| F2 | Works from mounted folders; understands `Show Name - Season 00 - 'S00E01-Episode name'` | ✅ (tested, including the quoted form) |
| F3 | Download content | ✅ original-file download (`/api/files/{id}/download`) |
| F4 | Auto refresh every X hours | ✅ |
| F5 | H.264, H.265, MKV, MP4, MP3, AVI; ISO if possible | H.264/HEVC/MKV/MP4 ✅ play; MP3 ✅ (music libraries); AVI/Xvid ✅ (transcoded to H.264); ISO 🔜 phase 3 |

## 3. Decisions log (and why)

| Date | Decision | Why |
|---|---|---|
| 10-07 | Python 3.11+ / FastAPI / SQLite server; React + Vite + TS web | Owner prefers Python; SQLite = no DB server; 3.11 = Debian 12 |
| 10-07 | **MIT** license | Owner: "the most permissive" |
| 10-07 | Plex-style data model (items: show>season>episode / movie; files; file_items) | Handles multi-episode files and multiple versions |
| 10-07 | TMDB primary; store IMDb IDs; never scrape IMDb | IMDb has no free API and forbids scraping; this is what Plex does too |
| 10-08 | **No shared TMDB key**: each install uses its owner's key; banner until set | Owner decision (Plex avoids keys only because it runs its own paid metadata proxy) |
| 10-08 | Media read-only, enforced by code + audit hook + OS (systemd `ProtectSystem=strict`, Windows ACLs) | Owner requirement O5 |
| 10-08 | FFmpeg not bundled; discovered on PATH / winget folder / `BAMS_FFPROBE`/`BAMS_FFMPEG` | Keeps BAMS MIT, avoids GPL/LGPL redistribution duties |
| 10-08 | Libraries are single-type (TV or Movies), like Plex; misplaced files are flagged with a hint | Parsing rules differ per type |
| 10-08 | Browser-incompatible **audio** → on-the-fly remux (video copied, audio → AAC stereo) instead of full transcode | Most releases use AC3/EAC3 audio, which browsers can't decode; this is cheap and lossless for video |
| 10-08 | Server listens on **127.0.0.1** by default | Safest default; `--host 0.0.0.0` opens it to the LAN now that there's a login |
| 10-08 | Owner: "server first; don't sink time into UI features": UI is functional but its design waits for owner mockups | Scope |
| 10-08 | Music reuses the `items` graph (artist > album > track, like Plex), schema v2 | One API/detail/cleanup path for every kind; Plex does the same |
| 10-08 | Music tags read by **ffprobe**, not mutagen (PLAN.md had mutagen) | mutagen is GPL-2.0; ffprobe is already required for video and reads every tag format |
| 10-08 | Albums group by album artist + album title (not folder) | An album split over two folders stays one; same as Plex |
| 10-08 | Browser-unplayable music (ALAC, AIFF, WMA, APE, DSD…) → AAC 256k stereo on the fly | Same approach as the video audio remux; no stored copies |
| 10-08 | Music identification: **MusicBrainz** (no key), Cover Art Archive, Wikidata → Wikipedia/Commons; on by default, Settings toggle | Owner asked for identification. All open services, no keys. Only core CC0 MusicBrainz data is used (its genres/tags are CC BY-NC-SA, so genres stay from file tags). Wikipedia text and Commons photos are shown with their credit |
| 10-08 | Local music data wins: own tags, genres, `cover.jpg`/`artist.jpg`/embedded art beat downloaded data | Owner's files are the source of truth; downloads only fill gaps |
| 10-08 | Artists sort by MusicBrainz sort name ("MacLeod, Kevin") once matched; display name unchanged | What music apps do |
| 10-08 | Schema migrations run as steps from v1 (new DBs too) and back the DB up to `data/backups/` first | Every install and test exercises every migration |
| 10-08 | Video transcoding = FFmpeg → H.264 + AAC, streamed as fragmented MP4 like the remux (seek = restart at `?t=`, frame-accurate) | Reuses the remux plumbing and player logic; HLS was the alternative (see later entries) |
| 10-08 | Encoder picked by test-encoding: NVENC > QSV > AMF > VAAPI > libx264 > Media Foundation; `BAMS_VIDEO_ENCODER` overrides | Whatever the machine has, best first; nothing to configure |
| 10-08 | The **browser** decides whether HEVC/AV1/VP9 play as-is (`MediaSource.isTypeSupported`, then a decode failure), and switches itself to the transcode | Only the client knows what it decodes (HEVC: Edge/Chrome with hardware yes, Firefox mostly no) |
| 10-08 | Transcodes cap at 4K on a GPU encoder, 1080p on the CPU; HDR is tone-mapped to SDR (zscale/Hable) | 4K x264 isn't real-time; H.264 output is SDR |
| 10-08 | The player converts over **HLS** (4 s MPEG-TS segments made on demand, VOD playlist up front, FFmpeg restarted at the requested segment); the fMP4 `/transcode` stays as the fallback for browsers with neither MSE nor native HLS | Native seeking inside a converted stream; segments from different FFmpeg runs line up because timestamps are kept and keyframes forced on boundaries |
| 10-08 | HLS FFmpeg stops 15 segments past the last request and restarts on demand; segments > 75 from the playhead are deleted | Bounded CPU and disk per viewer (a paused film doesn't keep converting) without pausing processes (cross-platform) |
| 10-08 | The conversion limit counts **open sessions** (players), not running FFmpeg processes; automatic = 4 on a GPU encoder, 2 on the CPU | Counting processes let a newcomer take a paused viewer's place, who then got "busy" mid-film (found in testing) |
| 10-08 | Hardware decoding is "hybrid": GPU decodes, frames come back to system memory for the CPU filters; on only with a GPU encoder | All-GPU was 2.5× slower here, can't run the HDR filters, and fails outright on codecs the GPU can't decode; hybrid falls back by itself |
| 10-08 | Dolby Vision is tone-mapped by **libplacebo** (Vulkan; applies the DV metadata), when it runs; HDR10/HLG stay on zscale | Profile 5 has no HDR10 base layer and comes out green/purple otherwise; zscale needs no GPU |
| 10-08 | hls.js (Apache-2.0) is loaded on demand, only when a video is converted | It's ~575 KB, more than the rest of the UI |
| 10-08 | **Accounts + login** (admin / viewer), session cookie (HttpOnly, SameSite=Lax; DB keeps only its SHA-256), scrypt password hashes (stdlib) | Owner asked for users + login; no new dependency. Viewers watch/download; admins manage libraries, settings, accounts |
| 10-08 | The **first admin** can only be created from a browser on the server itself (loopback) or with `bams user add --admin` | So nobody on the LAN can claim a freshly upgraded server |
| 10-08 | Login enforced by a **plain ASGI middleware** on every `/api/` route except `/api/auth/{state,login,setup}`; changes from another site's Origin refused | BaseHTTPMiddleware would sit between FFmpeg streams and the client; Origin check covers other ports on the same host, which SameSite doesn't |
| 10-08 | **Watch state per user, per item** (movie/episode), not per file; watched at **90%**; position < 10 s not kept, < 30 s not offered as resume | Plex's rules; multi-episode files and versions share the item's state |
| 10-08 | Continue Watching = titles stopped part-way + the **next episode** after a show's most recently finished one (specials only after specials) | What Plex calls On Deck, folded into one row |
| 10-08 | The audio-only remux goes over **HLS with the video copied**: segments cut at every source keyframe (ffprobe packet list, cached in `data/cache/keyframes`), fMP4 with `frag_discont` | Native seeking without re-encoding. fMP4 because HEVC/AV1 copy cleanly for MSE; frag_discont because the MP4 muxer otherwise counts each run from 0 |
| 10-08 | Copy-HLS runs number their segments from where a **dry run of the same seek** lands (`remux_start(zero=True)`), not from the keyframe asked for | MKV seeks land on the index point before the target (often a keyframe or two early); measured on real files |
| 10-08 | **"Auto" quality** = several converted sizes in one session (full, then 1080/720/480 below it), hls.js ABR picks; a size not asked for in 10 s stops its FFmpeg; a session counts once against the limit | Adapts to network *and* to how fast the server converts (segment time includes the wait) |
| 10-08 | **All-GPU filters** (NVDEC → bwdif_cuda/scale_cuda → NVENC) by default on NVIDIA for SDR, no burn-in, NVDEC-decodable codecs; a failed run retries on the hybrid path; `BAMS_GPU_FILTERS=0` off | Re-measured on FFmpeg 9.0.2: 1.7 s vs 2.6 s per minute at 720p and far less CPU (the earlier "2.5× slower" no longer holds) |
| 10-08 | **Subtitles**: text → WebVTT through `<track>` (cached in the data dir); image (PGS/VobSub/DVB) → **burned in** to a conversion, read from a second input seeked 30 s earlier | Browsers render WebVTT natively; burn-in from the same input misses the line already on screen when a run starts mid-cue |
| 10-08 | **5.1 AAC** only when the viewer picks Surround (per browser), stereo by default; another audio track than the first plays through the remux | Laptops/phones are stereo; browsers only play a file's first track |
| 10-08 | HTML pages are served with `cache-control: no-cache`; unknown `/assets/` paths 404 instead of falling back to the page | A cached old page after a UI rebuild named scripts that no longer exist (blank page) |
| 10-08 | **Installers**: Inno Setup `.exe` for Windows, a `.deb` built in Python for Debian/Ubuntu/Mint; one file, double-click; a newer one installs over the old one and keeps data, settings and choices | Owner: "ungodly easy", "double click install and done", updates without reinstalling or reconfiguring |
| 10-08 | Windows: BAMS runs as a **Windows service under LocalSystem** (WinSW 2.12), starts at boot | Owner chose this over "run at sign-in as the user". Cost: mapped drive letters and password-protected NAS shares aren't visible; use `\\NAS\share` with guest/computer read access |
| 10-08 | Windows bundles an **embeddable Python 3.13** + locked packages; FFmpeg (gyan.dev 9.0.2 full-shared) is **downloaded by the installer** on the user's machine from its publisher, SHA-256 pinned | Nothing to install by hand; BAMS still never redistributes FFmpeg (GPL) |
| 10-08 | Linux: apt pulls `python3`, `python3-venv`, `ffmpeg`; the `.deb` carries wheels for Python 3.11–3.14 × x86_64/aarch64, installed offline into `/opt/bams/venv` | Works across Debian 12 / Ubuntu 24.04 / Mint 22 / Debian 13 Pythons; distro packages of FastAPI are too old |
| 10-08 | Linux: the service runs as the **installing (desktop) user**, still `ProtectSystem=strict` + `ProtectHome=read-only` | A `bams` system user can't read 750 home folders or udisks USB mounts (Plex's #1 Linux problem); the kernel keeps media read-only either way |
| 10-08 | `/etc/default/bams` is written once by postinst, **not a conffile** | A conffile prompt would stop a double-click upgrade |
| 10-08 | Python dependencies locked with hashes (`deploy/requirements.txt`, `uv pip compile --universal`) | Installers ship exactly what the tests ran against |
| 10-08 | TMDB key guide is a page inside BAMS (`/help/tmdb.html`), not a repo doc | The repo is private; the people who need the guide only have BAMS |
| 10-08 | Saving a TMDB key queues a scan (with rematch) of every TV/movie library | Posters appear right after setup instead of at the next scheduled scan |
| 10-08 | Scans walk and fingerprint files **outside** a transaction, then write in batches of 200 | A walk inside `BEGIN IMMEDIATE` held the write lock for a whole first scan: logins and adding a library hit "database is locked" (HTTP 500, tester on Linux) |
| 10-08 | `title - alternative_title` from guessit is kept as one title ("Star Trek - Lower Decks") | guessit splits on " - "; two shows (and movies like "Spider-Man - Into the Spider-Verse") collapsed into one |
| 10-08 | A file **in a season folder** with no episode number is an unnumbered episode (an extra) of that season; loose in a show folder it stays unrecognised | Tester's Season 00 extras weren't shown. A loose file is often a movie in the TV library; a fake show would be worse than the Unrecognized list |
| 10-08 | Files can be **identified by hand** (`files.manual`, schema v6): stored per file and used instead of the name on every scan; TMDB/IMDb links fill the fields (IMDb ids via TMDB `/find`) | Owner request; survives rescans, file changes and moves; IMDb itself is never fetched |
| 10-08 | Watched % and "started after N s" are **admin settings** (one for everyone; defaults 90% / 30 s); saving progress and Continue Watching use the same threshold | Tester request (10 s / 95%); the old split (save at 10 s, offer at 30 s) wasn't worth two settings |
| 10-08 | Per-user display preferences in `users.prefs` (schema v5), first one `home_hero` | Follows the person across devices, unlike browser storage |
| 10-08 | The admin can **choose the encoder** (`settings.video_encoder`, Settings → Playback); only encoders that pass a test encode are offered; a choice that stops working falls back to automatic; `BAMS_VIDEO_ENCODER` still wins | Tester asked for a CPU/GPU switch; GPU is faster, x264 can look better per bit |
| 10-08 | Scan progress = step + done/total + bytes, "left" counted in **files and size** (titles while matching), time left from the step's own pace | Shows/episodes aren't known until files are parsed; files and bytes are exact. Time left comes from the server's clock (`step_elapsed`) |
| 10-08 | Libraries have an **admin-set order** (`libraries.sort_order`, schema v7), shared by everyone; sidebar drag + Settings ▲▼ | Tester request; one order for the household like Plex's pinned sources; the icon-only sidebar on small screens hides the handles, so Settings has buttons |
| 10-08 | Logo tagline changed from "Your Personal Media Stream" to "Bad Ass Media Server"; logo set redrawn at higher res (`tools/brand_art/rework.py`) | Owner request |

## 4. Built so far

### Server (`server/`, ~6,350 lines + 195 tests)
- **Libraries:** create/rename/delete, add/remove folders, scan interval, order (`PUT /api/libraries/order`). Validation: folder must exist and be
  readable, can't overlap the data dir or another library. Removing a library never touches media.
- **Read-only enforcement:** `readonly.py` (RO opener, walker, audit hook blocking ~25 write operations
  inside media roots). Verified on real data: a full scan changed 0 of 211 file attributes.
- **Scanner:** walk → diff (size + mtime) → parse → link → probe. Detects moved/renamed files by
  fingerprint (OpenSubtitles-style hash) and keeps their identity. Missing files are flagged, not deleted.
  Offline roots are skipped, not marked missing. Files still being copied (locked) are retried next scan.
  Parser upgrades trigger re-parse (`PARSER_VERSION`).
- **Parser:** guessit plus our own rules: show folder vs season folder, SxxEyy/NxNN/ranges/multi-episode,
  quoted names, release-tag stripping (`(1080p … English - HONE)`), id tags `{tmdb-}` `{imdb-}` `{tvdb-}`,
  Specials = Season 0, " - " kept inside titles, unnumbered files in season folders = extras of that season.
  ~35 real-world cases in `tests/test_parse.py`.
- **Identify by hand** (`identify.py`): unrecognised files listed with hints; an admin pastes a TMDB/IMDb link or
  enters title/year/season/episodes; kept in `files.manual` across rescans; undo.
- **Grouping:** `item_keys` aliases so differently-named folders of one show (e.g. "Bobs Burgers S01-S08…" and
  "Bob's Burgers (2011) S14…") become one show, and stay merged on later scans.
- **TMDB matcher:** path-id hints → `/find`, else search + confidence score (≥0.80) → details, images, seasons,
  episodes. Duplicate titles are merged. Low confidence → "unmatched" (never guessed). Refresh before 6 months.
  Fix-match endpoint.
- **Probe:** ffprobe summary (container, codecs, resolution, HDR, audio/subtitle tracks; music tags, embedded cover flag).
- **Music libraries:** artist > album > track from tags (ffprobe) with the folder layout as fallback (disc folders,
  `Artist - Album`, FMA-style names). Album covers from `cover.jpg`/`folder.jpg`… or the embedded picture;
  `artist.jpg` for artists; all copied into `data/images/music/`. Browser-unplayable formats converted to AAC on
  the fly (`/audio?t=`). `/api/items/{id}/tracks` gives a play queue.
- **Music identification:** MusicBrainz (release id from tags, else scored search), Cover Art Archive covers,
  Wikidata → Wikipedia summaries and Commons artist photos with credits. Fix match for albums/artists. On/off
  setting. Respects MusicBrainz's 1 request/second.
- **Playback:** `stream.plan()` picks Direct Play / Direct Stream (file) / Direct Stream (remux) / Transcode.
  `/stream` (Range), `/remux?t=` (FFmpeg: copy video + AAC audio, fragmented MP4), `/seek?t=` (real
  keyframe start via a dry run), `/download`.
- **Video transcoding:** `/transcode?t=` converts video browsers can't decode (Xvid/DivX, MPEG-1/2, VC-1, Theora,
  ProRes, 10-bit/4:2:2/4:4:4 H.264…, and HEVC/AV1/VP9 for browsers without them) to H.264 + AAC on the best working
  encoder (NVENC/QSV/AMF/VAAPI, else x264). Deinterlaces, squares anamorphic pixels, caps the size, tone-maps HDR
  (Dolby Vision through libplacebo). GPU decoding with a GPU encoder. **HLS sessions** (`hls.py`): segments made
  on demand, native seeking, quality (max height) per session, bounded CPU/disk, idle sessions closed. A limit on
  simultaneous conversions (Settings).
- **Accounts:** `auth.py` (scrypt hashes, sessions, throttle), admin/viewer roles, first-admin setup from the server
  itself, login middleware on `/api/`, `bams user add|list|passwd|remove`.
- **Watch state:** `watch.py`: progress (watched at 90% / started after 30 s by default; admin settings), watched flags for movie/episode/season/show, per-user counts on
  every item list, Continue Watching (resume + next episode), next episode for up-next.
- **Subtitles:** `subtitles.py`: embedded + sidecar tracks with language labels, WebVTT conversion (cached, any sidecar
  encoding, `?shift=` for live streams), picture subtitles burned in with a 30 s lead.
- **Audio:** track list with labels, any track via the remux, 5.1 AAC on request (`channels`/`ch`).
- **HLS (more):** copy variants for the remux (keyframe-cut fMP4), Auto quality ladder, all-GPU filters with fallback.
- **Scheduler:** one worker thread (scans run one at a time), timer queues due libraries, progress reporting
  (step, done/total, bytes, seconds into the step) shown in Settings.
- **API:** ~40 endpoints (see CODEBASE.md). **CLI:** `bams serve|library|scan|tmdb-key|status`.
- **Installers** (`deploy/`, v0.3.0; release notes in `CHANGELOG.md`): `build.py` makes `BAMS-Setup-<v>.exe` (Inno Setup: embeddable Python + locked
  packages, FFmpeg downloaded at install with a pinned hash, WinSW service, firewall rule for private networks,
  admin-only data dir, update in place, uninstall that asks before deleting data) and `bams_<v>_all.deb` (offline wheels,
  venv, systemd unit as the desktop user, `/etc/default/bams`, ufw, update in place, remove keeps / purge deletes data).
  User guide `docs/INSTALL.md`; build/release notes `deploy/README.md`. In-app TMDB key guide `/help/tmdb.html`.
- **Deploy (manual):** `deploy/linux/bams.service` (hardened systemd unit; kernel-level read-only media).

### Web (`web/`, React 19 + Vite + TS, ~2,600 lines + 530 lines CSS)
- Pages: Home (hero, Recently Added, per-library rows, Top Rated, genre rows), Library grid (sort, genre
  filter), Title page (show: season tabs + episodes; movie: tech info + Download), Player (real `<video>`,
  remux-aware seeking, converted video over HLS (hls.js, loaded on demand), switches to the conversion when the
  browser can't decode the video, quality menu, keyboard shortcuts), Search, Settings (libraries with folder picker,
  scan status; Unrecognized files (identify by hand: link or fields with suggestions); TMDB key card; Playback card:
  encoder in use + conversion limit; Watched and Continue Watching thresholds). Library pages have an Unrecognized
  tab for admins. Player: speed 0.1x–3x. Music queue: drag (or arrow keys) to reorder. Show-password buttons,
  confirm-new-password, per-person "hide the Home banner". Playback card: encoder choice (CPU/GPU). Library cards:
  live scan progress (N of M, size, time left, bar) and ▲▼ order buttons. Sidebar: admins drag libraries into order.
- Music: library page (Artists/Albums tabs, sort, genres), artist page (bio, photo credit, albums), album page
  (tracklist by disc, format note, Wikipedia/MusicBrainz links), Fix match, a now-playing bar with queue that keeps
  playing across pages (media keys via Media Session) and pauses when a video starts; music in Home and Search;
  Music library type + identification toggle in Settings.
- Sign-in / first-admin screens (`auth.tsx`), account menu, Settings → Accounts (password, users); viewers see only
  their account. Continue Watching row, watched ticks / unwatched counts / progress bars, mark watched on movie,
  show, season and episode, Resume / Start over. Player: resume, progress reports, up-next countdown, sound menu
  (tracks, Surround), subtitles menu (text via `<track>`, picture = burned in), quality Original / Auto / sizes,
  remux over HLS with fallback to the live remux.
- TMDB-missing banner (admins) on every page → `/settings#tmdb`. "Can't reach server" banner.
- Brand: logo files in `branding/logo/` + `web/public/brand/`; palette as CSS tokens in `web/src/styles.css`.

### Docs
README.md, CLAUDE.md, docs/PLAN.md, docs/STATUS.md, docs/CODEBASE.md, docs/FORMATS.md, docs/READ-ONLY.md,
docs/INSTALL.md, deploy/README.md, server/README.md.

## 5. Not built yet / next

Roughly in priority order:
1. **Playback leftovers (minor):** Dolby Vision profile 5 checked on a real file (none available); all-GPU filters
   for QSV/AMF/VAAPI (NVIDIA only so far); VobSub `.sub/.idx` sidecars; Dolby pass-through for TV clients.
2. **Filesystem watcher** (periodic scans cover it for now).
3. **Music follow-ups**: CUE-sheet albums, playlist import (`.m3u`/`.pls`), gapless playback, merge two local
   albums pinned to the same MusicBrainz release, periodic refresh of matched music data, pick up a `cover.jpg`
   added after an album already has art, lossless (FLAC) output option for converted files.
4. **ISO / DVD / Blu-ray folders** (phase 3).
5. **Packaging leftovers**: code-signing the `.exe` (SmartScreen warning), Docker image, an apt repository for
   automatic updates, an in-app "update available" notice. **CI** on Windows + Ubuntu (build both installers too).
6. **UI redesign** from the owner's mockups.

## 6. Dev environment (owner's machine)

| | |
|---|---|
| OS / GPU | Windows 11, RTX 5070 Ti 16 GB |
| Repo | `C:\Users\Beached\bams` → github.com/TomSomerville/bams (**private**) |
| Python | `server\.venv` (3.11 via `uv`) |
| Node | 23 (`web/`) |
| FFmpeg | winget `Gyan.FFmpeg` (found automatically, even without PATH) |
| Server data dir | `C:\Users\Beached\bams\data` (gitignored): DB, image cache, logs |
| Ports | 8484 = the owner's server · 8485 = scratch test instances (`.claude/launch.json` → `bams-test`, data dir in the session scratchpad: edit the path) · 5173 = Vite dev |
| Test media | `C:\Users\Beached\Shows` (TV: Bob's Burgers, Family Guy, Simpsons, Burn Notice, South Park…) · `C:\Users\Beached\Movies` (2 movies) · `C:\Users\Beached\MyMusic` (8 CC0/CC BY albums, 4 artists, `CREDITS.txt`) |
| Libraries on the owner's server | 1 = "TV Shows" (`…\Shows`), 2 = "Movies" (`…\Movies`); the owner adds "Music" (`…\MyMusic`) when testing |
| Art tools | local ComfyUI (Qwen Image); `tools/brand_art/rework.py` redraws the logo set from the supplied art |

## 7. Repo state notes
- Initial commit `3c79290` (plan, branding, UI prototype). Everything after it, server included, was
  **uncommitted** at the time of writing; check `git status`. Commit/push only when the owner asks.
- The logo files in `branding/logo/` and `web/public/brand/` were re-rendered by `tools/brand_art/rework.py`
  (a separate session) after the initial commit.

## 8. Work log

One entry per **finished, owner-approved** piece of work, **newest first**. It's the record of what other
agents did. Keep entries short; link to files instead of repeating them. Template:

```
### YYYY-MM-DD: <short title>
- **What / why:** one or two lines, including the owner's request it answers.
- **Files:** main files added/changed.
- **Verified:** tests run, manual checks (what was actually observed).
- **Left open:** follow-ups, known gaps, or "none".
```

### 2026-10-08: CPU/GPU choice, scan progress with what's left, library order (release 0.3.0)
- **What / why:** the three tester requests left open in 0.2.0, which the owner asked for next. **CPU/GPU:**
  Settings → Playback → *Convert with* lists every H.264 encoder that passes a test encode (`stream.available_encoders`)
  plus Automatic; saved as `settings.video_encoder`, applied at startup and on save (`stream.set_preferred`), used by new
  conversions; `BAMS_VIDEO_ENCODER` still wins. **Scan progress:** each step reports `progress(step, done, total,
  bytes_done, bytes_total)`; the Scheduler keeps it with the step's start; `/api/status` adds `step_elapsed`; the library
  card shows "N of M files (K left) · X of Y GB · about T min left" and a filling bar. Probe results are now saved in
  batches of 200 as they arrive (they were saved only at the end). **Library order:** `libraries.sort_order` (schema v7;
  existing libraries numbered alphabetically), new ones last, `PUT /api/libraries/order`, `library.listed()` everywhere
  (API, CLI). Sidebar: admins drag by a hover handle (or arrow keys); Settings: ▲▼ on each card; a `bams:libraries`
  window event keeps the sidebar and Settings in step (the sidebar also never refreshed after add/rename/remove before).
  The drag code moved from the music queue into a shared `useReorder` hook. Released as **0.3.0**.
- **Files:** server `stream.py` (`_works`, `_tested`, `available_encoders`, `set_preferred`, `preferred`, `encoder_forced`),
  `app.py` (`/api/settings/encoders`, `/api/settings/encoder`, `/api/libraries/order`, startup reads the encoder),
  `scanner.py` (`Progress`, per-step reports, batched probe saves), `jobs.py` (structured `_progress`, `step_elapsed`),
  `matcher.py` + `music_match.py` (done/total), `library.py` (`ORDER`, `listed`, `reorder`, new = last), `db.py` (v7),
  `__main__.py`, `config.py` (0.3.0); tests `test_stream.py`, `test_scanner.py`, `test_api.py`, `test_auth.py`. Web: new
  `components/useReorder.ts`; `Sidebar.tsx`, `NowPlaying.tsx` (on the hook), `TranscodeSettings.tsx` (`EncoderChoice`),
  `Settings.tsx` (`ScanProgress`, ▲▼, event), `api.ts` (`ScanState`, `LIBRARIES_CHANGED`), `Icon.tsx`, `styles.css`.
  Docs: CHANGELOG, server/README, CODEBASE, CLAUDE.md.
- **Verified:** 195 tests (new: encoder choice incl. fallback, env override and the API with a restart; progress
  reports with totals/bytes and the Scheduler's record; library order incl. ignored/omitted ids and viewer 403; v7
  migration orders existing libraries by name). Test server on a DB copy: encoder list on the owner's PC = NVENC, x264,
  Media Foundation; switching to x264 changed status and the automatic limit (4 → 2), and a real 480p HLS segment carried
  x264's signature; back to automatic = NVENC. A 586-file music re-probe showed live "N of 586 files (left) · GB of
  5.4 GB" with a filling bar. Sidebar drag (synthetic pointer events; screenshots were unavailable) and Settings ▲▼
  reordered sidebar, Settings and server alike. `.deb` 0.2.0 → 0.3.0 in Docker (Debian 12, Ubuntu 24.04): DB v6 → v7
  with backup, existing libraries listed alphabetically, reorder API, encoder list (x264 only, no GPU there), UI served.
- **Left open:** scans still run one at a time; the music queue's drag (now on the shared hook) wasn't re-tried by hand
  after the refactor; extras folders (`Featurettes`…) are still skipped. The Windows 0.3.0 upgrade of the owner's service
  is run by the owner.

### 2026-10-08: Tester round 1 fixes + identify unrecognised files by hand (release 0.2.0)
- **What / why:** the friend's tester sent notes on 0.1.0; the owner picked a first batch and added a request.
  **Bugs:** HTTP 500 on login / adding a library during a first scan (the walk held SQLite's write lock: now it
  walks and fingerprints outside a transaction); titles cut at " - " ("Star Trek - Lower Decks" → "Star Trek"; parser
  v4 rejoins guessit's `alternative_title`); Season 00 extras without episode numbers not shown (parser v5:
  unnumbered episode in its season folder's season). **Requests:** show-password buttons, confirm new password,
  per-person toggle for the Home banner (`users.prefs`, schema v5), watched % / started-after seconds as admin
  settings, playback speed 0.1x–3x, drag-to-reorder music queue. **Owner request:** identify unrecognised files by
  hand: Settings → Unrecognized files + a library Unrecognized tab; TMDB/IMDb link fills the fields, or type them
  with suggestions from the library; stored in `files.manual` (schema v6) and used on every scan; undo. Released as
  **0.2.0** (`CHANGELOG.md`).
- **Files:** server `scanner.py` (no lock during walk/hash; manual identifications), `parse.py` (`_title`,
  `unnumbered`, `_loose_title`, v5), `items.py` (unnumbered episodes by title, merges), new `identify.py`, `app.py`
  (identify/lookup/names/unrecognized routes, `/api/me/prefs`, `/api/settings/watch`, hint from the file name),
  `watch.py` (`thresholds`), `auth.py` (prefs), `db.py` (v5, v6), `config.py` (0.2.0); tests `test_identify.py` (new),
  `test_scanner.py`, `test_parse.py`, `test_watch.py`, `test_auth.py`. Web: new `PasswordInput.tsx`, `WatchSettings.tsx`,
  `Combo.tsx`, `Identify.tsx`; `auth.tsx` (prefs), `AccountSettings.tsx`, `Home.tsx`, `Player.tsx` (speed),
  `music.tsx` + `NowPlaying.tsx` (queue move), `Library.tsx` (tab), `Settings.tsx`, `Detail.tsx`/`Cards.tsx`/`format.ts`
  (unnumbered `S00`), `api.ts`, `styles.css`. Docs: `CHANGELOG.md` (new), README, INSTALL.md, server/README.md,
  CODEBASE.md, CLAUDE.md.
- **Verified:** 190 tests (new: the scan no longer blocks another writer during walk or hashing (fails on the old
  code); dashed titles; unnumbered extras + rescan + merge; thresholds + prefs API; identify flow, rescan keeps it, undo,
  validation, viewer 403; TMDB/IMDb link parsing against a fake TMDB). Browser (test server, copy of the dev DB + a
  generated demo show): sign-in during a 505-file scan, show password, confirm mismatch, banner off, thresholds saved,
  speed menu/keys/slider (kept across a quality switch), queue drag + keys (current track kept playing), Specials
  extras listed, identify by suggestions (extra) and by a real IMDb episode link (matched on TMDB with poster),
  movie link refused in a TV library, undo. `.deb` 0.1.0 → 0.2.0 in Docker (Debian 12, Ubuntu 24.04): DB v4 → v6 with
  backup, account kept, UI served.
- **Left open:** tester requests not started: CPU/GPU encoder choice in Settings, scan progress with "remaining",
  reorder libraries in the sidebar; scans still run one at a time (a second library waits as "Scan queued"). Extras
  folders (`Featurettes`, `Behind The Scenes`…) are still skipped by the walk. The Windows 0.2.0 upgrade of the
  owner's installed service is run by the owner.

### 2026-10-08: Installers (Windows + Debian/Ubuntu/Mint), updates in place, TMDB key guide
- **What / why:** owner asked for deployment and packaging that is "ungodly easy": double-click install, all
  dependencies fetched first, updates installed right over the top without redoing config, DBs or libraries, and a
  TMDB key write-up with screenshots. **Windows:** Inno Setup installer with embeddable Python 3.13.16 + hash-locked
  packages; downloads FFmpeg 9.0.2 (gyan.dev full-shared, SHA-256 pinned) into `{app}\ffmpeg`; WinSW service `BAMS`
  (LocalSystem, automatic, restart on failure; owner chose a boot service over run-at-sign-in); task "home network" →
  `0.0.0.0` + firewall rule (private/domain); data `C:\ProgramData\BAMS` (SYSTEM + Administrators only); waits for the
  server and opens it; updates skip the questions, stop the service, replace only program folders, keep FFmpeg; uninstall
  asks before deleting data. **Linux:** `.deb` assembled in Python (builds on Windows), wheels for 3.11–3.14 ×
  x86_64/aarch64, postinst builds `/opt/bams/venv`, runs the service as the installing user via a drop-in from
  `/etc/default/bams`, opens ufw if active; remove keeps data, purge deletes it. **Server:** finds the installed UI
  (`bams/web`) and the installer's FFmpeg (`probe.app_ffmpeg_dir`); folder picker offers `C:\Users` when running as
  SYSTEM; saving a TMDB key queues video libraries for matching. **UI:** TMDB guide page with screenshots
  (`/help/tmdb.html`), linked from the key card and the Start menu; UNC hint in the folder picker; the server-unreachable
  banner no longer says to run Python. Version is single-sourced from `config.VERSION`.
- **Files:** new `deploy/build.py`, `pins.json`, `requirements.txt`, `README.md`, `windows/` (`bams.iss`, `bams.cmd`,
  `bams.ico`, `wizard-small.png`), `linux/` (`debian/control|postinst|prerm|postrm`, `bams`, `bams.desktop`, `bams.png`;
  `bams.service` reads `/etc/default/bams`), `docs/INSTALL.md`, `web/public/help/` (`tmdb.html`, `img/`); changed
  `server/bams/__main__.py` (`_web_dir`), `probe.py` (`app_ffmpeg_dir`), `stream.py`, `fsbrowse.py`, `app.py` (key →
  scans), `pyproject.toml` (dynamic version), `tests/test_api.py`; web `TmdbSettings.tsx`, `FolderPicker.tsx`,
  `ConfigBanner.tsx`; README, READ-ONLY.md, CODEBASE.md, CLAUDE.md, `.gitignore` (`/build/`, `/dist/`), `.gitattributes`.
- **Verified:** 173 tests on Python 3.11 and 3.13 with the locked packages. `.deb` in Docker: Debian 12 and Ubuntu
  24.04 install → setup → UI + guide → reinstall → login kept → remove keeps data → purge clean; Debian 12 under real
  systemd: running as the desktop user, `/home` read-only to it, 0.1.0 → 0.1.1 upgrade restarted it with the account
  kept. Windows on the owner's PC: install (FFmpeg fetched, service LocalSystem/auto, 0.0.0.0, firewall rule, data dir
  closed), status shows the installer's FFmpeg + NVENC, same version over the top, 0.1.0 → 0.1.1 while running (no second
  FFmpeg download, choices reused, login kept), uninstall (service, rule, program files gone; data kept). Found and fixed:
  `icacls /inheritance:r /T` emptied the ACLs of existing files, so updates couldn't start (owner saw "Starting BAMS"
  hang). Guide checked at desktop and phone widths. Owner signed off; released as GitHub release v0.1.0.
- **Left open:** TMDB's signed-in API pages have no screenshots (text steps only); the `.exe` isn't code-signed; no
  automatic update check; the test `C:\ProgramData\BAMS` on the owner's PC may still exist.

### 2026-10-08: Users + login, watch state, subtitles, audio tracks, playback follow-ups
- **What / why:** owner asked to "oneshot" items 1-5 of §5. **Accounts:** schema v4 (`users`, `sessions`,
  `watch_state`); scrypt hashes; HttpOnly session cookie (DB keeps its SHA-256, sliding 30 days); `LoginRequired`
  ASGI middleware on `/api/`; admin-only routes (`ADMIN` dependency); first admin only from loopback or the CLI;
  throttle (10 wrong passwords / 10 min / address); Origin check on changes; `bams user ...`. **Watch state:**
  progress every 10 s / on pause / on leave, watched at 90%, mark watched (movie/episode/season/show), counts on item
  lists, `/api/continue`, `next_id` + up-next countdown; merges carry watch state over. **Subtitles:** embedded +
  sidecar tracks, WebVTT cached in `data/cache/subtitles`, live streams shifted, picture tracks burned in (second
  input 30 s earlier). **Audio:** track menu (browser language by default), other tracks via the remux, Surround = 5.1
  AAC. **Playback:** remux over HLS with the video copied (keyframe-cut fMP4, dry-run numbering, frag_discont),
  Auto quality (ABR ladder), all-GPU NVIDIA filters with hybrid fallback. Also: HTML served `no-cache` (stale page
  after rebuilds).
- **Files:** new `server/bams/auth.py`, `watch.py`, `subtitles.py`, `tests/test_auth.py`, `test_watch.py`,
  `test_subtitles.py`, `web/src/auth.tsx`, `components/AccountSettings.tsx`; changed `db.py` (v4), `app.py` (middleware,
  auth/users/watch/subtitle routes, HLS variants, SpaFiles), `hls.py` (rewritten around variants, `Keyframes`),
  `stream.py` (`audio_channels`, burn-in, `gpu_filters`, `keyframes`, `hls_copy_cmd`, `remux_start(zero)`),
  `items.py`, `config.py` (`Paths.cache`), `__main__.py`; web `api.ts`, `main.tsx`, `Player.tsx` (rewritten),
  `Detail.tsx`, `Home.tsx`, `Cards.tsx`, `Settings.tsx`, `TopBar.tsx`, `ConfigBanner.tsx`, `styles.css`; tests
  `conftest.py` (`signed_in`) + every API test signs in; docs FORMATS.md, READMEs.
- **Verified:** 172 tests (30 new: auth, roles, throttle, cross-site refusal, v4 migration; watch rules, per-user,
  continue/next, merges; subtitle labels, sidecar encodings, shift, a hand-made PGS track burned in, also when the run
  starts mid-line (fails without the lead); copy-HLS through the API with segments from two runs 12 s apart; ABR
  switch, GPU fallback, keyframe cache). Real files: copy-HLS segments of an H.264 and an HEVC MKV identical whichever
  FFmpeg run made them; all-GPU 720p 1.7 s vs 2.6 s/min. Browser on a :8485 copy of the owner's DB: first-admin setup,
  AC3 episode over copy-HLS (seek to 10:00 playing in 3 s), embedded SRT subtitles, progress saved → Continue
  Watching → resume at 11:18; Family Guy 11 tracks, English picked, Surround switched mid-play; HEVC Auto quality
  (1080p → 720p capped to the window, all-GPU FFmpeg seen); up-next to S01E02 with S01E01 marked watched; episode /
  season / show toggles; viewer account: own state only, 403 on admin routes; PGS burn-in switched on mid-line. Owner
  signed off.
- **Left open:** DV profile 5 on a real file; GPU filters for QSV/AMF/VAAPI; `.sub/.idx` sidecars; a remembered
  quality (incl. Auto) applies to every video in that browser; row arrows overflow the page by 2 px (pre-existing).

### 2026-10-08: Transcoding follow-ups (HLS, GPU decoding, quality menu, limit, Dolby Vision)
- **What / why:** owner asked to complete the "left for later" list of the video transcoding work.
  **HLS:** `POST /api/files/{id}/hls {height?}` opens a session; the player loads its VOD playlist (every 4 s
  segment listed up front) with hls.js (or Safari natively) and seeks by itself. `hls.Transcodes` makes segments on
  demand: a request for a missing segment that isn't coming soon restarts FFmpeg there (`stream.hls_cmd`: `-copyts
  -start_at_zero`, keyframes forced every 4 s from the start, scene cuts off, `-output_ts_offset 10`, so runs line
  up). An older request superseded by a seek gives up instead of fighting over FFmpeg. FFmpeg stops 15 segments
  ahead and restarts when needed; segments > 75 from the playhead are deleted; idle sessions close after 90 s; the
  player closes its session on leave. **GPU decoding** (`stream.hwaccel_args`: cuda for NVENC, vaapi, d3d11va;
  `BAMS_HWACCEL`). **Quality menu** in the player (sizes below the source; forces a conversion; remembered per
  browser). **Limit** on simultaneous conversions (`settings.max_transcodes`, 0 = automatic 4 GPU / 2 CPU; counts
  open sessions + fMP4 streams; Settings → Playback card; "server busy" message). **Dolby Vision**: probe records
  `dv_profile`; `stream.tonemap_mode` uses libplacebo (tested once per FFmpeg, needs Vulkan) for DV; the player
  converts DV profile 5 for browsers without `dvh1`.
- **Files:** `server/bams/hls.py` (new), `stream.py` (shared `_transcode_parts`, `hls_cmd`, `hwaccel_args`,
  `has_libplacebo`, `tonemap_mode`, `max_height`), `probe.py` (`dv_profile`), `config.py` (`Paths.transcode`),
  `app.py` (HLS routes, `/transcode?h=` + limit, `playback.hls_url`, `PUT /api/settings/transcoding`, status
  `transcodes` + `hw_decode`); `web/src/pages/Player.tsx` (HLS, quality menu), `components/TranscodeSettings.tsx`
  (new), `Settings.tsx`, `api.ts`, `styles.css`, `package.json` (hls.js); `tests/test_hls.py` (new), `test_stream.py`.
- **Verified:** 142 tests (13 new: session logic against a fake FFmpeg — on-demand restarts, superseded requests,
  failures, stop-ahead + pruning, idle close, limit; a real Xvid HLS conversion through the API at 180p where
  segment 3 from one FFmpeg run starts exactly 12 s after segment 0 from another; hw decode/tone-map/HLS command
  building; `dv_profile`; settings API). Manual: segment timestamps identical across two runs of a real HEVC
  episode; GPU decode −12% CPU at equal speed, Xvid/MPEG-2 fall back silently; libplacebo runs here. Browser on a
  :8485 test instance: Xvid over HLS; the Simpsons episode switched to 720p mid-play from the same spot; a seek to
  10:50 resumed in 0.6 s; paused, FFmpeg stopped 60 s ahead and old segments were pruned; playback crossed the
  restart boundary with one contiguous buffer; limit 1 → second tab got "server busy"; leaving freed the place; HEVC
  marked unsupported → full 1080p conversion; no leftover FFmpeg or segment folders, no errors in the log. Owner
  signed off.
- **Left open:** the audio-only remux still restarts on seek; no adaptive bitrate; Dolby Vision profile 5 untested
  on a real file (none available).

### 2026-10-08: Video transcoding
- **What / why:** owner asked to implement video transcoding (STATUS §5 item 1). Video no browser decodes is
  converted on the fly to H.264 + AAC (fragmented MP4 over `/api/files/{id}/transcode?t=`), on the best H.264
  encoder FFmpeg can actually run (detected once by test encodes; NVENC on the owner's RTX 5070 Ti). The filter
  chain deinterlaces flagged frames, makes anamorphic DVD video square-pixel, caps the size (GPU 4K, CPU 1080p) and
  tone-maps HDR10/HLG to SDR. `plan()` now sends Xvid/MPEG-2/VC-1/Hi10P etc. to `mode:"transcode"`; HEVC/AV1/VP9
  stay pass-through and the player switches to `playback.transcode_url` when `MediaSource.isTypeSupported` says no
  or the video fails to decode. VP8 counts as browser-OK (WebM). FFmpeg's stderr now goes to the server log.
- **Files:** `server/bams/stream.py` (`video_copyable`, encoder detection, `transcode_filters`, `transcode_cmd`,
  stderr logging), `app.py` (`/transcode`, `playback.transcode_url`, `video_encoder` in `/api/status`, detection
  warmed at startup); `web/src/pages/Player.tsx` (modes, `canDecode`, fallback, "X → H.264" note), `Detail.tsx`,
  `Settings.tsx`, `api.ts`, `format.ts`; `tests/test_stream.py`.
- **Verified:** 129 tests (11 new: plan table incl. Xvid/MPEG-2/VC-1/VP8/Hi10P, no-FFmpeg fallback, encoder
  order/platform/override/caching, filter chains, command building, a real Xvid → H.264 transcode through the API
  that starts exactly at `t` and leaves the file untouched). Manual: Xvid, interlaced anamorphic MPEG-2 (→ 852×480)
  and HDR10 HEVC (→ BT.709) through NVENC, x264 and Media Foundation; a real 1080p HEVC Main 10 episode transcodes at
  18× real time (NVENC) / 16× (x264). Browser on a :8485 test instance: Xvid and MPEG-2 play and seek, HEVC with
  support switched off goes straight to the transcode, Settings shows "NVIDIA NVENC (GPU)", no leftover FFmpeg.
  Owner signed off.
- **Left open:** HLS, hardware decoding, quality picker, concurrency limit, Dolby Vision profile 5 (§5 item 1).
  The decode-failure fallback was exercised only through the capability path. Seeking in `.mpg` logs a harmless AC3
  decoder warning.

### 2026-10-08: Music identification (MusicBrainz, Cover Art Archive, Wikipedia)
- **What / why:** owner asked for music identification after testing the music library. After each music scan,
  new albums are matched on MusicBrainz (release id from tags, else a scored search; below `ACCEPT` = unmatched,
  never guessed), then get the official title, original year, a Wikipedia description, a Cover Art Archive cover
  when there's no local art, and MusicBrainz titles for tracks named only by their file. Artists get their id via
  their albums (or an unambiguous name search), MusicBrainz sort name, a Wikipedia bio and a Commons photo with
  author/licence credit. Fix match for albums and artists. Settings toggle (on by default). Schema v3 (`mbid`,
  `extra`). Matched titles/years survive rescans.
- **Files:** `server/bams/musicbrainz.py` (clients, shared 1 req/s throttle), `music_match.py`, `jobs.py`
  (identify step, `music_lookup` setting), `app.py` (`/api/musicbrainz/search`, `/api/items/{id}/music-match`,
  `/api/settings/music-lookup`, `ids.musicbrainz` + `extra` in item detail), `db.py` (v3), `music.py` (keep
  matched year/titles); `web/src/components/MusicFixMatch.tsx`, `MusicSettings.tsx`, `pages/Music.tsx` (About,
  credits, Fix match), `api.ts`; `tests/test_music_match.py`.
- **Verified:** 118 tests (6 new, fake services via `httpx.MockTransport`: matching, tag ids, unmatched/ambiguous,
  rescans keep data, local art wins, service down, API toggle + fix match). Real run on `MyMusic`: 4/8 albums
  matched (the other 4 aren't on MusicBrainz and stayed unmatched), 4/4 artists, 2 Wikipedia bios + Commons photos.
  Browser on a test instance: artist/album pages, credits, Fix match (search, empty state, pick). Owner tested
  and signed off.
- **Left open:** merging local albums pinned to the same release; refresh of matched data; see §5 item 7.

### 2026-10-08: Music libraries
- **What / why:** owner asked to build the music library (phase 3, brought forward). Music libraries index
  audio files into artist > album > track (tags read by ffprobe, folder layout as fallback), with covers and artist
  images from the files/folders, a play queue API, on-the-fly AAC conversion for formats browsers can't play, and a
  music UI with a persistent now-playing bar. Schema v2 (rebuilt `items` table with the music kinds and columns);
  migrations now back up the DB to `data/backups/` first.
- **Files:** `server/bams/music.py` (new), `db.py` (v2 + migration steps), `config.py` (`AUDIO_EXTS`, art names),
  `probe.py` (tags, cover flag, audio codec names), `scanner.py` (music: probe before linking), `items.py`
  (cleanup of albums/artists), `stream.py` (`plan_audio`, `audio_cmd`), `jobs.py` (artwork step), `library.py` +
  `__main__.py` (music type), `app.py` (`kind=` on library items, `/api/items/{id}/tracks`, `/api/files/{id}/audio`,
  music fields in item JSON); `web/src/music.tsx`, `components/NowPlaying.tsx`, `pages/Music.tsx`, plus
  `Cards`, `Library`, `Detail`, `Home`, `Search`, `Settings`, `Sidebar`, `TopBar`, `App`, `main`, `api.ts`,
  `format.ts`, `styles.css`; `tests/test_music.py`.
- **Verified:** 112 tests at the time (44 new: parsing, tag normalisation, scanning, moves, parser bumps, real
  FLAC/ALAC/MP3 album with embedded cover, folder/artist art, playback plans, v1→v2 migration). A copy of the
  owner's DB migrated with all 248 items / 228 files / links intact. `MyMusic` scanned to 4 artists, 8 albums,
  81 tracks, 6 embedded covers; the media folder was byte-for-byte unchanged. Browser on a test instance: direct
  MP3/FLAC 24/96/Opus playback, ALAC/AIFF/WMA conversion with seeking, queue auto-advance, music keeps playing
  across pages and pauses for video, phone layout, no leftover FFmpeg processes. Owner tested: "basic function".
- **Left open:** see §5 item 7.

### 2026-10-08: Agent coordination docs
- **What / why:** owner asked that agents can pick up work without full context: CLAUDE.md (rules, pitfalls,
  multi-agent protocol), this STATUS file with its Work log, CODEBASE.md (knowledge tree).
- **Files:** `CLAUDE.md`, `docs/STATUS.md`, `docs/CODEBASE.md`, README layout table.
- **Verified:** file list and API routes checked against the code; line and test counts measured.
- **Left open:** none.

### 2026-10-08: Format reference + test music
- **What / why:** owner asked for every video/audio format in the design docs, and for open-licensed test
  albums.
- **Files:** `docs/FORMATS.md`; `config.VIDEO_EXTS` extended to match it (asf, wtv, dvr-ms, f4v, 3g2, rm, rmvb,
  mpe). Music: `C:\Users\Beached\MyMusic` (outside the repo), 4 artists / 8 albums / 81 MP3s, CC0 + CC BY,
  with `CREDITS.txt`.
- **Verified:** every MP3 MD5 matched archive.org's published checksum; 68 tests pass.
- **Left open:** music libraries themselves (phase 3).

### 2026-10-08: Silent audio fix (on-the-fly audio remux)
- **What / why:** owner reported Bob's Burgers playing without sound. Cause: AC3/EAC3 audio, which browsers
  can't decode. The server now copies the video and converts the audio to AAC via FFmpeg.
- **Files:** `server/bams/stream.py` (plan, remux, `remux_start`), `/remux` + `/seek` in `app.py`,
  `web/src/pages/Player.tsx` (remux-aware seeking), `tests/test_stream.py`.
- **Verified:** in the browser, the original file decoded 0 audio bytes and the remux decodes audio; seeking ±10 s
  and to 10:00 works; no FFmpeg processes are left behind; a real FFmpeg remux test passes.
- **Left open:** video transcoding (Xvid/MPEG-2, HEVC for devices that can't decode it), audio track picker, 5.1.

### 2026-10-08: Movies library + unrecognised-file hints
- **What / why:** owner's movies folder had been added to the TV library and the movies didn't show. Moved it to
  a new Movies library (id 2). Unidentified files are now listed on the library card with a hint; adding or
  removing a folder triggers a scan.
- **Files:** `app.py` (`unrecognized_hint`, PATCH → scan), `library.describe` (unrecognized count),
  `web/src/pages/Settings.tsx`.
- **Verified:** both movies matched on TMDB; the hint was shown for a movie placed in a TV library; API test.
- **Left open:** none.

### 2026-10-08: UI wired to real data (placeholders removed)
- **What / why:** owner wanted only real data shown. Removed the mock catalog, mock art and art generator;
  Home, Library, Detail, Player, Search and Sidebar now use the API; Fix match modal; real `<video>` playback.
- **Files:** `web/src/pages/*`, `components/*`, `api.ts`, `useApi.ts`, `format.ts`; `app.py` (`/api/items`,
  `ancestors`, `child_count`); ffprobe discovery in the winget folder.
- **Verified:** browser checks against a copy of the owner's DB: 6 shows with TMDB art, seasons and episodes,
  H.264 and HEVC playback with seeking, search, sidebar; no placeholder text left.
- **Left open:** watch state (Continue Watching was removed until it exists).

### 2026-10-08: Settings wired to the server (libraries + TMDB key)
- **What / why:** owner couldn't configure library folders (the Settings page was mock). Added a server-side
  folder picker, library add/edit/remove/scan in the UI, and the TMDB key saved on the server.
- **Files:** `server/bams/fsbrowse.py`, `app.py` (`/api/fs/browse`, key test, SPA fallback),
  `db.connect(check_same_thread=False)` fix, `web/src/pages/Settings.tsx`, `FolderPicker.tsx`,
  `TmdbSettings.tsx`, `settings.tsx`, `api.ts`.
- **Verified:** full UI flow on a test instance (add, browse, rename, interval, overlap error, remove); API tests.
- **Left open:** none.

### 2026-10-08: Server iteration 1
- **What / why:** owner: "server first". Read-only crawler, parser, TMDB matcher, scheduler, REST API, CLI,
  systemd unit.
- **Files:** everything in `server/`, `deploy/linux/bams.service`, `docs/READ-ONLY.md`.
- **Verified:** 54 tests at the time. A real scan of `C:\Users\Beached\Shows` (≈200 files) changed 0 of 211 file
  attributes. All shows matched once the key was set.
- **Left open:** see §5.

### 2026-10-08: Logo set redrawn (separate session)
- **What / why:** tagline changed to "Bad Ass Media Server"; higher-res redraw of the supplied logo.
- **Files:** `tools/brand_art/rework.py`, `branding/logo/*`, `web/public/brand/*`, `web/public/favicon.png`.
- **Verified:** by that session (details not recorded here).
- **Left open:** owner's GUI mockups.

### 2026-10-08: TMDB key UI + config banner (prototype)
- **What / why:** owner: each user pastes their own key, no shared key; warning banner links to the setting.
- **Files:** `web/src/components/ConfigBanner.tsx`, `TmdbSettings.tsx` (later moved to server storage).
- **Verified:** a fake key was rejected by TMDB (401) and not saved; the owner's real key was accepted.
- **Left open:** none.

### 2026-10-07: Project start
- **What / why:** plan (how Plex works, licensing), logo concepts, then the owner's own logo; repo renamed to
  `bams`, git + private GitHub repo; Netflix-style UI prototype.
- **Files:** `docs/PLAN.md`, `branding/`, `web/`, `README.md`, `LICENSE`. Commit `3c79290`.
- **Verified:** UI built and checked at desktop and phone widths.
- **Left open:** none.
