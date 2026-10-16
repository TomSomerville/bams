# BAMS: build status, requirements and decisions

The hand-over document for anyone (human or Claude session) picking up the project.
Last updated: **2026-10-15** (release 0.18.1).

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
| O5 | **Crawler only uses read-only access** to media folders | ✅ 3 layers, docs/READ-ONLY.md, tests. One owner-made exception: "Download locally" saves a downloaded subtitle next to its video as a new `.srt` (create-only; 0.15.0, automatic in 0.14.0) |
| O6 | Runs on **Windows and Debian/Ubuntu/Mint** | ✅ double-click installers: Windows `.exe` (service) and `.deb` (systemd), both update in place (v0.4.0) |
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
| F3 | Download content | ✅ **Android app only** (0.17.0, owner's request): movies, episodes, seasons, shows, songs, albums, artists and playlists, original files, played offline. An admin turns it on per account. The web and TV apps still have no downloads (0.9.2) |
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
| 10-08 | **All-GPU filters on Quick Sync, VAAPI and AMF too**: QSV `vpp_qsv`, VAAPI `deinterlace_vaapi`/`scale_vaapi`, AMF (Windows) D3D11 decode → `vpp_amf`; given the output size as numbers and a deinterlacer only when the probe says interlaced (AMF: interlaced → hybrid; QSV: unknown scan → hybrid); a failed all-GPU run is remembered per encoder + codec/profile/bit depth until restart | Their filters can't read pixel aspect/interlacing per frame like CUDA's. **Not tested on real hardware** (owner's PC has only NVIDIA; VAAPI couldn't be reached through WSL/Docker): the fallback keeps a wrong guess cheap |
| 10-08 | Probe records `sar` + `field_order`; files probed earlier get them read on the fly (`probe.video_geometry`) when a QSV/AMF/VAAPI conversion needs them | No re-probe of whole libraries for one playback feature |
| 10-08 | **VobSub `.idx/.sub` sidecars** are picture tracks, one per `id:` stream in the .idx (`x{n}-{k}`), burned in from the .idx as a second input; `burn` takes a track id (old stream numbers still work) | FFmpeg reads the pair natively; the .idx has no start time, so it lines up with the film without offsets |
| 10-08 | **Dolby pass-through**: when the browser says it decodes AC3/EAC3 (`MediaSource.isTypeSupported`), the remux (HLS copy + live) copies the audio; Sound menu switch (remembered per browser); a decode error falls back to AAC by itself. Remux only: conversions stay AAC | TV browsers, Safari, Edge, Chromecast hand Dolby to an AV receiver. DTS/TrueHD don't go into MP4 cleanly. A device can claim support and fail, hence the automatic fallback |
| 10-08 | Live (non-HLS) burn-in from mid-film keeps the file's clock (`-copyts -start_at_zero`, `-output_ts_offset -t`) like HLS | The old `-itsoffset` on the subtitle input lost a line already on screen (found while adding VobSub) |
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
| 10-08 | Home's rows are **per user** (`home_rows` pref: ordered `{id, show}`; empty = default). Rows not in the saved list (a new library) are shown at their default place; genres were one entry (the 4 most common); since 0.6.2 one row per genre (`genre:<name>`), an old `genres` entry expands in place | Owner request. Per user like the banner toggle, unlike the shared library order: Home is personal. No schema change (prefs is JSON) |
| 10-08 | The admin can **choose the encoder** (`settings.video_encoder`, Settings → Playback); only encoders that pass a test encode are offered; a choice that stops working falls back to automatic; `BAMS_VIDEO_ENCODER` still wins | Tester asked for a CPU/GPU switch; GPU is faster, x264 can look better per bit |
| 10-08 | Scan progress = step + done/total + bytes, "left" counted in **files and size** (titles while matching), time left from the step's own pace | Shows/episodes aren't known until files are parsed; files and bytes are exact. Time left comes from the server's clock (`step_elapsed`) |
| 10-08 | Libraries have an **admin-set order** (`libraries.sort_order`, schema v7), shared by everyone; sidebar drag + Settings ▲▼ | Tester request; one order for the household like Plex's pinned sources; the icon-only sidebar on small screens hides the handles, so Settings has buttons |
| 10-08 | **No filesystem watcher** (dropped from the roadmap) | Owner: scheduled scans plus Scan now are enough; watchers are unreliable on SMB/NFS mounts anyway |
| 10-08 | **No Docker image, apt repository or CI** (dropped from the roadmap) | Owner decision: the `.exe` and `.deb` installers are the distribution; packaging work left is code-signing and an "update available" notice |
| 10-08 | **CUE sheets** split one file into tracks by `file_items.cue_start/cue_end` (schema v8); the track rows are kept across re-reads, matched by track number; a pregap stays with the track before it | One file holding several items already fits the model (multi-episode files); the player plays a stretch of the file instead of a cut copy, so nothing is written or duplicated |
| 10-08 | **Playlists are imported, not authored**: the `.m3u/.m3u8/.pls` file stays the source (re-read when it changes, gone when it's deleted); entries kept as written and re-matched after every scan (relative path → absolute path under a root → unique path tail) | Owner asked for import. Re-matching each scan follows moves and picks up music added later; the tail match covers playlists made on another computer |
| 10-08 | **Gapless = two `<audio>` elements** with the next track preloaded and started at the current one's end (timer from the element's clock, `ended` as fallback); consecutive CUE tracks of one file play as one stream | Works in every browser with the existing file/convert endpoints. Sample-perfect gapless would need Media Source Extensions (every track repackaged by FFmpeg): left open |
| 10-08 | Albums on the **same MusicBrainz release are merged only when both are pinned** (tag id, Fix match, or a search ≥ 0.95); the merged-away name stays an `item_keys` alias by **artist + album name** (not ids) | A fuzzy search match merging two different albums would compound the error. Names, because the merged-away artist is deleted and would come back with a new id |
| 10-08 | `items.poster_src` records **where music art came from**; a new or changed `cover.jpg`/`artist.jpg` replaces embedded, Cover Art Archive or Commons art; downloaded art is re-downloaded on refresh, the owner's never | "Local data wins" now also holds for art added later. Images are seen in the scan's own walk, so no extra folder listings |
| 10-08 | Identified music is **refreshed after ~4 months, 50 items per scan** | Picks up MusicBrainz corrections and new Wikipedia text while keeping to 1 request/second |
| 10-08 | Converted music: admin choice **AAC 256k (default) or FLAC** (`settings.music_output`); FLAC keeps 24-bit and the channels, caps the rate at 96/88.2 kHz | Every current browser plays FLAC; it's lossless and has no encoder delay (better gapless), but ~4x the data, so not the default |
| 10-08 | **Settings → Security** (owner request): sign-in log, wait after each wrong password (1 s, doubling), lockout after N in a row (default 5, admin setting), lock/unlock accounts, IP allow/block lists with two modes, a traffic log of every request (10 GB cap, folder and size adjustable) | Owner request. Details in the rows below and the work log |
| 10-08 | Sign-in state and log live in a **separate `security.db`** in the data dir, not in `bams.db` | Written on every sign-in and read by nothing else; kept out of the main DB's schema/migrations (another session was mid-way through schema v8) |
| 10-08 | **Unknown names get the same waits/lockout** as real accounts (kept as `n:<name>` rows) | Different answers would tell an attacker which names exist |
| 10-08 | An account **locked by wrong passwords stays signed in** where it already was; a lock **by an admin** signs it out everywhere | Otherwise anyone could sign a family member out just by typing wrong passwords |
| 10-08 | IP lists: **block list always wins**; the server's own **loopback is always let in**; saving a change that would block the admin's own address is refused; `bams security allow-all` resets the mode | So the owner can't lock themselves out of the machine BAMS runs on |
| 10-08 | The "netflow" log is **every HTTP request BAMS receives** (JSON lines), not packet-level NetFlow | BAMS can only see what reaches it; port scans etc. need router/OS flow logging |
| 10-08 | Traffic log written by a background thread in files of a tenth of the cap, oldest deleted to stay under the cap; moving the folder leaves old files where they were | Requests never wait on the disk; trimming whole files is cheap; moving up to 10 GB inside a request isn't |
| 10-08 | Logo tagline changed from "Your Personal Media Stream" to "Bad Ass Media Server"; logo set redrawn at higher res (`tools/brand_art/rework.py`) | Owner request |
| 10-08 | **Show folder = the folder right above the season folder** (not the top folder under the root); without a season folder, the deepest folder that reads as a season pack | Tester's "Star.Trek.Megapack/Star.Trek.DS9/S03/…" put five series into one fake show; "Pack/The Simpsons S28/…" was named after the pack |
| 10-08 | **Star Trek short forms** (DS9, TNG, TOS, VOY, ENT) are spelled out in the parser | The one franchise where scene packs routinely abbreviate; TMDB only knows the full names (TOS is just "Star Trek") |
| 10-08 | TMDB: a **near-exact title (≥ 0.95) is accepted even with a wrong year**; TMDB's first result is accepted when its name is the tail of ours ("Star Wars Andor" → "Andor") | Years in scene names are often an episode's air year or a season's; South Park and Parks and Recreation sat at 0.75 for that. Only rank 0 gets the tail rule |
| 10-08 | A scan **retries `unmatched` titles** when it re-parsed files or when `matcher.MATCHER_VERSION` changed since that library was last matched (else only `pending`) | Parser/matcher fixes otherwise never reach titles that failed once; found on the owner's server after 0.5.0 |
| 10-09 | **Samsung TV app** = a Tizen web app (`tv/`, React + Vite, one classic script loaded from file://) using **AVPlay**, released as its own `.wgt` next to the server installers, installed in Developer Mode | Owner request. Tizen web apps are HTML/JS (same skills as `web/`); AVPlay decodes far more than a browser (MKV, HEVC/HDR, AC3/EAC3). No store submission for a home app |
| 10-09 | TV signs in by **link code** (`/link` page + QR) or name+password, getting an ordinary **session token** sent as `Authorization: Bearer`; media through **ticket paths** `/api/t/<ticket>/…` (HMAC over the session digest, 24 h, key per process, GET-only, files/hls/images only); CORS `*` without credentials | The packaged app runs from its own origin (no cookies); AVPlay and `<img>` can't send headers; a ticket in a URL can't sign anyone in and dies with the session |
| 10-09 | On the TV **everything the TV decodes is played as copy-HLS in MPEG-TS** (`hls?remux&ts&passthrough`), not from the file | The owner's 2022 Frame (Tizen 6.5) **can't seek** in a progressively streamed file (AVPlay and `<video>` both: one `bytes=0-` request, then `PLAYER_ERROR_SEEK_FAILED`), so resume/skip froze; and it **rejects fMP4 HLS** (`NOT_SUPPORTED_FILE`). Copy-HLS in TS seeks fine and converts nothing (AC3/EAC3 copied) |
| 10-09 | Continue Watching **ignores episodes opened but not really watched** (position 0, not watched) when deciding what a show offers | Opening the next episode for a few seconds (or a play that failed) hid a show the viewer was half-way through |
| 10-10 | **The web app and the TV app are clients of any number of BAMS servers.** Each browser and each TV keeps its own list (localStorage) and talks to each server **directly** (bearer token from `/api/auth/token`, media through that server's tickets); servers store nothing about other servers | Owner: "just clients that front the servers' contents… 6 servers on one TV, 3 on another, 4 on the desktop". A first version kept connections per account on the home server and proxied everything through it; dropped for this. Cost: every device must reach every server itself (an https page can't use a plain-http server) |
| 10-10 | Each server's **history stays with the account on that server**; libraries of other servers can be hidden (web + TV) and renamed (web) per device | What you watch where is that server's business; per-device lists mean per-device names |
| 10-10 | **Home and Search combine every server, identically on web and TV** (`web/src/everywhere.ts`, imported by the TV): Continue Watching by `last_watched_at` (new field; older servers interleaved), Recently Added by `added_at`, Top Rated and genres interleaved, genres merged by name; a library's own row stays that library's (first server's libraries only, from its `home_rows`) | Owner: "Home and search should show a combined ALL servers content… TV and Web app should have a uniform view. Nothing different." One shared module so they can't drift |
| 10-10 | A **ticket path accepts POST/DELETE with the session's own cookie/bearer** (a ticket alone still only reads media) | The web keeps another server's media links as ticket URLs; `hls_url` (POST) and closing a session (DELETE) are such links |
| 10-10 | **Server name** = admin setting `server_name`, default "<oldest admin>'s BAM Server" (owner's wording), returned by `/api/hello` | Owner request; the hostname said nothing to people choosing a server |
| 10-10 | **"Must change password at next sign-in"** per account (`users.must_change_password`): such a session opens only `PUT /api/auth/password` and logout (403 `must_change_password` elsewhere); setting it signs them out; on by default in the add/reset forms; `/api/auth/token` refuses (apps have no new-password screen) | Owner request: "force password change upon next authentication to allow a user to set their own password" |
| 10-10 | **Two-step sign-in = TOTP** (RFC 6238, SHA-1/6 digits/30 s) in stdlib, secret in `users.totp_secret` (plain, like the rest of `bams.db`), ±1 step, each step once (`totp_last`); no recovery codes: an admin or `bams user 2fa-off` turns it off | Owner asked for Google Authenticator. No new server dependency. A wrong code counts toward the same waits/lockout; the right password alone neither counts nor resets them (else codes could be tried forever) |
| 10-10 | **Music on the TV** with one HTML `<audio>` (not AVPlay), no gapless | AVPlay is the video player and owns the screen; `<audio>` plays MP3/AAC/FLAC and falls back to the server's conversion on an error |
| 10-10 | **Auto fill** (`parse.guess`, setting `autofill`, on by default): files the naming rules can't place are **placed automatically** by a best guess (show from the folder, season from "Season/Volume/Level" folders, number from "Part 3"/"Lesson 12"/"01 - Name", no number = extra, a film in its show's folder = Specials), marked `parse.guessed` and listed for review (Keep / Change / Don't place). Replaces the 10-08 "loose in a show folder stays unrecognised" rule while it's on. Still not guessed: a loose top-level file with no number, a movie in its own folder in a TV library | Owner asked for a best-guess parser and chose automatic placing over a pre-filled form. A wrong guess is one click to fix; turning the setting off takes every guess out at once |
| 10-10 | **No downloads** (0.9.2): no `/api/files/{id}/download`, no `download_url`, no Download buttons; `/stream` sends no file name; right-click on the player's video is blocked | Owner: "remove the ability to download the files from the server completely. across the entire application". Playing still sends the file's bytes (direct play, copy-HLS), so a technical viewer could save a stream; stopping that would mean converting everything |
| 10-11 | **OpenSubtitles: each server's admin pastes their own API key** in Settings, like TMDB (checked with a search before it's kept, never sent back); an OpenSubtitles account is optional (more downloads a day) | Owner's decision (test session 3 asked for "an area to add that API"). OpenSubtitles' terms ask for **one key per application** and say they may ban apps whose users bring their own; a single BAMS key was built first and replaced at the owner's request, so a key may get blocked |
| 10-11 | **Downloaded subtitles belong to the file, for everyone**: kept in the data dir (`subtitles/opensubtitles/<id>.srt`, table `subtitle_downloads`, schema v10), listed as tracks `d<n>`; removable by whoever downloaded them or an admin; a subtitle the server already has isn't downloaded again | Media folders are read-only; downloads are limited per day (5 without an account, 20 free), so one pick should serve the whole household |
| 10-11 | **Remove from Continue Watching** takes out the **title** (the movie, or the episode's whole show) for that account until there's **later activity** on it (`continue_hidden.hidden_at` vs the deciding row's `updated_at`; opened < "started" threshold doesn't count). A long press (web: or right-click; TV: holding OK) opens a menu with Remove / Cancel rather than removing at once | Owner: "Long press… to remove it from continue watching. If the show is later watched, it will get added back in." Hiding one episode would just show the next; the menu step guards against a stray hold while scrolling a row on a phone |
| 10-11 | OpenSubtitles is searched by the title's **TMDB id** (show id + season/episode for episodes), else IMDb, plus the file's **moviehash** (BAMS's `quick_hash` is their hash); by name only when that finds nothing | Their advice; the hash puts subtitles made for the exact file first ("made for this file") |
| 10-11 | **Sleep mode** = this episode **and 2 more**, then stop (a movie: stop at its end); toggled in the player, per viewing, not saved | Tester request ("finish the current episode, play 2 more, and then stop"). Carried to the next episode in the navigation state |
| 10-12 | **0.15.0 replaces the automatic copy with a button**: downloads go to `cache/subtitles/opensubtitles/`; "Download locally" (dialog → *Already on this video*) saves one next to the video as **`<video stem>.srt`** (the video's own name; taken → `<stem>.<lang>[.sdh].srt`, then numbers), create-only as before; who downloaded it or an admin | Owner: "By default subtitles should go to cache/subtitles… a 'Download locally' button… rename the subtitle file to the same name as the video file". The owner first wrote ".vtt", then "whatevertheextensionis": the file is written as the SRT it is, which is what other players read |
| 10-12 | **Downloaded subtitles are also saved next to the video** ("Episode.en.srt"), **on by default**, a setting to turn it off; **create-only** (`readonly.create_sidecar`: exclusive create of a new `.srt` in the video's folder, a taken name gets `.2`, identical file reused); removing a download **leaves its copy** | Owner: "it downloads a local copy to the episode's directory so you always have the subtitles", then chose opt-out and "leave the copy". The first exception to rule 1 / O5 (media read-only): kept as narrow as possible (one function, one thread, one path, no overwrite/rename/delete) so the guarantee that BAMS can't damage media still holds |
| 10-12 | The Linux service's sandbox stays as shipped; Settings shows the **`ReadWritePaths=-<folder>` drop-in** the admin runs once (sudo) for their TV/movie folders | Library folders are only known at run time and the `.deb` can't loosen the kernel's read-only wall by itself; a drop-in survives upgrades and is easy to undo |
| 10-11 | **"Keep" takes a file off the Unrecognized list** (`files.manual.kept`): hand-identified files as well as Auto fill's guesses (saved as a hand identification) | Owner: identified files stayed listed for good, so the list never emptied. A kept file is still identified by hand: rescans keep it, `DELETE /identify` forgets it |
| 10-11 | **The OpenSubtitles key box rules out only what can't be a key** (spaces, under 8 or over 4096 characters); a pasted sign-in token (a JWT whose `exp` is under 30 days away) is refused with a pointer to the API consumers page | Owner's paste was refused by the 0.10.0 check (16–64 letters, digits, `-`, `_`), which guessed a format nobody documents. What they had pasted was a 24-hour sign-in token, so a clear message beats a vague one |
| 10-11 | **Hyphenated words in names are read whole** (`parse._read`): when guessit's title cuts through one, it's read again with the hyphen protected. In file names "Show-01" stays episode 1 and an all-lowercase "grp-title.2010" keeps its group; a movie folder's name wins when the file's lost its front | Tester: "Catch-22" was "Catch" (guessit read "-22" as the episode; "Ant-" in "Ant-Man.2015" as a release group). Dry run over the owner's 4,391 real paths: nothing else changed |
| 10-11 | **Another server's library order is kept per browser** (dragged in the sidebar, `bams.servers` → `order`), by anyone; this server's own order stays the admin's, shared by everyone. This server's libraries sit under its **name** in the sidebar, like other servers' | Owner: "allow me to drag and re-arrange the library order on other servers" and "This should say your server name, not Libraries". Kept where that browser's names and hidden flags for the server already are: no admin rights needed there, nothing changes for its other users |
| 10-11 | **Fix match lists the title's folders** (shows: the folder above the season folders, as the parser picks it, with file counts; movies: their files), admins only | Tester request: check the right folder is being fixed. Server paths are admin information (`/api/status` hides them from viewers too) |
| 10-11 | **The Fire TV app is the Samsung TV app** (`tv/`, built page bundled as APK assets) in a full-screen WebView, with **ExoPlayer** drawing under the see-through page and the device's decoders read from Android (`Caps.kt`), not a table. Fire OS 6+ only (not Vega OS) | One app to keep in step with the web/TV look (owner wants web and TV to show the same). ExoPlayer seeks inside a streamed file (AVPlay can't), so files the device decodes play from `/stream`; Fire TV models differ too much for a codec table |
| 10-11 | **Fire TV releases are signed with a release key** made for BAMS (`C:\Users\Beached\bams-firetv.jks`, passwords in git-ignored `firetv/keystore.properties`); debug builds use this PC's debug key | Owner's choice at release 0.12.0. Android installs an update only over an app signed with the same key: losing it means every Fire TV uninstalls, reinstalls and signs in again |
| 10-11 | **Quality menu: sizes up to the file's own** (the 16:9 box it fills: 1920×800 counts as 1080p), 4K/1440p only on a GPU encoder (`/api/status.video_encoder.hardware`); a size picked in this player applies even at the file's own size (converted), one **remembered** from another video only shrinks bigger files | Owner: "add a 1080P and 4k option". The CPU encoder stops at 1080p (`stream._box`), so 4K there was a 1080p picture. Remembering "1080p" from one workaround must not convert every 1080p file afterwards |
| 10-11 | **One watch list across every server, stored on the servers**: each server keeps the watch list entries of its own items per account (table `watchlist`, schema v12); the web and TV apps put every connected server's part into one list (newest added first, `everywhere.listedOrder`). It sits under Home in the sidebar/rail, above the first library, and is a Home row (`watchlist`, after Continue Watching) | Owner: "a universal watch list, where episodes from EVERY server can be added… stored server side so all clients sync it". Keeping each item on its own server honours the 10-10 rule that servers store nothing about other servers; any device signed in to those servers shows the same list. A device not connected to a server doesn't see that server's entries (it couldn't play them either) |
| 10-11 | The watch list holds **movies, shows, seasons and episodes** (not music); watching something **doesn't** take it off; its **name** is a per-account pref (`watchlist_name`, "" = "My Watch List") on the client's first server, renamed on the web list page | Owner: "ALL files I should be able to add… 'My Watch List' will be its default name". A watch list is for video; removal stays the person's choice (Netflix-style), with the watched tick shown on the card |
| 10-13 | **Android phone app** = the server's own web UI in a WebView online (the same pages, plus Download buttons through `window.bamsAndroid`), its own pages bundled in the APK offline (built from `web/`, same styles), native ExoPlayer/Media3 for downloaded video and music. Android 8+, sideloaded APK | Owner: "look exactly like the web version… work even if it can't find a server". Server-served pages stay in step with every release; offline pages can't come from a server. Browsers can't play most original files (MKV, AC3) and music must play on with the screen off |
| 10-13 | **Downloads come back for the Android app only**, gated by a **per-account switch** (`users.can_download`, schema v14; admins always) and their own route (`/api/files/{id}/download` + manifests). The web and TV apps still offer none | Owner's choice for the phone app, reversing 0.9.2 there only. Playing already sends the bytes (`/stream`), so the switch is a policy, not a lock |
| 10-13 | Downloads go to the **app's own folder** on the phone's storage or an **SD card** (picked in Settings → This phone; no permission; deleted with the app); **Wi-Fi only** by default; each original file kept once however many downloads need it | Owner's choice (simplest, reliable on Android 11+). Wi-Fi only because originals can be many GB |
| 10-13 | Sound the phone can't decode offline (DTS, TrueHD, AC3 on some phones): **warn on Download**, play another track the file has; **no FFmpeg in the app** | Owner's choice; bundling an FFmpeg decoder would break "FFmpeg is never bundled" |
| 10-13 | The app knows a server by **`/api/hello` `id`** (new, stable) with **every address it was reached at** (home LAN, away), trying each; the WebView's sign-in cookie is shared between them | Owner: the server is reachable only sometimes (walks: nothing; trips: internet). Downloads must stay one server's whichever address answers |
| 10-14 | **Releases are made from the Linux PC**: `.deb` and APKs built there, the Windows `.exe` by **GitHub Actions** on GitHub's Windows machine when the release is published; the Fire TV release key gets a copy on the Linux PC; Samsung builds stay on the Windows PC (10-15: the maintainer keeps the Samsung certificate passwords; the Tizen CLI tried on Linux was removed) | Owner: "configure everything needed for me to deploy windows and firetv builds" from Linux, and "I don't think we need Wine". Inno Setup runs only on Windows; a hosted Windows runner is a real Windows build without a Windows PC |
| 10-14 | **Android releases are signed with a BAMS release key** (`/mnt/Data/Sandboxes/Android/bams-android.jks`, passwords in git-ignored `android/keystore.properties`), first used for 0.2.0 | Owner's go-ahead. Updates install only over the same key; switching from the debug builds meant one reinstall while there was little to re-download |
| 10-13 | **Playlists made in BAMS are each account's own and private** (`user_playlists`, schema v15); albums/artists add their tracks as they are now, each track once; imported playlists stay read-only with **"Make a copy"**; full editing on web, TV (hold-OK menus, TV keyboard) and the phone online; downloadable to the phone | Owner: "create playlist, name them, add a brief description, add individual songs, albums or artist… for all versions", then chose "personal and private" and full TV editing. Playlist files live in read-only media folders |
| 10-13 | **Quality line** under a playing song's title and artist on every player (`web/src/quality.ts`): codec + bit depth/sample rate (lossless) or bitrate (lossy); a converted song shows both ("ALAC 24-bit / 96 kHz → AAC 256 kbps") | Owner: "list the current format/quality of the song… below the song name and artist" |
| 10-10 | The **encoder test uses the real rate-control options**; VAAPI falls back to **constant QP** (`-rc_mode CQP -qp 23`, no bitrate cap) when the driver refuses a bitrate | Owner's Ubuntu server (Intel HD 630, Ubuntu's free `intel-media-va-driver`) supports only CQP: the old option-less test passed and every real conversion failed. Bitrate modes stay where the driver has them |
| 10-15 | **Theatre mode = the TV app's page in a browser**, served by the server at `/theatre/`, with a "Theatre mode" item in the web UI's account menu; a PC at a TV runs it in **Chrome kiosk mode** started at sign-in (`docs/THEATRE.md`). A native app (Qt WebEngine + libmpv under the page, like Plex HTPC / Jellyfin Desktop) was planned as a second step and **set aside by the owner** | Owner: PCs with USB remotes as "theatre" boxes like Plex HTPC, "if possible a toggle for the web version"; after trying it: "I think i can make this work on all my devices". The TV page already is BAMS's 10-foot UI, so the boxes show exactly what the TVs do. Cost: browser codecs (the server converts more than for the TVs), no Dolby/DTS bitstream to a receiver, HDR only where the browser does it |
| 10-15 | **Theatre mode signs in with name and password only** (no link code / QR); the TVs keep the code. The theatre page uses its **own token, never the web UI's cookie** (`credentials: "omit"`; the server prefers a cookie over a bearer token) and **its own storage keys** (`bams.theatre.*`) on the shared origin | Owner: "remove the QR/link login, lets just do username and password" (a PC has a keyboard). Same origin as the web UI: its cookie would make the page act as whoever is signed in there, and both use `bams.servers` in different shapes |
| 10-15 | **Chrome/Chromium for theatre boxes, not Edge's `--kiosk`** | Both of Edge's kiosk types run InPrivate (Microsoft's docs): the box would forget its sign-in at every boot; Edge kiosk isn't supported on Linux |

## 4. Built so far


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
  Specials = Season 0, " - " kept inside titles, unnumbered files in season folders = extras of that season
  (also when the file name carries the season), the show = the folder right above the season folder (nested packs),
  else the deepest season-pack folder; Star Trek short forms (DS9/TNG/TOS/VOY/ENT) spelled out; a year after a
  "Series N" marker is the season's, not the show's; hyphenated names kept whole ("Catch-22", "Ant-Man", "9-1-1",
  `parse._read`). ~65 real-world cases in `tests/test_parse.py`.
- **Identify by hand** (`identify.py`): unrecognised files listed with hints; an admin pastes a TMDB/IMDb link or
  enters title/year/season/episodes; kept in `files.manual` across rescans; undo; "Don't place" (`{skip: true}`);
  "Keep" (`{…, kept: true}`, 0.13.1) takes a hand-identified or guessed file off the Unrecognized list.
- **Auto fill** (0.9.0, `parse.guess`): what the rules can't place is placed by a best guess from folders and name
  (on by default, Settings → Unrecognized files → Auto fill); guesses are listed for review (Keep / Change / Don't place).
- **Grouping:** `item_keys` aliases so differently-named folders of one show (e.g. "Bobs Burgers S01-S08…" and
  "Bob's Burgers (2011) S14…") become one show, and stay merged on later scans.
- **TMDB matcher:** path-id hints → `/find`, else search + confidence score (≥0.80) → details, images, seasons,
  episodes. Duplicate titles are merged. Low confidence → "unmatched" (never guessed). Refresh before 6 months.
  Fix-match endpoint; Fix match lists the title's folders/files (`/api/items/{id}/folders`).
- **Probe:** ffprobe summary (container, codecs, resolution, HDR, audio/subtitle tracks; music tags, embedded cover flag).
- **Music libraries:** artist > album > track from tags (ffprobe) with the folder layout as fallback (disc folders,
  `Artist - Album`, FMA-style names). Album covers from `cover.jpg`/`folder.jpg`… or the embedded picture;
  `artist.jpg` for artists; all copied into `data/images/music/`; a `cover.jpg`/`artist.jpg` added or changed later
  replaces embedded/downloaded art (`items.poster_src`). Browser-unplayable formats converted on the fly
  (`/audio?t=`) to AAC or, by admin choice, lossless FLAC. `/api/items/{id}/tracks` gives a play queue (best file
  per track; CUE `start`/`end`).
- **CUE sheets** (`cue.py`): a `.cue` next to a whole-album file (or a CUESHEET tag inside it) makes one track per
  entry; adding/editing/removing the sheet re-reads the file's tracks on the next scan.
- **Playlists** (`playlists.py`): `.m3u`/`.m3u8`/`.pls` files in music folders imported and kept in step with their
  files; entries matched by relative path, absolute path under a root, `file://`, or a unique path tail.
- **Music identification:** MusicBrainz (release id from tags, else scored search), Cover Art Archive covers,
  Wikidata → Wikipedia summaries and Commons artist photos with credits. Fix match for albums/artists. On/off
  setting. Respects MusicBrainz's 1 request/second. Albums pinned to the same release are merged; identified
  albums/artists refreshed after ~4 months (50 per scan).
- **Playback:** `stream.plan()` picks Direct Play / Direct Stream (file) / Direct Stream (remux) / Transcode.
  `/stream` (Range), `/remux?t=` (FFmpeg: copy video + AAC audio, fragmented MP4), `/seek?t=` (real
  keyframe start via a dry run). No downloads (removed in 0.9.2).
- **Video transcoding:** `/transcode?t=` converts video browsers can't decode (Xvid/DivX, MPEG-1/2, VC-1, Theora,
  ProRes, 10-bit/4:2:2/4:4:4 H.264…, and HEVC/AV1/VP9 for browsers without them) to H.264 + AAC on the best working
  encoder (NVENC/QSV/AMF/VAAPI, else x264). Deinterlaces, squares anamorphic pixels, caps the size, tone-maps HDR
  (Dolby Vision through libplacebo). GPU decoding with a GPU encoder. **HLS sessions** (`hls.py`): segments made
  on demand, native seeking, quality (max height) per session, bounded CPU/disk, idle sessions closed. A limit on
  simultaneous conversions (Settings).
- **Accounts:** `auth.py` (scrypt hashes, sessions, throttle), admin/viewer roles, first-admin setup from the server
  itself, login middleware on `/api/`, `bams user add|list|passwd|remove|unlock|2fa-off`. "Must change password at
  next sign-in" per account; two-step sign-in with an authenticator app (TOTP) (0.8.0).
- **Security** (`security.py`, `netflow.py`): sign-in log (`security.db`), per-account wait after wrong passwords
  (1 s doubling) and lockout (default 5), admin lock/unlock, IP allow/block lists (`security.Gate`, outermost
  middleware), traffic log of every request (10 GB cap, folder/size settable), `bams security allow-all`.
- **Watch state:** `watch.py`: progress (watched at 90% / started after 30 s by default; admin settings), watched flags for movie/episode/season/show, per-user counts on
  every item list, Continue Watching (resume + next episode; a title can be taken out until it's watched again,
  `hide_continue`, 0.11.0), next episode for up-next.
- **Subtitles:** `subtitles.py`: embedded + sidecar tracks with language labels, WebVTT conversion (cached, any sidecar
  encoding, `?shift=` for live streams), picture subtitles burned in with a 30 s lead, VobSub `.idx/.sub` sidecars
  (one track per language) burned in too.
- **Download locally** (0.15.0): a downloaded subtitle saved next to its video as `<video name>.srt` on request
  (create-only; Linux needs a `ReadWritePaths` drop-in shown in Settings). Downloads stay in `cache/subtitles`.
- **OpenSubtitles** (0.10.0, `opensubtitles.py`): each server's own API key + optional account (Settings → Playback);
  "Check OpenSubtitles" in the web and TV players searches by TMDB/IMDb id + moviehash; a picked subtitle is
  downloaded into the data dir and becomes a track (`d<n>`) of that file for everyone; removable.
- **Audio:** track list with labels, any track via the remux, 5.1 AAC on request (`channels`/`ch`), Dolby (AC3/EAC3)
  pass-through on devices that decode it.
- **HLS (more):** copy variants for the remux (keyframe-cut fMP4), Auto quality ladder, all-GPU filters with fallback
  (NVIDIA tested; Quick Sync, VAAPI, AMF built but untested on hardware). Dolby Vision profile 5 verified on a real file.
- **Scheduler:** one worker thread (scans run one at a time), timer queues due libraries, progress reporting
  (step, done/total, bytes, seconds into the step) shown in Settings.
- **API:** ~40 endpoints (see CODEBASE.md). **CLI:** `bams serve|library|scan|tmdb-key|status`.
- **Installers** (`deploy/`, v0.4.0; release notes in `CHANGELOG.md`): `build.py` makes `BAMS-Setup-<v>.exe` (Inno Setup: embeddable Python + locked
  packages, FFmpeg downloaded at install with a pinned hash, WinSW service, firewall rule for private networks,
  admin-only data dir, update in place, uninstall that asks before deleting data) and `bams_<v>_all.deb` (offline wheels,
  venv, systemd unit as the desktop user, `/etc/default/bams`, ufw, update in place, remove keeps / purge deletes data).
  User guide `docs/INSTALL.md`; build/release notes `deploy/README.md`. In-app TMDB key guide `/help/tmdb.html`.
- **Apps on other devices** (`devices.py`): `/api/hello` (public: "this is BAMS"), TV link codes (`/api/devices/link`,
  `/poll`, `/approve`), `/api/auth/token` (name+password → bearer token), `/api/devices` (your TVs, sign one out),
  `/api/media-ticket` (`/api/t/<ticket>/…` paths for players that can't send headers), CORS for the TV's origin;
  copy-HLS can make MPEG-TS segments (`ts`) for Samsung's player.
- **Deploy (manual):** `deploy/linux/bams.service` (hardened systemd unit; kernel-level read-only media).

### Web (`web/`, React 19 + Vite + TS, ~2,600 lines + 530 lines CSS)
- Pages: Home (hero, Recently Added, per-library rows, Top Rated, genre rows; each user picks which rows show and their order), Library grid (sort, genre
  filter), Title page (show: season tabs + episodes; movie: tech info), Player (real `<video>`,
  remux-aware seeking, converted video over HLS (hls.js, loaded on demand), switches to the conversion when the
  browser can't decode the video, quality menu, keyboard shortcuts), Search, Settings (libraries with folder picker,
  scan status; Unrecognized files (identify by hand: link or fields with suggestions); TMDB key card; Playback card:
  encoder in use + conversion limit; Watched and Continue Watching thresholds). Library pages have an Unrecognized
  tab for admins. Player: speed 0.1x–3x. Music queue: drag (or arrow keys) to reorder. Show-password buttons,
  confirm-new-password. Settings → Home page (per person): banner on/off, rows on/off and order (drag, arrow keys, ▲▼), reset. Playback card: encoder choice (CPU/GPU). Library cards:
  live scan progress (N of M, size, time left, bar) and ▲▼ order buttons. Sidebar: this server's libraries under its
  name; admins drag them into order; anyone drags another server's libraries into order (kept in the browser).
- Music: library page (Artists/Albums/Playlists tabs, sort, genres), artist page (bio, photo credit, albums), album page
  (tracklist by disc, format note, Wikipedia/MusicBrainz links), playlist page (`/playlist/:id`, cover mosaic, missing
  entries), Fix match (goes to the kept album after a merge), a now-playing bar with queue that keeps playing across
  pages (media keys via Media Session) and pauses when a video starts; gapless hand-over between tracks and CUE
  tracks played as stretches of one file; music in Home and Search; Music library type + identification toggle +
  converted-music format (AAC/FLAC) in Settings.
- Settings → Security (`SecuritySettings.tsx`, admins): wrong-password threshold, account locks (lock/unlock), who can
  connect (mode + allow/block lists, "Allow my address"), sign-in log (filter, older), traffic log (folder, size, usage,
  search, older).
- Sign-in / first-admin screens (`auth.tsx`; code box for two-step accounts; "Pick your own password" screen),
  account menu, Settings → Accounts (password, two-step sign-in with QR code, users with "must change password" and
  "Turn off two-step"); viewers see only their account. Continue Watching row, watched ticks / unwatched counts / progress bars, mark watched on movie,
  show, season and episode, Resume / Start over; Continue Watching cards link the show and the episode's season, and a
  long press or right-click offers "Remove from Continue Watching". Player:
  resume, progress reports, up-next countdown (at the end and 30 s before it), next-episode button, skip +30 / −10 s, sound menu
  (tracks, Surround, Dolby pass-through on/off), subtitles menu (text via `<track>`, picture incl. VobSub = burned in),
  quality Original / Auto / sizes up to the file's own (4K on a GPU server, 0.12.0), remux over HLS with fallback to
  the live remux. Sleep mode (bed button: this
  episode + 2 more, a movie to its end), "Check OpenSubtitles…" in the subtitles menu (`FindSubtitles.tsx`).
- Watch list (0.13.0): "My Watch List" under Home in the sidebar (`/watchlist`: every server's entries, sort, kind
  chips, rename), a Home row, a "+ My Watch List" button on title pages (show, movie, season), a bookmark on episode
  rows and on posters (hover), episode entries open their season with the episode picked out.
- TMDB-missing banner (admins) on every page → `/settings#tmdb`. "Can't reach server" banner.
- Brand: logo files in `branding/logo/` + `web/public/brand/`; palette as CSS tokens in `web/src/styles.css`.

### Samsung TV app (`tv/`, Tizen web app, React + Vite + TS)
- Finds the server (TV's /24 from Tizen system info, else common home ranges, or typed), links with a code + QR or
  name/password, Home (hero of the focused title, Continue Watching (hold OK on a card: remove it), Recently added,
  per-library rows), library grids
  (sorts), detail (seasons/episodes, resume/start over/mark watched), search, settings (server, sign out, always
  convert, "TV plays DTS"). Remote: spatial navigation (`nav.ts`), Back, media and colour keys registered.
  Tests (0.7.1): `cd tv && npm test` runs `tv/test/*.test.ts` in headless Chrome/Edge at 1920×1080 (`scripts/test.mjs`).
- Player (`screens/Player.tsx`, `engine.ts`): AVPlay on the TV (`<video>` + hls.js in a browser); copy-HLS in TS for
  what the TV decodes (`plan.ts`), full conversion otherwise or after a failure; resume, ±skip, progress every 10 s,
  sound/subtitle menus (text subtitles drawn by the app from the server's WebVTT, with a timing control; picture
  subtitles burned in), up-next countdown, Sleep button, Check OpenSubtitles (results + language list). Packaging: `npm run package` (`scripts/wgt.mjs`) signs with the Tizen
  Studio profile `BAMS`, `--install --run` puts it on the TV, `--release` copies `dist/BAMS-SamsungTV-<v>.wgt`.
- Web: Settings → Your TVs (`TvSettings.tsx`) and `/link` (`LinkTv.tsx`).
- More servers (0.7.0): Settings → Other BAMS servers (add with the find/link screens, link again, remove, show/hide
  each library); their libraries in the menu under the server's name; Home and Search combined with the web's rows
  (`web/src/everywhere.ts`). Music (0.7.0): music libraries, artist/album/playlist pages, a music bar, media keys.
- Watch list (0.13.0): rail entry under Home (`screens/Watchlist.tsx`, every server's entries; hold OK: take one
  off), the Home row, a watch list button on detail screens, hold OK on an episode to add/remove it (`ListMenu.tsx`).
- Play Random (TV 0.14.0): on libraries, shows and artists (`random.tsx`); "Up next" (`Queue.tsx`: ▲ ▼ move, ✕ remove,
  OK plays) for the random video queue in the player and for the music queue (a queue button on the music bar).

### Fire TV app (`firetv/`, 0.12.0, Android shell around `tv/`)
- Fire OS 6+ (Fire TV Stick 4K / 4K Max / Lite / 3rd gen, Cube, Fire TV TVs). The `tv/` page in a full-screen WebView
  (`MainActivity.kt`), ExoPlayer under it (`Video.kt`, page side `ExoEngine` in `tv/src/engine.ts`), the device's
  decoders and audio output (`Caps.kt` → `plan.ts`: sizes too, a 1080p stick converts 4K; conversions no taller than
  its H.264 decoder), device name/IP and exit (`Bridge.kt` ↔ `tv/src/firetv.ts`). Remote: Back/OK/media keys passed
  on with the Samsung key codes; OK on a text box simulates a tap so the Fire TV keyboard opens. Files it decodes
  play from `/stream` (ExoPlayer seeks in them), others through copy-HLS in fMP4 or a conversion.
- Build: `cd tv && npm run build && npm run firetv` (Gradle 8.11.1, JDK 17, Android SDK 35); `--install --device <ip>`
  over adb; `--release` signs with the release key and copies `dist/BAMS-FireTV-<v>.apk`. Tests in
  `tv/test/firetv.test.ts` (fake bridge).

### Theatre mode (the TV page in a browser on a PC at a TV)
- The server serves `tv/dist` at `/theatre/` (`app.TheatreFiles`, `__main__._theatre_dir`, installers ship it as
  `bams/theatre`); web: account menu → Theatre mode, Settings → This browser (start this browser in theatre mode,
  start-up lines for Mint/Windows), "Your TVs and theatre PCs". Guide: `docs/THEATRE.md`.
- On a PC (`tv/src/platform.ts`: theatre / dev) the page scales its 1920-wide layout to any window (`scale.ts`,
  `--page-h`; `nav.ts` converts zoomed rectangles), maps PC and remote keys to the remote codes (`pckeys.ts`:
  BrowserBack, Home, Menu, media keys, Media Center shortcuts, Media Session, Back history trap, type-to-search), shows
  and uses the mouse (`pointer.ts`), asks the browser what it decodes (`plan.ts`) and follows the web player's order
  (fMP4 copy-HLS, Dolby kept only where decoded, AAC remux before a full conversion). Sign-in with name and password
  (or the web UI's account in that browser); a server that isn't up yet is retried every 5 s.
- Everywhere (TVs too): media tickets are renewed when a picture or the player fails or the page comes back from a
  sleep (tickets die with a server restart).

### Android phone app (`android/`, 0.2.1, release 0.17.1)
- Android 8+ (tested: Android 16 emulator, owner's Galaxy A17 5G). Online: the server's web UI in a WebView with
  Download buttons (movie, episode, season, show, song, album, artist, playlist), a Downloads menu item and Settings →
  This phone (phone storage / SD card, Wi-Fi only, space used, servers and addresses). Offline: its own pages (`web/src/phone/`,
  bundled): Downloads (in progress, shelves, everything downloaded with Remove), Movies, TV Shows, Music, title /
  album / artist / playlist pages, Servers, and a banner that offers "Go online" when the server answers again.
- Downloads: foreground service, original files with Range resume, pictures and text subtitles (WebVTT) too, each
  file once (shared by downloads, deleted with the last one). Video plays in ExoPlayer (resume, next episode,
  subtitles, picture-in-picture), music in a Media3 session (screen off, lock screen); where you stopped is sent to
  the server when it's reached. Build: `android/README.md`.

### More servers (0.7.0, web + TV)
- Clients keep their own server lists: web `servers.tsx` (`bams.servers` in localStorage; `/r/<rid>/…` pages are the
  same page components scoped to that server), TV `api.ts` extras. Server name setting (Settings → This server).
  Web: another server's libraries can be renamed, hidden and put in order per browser (0.11.1).

### Docs
README.md, CLAUDE.md, docs/PLAN.md, docs/STATUS.md, docs/CODEBASE.md, docs/FORMATS.md, docs/READ-ONLY.md,
docs/INSTALL.md, deploy/README.md, server/README.md.

## 5. Not built yet / next

Roughly in priority order:
1. **Playback leftovers (minor):** all-GPU filters on real Quick Sync/AMD hardware (built, untested; VAAPI works on the
   owner's Intel HD 630 under Ubuntu 24.04); a copy-HLS session first reads every keyframe of the file (~8 s for a
   Family Guy episode on the owner's NAS, cached afterwards); Dolby
   pass-through on a real Dolby device (tested only with a faked "supported"); Dolby Vision profile 5 without
   libplacebo/Vulkan fails to convert (zscale can't read it); text MicroDVD `.sub` sidecars (no `.idx`) aren't listed.
2. **Music leftovers (minor):** sample-perfect gapless (Media Source Extensions); un-merging an album; `.cue` entries
   inside playlists; your own playlists can't be shared with other accounts (owner chose private) or edited offline.
3. **ISO / DVD / Blu-ray folders** (phase 3).
4. **Packaging leftovers**: code-signing the `.exe` (SmartScreen warning).
5. **OpenSubtitles leftovers:** not yet tried with a real key (built and tested against a fake; the API was read
   from their docs and probed with a made-up key); downloaded subtitles can't be saved next to the video ("Download locally") from the TV/theatre player, only removed; machine-made
   translations are left out (their default); subtitles split over 2 CDs are skipped.
6. **Theatre mode leftovers:** not tried on Windows (Chrome kiosk, the PowerShell start-up) or with Firefox; no
   bitstream passthrough or real HDR in a browser (a native app was planned and set aside, see the 10-15 decisions);
   an on-screen keyboard for remotes without one; Samsung and Fire TV need a smoke test at their next release (shared
   `tv/` code changed).
7. **TV app leftovers:** the TV's music has no queue view/reorder and no gapless hand-over; renaming other servers'
   libraries is web-only (the TV only hides them); Samsung TVs other than the owner's 2022 Frame untested (codec table in
   `tv/src/plan.ts` from Samsung's specs); the released `.wgt` is signed for the owner's TV only (others re-sign it,
   README); no store build; Settings → Your TVs shows TVs of your own account only (admins can't see others').
   Fire TV: video playback not yet tried on a real device (sign-in, Home, navigation, search and the keyboard were,
   on a Fire TV in the owner's home); no Amazon Appstore build; Vega OS sticks (2025+) would need a separate app.
8. **Watch list leftovers:** no music on it; renamed on the web only (the TV's rail picks a new name up at its next
   start, its Home at once); posters' bookmark needs a mouse (touch screens use the title page's button).
9. **UI redesign** from the owner's mockups.
10. **Android app leftovers:** music streamed online plays in the page (no lock-screen controls, may stop with the phone locked); new episodes of
   a downloaded show aren't fetched by themselves; a downloaded playlist is a snapshot (Download again to update);
   Android 15+ allows background downloads 6 h a day (the rest goes on when the app is opened); no Play Store build;
   the offline video player uses Android's controls, not the web player's look.

## 6. Dev environment (owner's machine)

| | |
|---|---|
| OS / GPU | Windows 11, RTX 5070 Ti 16 GB |
| Repo | `C:\Users\Beached\bams` → github.com/TomSomerville/bams (**private**) |
| Python | `server\.venv` (3.11 via `uv`) |
| Node | 23 (`web/`) |
| FFmpeg | winget `Gyan.FFmpeg` (found automatically, even without PATH) |
| Server data dir | `C:\Users\Beached\bams\data` (gitignored): DB, image cache, logs |
| Owner's server (since 10-10) | Ubuntu 24.04 at `192.168.1.253` (Intel HD 630, FFmpeg 6.1.1), the `.deb`, running as `beached`; data `/var/lib/bams`, log `/var/lib/bams/logs/bams.log`, media on `/mnt/nas/jellyfin-media`. Read-only access for agents: `ssh bams-server` (key `~/.ssh/bams_claude` on the owner's PC; `beached` is in `render`, so FFmpeg/VAAPI tests run there). Installing a package needs the owner's sudo |
| Linux PC (2026-10-13) | Debian 13 at `10.0.0.69`, user `yakob`, repo `/mnt/Data/Projects/bams`. **Sandbox server** `/mnt/Data/Sandboxes/bams/bams.sh {start\|stop\|update\|…}` (:8485, its own copy of the code, generated mock media; `BAMS_HOST=0.0.0.0` for the phone). Android tools in `/mnt/Data/Sandboxes/Android` (`source env.sh`: JDK 17, SDK 35, AVD `bams36` = Android 16 emulator), Chrome for Testing (TV tests: `CHROME_PATH=/mnt/Data/Sandboxes/chrome/chrome-headless-shell-linux64/chrome-headless-shell`). No Tizen tools: Samsung `.wgt` builds are made on the Windows PC only (tv/README.md). Not on the TV's network (10.0.0.x vs 192.168.1.x) |
| Ports | 8484 = the owner's server · 8485 = scratch test instances (`.claude/launch.json` → `bams-test`, data dir in the session scratchpad: edit the path) · 5173 = Vite dev |
| Test media | `C:\Users\Beached\Shows` (TV: Bob's Burgers, Family Guy, Simpsons, Burn Notice, South Park…) · `C:\Users\Beached\Movies` (2 movies) · `C:\Users\Beached\MyMusic` (8 CC0/CC BY albums, 4 artists, `CREDITS.txt`) · `C:\Users\Beached\TestMedia` (Jellyfin DV profile 5 clip + its SDR version, CC BY-SA 4.0, `CREDITS.txt`) |
| Libraries on the owner's server | 1 = "TV Shows" (`…\Shows`), 2 = "Movies" (`…\Movies`); the owner adds "Music" (`…\MyMusic`) when testing |
| Art tools | local ComfyUI (Qwen Image); `tools/brand_art/rework.py` redraws the logo set from the supplied art |
| Samsung TV | The Frame QN50LS03BAFXZA (2022, Tizen 6.5) at `192.168.1.211`, Developer Mode with host `192.168.1.40` (the owner's PC). Tizen Studio 6.1 in `C:	izen-studio` (TV Extensions, Samsung Certificate Extension); signing profile **BAMS** (`C:UsersBeachedSamsungCertificateBAMS`, keep it: updates must be signed with the same author certificate). `sdb connect 192.168.1.211`; remote inspector: `sdb shell 0 debug BAMSmedia1.BAMS` → port, `sdb forward tcp:P tcp:P`, then the DevTools protocol on `127.0.0.1:P` |

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

### 2026-10-15: Subtitle menu scrolls to its end; remove downloaded subtitles on the TV/theatre player (release 0.18.1)
- **What / why:** owner testing theatre mode: with 3+ downloaded subtitles the selection went down out of sight (the
  menu list had a fixed 900 px height under the title and the Timing control, so its bottom ran off a 1080 screen;
  TVs too), and there was no way to remove the ones not wanted (web only). The menu list now fills the menu's height
  left (flex) and scrolls; downloaded subtitles get a Remove button beside them (Right from the option) for whoever
  downloaded them or an admin (same rule as `DELETE /api/files/{id}/subtitles/{track}`); removing the one in use
  turns subtitles off.
- **Files:** `tv/src/screens/Player.tsx` (`Menu` `remove`, `removeSub`, `mayRemove`), `tv/src/styles.css` (`.menu`
  flex, `.menu-list`, `.menu-row`).
- **Verified:** TV tests 44 passed, `tsc`. Test copy (:8510) with six fake downloads at 1920x1080: with Timing shown,
  Down to the last subtitle keeps it on screen (list scrolled 302 px, bottom at 1020/1080); Right → Remove → OK takes
  it off (server row and file gone), focus back on the ticked option; removing the one in use → Off.
- **Left open:** to be tried by the owner on the main server with real OpenSubtitles downloads; Samsung/Fire TV get the
  menu fix at their next release.

### 2026-10-15: Theatre mode: the TV page in a browser on a PC at a TV (release 0.18.0)
- **What / why:** owner uses small PCs with USB remotes (keyboard on the back) at TVs, with Plex HTPC, and wanted that
  for BAMS, "if possible a toggle for the web version". Planned as two steps (browser theatre mode, then a Qt WebEngine
  + libmpv app); the owner tried step 1, liked it and set the app aside. The server serves the TV page at `/theatre/`;
  the web UI's account menu opens it; on a PC the page scales to the window, maps PC/remote keys, takes the mouse,
  asks the browser what it decodes and follows the web player's fallback order. Sign-in with name and password only
  (owner: no QR/link code); its own token and storage apart from the web UI on the same origin. Tickets renewed after
  a server restart (TVs too). Guide for automatic sign-in + Chrome kiosk at start-up.
- **Files:** `server/bams/{app,__main__}.py`, `server/tests/test_theatre.py`; `tv/src/{platform,pckeys,pointer,scale}.ts`
  (new), `api.ts`, `App.tsx`, `nav.ts`, `plan.ts`, `tizen.ts`, `styles.css`, `screens/{Link,Settings,Search,Player,…}`,
  `tv/test/pckeys.test.ts`; `web/src/components/{TheatreSettings,TopBar,TvSettings}.tsx`, `web/src/main.tsx`,
  `pages/Settings.tsx`; `deploy/build.py`; `docs/THEATRE.md`. The plan with the set-aside app design stayed outside the
  repo (`plan.md` in the owner's checkout, untracked).
- **Verified:** server tests 346 passed (Python 3.11 venv), TV tests 44 passed, web/TV `tsc`. Built page checked in the
  preview browser against a sandbox copy (:8510): `/theatre` redirect, sign-in by keyboard, Home scaled to 1024×768 and
  1920×1080, type-to-search, Enter to results, Back, scrolling under zoom; HEVC file played as-is, an E-AC-3 MKV as
  fMP4 copy-HLS with AAC; Space / media key / Ctrl+P / Ctrl+Shift+P / BrowserBack in the player; a picture recovering
  after a server restart (old ticket 401 → renewed); the web UI's menu item, "use this account", the redirect flag and
  `?web`; Settings remote test and Leave theatre mode. Probed in Chrome 155 on a plain-http LAN page: no Keyboard
  Lock/Clipboard, Media Session works; CSS zoom: rectangles zoomed, scrollTop not.
- **Owner:** on the sandbox (:8485): "It works perfect so far".
- **Left open:** see §5 item 6 (Windows/Firefox untried, no passthrough/HDR in browsers, on-screen keyboard, TV smoke
  test at the next TV release). Released as 0.18.0 (server only; TV apps unchanged).

### 2026-10-14: Lock-screen controls for streamed music in the Android app (release 0.17.1, app 0.2.1)
- **What / why:** owner picked it from the left-open list: music streamed online in the app played in the page
  (no lock-screen controls, could stop with the phone locked). In the app (0.2.1+, `android.appPlaysMusic` from the
  user agent) `web/src/music.tsx` `AppMusicProvider` hands the queue to the app's Media3 player (`musicStream`: media
  ticket URLs, no headers; queue kept in sessionStorage across page loads) and shows its state (`bams:music`); the
  browser player is unchanged. App: `Music.stream`, `Streams.kt` (a `ForwardingPlayer`: a converted track
  (`/audio?t=`) seeks by starting over, reports its time and length, isn't "live", so the lock screen gets seek and
  previous; a file the phone can't decode falls back to the conversion), seeks from the page through a session
  command (`Streams.SEEK`), bridge `musicStream`/`musicCmd`/`musicState` now allowed for server pages.
- **Files:** `web/src/{music.tsx, android.ts}`; `android/.../{Music,Streams,MusicService,Bridge}.kt`,
  `gradle.properties` 0.2.1; sandbox mock media got an AIFF album ("Test Signals", converted while streaming).
- **Verified:** Android 16 emulator, debug build driven over Chrome's remote debugging: streamed MP3/FLAC play in the
  media session (notification with art/title/artist, seek bar, prev/next), 20 s with the screen locked kept playing,
  media keys next/previous (previous restarts first), page bar follows; converted AIFF: quality line "PCM 44.1 kHz →
  AAC 256 kbps", seek to 27 s (`?t=27.00`), carries on into the next converted track, bar counts; MP3 seek 2 → 22 s;
  release 0.2.1 installs over 0.2.0. Web `tsc`, TV `tsc`.
- **Owner:** on the Galaxy against the sandbox: play/pause, next, previous, seek on the lock screen and headphone
  buttons all work; the converted album shows the conversion line and seeks from the lock screen.
- **Released:** v0.17.1 with `bams_0.17.1_all.deb` and `BAMS-Android-0.2.1.apk` from the Linux PC; the first
  `BAMS-Setup-0.17.1.exe` built by GitHub Actions (`.github/workflows/windows-installer.yml`, run by hand for this
  release; runs by itself on every published release from now on), attached with its `SHA256SUMS.txt` line (same
  size as the partner's 0.17.0 build, valid PE). TV apps unchanged (0.15.0). Not install-tested on Windows yet.
- **Left open:** the volume slider moves the app player's own volume (the phone's buttons still set the system volume).

### 2026-10-13: Your own playlists and the quality line (release 0.17.0, TV apps 0.15.0)
- **What / why:** owner: "an option to create playlist, name them, add a brief description, add individual songs,
  albums or artist… for all versions" and "list the current format/quality of the song… below the song name and
  artist". Private per account (owner's choice), imported playlists read-only + Make a copy, full TV editing.
  Server `user_playlists.py` + routes `/api/user-playlists*` (+ `/download`), schema v15; `stream.plan_audio` adds
  `sample_rate`, `bit_depth`, `bitrate`, `channels`, `convert_to`. Web: Playlists tab (yours + New playlist, then
  imported), Add to playlist on albums/artists and a small icon per song, `/my-playlist/:id` (drag, take out, edit,
  delete, download in the app). TV: New playlist tile, Add to playlist on album/artist pages, hold OK on a song (add;
  in your playlist: move up/down, take out), Make a copy. `web/src/quality.ts` shared by all three players (the TV
  says "→ AAC/FLAC" when it falls back to the server's conversion).
- **Files:** `server/bams/{user_playlists,app,db,stream}.py`, `tests/test_user_playlists.py`; `web/src/{quality.ts,
  components/Playlists.tsx, pages/Music.tsx, components/NowPlaying.tsx, App.tsx, api.ts}`; `tv/src/{PlaylistMenus.tsx,
  screens/Music.tsx, music.tsx, api.ts, App.tsx, Icon.tsx, styles.css}`, `tv/test/nav.test.ts`; `web/src/phone/*`.
- **Verified:** 342 server tests (+ `test_encoder_choice_api`, Linux-only failure as before); TV `npm test` 39/39
  (Chrome for Testing); `tsc` web + TV; browser: made/edited/filled/reordered a playlist, quality line on FLAC; TV app
  at 1920×1080 in the browser: playlists tab, hold-OK menu (move), New playlist from an album; emulator: download a
  playlist, offline page + play + quality line. Owner on the phone: made playlists, added songs, saw descriptions and
  the quality line, downloaded a playlist and played it offline (0.1.1).
- **Released (2026-10-14):** GitHub release **v0.17.0** with `bams_0.17.0_all.deb` (built on the Linux PC; unpacked,
  installed offline from its wheels and started: 0.17.0, UI served) and `BAMS-Android-0.2.0.apk`. The owner's partner
  adds `BAMS-Setup-0.17.0.exe`, `BAMS-SamsungTV-0.15.0.wgt` and `BAMS-FireTV-0.15.0.apk` from the Windows PC
  (`gh release upload v0.17.0 …`, `SHA256SUMS.txt` regenerated with all five): done 2026-10-14, from the tagged commit
  after 343 server tests and TV `npm test` 39/39; the `.wgt` has the same certificates as 0.14.0, the Fire TV APK the
  same release key (versionCode 1500). The owner updated their Ubuntu server to 0.17.0 (`sudo apt install`) and
  reports it working.
- **Left open:** not tried on a real TV.

### 2026-10-13: Android phone app with downloads (release 0.17.0, app 0.2.0)
- **What / why:** owner: an Android app that looks like the web version, plus downloads of movies, episodes, seasons,
  shows, songs, albums, artists and playlists (original files) to the phone or an SD card, that works with no server
  and shows what's downloaded. Decisions in §3 (10-13). Server: `can_download` (v14), `/api/files/{id}/download`,
  manifests (`/api/items|playlists/{id}/download`), `/api/hello` `id`. Web: `android.ts` bridge, Download buttons,
  Settings → This phone, account switch in Settings → Accounts, Downloads in the menu, and a fix for an older bug
  (libraries stacked in the phone-width menu bar: `.nav-libs` had no phone rule). App: `android/` (see README).
- **Files:** `android/` (new), `web/src/{android.ts, components/{Download,PhoneSettings}.tsx, phone/, servers.tsx,
  pages/{Detail,Music,Settings}.tsx, components/{Sidebar,AccountSettings}.tsx, styles.css}`, `web/phone/`,
  `web/vite.app.config.ts`; `server/bams/{app,auth,db}.py`, `tests/test_downloads.py`, `test_devices.py`, `test_api.py`.
- **Verified:** server tests; Android 16 emulator against a test server: sign-in in the app, downloads of a show
  (byte-identical to the originals), a movie with AC3 (warning shown, plays picture-only), an artist, a playlist to
  an SD card (a shared song reused, removing it kept the shared one), offline start → Downloads, episode playback with
  resume, music with the screen off (media session), "Go online" when the server returned, offline progress sent.
  Owner on a Galaxy A17 5G (Android 16): connected, downloaded, played offline.
- **Left open:** see §5 item 9 (release key first). The version is shown at the bottom of offline Downloads after a
  stale install of 0.1.0 looked like a bug.

### 2026-10-12: Play Random and Up next on the TV apps (TV 0.14.0)
- **What / why:** owner: "lets update the TV apps with this same functionality" (0.16.0's Play Random). Buttons on the
  library (chip in the head), show (after the watch list button) and artist (after Shuffle) screens. Video queue in
  `tv/src/random.tsx` (module store + `useSyncExternalStore`, sessionStorage); the player's `nextOf()` reads it before
  `item.next_id` (Next, countdown, sleep mode). `tv/src/Queue.tsx` "Up next": a remote can't drag, so each row has
  ▲ / ▼ / ✕ buttons, focus follows the moved row; used by the player (pill "Up next") and the music bar (new queue
  button; `music.tsx` got `jump`/`move`/`remove`). Icons `list`, `up`, `down`, `close`.
- **Files:** `tv/src/random.tsx`, `tv/src/Queue.tsx` (new), `tv/src/music.tsx`, `Icon.tsx`, `styles.css`,
  `screens/{Player,Library,Detail,Music}.tsx`, `tv/test/nav.test.ts` (Up next case), `tv/package.json` 0.14.0.
- **Verified:** `tsc`; TV test page in the browser pane at 1920×1080 (no Chrome/Edge on that PC): 36/38, the 2 rail
  tests fail identically without these changes (pane quirk); the dev TV app against a sandbox server with remote
  key events: random queue, move/remove/jump, Next follows the queue, music queue remove, Back.
- **Released:** on the owner's PC, `npm test` 38/38 (headless Chrome), signed `BAMS-SamsungTV-0.14.0.wgt` and
  `BAMS-FireTV-0.14.0.apk` (release key, same certificate as 0.12.0/0.13.0) attached to the **v0.16.0** release with
  an updated `SHA256SUMS.txt` and notes. Not a release of its own: the in-app updater reads GitHub's *latest* release
  for the `.exe`/`.deb` (`updates.LATEST_URL`), so a TV-only release would hide the server installers.
- **Left open:** not tried on a real TV.

### 2026-10-12: Play Random, video Up next, remove from queues (release 0.16.0)
- **What / why:** owner: a "Play Random" button on each library, show and artist that plays a random selection, "with
  the same playlist edit functionality as music has", then "add a delete option to the playlist".
  `GET /api/libraries/{id}/random` and `GET /api/items/{id}/random` (show/season → episodes, artist/album → tracks;
  `limit` default 100; only items with an available file; season 0 left out). Music goes to the music queue; videos to
  the new video queue (`web/src/random.tsx`, sessionStorage, per tab), which the player follows (`nextId` in
  `Player.tsx` replaces `item.next_id` while the item is in the queue) and shows as a reorderable *Up next* panel.
  Both queues got a remove (×) button; the playing entry can't be removed.
- **Files:** `server/bams/app.py` (`_random_videos`, `_random_tracks`, two routes), `web/src/random.tsx` (new),
  `web/src/pages/{Player,Library,Detail,Music}.tsx`, `web/src/music.tsx` (`remove`), `components/NowPlaying.tsx`,
  `main.tsx`, `styles.css`; `tests/test_watch.py::test_play_random`.
- **Verified:** 335 server tests; `tsc` + build; in a sandbox (:8485, generated clips) Play Random on the TV and Music
  libraries, Up next panel, removing rows (music 8→7, video 20→19). Owner tried it and approved.
- **Left open:** the credits countdown applies to episodes only (movies go on at the end). TV apps: see the next entry.

### 2026-10-12: "Download locally" instead of automatic copies, downloads in cache/subtitles (release 0.15.0)
- **What / why:** owner: "By default subtitles should go to cache/subtitles. … Next to each subtitle under 'Already on
  this video' should be a 'Download locally' button. Clicking this button will download the subtitle file, move it to
  the same location as the video file, and rename the subtitle file to the same name as the video file". Downloads now
  go to `cache/subtitles/opensubtitles/` (`opensubtitles.FOLDER`; older rows keep their `path`; nothing empties
  `cache/`). The 0.14.0 automatic copy (`keep_beside`, `save_beside`, the `opensubtitles_save_beside` setting and
  `PUT /api/settings/opensubtitles-save`, `save_error`) is gone. `POST /api/files/{id}/subtitles/d<n>/local` →
  `opensubtitles.save_locally`: `<video stem>.srt` first (`_local_names`; taken by another subtitle →
  `<stem>.<lang>[.sdh].srt` → numbers; identical file reused), through `readonly.create_sidecar` as before, recorded in
  `subtitle_downloads.sidecar` (tracks carry `sidecar`); who downloaded it or an admin (403), refused by the OS → 409
  with the reason. The owner wrote ".vtt" then "whatevertheextensionis": the file keeps its own format (SRT, `.srt`).
  Web: the button in `FindSubtitles.tsx` ("Saved as …" afterwards), Settings' section explains the button and keeps
  the folder check + Linux command (`GET /api/settings/opensubtitles-save`). TV apps: no button (not asked).
- **Files:** `server/bams/opensubtitles.py` (`FOLDER`, `SaveError`, `_local_names`, `_write_beside`, `save_locally`,
  `tracks` → `sidecar`, `download`, `status`), `app.py` (`save_subtitle_locally`, PUT route removed); tests
  `test_opensubtitles.py` (downloads in the cache with the media untouched; Download locally: `<stem>.srt`, once, listed
  once, a taken name → `.en.sdh.srt`, the owner's own `.fr.srt` never overwritten → `.fr.2.srt`, removal leaves the copy,
  rights; a read-only folder → 409 + the Linux command; the fake now sends different text per subtitle); web
  `api.ts`, `components/FindSubtitles.tsx`, `OpenSubtitlesSettings.tsx`, `pages/Settings.tsx`, `styles.css`; docs
  CLAUDE.md (rule 1, pitfalls), READ-ONLY.md, INSTALL.md, FORMATS.md, STATUS, CODEBASE, CHANGELOG; VERSION 0.15.0.
- **Verified:** server tests (full suite) and a clean worktree of the release commit; web + TV `tsc`. Scratch server
  (:8498, DB copy, generated clips, the fake OpenSubtitles): a download left the episode folder untouched; the dialog
  listed it under *Already on this video* with **Download locally**; clicking it wrote `Catch-22 S01E04.srt` next to
  `Catch-22 S01E04.mkv` and the row then read "Saved as Catch-22 S01E04.srt".
- **Left open:** no button in the TV apps; 0.14.0 copies already made (`*.en.srt`) stay as they are; the owner's server
  still needs the drop-in command for its folders.

### 2026-10-12: Subtitle copies next to the videos (release 0.14.0)
- **What / why:** owner: "when you download the subtitles for a show… downloads a local copy to the episode's directory
  so you always have the subtitles". That's the first write BAMS makes in a media folder (rule 1 / O5), so the owner
  was asked first and chose: on by default with a setting to turn it off (they picked opt-out over the proposed
  opt-in), create-only, and removing a download leaves its copy. `readonly.create_sidecar(video, name, data)`: a plain
  `.srt` name in the video's folder, `open(…, "xb")` (exclusive create), its own half-written file removed on a failed
  write; the audit hook lets exactly that through (`_allowed.target`, thread-local, path-exact, "x" mode or that
  file's removal) and refuses everything else as before. `opensubtitles.keep_beside` after each download (and on a
  re-pick, so earlier downloads or failed copies get one): `save_beside` names it `<stem>.<lang>[.sdh][.n].srt`
  ("pt-BR" style), reuses an identical file, records `subtitle_downloads.sidecar` (schema v13), failures go to the
  player (`save_error`) and Settings (`opensubtitles_save_error`) without failing the download. `listing()` hides
  BAMS's own copies from the player's track list (the download has the better label). Settings: `PUT/GET
  /api/settings/opensubtitles-save` (on/off; per TV/movie folder whether the OS lets BAMS write, checked with
  `os.access`, and on a Linux systemd service the `ReadWritePaths=-…` drop-in command). Web: "Copies next to your
  videos" in the OpenSubtitles card (toggle, folders, command with Copy, last failure), the player's note after a pick
  says where the copy went, the library card's "writable" badge is no longer a warning for TV/movie folders.
- **Files:** `server/bams/readonly.py` (`create_sidecar`, `_sidecar_write`, `_allowed`, `SIDECAR_EXTS`),
  `opensubtitles.py` (`SAVE_SETTING`, `save_beside_on`, `_beside_name`, `save_beside`, `_save_problem`, `_video`,
  `keep_beside`, `save_check`, `set_save_beside`, `listing`, `status`, `download`), `db.py` (v13), `app.py` (routes,
  `get_item` → `listing`); tests `test_readonly.py` (+2: the one write and nothing else, the door is exclusive-create
  of one path), `test_opensubtitles.py` (copy saved and media otherwise byte-identical, no second copy on a re-pick,
  the owner's own file never overwritten → `.en.2.srt`, `.sdh`, removal leaves the copy as a sidecar, setting off/on
  and the re-pick saving it, a read-only folder: download still works + `save_error` + the systemd command),
  `test_auth.py` (v13), `test_watchlist.py` (its migration check follows `SCHEMA_VERSION` instead of pinning 12); web
  `api.ts`, `components/OpenSubtitlesSettings.tsx` (`SaveBeside`), `FindSubtitles.tsx`,
  `pages/Settings.tsx`, `styles.css`; docs: CLAUDE.md rule 1 + pitfalls, READ-ONLY.md, INSTALL.md, STATUS, CODEBASE,
  CHANGELOG; VERSION 0.14.0.
- **Verified:** 334 server tests (clean worktree of the release commit too). Scratch server (:8498, DB copy, generated
  Catch-22 clips, the fake OpenSubtitles): a pick on S01E03 wrote `Catch-22 S01E03.en.srt` next to it through the
  running server (audit hook installed), the videos untouched, the player listed the subtitle once; Settings showed the
  section and the folders. The `ReadWritePaths` syntax was checked against the owner's server's own `systemd.exec`
  manual (systemd 255: allow-list under `ProtectSystem=strict`, may repeat, "-" = ignore if missing); the drop-in
  itself hasn't been run on a real service yet (it needs the owner's sudo).
- **Left open:** the owner's server needs the drop-in command (Settings shows it) before copies are saved there;
  the TV apps show no note about the copy (they still save it: it's server-side); downloads made before 0.14.0 get a
  copy only when picked again.

### 2026-10-12: OpenSubtitles account sign-in error, VIP account on the owner's server, tools committed (release 0.13.2)
- **What / why:** owner: "Tester cannot log into open subtitles with their account credentials" (screenshot: "OpenSubtitles
  didn't accept the API key (You cannot consume this service)" under the account form). Probing `/login` with a
  made-up key gives exactly that 403 before any credentials are read, so the tester's *server* key was refused, not
  the account. The owner's server (0.13.1) was fine: key verified, and its traffic log had no failed sign-in, so the
  screenshot came from the tester's own server. `Client.request` now answers a 403 on `/login` with "OpenSubtitles
  refused this server's API key …, so it couldn't sign in to the account; the name and password weren't checked.
  Press Test next to the key; if it's refused too, paste the API key again from …/consumers". The owner then signed
  in on their own server with the tester's account: OpenSubtitles reported "VIP Member", 1000 downloads a day.
  Also committed at the owner's request ("commit everything"): `tools/hwcheck/` (hardware check scripts, Windows +
  Linux, made by another session) and the project skills `.claude/skills/bams-server`, `.claude/skills/tv-connection`.
- **Files:** `server/bams/opensubtitles.py` (`Client.request`), `tests/test_opensubtitles.py` (a refused key on account
  sign-in: 409 with the key message, account not kept); `tools/hwcheck/`, `.claude/skills/`, `.claude/launch.json`
  (scratch servers); README, CODEBASE (tree), CHANGELOG, VERSION 0.13.2.
- **Verified:** 330 server tests (clean worktree of the release commit too); on the owner's server (read-only, over
  SSH): key 32 letters/digits verified 2026-10-12 15:23 UTC, account `VIP Member` / 1000 a day, sign-in 200 in the
  traffic log; the key and password themselves were never read (length/shape only).
- **Left open:** no subtitle downloaded with the VIP account yet (0 rows in `subtitle_downloads` when checked); the
  tester's own server still needs its key checked (Test) or pasted again.

### 2026-10-11: Keep for hand-identified files, OpenSubtitles key check (release 0.13.1)
- **What / why:** (1) Another session's finished work, documented here at release: "Keep" in the Unrecognized list
  now also works on files identified by hand. `PUT /api/files/{id}/keep` (admin) → `identify.keep`: a hand
  identification gets `kept: true`; an Auto fill guess is stored as a hand identification with `kept: true`; an
  unplaced or "Don't place" file → 409. `_unrecognized` leaves kept files out. Web `Identify.tsx`: Keep shown on
  guessed and hand-identified rows, calls `/keep`. (2) Owner: "subtitle api key has underscores and stuff but it
  wont accept it". The 0.10.0 format check (16–64 of `[A-Za-z0-9_-]`) was a guess; it now accepts 8–4096 printable
  characters without spaces and OpenSubtitles decides (`Client.check`). The owner's paste was actually a sign-in
  token (JWT, `exp` a day away, already expired): `opensubtitles._sign_in_token` refuses such a value in `save_key`
  with "That's an OpenSubtitles sign-in token (it expired …), not an API key" + the consumers link, without sending it.
- **Files:** `server/bams/identify.py` (`keep`), `app.py` (`/keep`, `_unrecognized`), `opensubtitles.py`
  (`valid_key_format`, `_sign_in_token`, `save_key`); tests `test_identify.py` (keep: hand-identified, guessed,
  nothing to keep 409, 404, viewer 403, rescan keeps it off the list), `test_opensubtitles.py` (long key with dots
  goes to OpenSubtitles; sign-in tokens, fresh and expired, refused without a request); web
  `components/Identify.tsx`; CHANGELOG, VERSION 0.13.1.
- **Verified:** 330 server tests in the main checkout and again in a clean worktree of the release commit; web
  `tsc` + build. The owner's key itself was never read or replayed: only the expiry visible in their screenshot was
  converted to a date.
- **Left open:** a kept file can't be un-kept from the web (it's off the list; only `DELETE
  /api/files/{id}/identify` forgets it). The real OpenSubtitles API key's format is still undocumented.

### 2026-10-11: Watch list across every server (release 0.13.0)
- **What / why:** owner: "implement a watchlist feature. ALL files I should be able to add… 'My Watch List' will be its
  default name… like a library in the library list under Home but above the first library… a universal watch list,
  where episodes from EVERY server can be added… stored server side so all clients sync it". Each server keeps its own
  items' entries per account (schema v12 `watchlist (user_id, item_id, added_at)`); web and TV merge every connected
  server's list into one, newest added first (decisions log). Movies, shows, seasons, episodes; music can't go on it.
  Every item list/page carries `watchlist` (in `watch.annotate`), so buttons show their state; merges move entries
  (`items._move_watchlist`). The name is the pref `watchlist_name`.
- **Files:** server `db.py` (v12), `watch.py` (`LISTABLE`, `add_to_list`, `remove_from_list`, `watch_list`,
  `annotate`), `items.py`, `auth.py` (pref), `app.py` (`GET /api/watchlist`, `PUT`/`DELETE /api/watchlist/{id}`,
  `PrefsIn`), `tests/test_watchlist.py` (9), `test_watch.py`/`test_auth.py` (prefs dict, v12). Shared
  `web/src/everywhere.ts` (`listedOrder`, `listedLook`, `WATCHLIST_PATH`, Home spec `watchlist`), `homeRows.ts`
  (`watchlist` row, `listName`). Web `pages/Watchlist.tsx`, `components/Cards.tsx` (`ListToggle`, `ListedCard`,
  `listedPage`, bookmark on `PosterCard`), `Sidebar.tsx`, `Home.tsx`, `Detail.tsx` (buttons, `&episode=` picked),
  `HomeSettings.tsx`, `Icon.tsx` (bookmark), `styles.css`. TV `screens/Watchlist.tsx`, `ListMenu.tsx`, `Rail.tsx`,
  `App.tsx`, `Cards.tsx` (`Poster` `look`/`onHold`), `screens/Home.tsx`, `screens/Detail.tsx`, `styles.css`.
- **Verified:** 9 new server tests (add/list/remove, video kinds only, flags on every list and page, per account,
  401, merges, deleted items, name pref, v12 migration); full suite 330; web + TV `tsc`; TV tests 37/37. Two scratch
  servers (:8503, :8504, copies of the dev DB) with this browser connected to both: entries seeded on :8504 and added
  on :8503 from a show page (show, season, episode bookmark) showed as one list of 6, newest first, posters through
  :8504's tickets; rename changed the page, sidebar and pref; :8504's episode entry opened its season with the episode
  picked out and in view; taking it off there removed it from Home's row; a poster's bookmark added Burn Notice without
  opening it. TV page (Vite, signed in to :8503): rail "Weekend picks" under Home, Home row, list screen (focus on the
  first poster), detail button "Remove from…", hold on an episode → menu → added, badge shown, focus back on it.
- **Left open:** see §5 "Watch list leftovers"; not tried on the real TV/Fire TV.

### 2026-10-11: Fire TV app (release 0.12.0)
- **What / why:** owner asked for a FireTV/Firestick app (a separate session built it; released by the session that
  cut 0.12.0, at the owner's request "include the firetv work"). An Android app for Fire OS 6+ that **is** the TV app:
  `tv/dist` bundled as APK assets in a full-screen WebView, ExoPlayer under the see-through page, the device's
  decoders from Android. See "Fire TV app" in §4 and `firetv/README.md` (build, install over adb, release key).
- **Files:** `firetv/` (Gradle project: `MainActivity.kt`, `Bridge.kt`, `Video.kt`, `Caps.kt`, `build.mjs`, `art.py`,
  icons/banner), `tv/src/firetv.ts`, `ExoEngine` in `tv/src/engine.ts`, Fire TV branches in `tv/src/plan.ts`
  (device caps + `convertHeight`), `tizen.ts`, `screens/Player.tsx` (fMP4 copy-HLS, pass-through, conversion height),
  `screens/Settings.tsx` (no DTS toggle, "player: ExoPlayer"), `tv/test/firetv.test.ts`, `tv/package.json`
  (`npm run firetv`); web `TvSettings.tsx` wording; README. Release signing key made at release time (decisions log).
- **Verified:** the building session installed debug builds on a Fire TV in the owner's home ("Haley's 2nd TV") and
  drove it with adb key presses: server found, linked, Home with Continue Watching and artwork, rail/rows navigation,
  Search with the Fire TV keyboard (typed "bob" → Bob's Burgers), Back closing only the keyboard. TV tests (37, incl.
  7 Fire TV ones with a fake bridge) pass. Release: signed `BAMS-FireTV-0.12.0.apk` built from the release worktree.
- **Left open:** video playback not tried on the Fire TV yet (ExoPlayer direct play, fMP4 copy-HLS, conversions,
  Dolby/DTS pass-through); the release APK doesn't install over the debug build on that Fire TV (uninstall first:
  it forgets its servers and sign-in); no Appstore build; Vega OS sticks unsupported.

### 2026-10-11: 1080p and 4K in the web player's Quality menu (release 0.12.0)
- **What / why:** owner: "For quality options, please add a 1080P and 4k option… H.264 1080p video files dont play and
  just sit there at a black screen at 00 seconds". The menu offered only sizes *below* the source (`h < height`), so
  a 1080p file had no 1080p and a 4K file no 4K. Now: sizes up to the file's own (16:9 box it fills, 5 % leeway:
  1920×800 and 1912×1072 are 1080p), 2160 shown as "4K", 4K/1440p only when `/api/status.video_encoder.hardware`
  (the CPU stops at 1080p, `stream._box`); "Full size" only when no listed size is the whole picture. A size picked in
  this player applies even at the file's own size (converted); one remembered from another video (`bams.quality`)
  only shrinks bigger files. Web only, no server change (the server already took heights up to 4320).
- **Black screen:** not a BAMS fault as far as could be found. Server log + traffic log (`/var/lib/bams/netflow`):
  the owner's Chrome 155 on the PC made one `/stream` request per MP4 and never a second (on 10-10, with 0.9.2, the
  same Chrome made three and played); nothing in how files are sent changed 0.9.2 → 0.11. The same file played
  through the owner's server (0.11.1 code run on a DB copy in `/tmp`, SSH tunnel) in the app's Chromium 152, direct
  and HEVC copy-HLS. The PC's GPU had 14.3 of 16 GB in use. Owner asked to restart Chrome / try Edge and, if it
  persists, send `chrome://media-internals`. Found on the way (spun off as a task): an abandoned `/stream` request
  still reads the whole file off the NAS (uvicorn's `send` ignores writes after a disconnect; `FileResponse` doesn't
  watch for it).
- **Files:** `web/src/pages/Player.tsx` (`qualityName`, `srcSize`/`maxSize`/`fullSize`, `picked`, `bigOk` from
  `/api/status`); CHANGELOG, VERSION 0.12.0.
- **Verified:** web `tsc` + build. Scratch server (:8502, own data dir, NVENC) in the app's browser: The Throne
  (1920×800) listed Original/Auto/1080p/720p/480p/360p, 1080p converted over HLS and played at 1920×800 from where it
  was; reload with "1080" remembered → Original. A generated 3840×2160 clip listed 4K/1440p/1080p…, 4K converted and
  played at 3840×2160; with the encoder set to x264 (CPU) 4K/1440p were gone and the remembered 2160 fell back to
  Original. Release worktree: 321 server tests, web + TV `tsc`, TV tests 37/37; the `.deb` installed in Docker
  `ubuntu:24.04` and served 0.12.0 with the new menu in its UI bundle; APK signed with the release key (`CN=BAMS`,
  versionCode 1200), `.wgt` signed with the Samsung profile. The Windows `.exe` was built, not installed.
- **Left open:** the owner's Chrome stall (waiting on them); the NAS read-after-disconnect fix (separate task).

### 2026-10-11: Server name over its own libraries, other servers' libraries in any order (release 0.11.1)
- **What / why:** owner: "Your server's Libraries are categorized under the word 'Libraries' instead of the server
  name… This should say your server name", then "allow me to drag and re-arrange the library order on other servers.
  Currently I can only do this on mine". Web only. The sidebar's "Libraries" heading is now the server's name
  (`GET /api/hello` → `name`, the Server name setting), cut with "…" when long (full name on hover); saving a new
  name in Settings fires `SERVER_RENAMED` (`bams:server-name`) and the sidebar reloads it. Another server's shown
  libraries get the same drag handle (and arrow keys) as this server's (`RemoteLibraries` in `Sidebar.tsx`, on
  `useReorder`); the order is stored per browser with that server's other choices (`Stored.order` in
  `bams.servers`, `setLibraryOrder`), `describe()` applies it (libraries not in it follow in the server's order),
  so Settings → Other BAMS servers lists them in that order too. Hidden libraries keep their place: the shown ones
  swap places among themselves. Signing in to the server again keeps the order. Anyone can do it (no admin rights
  there needed); the other server and its other users see nothing of it.
- **Files:** web `components/Sidebar.tsx`, `servers.tsx`, `api.ts` (`SERVER_RENAMED`),
  `components/ServerNameSettings.tsx`, `styles.css` (comment); CHANGELOG, VERSION 0.11.1. TV app unchanged (0.11.0).
- **Verified:** web `tsc` + build; 321 server tests in the release worktree. Scratch server (:8501, copy of the
  local DB, own admin account): heading read "Beached's BAM Server" (fits uncut at 1280 px); renaming it to "Living
  Room Test Server" in Settings changed the heading without a reload (one `/api/hello`), "Use the default" changed it
  back. Same server connected to itself as an "other server": a real mouse drag moved Music below Movies (no
  navigation), arrow keys on a handle moved a library, a hidden library kept its place while the others were
  reordered and came back there, Settings listed the same order, the order survived a reload, one shown library
  showed no handle, this server's own list didn't move.
- **Left open:** the TV app's rail still shows this server's libraries without a heading (other servers' have their
  names) and can't reorder; offered to the owner. Released alone while another session's Fire TV app and "Keep" for
  hand identifications stay uncommitted.

### 2026-10-11: Remove from Continue Watching (release 0.11.0)
- **What / why:** owner: "Long press on a video card in the Continue Watching category to remove it from continue
  watching. If the show is later watched, it will get added back in." Server: schema v11 `continue_hidden (user_id,
  item_id = movie or show, hidden_at)`; `watch.hide_continue` (movie → itself, episode/season → its show);
  `continue_watching` skips a title whose deciding activity is not newer than `hidden_at` (a hidden show still uses
  up its older rows, so an older episode doesn't take its place); `DELETE /api/continue/{id}`; `items.merge_titles`
  carries hidden rows over. Web: `ContinueCard` long press (500 ms held still, `useLongPress`) or right-click →
  `ContinueMenu` over the card (Remove / Cancel; Escape or a press elsewhere closes it; the click ending a long press
  is swallowed); Home drops the card once the item's own server confirms. TV: `tv/src/hold.ts`: OK on a `[data-hold]`
  element is decided there (key-up before 800 ms = press; held = a `contextmenu` event). The Fire TV app passes no
  key-ups, so there repeats decide (600 ms); key-downs that keep coming after a hold press nothing. `Wide` `onHold`;
  Home's `ContinueMenu` (data-trap, Back closes, focus to the next card after removing).
- **Files:** `server/bams/db.py` (v11), `watch.py`, `items.py`, `app.py`; `tests/test_watch.py`
  (`test_take_out_of_continue_watching`, merge case), `test_auth.py` (v11); web `components/Cards.tsx`,
  `pages/Home.tsx`, `styles.css`; TV `src/hold.ts` (new), `App.tsx` (OK + key-up), `Cards.tsx`, `screens/Home.tsx`,
  `styles.css`, `test/hold.test.ts` (new), `test/run.ts`; CHANGELOG, VERSION 0.11.0, TV 0.11.0.
- **Verified:** 321 server tests; TV `npm test` 37 (5 new: Samsung-style press/hold with key-ups, Fire TV-style
  press/hold from repeats only, repeats after a hold swallowed); web + TV `tsc`. Scratch server (:8499, copy of the
  local DB, own account): right-click and a held press opened the menu (not at 300 ms, yes at 700 ms), the click ending
  the hold didn't navigate, a swipe didn't open it, a tap still played, Escape / a press elsewhere closed it; Remove
  took Bob's Burgers out (card gone, `/api/continue` agreed); 5 s of it kept it out, 400 s brought it back; menu fits
  a 240 px phone card. TV app in a browser at 1920×1080 with synthetic remote keys: held OK (with repeats) opened
  the menu and the repeats didn't press Remove; Back closed it with the focus back on the card; Remove took the card
  out with the focus on the next one; a short OK still played.
- **Left open:** holding OK not tried on the owner's Frame or a Fire TV (Tizen's docs don't say whether a held key
  repeats; both cases are handled); on Fire TV a press on a Continue Watching card waits 600 ms because
  `MainActivity.kt` passes no key-ups (passing them would remove the wait). Released alone while another session's
  Fire TV app and "Keep" for hand identifications stay uncommitted.

### 2026-10-11: Test session 3: OpenSubtitles, sleep mode, Fix match folders, hyphenated titles (release 0.10.0)
- **What / why:** tester requests and one bug. (1) Fix match shows "the path to the show/folder": `GET
  /api/items/{id}/folders` (admin) lists a show's folders as the parser picks them (`parse.title_folder` →
  `_show_dir_at`) with file counts, or a movie's files; `FixMatch.tsx` shows them above the search. (2) "Subtitle
  support: OpenSubtitles… an area to add that API… Check OpenSubtitles… select one… test another": new
  `opensubtitles.py` (client: Api-Key + `USER_AGENT`, 4 req/s throttle, optional account login with the 24 h token in
  memory and refused credentials not retried, a once-only re-login when a token stops working; search by TMDB/IMDb
  id + season/episode + moviehash, else by name; download → data dir; tracks `d<n>`), schema v10
  `subtitle_downloads`, routes for the key, the account, search, download and removal; web `OpenSubtitlesSettings.tsx`
  (Settings → Playback: key like TMDB's, optional account), `FindSubtitles.tsx` (player dialog: language, results with
  "made for this file", already-downloaded ones to switch to or remove); TV `FindSubs` in `screens/Player.tsx`
  (results + language list on the remote). First built with a single BAMS key (OpenSubtitles' rule), then changed at
  the owner's request to a key per server (decisions log). (3) Sleep mode: "an icon… a silhouette of a bed with stars
  above it… finish the current episode, play 2 more, and then stop… a movie… finish… and then stop": web button next
  to volume (new `sleep` icon: bed strokes + filled stars, `Icon.tsx` FILLS), TV "Sleep" pill; the count rides in the
  navigation state to the next episode; at the end "Sleep mode stopped playback here". (4) Bug "In Linux… a dash…
  Catch-22 is identified as Catch": not Linux-only; guessit splits at hyphens (folder "Catch-22" = "Catch" + episode
  22; "Ant-Man.2015" = group "Ant" + "Man"; "She-Ra and…" = "She" + a ".ra" file). `parse._read` re-reads a name
  with the cut word's hyphens protected (U+2010, swapped back); `PARSER_VERSION` 9.
- **Files:** `server/bams/opensubtitles.py` (new), `app.py` (routes, `os_client`, `item_folders`, downloaded tracks in
  `get_item` and the `.vtt` route, `opensubtitles` flag on items), `db.py` (v10), `parse.py` (`_read`, `_protect`,
  `_labels`, `_show_dir_at`, `title_folder`, movie folder wins when the file's name lost its front, v9),
  `subtitles.py` (`webvtt(src=)`); tests `test_opensubtitles.py` (new, fake OpenSubtitles), `test_parse.py` (+13
  hyphen cases, `test_title_folder`), `test_api.py` (Fix match folders), `test_auth.py` (v10); web `api.ts`,
  `subtitleLangs.ts` (new, shared with the TV), `components/FindSubtitles.tsx`, `OpenSubtitlesSettings.tsx` (new),
  `FixMatch.tsx`, `Icon.tsx`, `pages/Player.tsx`, `Settings.tsx`, `styles.css`; TV `App.tsx` (route `sleep`),
  `Icon.tsx`, `api.ts`, `prefs.ts` (`osLang`), `screens/Player.tsx`, `styles.css`; CHANGELOG, VERSION 0.10.0, TV 0.10.0.
- **Verified:** 320 server tests (OpenSubtitles against a fake: search parameters sorted/lowercase with the file's
  real hash, key refused/kept/never returned, account refused then kept, token reuse and re-login, quota 429,
  download stored in the data dir with the media untouched, re-picks not downloaded again, removal rights); TV `npm
  test` 32 pass; web + TV `tsc` and builds. Parser dry run over the owner's 4,391 video paths (read-only export from
  the Ubuntu server): no result changed. Scratch server (:8498, DB copy + generated "Catch-22" clips + the fake
  OpenSubtitles): the show read as "Catch-22"; Fix match listed the folders; Settings refused a wrong key and a wrong
  account, kept the right ones; the player's dialog downloaded a pick, the subtitle showed and stayed after a reload;
  sleep mode played E01 → E02 → E03 and stopped; TV app in a browser at 1920×1080 with the remote keys: Subtitles →
  Check OpenSubtitles → language list (Back returns) → pick → line drawn; Sleep on the last episode showed the stop
  message; E02 → E03 → E04 then stopped. The real OpenSubtitles API was only probed with a made-up key (403 "You
  cannot consume this service" on searches, `/infos/formats` open to any key).
- **Left open:** not tried with a real OpenSubtitles key/account; the TV app isn't installed on the owner's Frame;
  released alone while another session's Fire TV app and "hide from Continue Watching" (schema v11) were still
  uncommitted (owner's choice).

### 2026-10-10: Converted playback on Ubuntu fixed (FFmpeg 6.1 init file, VAAPI constant QP), downloads removed (release 0.9.2)
- **What / why:** owner: Family Guy episodes (HEVC + AC3 MP4) didn't play on their new Ubuntu 24.04 server: a long
  wait, then "The converted stream stopped". The server log (read over SSH) had two failures, each retried by the
  player: (1) copy-HLS: FFmpeg 6.1 joins the playlist's folder to `-hls_fmp4_init_filename` even when it's absolute
  (strace: `…/0//var/lib/bams/…/0/init_0.mp4`, ENOENT), while FFmpeg 9 on Windows takes it as given and puts a bare
  name in the working dir. Now the name is bare and `hls.Transcodes._restart` starts FFmpeg with `cwd=` the variant's
  folder (`stream.spawn(cwd=)`): right under both. (2) Full conversion: `h264_vaapi` on the HD 630 with Ubuntu's
  free iHD driver supports only CQP ("Driver does not support any RC mode… supported modes: CQP"); the startup test
  encoded without a bitrate, so it passed. `_encoder_works` now tests every encoder with `_encoder_args` (its real
  options); VAAPI retries with `-rc_mode CQP -qp 23` and remembers it per FFmpeg (`_vaapi_cqp`); a forced
  `BAMS_VIDEO_ENCODER` is tested too, to learn that. Also, owner request: "remove the ability to download the files
  from the server completely": `/api/files/{id}/download` and `download_url` (files, music tracks) gone, `/stream` sends
  no file name, Download buttons gone (Detail, player bar, player error), "You can download it" dropped from player
  messages, right-click on the video blocked, Accounts text no longer says viewers can download.
- **Files:** `server/bams/stream.py` (`_encoder_works`, `_encoder_args(cqp=)`, `_vaapi_cqp`, `VAAPI_QP`, `hls_copy_cmd`,
  `spawn(cwd=)`, `video_encoder` forced path), `hls.py` (`_restart`), `app.py` (download route, `download_url`, `/stream`);
  tests `test_stream.py` (VAAPI fallback test, bare init name, copy-HLS playlist check tolerant of FFmpeg 6.1's -6 ms
  MKV start), `test_hls.py` (runs start in the variant's folder), `test_api.py` (no download); `web/src/api.ts`,
  `pages/Detail.tsx`, `pages/Player.tsx`, `components/AccountSettings.tsx`; CHANGELOG, VERSION 0.9.2.
- **Verified:** 300 server tests on Windows (FFmpeg 9.0.2). Docker `ubuntu:24.04` (FFmpeg 6.1.1): the old code gives the
  server's exact error (`Failed to open segment …/init_3.mp4`, 500), the new one passes the real copy-HLS test (one
  unrelated Linux-only failure, see Left open). On the owner's server with the patched code and its own Python/FFmpeg:
  copy-HLS of Family Guy S01E01 made `init_0.mp4` + 29 segments in 6 s (HEVC + AAC); raw FFmpeg on the HD 630:
  bitrate options fail, CQP works; patched detection picks VAAPI in CQP mode and converts S01E01 at ~14× real time
  all-GPU, ~11× hybrid (H.264 720×552 + AAC). Test server :8497 (preview browser): H.264+AC3 film and HEVC+AC3 episode
  play over copy-HLS, no Download anywhere, no stray `init_*.mp4` in the server's working dir, right-click blocked.
- **Left open:** `test_encoder_choice_api` fails on Linux (it fakes `sys.platform = "win32"`, which breaks
  `shutil.which`); copy-HLS sessions read every keyframe first (~8 s per episode on the NAS, cached); with CQP the
  quality menu lowers the size but there's no bitrate cap; `intel-media-va-driver-non-free` would give the HD 630
  bitrate modes (not tried).

### 2026-10-10: Best guess button, a show's films go to its Specials (release 0.9.1, parser v8)
- **What / why:** owner, after 0.9.0 on the real library: no way to run the guess on one file by hand; "feature length
  movies or specials of a tv show" in the TV folder should be Season 00 specials of that show. Their case:
  `Daria Complete Series/Daria Is It College Yet 2002 DVDRip XviD AC3 JUGGALOTUS/…avi` was unrecognised because
  `_show_dir` took the film's own folder (it has a year) as the show, and the 0.9.0 guard refused films named like
  their folder. Now `parse.guess`: a file that reads as a film (title + year, no number) goes to Specials of the show
  named by the nearest folder that **isn't the film's own** (`_names_film`); with no such folder (Happy Gilmore 2 at the
  top) it's still left alone. `_decollect` drops "Complete Series/Collection", "Box Set", "All Seasons" from guessed
  show names so they join the existing show ("Daria"). `_tidy`: leading tag groups ("(En_Jp)") dropped, " _ " read as
  " - " in guessed episode titles. `guess(force=True)` also guesses what auto fill leaves alone (a movie in its own
  folder → Specials of a show named after it; a loose top-level file → its own show, an extra) and returns the rules'
  result for files they place: `GET /api/files/{id}/guess` (admin, fills the form, saves nothing; 422 when there's
  no name at all). Web: "Best guess" button next to "Fill in" in the identify form.
- **Files:** `server/bams/parse.py` (`guess`, `_folder_show`, `_names_film`, `_decollect`, `_tidy`, v8), `app.py`
  (`/api/files/{id}/guess`), tests `test_parse.py` (+4 guess cases, `test_forced_guess`), `test_identify.py` (guess
  route, 404, viewer 403); `web/src/components/Identify.tsx` (`bestGuess`); CHANGELOG, VERSION 0.9.1.
- **Verified:** 298 server tests; `web` tsc + build. Test server :8496: the Daria film joined an existing "Daria" show as
  a Season 0 extra next to Season 1; Best guess on the Happy Gilmore file filled Show/Season 0/title in the form.
- **Left open:** guessed episode titles of long YouTube-style names are still long (the real name can't be told apart
  from series words); unnumbered Specials don't get TMDB episode data.

### 2026-10-10: Auto fill: unrecognised files placed by a best guess (release 0.9.0, parser v7)
- **What / why:** owner: "an Auto fill parser… when a file cannot be identified… a best guess based on the file name and
  directories". Asked how far to go, the owner chose **placing automatically** (marked "guessed", reviewable) over a
  pre-filled form. `parse.guess(rel, type)` runs only when `parse.parse` can't place a file. TV: the show from the
  folders (`_show_dir`, else the nearest non-season folder), season from Season/Volume/Level/Book/Part/Disc folders else 1,
  an episode number from `_LOOSE_EP_RE` (Part/Lesson/Ep/Chapter/Day/#…), a leading "01 - " or a trailing " - 05", else an
  unnumbered extra named after the file (release tags, "-GRP" and a bare "S01" stripped). A file that reads as a film
  (title + year) in its show's folder → Specials, but a film whose folder is its own name ("Happy Gilmore 2/…2025…") is
  left unrecognised with the movie hint, as is a loose top-level file with no number. Movies: the nearest folder with a
  name ("CD1", "1080p" skipped), else the bare file name. `Parsed.guessed` is stored in `files.parse`.
  `identify.from_name` = rules, then guess when `autofill` is on; used by the scanner (`parsed_for`) and `store`. "Don't
  place" = `files.manual {skip: true}` (`PUT /api/files/{id}/skip`, undone by `DELETE …/identify`); "Keep" saves the guess
  as a hand identification. `PUT /api/settings/autofill` re-places every unplaced/guessed file at once
  (`identify.replace_unplaced`) and, when turned on, queues a scan of each TV/Movies library for TMDB matching.
  `library.describe` → `files.guessed`; skipped files no longer count as unrecognised. Web: Auto fill card, guessed rows
  (dashed border, "Placed by a best guess: …", Keep / Change / Don't place), "N placed by a best guess: review them" on
  the library card, the library's Unrecognized tab counts guesses too. `PARSER_VERSION` 7 so existing unrecognised files
  are guessed on the next scan.
- **Files:** `server/bams/parse.py` (`guess`, `_loose_number`, `_bare`, `_words`, `_strip_show`, regexes, v7),
  `identify.py` (`autofill_enabled`, `from_name`, `replace_unplaced`, skip), `app.py` (`/api/settings/autofill`,
  `/api/files/{id}/skip`, `guessed` in `/unrecognized`, `autofill` in `/api/settings`), `library.py`; tests
  `test_parse.py` (+15 guess cases), `test_identify.py` (auto fill flow; the hand-identify fixture turns it off),
  `test_scanner.py`; web `components/Identify.tsx` (`AutofillSettings`, `fromGuess`, row actions), `pages/Settings.tsx`,
  `pages/Library.tsx`, `api.ts`, `styles.css`; CHANGELOG, VERSION 0.9.0.
- **Verified:** 291 server tests pass (this box has NVENC and the two encoder tests passed too); `web` and `tv` tsc.
  Test server on :8496 with dummy media: 4 of 6 problem files placed by guess (Korean Lessons extras in seasons 1/2,
  Random Show S01E03 "The End", Simpsons Movie in Specials), Happy Gilmore 2 and a loose file left with their hints;
  Keep turned a guess into a hand identification, Don't place took one out and showed "Left out", counts updated.
- **Left open:** not run against a copy of the owner's library (the service's `C:\ProgramData\BAMS` isn't readable from
  this session): check the Unrecognized list after the update. A guessed show is matched on TMDB like any other title,
  so a made-up folder name can pick up a wrong poster (Fix match / Don't place). Guesses aren't marked on title pages.

### 2026-10-10: Must change password at next sign-in, two-step sign-in (release 0.8.0)
- **What / why:** owner: a "Must Change Password on next login" checkbox per account "to allow a user to set their own
  password", and "2fa so they can use Google Authenticator". Schema v9 (`users.must_change_password`, `totp_secret`,
  `totp_last`). Flagged sessions get 403 except `MUST_CHANGE_API` (`LoginRequired`); the web shows `NewPassword` in
  `auth.tsx`. TOTP in `auth.py` (stdlib); `_sign_in` asks for the code after a right password (`CodeNeeded` → 401
  `code_required`), wrong codes go through `sec.failed`. Routes `/api/auth/2fa/setup`, `/api/auth/2fa`,
  `/api/auth/2fa/off`, admin `DELETE /api/users/{id}/2fa`; `auth_log` event `2fa`. Web: code box on sign-in and on
  "Connect to a server", `TwoFactor` card (QR via `qrcode-generator`, loaded on demand), admin checkboxes. TV: code box
  on name+password sign-in.
- **Files:** `server/bams/auth.py`, `app.py`, `db.py` (v9), `__main__.py`, `security.py` (comment),
  `tests/test_auth.py`; `web/src/auth.tsx`, `api.ts`, `servers.tsx`, `components/AccountSettings.tsx`,
  `RemoteSettings.tsx`, `SecuritySettings.tsx`, `styles.css`, `package.json` (`qrcode-generator`, MIT); `tv/src/api.ts`,
  `screens/Link.tsx`; CHANGELOG, VERSION 0.8.0.
- **Verified:** 274 server tests (new: RFC 6238 vectors, must-change flow incl. token refusal and admin reset, two-step
  sign-in incl. wrong code wait, reuse, token sign-in, admin/self turn-off); TV `npm test` 25 pass. Browser on a DB copy
  (:8495, v8 → v9 migration): flagged viewer got the new-password screen, then the app; two-step set up from the
  QR/key, sign-in asked for the code, a wrong code was refused with a wait, the right one signed in; admin list showed
  the checkbox and "Two-step", ticking/turning off worked; sign-in log showed "Two-step" and "wrong two-step code".
- **Left open:** not tried with a real phone (codes computed from the key) nor on the TV; no recovery codes; TOTP
  secrets are stored unencrypted in `bams.db`.

### 2026-10-10: TV remote navigation fixes, play bar timing, TV tests (release 0.7.1)
- **What / why:** owner: "Navigation on the tv app is poor. Sometimes I cannot move the focus from nav to the main
  screen, or up or down. Run a full unit test around navigation, identify bugs and resolve"; "reduce the time it takes
  for the play bar to disappear to 5 seconds". New browser tests showed 13 of 23 cases failing. Fixed in `nav.ts`:
  Right from the rail only went to things level with it (Home beside the banner, Settings beside a short page: stuck),
  now returns to the last element focused outside the rail (`focusin` listener), else the nearest on the page; Home
  focused nothing (shelves load after `ready`), so the first arrow went to the rail: `settleFocus` retries until the
  content is there (and the remembered `fid`), without taking the focus back from the user; Up/Down entered and left
  the rail, now only Left enters it (`[data-side]`) and Up/Down stay in it; a lost focus restarted in the rail, now on
  the page; long rail scrolls (`data-scroll`); music bar (`[data-cover]`): Left/Right stay in it, `reveal` keeps things
  above it; the rail lights the stack's root (`nav.root`) so Left from a title lands on its library. Player: the
  controls' hide was a one-off check at 5 s and stayed up for good if the stream was still starting/restarting then;
  now it looks again every second, and menu keys count as activity (`OSD_HIDE` was already 5000 ms).
- **Files:** `tv/src/nav.ts`, `App.tsx` (`useFocusOnReady` → `settleFocus`, `Nav.root`), `Rail.tsx`,
  `screens/Music.tsx` (`data-cover`), `screens/Player.tsx`; new `tv/test/` (`nav.test.ts`, `harness.ts`, `run.ts`,
  `index.html`), `tv/scripts/test.mjs` (`npm test`), `tsconfig.json` includes `test`; CHANGELOG, VERSION 0.7.1.
- **Verified:** `cd tv && npm test`: 25 pass (13 failed before the fix). TV app in a browser at 1920×1080 against a
  DB copy (:8495): Home focused a shelf on arrival, rail Left/Down/Right returned to the same poster, page scrolled,
  Library → title → Left landed on that library, Right back on Play; controls hid at 5 s after the start. 271 server
  tests pass. Installed on the owner's Frame.
- **Left open:** the TV tests cover `nav.ts` with fixture markup (not the React screens themselves); the player's key
  handling has no automated test.

### 2026-10-10: Several BAMS servers per client, server names, combined Home/Search, music on the TV (release 0.7.0)
- **What / why:** owner: "I should be able to connect to and have more than 1 BAMS server", then "the webapp and tv
  app should just be clients… 6 servers on the TV app, 3 on another, 4 on the desktop", "Home and search should show
  a combined ALL servers content", "TV and Web app should have a uniform view", "music libraries don't show up on tv
  app", "allow me to name my server". Web: Connect to a server (next to Add library), other servers' libraries in the
  sidebar (rename/hide per browser), `/r/<rid>/…` pages; TV: Settings → Other BAMS servers (Connect/Link screens reused
  with `adding`/`target`), the rail grouped by server; both: Home + Search across every server from the shared
  `web/src/everywhere.ts`; TV music (library tabs, artist/album/playlist, `music.tsx` player, NowPlaying bar, media
  keys, video pauses music); server name. A first design (connections stored per account on the server, a proxy
  `/api/remote/<id>/…`) was built, then replaced before release at the owner's request (clients only).
- **Files:** server `app.py` (LoginRequired: ticket paths take cookie/bearer for non-GET; `server_name`,
  `PUT /api/settings/server-name`, `/api/hello` name, `/api/continue` `last_watched_at`), `watch.py`
  (`continue_watching` returns when); web `servers.tsx`, `everywhere.ts`, `useApi.ts`, `components/RemoteSettings.tsx`,
  `ServerNameSettings.tsx`, `Sidebar.tsx`, `Cards.tsx`, `pages/Home.tsx`, `Search.tsx`, `Player.tsx`, `Detail.tsx`,
  `Library.tsx`, `Music.tsx`, `Settings.tsx`, `App.tsx`, `music.tsx`; TV `api.ts`, `App.tsx`, `Rail.tsx`, `Cards.tsx`,
  `music.tsx`, `screens/Music.tsx`, `Home.tsx`, `Search.tsx`, `Library.tsx`, `Detail.tsx`, `Player.tsx`,
  `Settings.tsx`, `Connect.tsx`, `Link.tsx`; tests `test_devices.py` (ticket non-GET, `test_server_name`),
  `test_watch.py` (`last_watched_at`); CHANGELOG, `config.VERSION` 0.7.0.
- **Verified:** 271 tests pass. Two scratch servers (:8495 copy of the dev DB, :8496 fresh): web connected to the
  other (CORS + bearer + tickets), browsed, played EAC3 copy-HLS with a seek to 40 min, progress and session close
  (204) on that server, music; the TV app in a browser added the server with a link code, played copy-HLS in TS with
  subtitles, hid a library; web and TV Home showed the same 14 rows with the same counts; Search found a title on
  both servers; TV music played album tracks from the other server, Next, video paused it. Installed on the owner's
  Frame (`npm run package -- --install --run`).
- **Left open:** library rows on Home only for the first server's libraries; a title on two servers shows twice;
  Continue Watching from servers before 0.7.0 is interleaved (no `last_watched_at`); TV music: no queue view, no
  gapless; renaming other servers' libraries on the TV.

### 2026-10-09: Every genre on Home, each one its own row in Settings (release 0.6.2)
- **What / why:** owner saw genres in the library filters that Home didn't show. Home only counted the 500 newest
  titles, needed 2+ titles and kept the top 4. New `GET /api/genres` (every show/movie genre, most titles first);
  Home and Settings → Home page show one row per genre (`genre:<name>` ids), so each can be hidden and moved. A saved
  layout's old single `genres` entry expands in place into the genres it doesn't place itself, keeping its on/off.
- **Files:** `server/bams/app.py` (`all_genres`), `auth.py` (pref comment), `tests/test_watch.py`
  (`test_home_lists_every_genre`); web `homeRows.ts` (`defaultRows(libs, genres)`, `rowGenre`, old-save expansion),
  `pages/Home.tsx`, `components/HomeSettings.tsx`, `api.ts` (`Genre`); CHANGELOG, `config.VERSION` 0.6.2.
- **Verified:** 269 tests pass; `homeRows` merge checked with tsx (default, old `genres` save, new genre lands after its
  neighbour). Test server on a DB copy: an old-style save showed all 8 genres where "Genres" was; unticking Drama and
  moving Science Fiction saved `genre:Drama` off and the new order, and Home rendered exactly that.
- **Left open:** none.

### 2026-10-09: TV app shows the web's Home (rows, genres) and the account it uses (release 0.6.3)
- **What / why:** owner: the TV should have the same history, genres and settings as the web, all server-side, and one
  account should be able to watch on the web and the TV at once. History already was per account on the server; the
  owner's TV was linked as **Alex** (approved from a browser signed in as Alex), so it showed Alex's history. The TV's
  Home now builds its rows with the web's `homeRows.ts` (imported, not copied) from the user's server-side
  `home_rows`/`home_hero` prefs and the same endpoints (`/api/genres`, `sort=random&min_rating=7`, `sort=recent`);
  music rows skipped. TV library pages got the genre filter; TV Settings explains the account and offers Switch account.
- **Files:** `tv/src/screens/Home.tsx`, `Library.tsx`, `Settings.tsx`, `tv/src/styles.css`,
  `server/tests/test_watch.py` (`test_one_account_on_two_devices_at_once`), CHANGELOG, `config.VERSION` 0.6.3.
- **Verified:** 270 tests pass (new: web cookie + TV bearer of one account report progress on two titles interleaved;
  both see both in Continue Watching; watched on the TV shows on the web). On the TV (inspector): Home rows = Continue
  Watching, Recently Added, Science Fiction, Comedy, Animation, Drama, Action & Adventure, exactly Alex's saved layout
  (library rows and Top Rated switched off there).
- **Left open:** the same title on two devices at once: the latest report wins. Per-TV playback settings (always
  convert, DTS, subtitle timing, languages) stay on the TV on purpose, like the web's per-browser ones.

### 2026-10-09: Samsung TV app (The Frame), link codes, tickets, TS copy-HLS (release 0.6.1)
- **What / why:** owner asked for a Samsung TV app driven by the remote. `tv/` (Tizen web app, AVPlay) + server support
  (`devices.py`: link codes, bearer tokens, media tickets; CORS; `/api/hello`) + web Settings → Your TVs and `/link`.
  Brought up on the owner's QN50LS03BAFXZA (Tizen 6.5) over sdb with the remote inspector: the TV can't seek in a
  progressive file and rejects fMP4 HLS, so TV playback goes through copy-HLS in MPEG-TS (`hls_copy_cmd(ts=True)`).
  Fixed on the TV: video hidden behind the page (`html` background), grey dot (full-size `<object>`), focus scrolling,
  no server found (`webapis.network.getIp` refused). Continue Watching now skips opened-not-watched episodes. Released
  as its own asset `BAMS-SamsungTV-<v>.wgt`; README has install steps for The Frame.
- **Files:** `tv/` (all), `server/bams/devices.py`, `app.py` (LoginRequired: bearer + ticket paths; CORS; device
  routes; `HlsIn.ts`), `auth.py` (`digest`, `session_user_by_digest`), `hls.py`/`stream.py` (TS copy variant),
  `watch.py`, `tests/test_devices.py`, tests in `test_hls.py`/`test_stream.py`/`test_watch.py`,
  `web/src/components/TvSettings.tsx`, `web/src/pages/LinkTv.tsx`, README, CHANGELOG, `config.VERSION` 0.6.1.
- **Verified:** 268 tests pass. Browser run of the TV app at 1920×1080 against a DB copy (link, navigation, direct /
  copy / converted playback, subtitles, up-next). On the TV (via `tveval.mjs`-style inspector scripts): AVPlay seeks
  fail on progressive MKV/MP4 from BAMS and from a plain test server (no second Range request), fMP4 copy-HLS
  `NOT_SUPPORTED_FILE`, TS copy-HLS plays AC3 5.1 and seeks (10:00, +30 s); after 0.6.1 + TV 0.1.5 resume from
  Continue Watching and ±skip on the real app. Owner confirmed picture, dot gone, sign-in, playback.
- **Left open:** see §5 4b. Subtitle timing default 0 (owner adjusts per TV). Release 0.6.1 also carries another
  session's uncommitted-at-the-time work (in-app updates `updates.py` + Settings → About, Home rows, web player
  subtitle timing / autoplay), bundled at the owner's request; that session documents its own part.

### 2026-10-08: Tester session 2: Continue Watching links, next episode, credits countdown, 30 s skip (release 0.5.3)
- **What / why:** tester requests. Continue Watching card: picture plays, show name opens the show, episode line opens
  its season (`/title/<show>?season=<season id>`; `/api/continue` adds `season_id`, Detail picks the tab from it).
  Player: a next-episode button (keeps the place, not counted watched); the up-next countdown also starts 30 s before
  the end (`CREDITS`; not on videos under 2 min), pauses with playback, Cancel hides it for that viewing, and leaving
  from it counts the episode as finished (`finished` ref → the leave report sends the duration); skip forward 30 s,
  back 10 s (buttons labelled, arrow keys the same). Bug "Firefox: spot saved but starts over": the copy-HLS → live
  remux fallback restarting from 0, already fixed in 0.5.2; confirmed with headless Firefox 157 through an injecting
  proxy (normal HLS resumes; a forced HLS failure resumes the live remux at the saved 10:00).
- **Files:** `web/src/components/Cards.tsx`, `web/src/pages/Detail.tsx`, `web/src/pages/Player.tsx`, `web/src/api.ts`,
  `web/src/styles.css`, `server/bams/app.py` (`/api/continue`), `tests/test_watch.py`, `CHANGELOG.md` 0.5.3,
  `config.VERSION` 0.5.3.
- **Verified:** 245 tests pass. Test instance with the owner's Bob's Burgers S03+S04 (read-only): card links
  (`/play/12`, `/title/4`, `/title/4?season=5` → Season 4 tab, not the default Season 3); skip +30.4 / −9.5 s; the
  panel appears with 28 s left, holds at 9 while paused, the countdown → `/play/13` with 12 watched; Cancel keeps it
  hidden; the next button at 3:22 → 14 kept at 3:22, unwatched. Screenshot of the controls at phone width.
- **Left open:** arrow keys changed to 30/10 with the buttons (owner may prefer 10/10). Real credit lengths per show
  aren't known: `CREDITS` is a fixed 30 s.

### 2026-10-08: AC3 → AAC playback: picture behind the sound after a skip, resume lost (release 0.5.2)
- **What / why:** owner (laptop, Firefox, a scan running): after fast-forwarding an AC3 episode the picture ran behind
  the sound (a 10 s pause fixed it), and after closing, the spot showed as saved but playback started over; unprobed
  episodes stayed "unwatched". Three causes. (1) The **live remux** (`/remux?t=`, the fallback when the copy-HLS
  isn't used) copied video from the keyframe before `t` but FFmpeg's accurate seek trimmed the converted audio to `t`,
  and both began at 0: picture behind by `t` − keyframe (measured 0.3–4 s on Bob's Burgers S03E09/S04E08 by
  cross-correlating the output audio with the original). `remux_cmd` now passes `-noaccurate_seek` (error < 0.05 s).
  Copy-HLS was already right (kept timestamps). (2) When copy-HLS failed before playback began, `toLive` carried on
  from `posRef` = 0, not the resume point: `pos` now falls back to `startAt` until something played. (3) A file the
  scan hadn't probed yet had no duration: no HLS, a `0:00` timeline, and `report()` skipped every save.
  `get_item` now probes a movie's/episode's unprobed files on the spot (`app._probe_now`, probe first, then one
  short write), and the player saves the position without a duration too. Also: `bams scan` crashed on the
  5-argument progress callback (`__main__`).
- **Files:** `server/bams/stream.py` (`remux_cmd`), `server/bams/app.py` (`_probe_now`, `get_item`),
  `server/bams/__main__.py`, `web/src/pages/Player.tsx` (`pos`, `report`, `onEnded`), `tests/test_stream.py`
  (+2: live remux audio matches the original at the keyframe, by correlation; unprobed file probed when opened),
  `CHANGELOG.md` 0.5.2, `config.VERSION` 0.5.2.
- **Verified:** 245 tests pass on Windows (with 0.5.1); the new sync test fails with the old command. Test instance (:8491, own
  data dir) with the owner's real episodes (read-only): copy-HLS skips/jumps stay within 0.03 s (rVFC frame time vs
  clock), the HLS POST forced to fail on a resumed episode → live remux from the saved 19:06, an episode with its probe
  cleared → probed on open, HLS, 21:22, position saved.
- **Left open:** why copy-HLS falls back in the owner's Firefox (couldn't drive Firefox here; asked the owner to check
  which requests it makes). The rVFC check showed a ~1.9 s picture lag for a few seconds right after switching to 2x
  in Chromium, then caught up (browser behaviour, not addressed).

### 2026-10-08: Unmatched titles retried after a re-parse or a matcher change (0.5.1)
- **What / why:** after 0.5.0's scan on the owner's server, South Park, Parks and Recreation, Andor and the Animated
  Series were still `unmatched`: `match_library` only tries `pending` titles unless `retry_unmatched` (API
  `?rematch=true`, or setting the TMDB key), and nothing in the UI asks for it. `jobs.should_rematch`: retry when
  asked, when the scan re-parsed files, or when `matcher.MATCHER_VERSION` differs from the per-library setting
  `matcher_version:<lib>` (written by `note_matched` after a match).
- **Files:** `server/bams/jobs.py` (`should_rematch`, `note_matched`, `run_scan`), `matcher.py` (`MATCHER_VERSION`),
  `tests/test_matcher.py` (+1), `CHANGELOG.md` 0.5.1, `config.VERSION` 0.5.1.
- **Verified:** 241 tests pass; the owner's server after the 0.5.1 scan (see the next entry's numbers for the rest).
- **Left open:** no "retry unmatched" button in the UI; bump `MATCHER_VERSION` when matching rules change.

### 2026-10-08: Nested packs, extras with a season in their name, exact titles vs wrong years (parser v6)
- **What / why:** owner: 195 files in the TV library were "unrecognized" though "they use default naming". 139 were
  DVD extras in a nested Star Trek pack (`Star.Trek.Megapack.TheZerg/Star.Trek.DS9/S03/…Extras…/…S03.Extra10.avi`):
  the season in the file name stopped the "unnumbered extra" rule, and worse, the pack folder was taken as the show,
  so 688 episodes of five series sat in one unmatched "Star Trek Megapack TheZerg". `parse._show_dir`: the show is the
  folder right above the (deepest) season folder, else the deepest season-pack folder (a one-word inner name like
  "Parks S07" is expanded by the enclosing pack); extras under a season folder are unnumbered episodes of that season
  whatever the file name says; `_title` drops a "Series N" alternative title and spells out DS9/TNG/TOS/VOY/ENT;
  `_folder_year` ignores a year that follows a season marker ("Series 5 (2019)"); `_loose_title` prefers guessit's
  alternative title ("Extra10"). Matcher: `choose()` accepts a near-exact title (`EXACT` 0.95) when the year is
  wrong (South Park, Parks and Recreation were at 0.75), and `score()` accepts TMDB's first result when its name is
  the tail of ours ("Star Wars Andor"). The other 54 were Korean lesson videos with no numbering (expected), one
  Simpsons file named after its pack (hand-identify as E01) and a TV movie in the show folder (by design).
- **Files:** `server/bams/parse.py` (v6: `_show_dir`, `_folder_year`, `_STAR_TREK*`, `_title`, `_loose_title`),
  `server/bams/matcher.py` (`EXACT`, `choose`, `score`), `tests/test_parse.py` (+14 cases from the owner's paths),
  `tests/test_matcher.py` (+2), `tests/test_scanner.py` (nested pack scan + v5→v6 re-parse leaves nothing behind),
  `CHANGELOG.md` 0.5.0, `config.VERSION` 0.5.0.
- **Verified:** 240 tests pass on Linux (Python 3.13; the two `test_stream` encoder tests fail on this machine because
  it has NVENC, unrelated). Dry run of the new parser over all 4,370 files of the owner's TV library from a DB
  **copy**: unrecognized 195 → 56 (54 Korean + the two above), the fake pack show gone, DS9/TNG/TOS/Voyager/Enterprise
  separate, Sewing Bee one show, no new oddities. Not yet run against the owner's live server (needs the release).
- **Left open:** "Star Trel Emterprise" is a typo in the owner's folder name (rename or hand-identify). Files with a
  year in the name still create a second "(year)" title until TMDB matching merges them (pre-existing). The release
  was cut from Linux with the `.deb` only; `BAMS-Setup-0.5.0.exe` was then built on the Windows desktop (242 tests
  pass there) and attached to the v0.5.0 release with an updated `SHA256SUMS.txt`.

### 2026-10-08: Playback leftovers (DV profile 5, all-GPU on QSV/AMF/VAAPI, VobSub sidecars, Dolby pass-through)
- **What / why:** the four "Playback leftovers" in §5, owner asked for all of them, with a free, licence-checked test
  file. **DV profile 5:** downloaded Jellyfin's CC BY-SA 4.0 clip (checksum matched); no code change needed, BAMS's
  libplacebo conversion matches the SDR version of the same clip. **All-GPU** chains for Quick Sync / VAAPI / AMF,
  probe now records `sar`/`field_order` (`probe.geometry`, `video_geometry` for older probes), failed GPU runs
  remembered (`stream.gpu_failed`), `stream.output_size` (SAR-aware, also used for the HLS master playlist).
  **VobSub** `.idx/.sub` sidecars as picture tracks (`subtitles.vobsub_streams`, `burn_source`), `burn` accepts a
  track id. **Dolby pass-through** (`stream.PASSTHROUGH_AUDIO`, `passthrough` on `/remux` and `POST /hls`, player
  detection + Sound menu + fallback). Bugs fixed on the way: copy-HLS lost `-hls_list_size 0 -hls_flags temp_file`
  into a comment (half-written segments could be served); the live burn-in lost a line already on screen when started
  mid-line (now `-copyts`); AC3/EAC3 copied into streamed MP4 needs `delay_moov`.
- **Files:** `server/bams/stream.py`, `hls.py`, `subtitles.py`, `probe.py`, `app.py`; `web/src/pages/Player.tsx`,
  `web/src/api.ts`; tests `tests/vobsub.py` (new: writes .idx/.sub, multi-pack pictures), `test_stream.py`,
  `test_subtitles.py`.
- **Verified:** 227 tests pass (new: GPU chains per vendor, failure memory, SAR sizes, probe geometry, VobSub listing
  and burn-in from HLS segments 0/1 + the live stream, live PGS burn-in mid-line, AC3 pass-through over HLS and live).
  Real files: DV P5 frame vs the SDR reference (same colours; a naive decode is teal). D3D11 → `scale_d3d11` failed on
  the NVIDIA driver, so AMF uses `vpp_amf` (untested). Browser on a :8490 test instance (fresh DB): DV P5 switches to
  the conversion (Chromium: no `dvh1.05`), VobSub English line burned in at 0:16 after picking it mid-line, Sound menu
  "EAC3 → AAC" without Dolby support; with `isTypeSupported` faked to say yes: pass-through requested, the decode
  failed, the player went to AAC by itself and the menu says "didn't play here". No console or server errors.
- **Left open:** see §5 item 1 (real Intel/AMD/VAAPI hardware, a real Dolby device, DV P5 without Vulkan, MicroDVD
  `.sub`). Conversions (as opposed to the remux) still always output AAC.

### 2026-10-08: Choose and order Home's rows
- **What / why:** owner asked to configure which categories Home shows and in what order. New Settings card
  **Home page** (admins: own section; viewers: under Your account): the banner toggle (moved from the account card)
  plus every Home row (Continue Watching, Recently Added, each library, Top Rated, Genres) with a checkbox, drag
  handle (arrow keys work when it's focused) and ▲▼; saves on each change; *Reset to default*. Per user, stored as
  the `home_rows` pref (`[{id, show}]`, ids `continue`, `recent`, `lib:<id>`, `top_rated`, `genres`; empty = default).
  Rows missing from the saved list (a library added later) appear switched on after their default neighbour;
  saved ids that no longer exist are ignored. Server validates shape, max 200 rows, drops duplicates.
- **Files:** `server/bams/auth.py` (`PREFS` now mixed types, `_valid`/`_home_rows`, `MAX_HOME_ROWS`), `app.py`
  (`HomeRowIn`, `PrefsIn.home_rows`), `tests/test_watch.py` (`test_home_rows_pref`, prefs test updated);
  web: new `homeRows.ts` (`defaultRows`, `homeRows` merge), new `components/HomeSettings.tsx`, `pages/Home.tsx`
  (renders rows from `homeRows()`), `pages/Settings.tsx`, `components/AccountSettings.tsx` (banner toggle removed),
  `api.ts` (`HomeRowPref`, `Prefs`), `auth.tsx` (`DEFAULT_PREFS`), `styles.css` (`.home-rows`, `.home-row`).
- **Verified:** `test_watch.py` passes; full suite 226 passed, 1 failed (`test_vobsub_sidecar_is_burned_in`, from
  another session's unfinished VobSub work, not touched here). `tsc` clean, `npm run build`. Test server on :8488
  with a DB copy: card lists 7 rows in the default order; ▲ and arrow key moved Genres, unticking Continue Watching
  saved `show:false`; `/api/auth/state` returned the saved list; Home rendered the genre rows above Movies with
  Continue Watching gone; Reset restored the default and disabled itself; no console errors.
- **Left open:** individual genres can't be picked (Genres is one entry); not in an installer yet (the owner's
  :8484 service needs a new build to show it).

### 2026-10-08: Music follow-ups (CUE sheets, playlists, gapless, merges, refresh, late covers, FLAC output)
- **What / why:** the seven music follow-ups from §5, which the owner asked to build. **CUE sheets:** a `.cue` next to
  a whole-album file (matched by name, by name with another extension, or as the folder's only audio file) or a
  CUESHEET tag makes one track per entry (`file_items.cue_start/cue_end`); sheet changes are detected by their
  size/mtime (`files.parse.cues`) and re-read without re-probing; long files probed before v8 are probed once more for
  embedded sheets (`probe.PROBE_VERSION`). **Playlists:** imported from `.m3u/.m3u8/.pls` in music folders, re-read when
  their file changes, deleted with it, entries re-matched to tracks every scan; Playlists tab + page. **Gapless:** two
  `<audio>` elements, next track preloaded ~20 s before the end and started at the end; consecutive CUE tracks of one
  file are one stream. **Merges:** albums pinned to the same release (both by tag id, Fix match or a ≥ 0.95 search)
  become one; same disc+number+similar title → one track with both files; the queue plays the best file. **Refresh:**
  identified albums/artists looked up again after 120 days, 50 per scan; how they were found and their score are kept;
  downloaded covers/photos re-fetched, the owner's never. **Late covers:** the scan's walk notes images (and cue sheets,
  playlists) for free (`readonly.walk(side=…)`); `fill_artwork` compares each album's best folder image with
  `items.poster_src` and replaces embedded/CAA/Commons art. **FLAC output:** Settings → Music → Converted music.
  Schema v8 (`file_items.cue_*`, `items.poster_src`, `playlists`, `playlist_items`); `music.PARSER_VERSION` 2.
- **Files:** new `server/bams/cue.py`, `playlists.py`; `db.py` (v8), `config.py` (`CUE_EXTS`, `PLAYLIST_EXTS`),
  `readonly.py` (`walk` side files, `read_text`), `scanner.py` (side files, `sheet_for`/`cues_near`, playlist import +
  resolve), `music.py` (`parse_cue_tracks`, `link_tracks`, `album_alias`, `fill_artwork` rewrite), `music_match.py`
  (`merge_same_release`/`merge_albums`, refresh, `matched_by`, `poster_src`), `probe.py` (`cuesheet`, `pv`),
  `stream.py` (`plan_audio(output)`, `audio_cmd` FLAC), `jobs.py`, `app.py` (`_queue`, playlists API,
  `/api/settings/music-output`, Fix match after a merge); `web/src/music.tsx` (rewritten player), `pages/Music.tsx`
  (Playlists tab, `PlaylistPage`, `TrackList numbered`), `App.tsx`, `api.ts`, `components/MusicSettings.tsx`,
  `MusicFixMatch.tsx`, `NowPlaying.tsx`, `styles.css`; `tests/test_music_extras.py` (new), `test_music.py`,
  `test_music_match.py`, `test_auth.py`.
- **Verified:** 227 tests (12 new: cue parsing; image split, edited/removed sheet; queue `start/end`; real FLAC with an
  embedded sheet; playlist parsing, import, edit/delete; late cover/artist image vs CAA/Commons; merge + rescan +
  best file; unsure matches not merged; refresh; FLAC command and API). Browser on a test instance (:8489, generated
  music): playlist with relative, `Z:\Old Laptop\…` and CUE-image entries (1 stream counted missing); MP3 → converted
  ALAC → FLAC CUE image played through with ~1 ms between one element ending and the next playing, CUE tracks one
  stream; a WavPack CUE track started at `?t=5` with the clock from 0:00; FLAC setting → `audio/flac`, "FLAC" badge;
  seek inside a CUE track; a `cover.jpg` added after the first scan shown on the album; media folder unchanged.
- **Left open:** sample-perfect gapless (MSE; MP3 padding and AAC priming can still leave a tiny gap, FLAC output and
  CUE images avoid both); un-merge; authoring playlists; playlists not in Home/Search.

### 2026-10-08: Settings → Security (sign-in log, lockout, IP lists, traffic log)
- **What / why:** owner asked for a security section in Settings. **Sign-in log:** every sign-in (ok/failed + reason:
  wrong password, no such account, account locked, tried again too soon, too many from this address) and every
  lock/unlock, in `security.db` (newest 100,000 kept); filter All/Successful/Failed/Locks, paging. **Wait:** after
  wrong password n the account waits 2^(n-1) s (1, 2, 4, 8…); a try during the wait gets 429 + `Retry-After` and isn't
  counted; a right password resets to 0. Attempts per account are serialised (`Security.attempt`) so parallel guesses
  can't share one wait. **Lockout:** `settings.lockout_threshold` (default 5, 1–50) wrong passwords in a row lock the
  account until an admin unlocks it (Settings, or `bams user unlock NAME`). Unknown names behave the same. The old
  per-address `auth.Throttle` (10 / 10 min) stays. **Lock/unlock by hand:** an admin lock signs the account out
  everywhere; nobody locks themselves. **IP lists:** `settings.ip_mode` `allow_all` (default) | `allowlist`,
  `ip_allow`/`ip_block` (JSON `[{cidr, note}]`, IPv4/IPv6 addresses or CIDR, normalised); block list wins; loopback
  always allowed; a save that would block the saver's own address is refused (400); `bams security allow-all` resets
  the mode (a running server re-reads the policy every 10 s). Blocked addresses get 403 for everything (UI too).
  **Traffic log:** `security.Gate` (outermost ASGI middleware) records each request (time, duration, client ip:port,
  server, scheme, HTTP version, method, path, query, status, bytes in/out, signed-in user, user agent, allow/block)
  into `netflow.Netflow`: a background writer, `netflow-<ms>.jsonl` files of cap/10 (≤256 MB), oldest deleted to stay
  under `settings.netflow_max_bytes` (default 10 GB, 10 MB–100 TB); `settings.netflow_dir` (default `data/netflow`) is
  checked (absolute, writable, not in a library or the transcode dir); old files stay when the folder changes. The
  viewer reads backwards with a substring search and a cursor (64 MB scanned per call).
- **Files:** new `server/bams/security.py`, `server/bams/netflow.py`, `server/tests/test_security.py` (13 tests),
  `web/src/components/SecuritySettings.tsx`; changed `app.py` (login flow, Gate, `/api/security*` routes, user add/remove
  clear lock state), `config.py` (`Paths.security_db`, `Paths.netflow`), `__main__.py` (`user unlock`, `security
  allow-all`), `tests/test_auth.py` (the throttle test now guesses different names), web `Settings.tsx` (Security
  section), `api.ts` (types), `styles.css` (IP lists, log tables). `.claude/launch.json`: `bams-test-8487`.
- **Verified:** `test_security.py` 13/13 (doubling waits, 429 not counted, lockout + admin unlock, reset on success,
  threshold setting, unknown names answer alike, admin lock signs out + log entries/filter/paging, CLI unlock and
  allow-all, IP policy rules incl. IPv6 and v4-mapped, lists through the API incl. self-block refusal, every request and
  blocked ones in the traffic log, size-cap trimming + gap-free paging + search, folder/size settings and refusals).
  Full suite 225 passed; the 2 failures (`test_stream.py`, `test_subtitles.py`) were in code other sessions were
  changing at the time. Browser on a test server (:8487, fresh data dir): all five cards render, Lock shows
  "Locked by …", the sign-in log shows ok/failed rows with reasons, traffic-log sizes match the responses; no console
  errors.
- **Left open:** not in an installer yet (the owner's :8484 service needs a new build). The traffic log can't be
  downloaded from the UI (the files are in the folder shown). Behind a reverse proxy on another machine all visitors
  share the proxy's address (uvicorn trusts `X-Forwarded-For` only from 127.0.0.1). No alert/e-mail on lockouts.

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
