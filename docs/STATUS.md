# BAMS: build status, requirements and decisions

The hand-over document for anyone (human or Claude session) picking up the project.
Last updated: **2026-10-10** (release 0.7.0).

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
| 10-10 | **Music on the TV** with one HTML `<audio>` (not AVPlay), no gapless | AVPlay is the video player and owns the screen; `<audio>` plays MP3/AAC/FLAC and falls back to the server's conversion on an error |

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
  "Series N" marker is the season's, not the show's. ~50 real-world cases in `tests/test_parse.py`.
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
  keyframe start via a dry run), `/download`.
- **Video transcoding:** `/transcode?t=` converts video browsers can't decode (Xvid/DivX, MPEG-1/2, VC-1, Theora,
  ProRes, 10-bit/4:2:2/4:4:4 H.264…, and HEVC/AV1/VP9 for browsers without them) to H.264 + AAC on the best working
  encoder (NVENC/QSV/AMF/VAAPI, else x264). Deinterlaces, squares anamorphic pixels, caps the size, tone-maps HDR
  (Dolby Vision through libplacebo). GPU decoding with a GPU encoder. **HLS sessions** (`hls.py`): segments made
  on demand, native seeking, quality (max height) per session, bounded CPU/disk, idle sessions closed. A limit on
  simultaneous conversions (Settings).
- **Accounts:** `auth.py` (scrypt hashes, sessions, throttle), admin/viewer roles, first-admin setup from the server
  itself, login middleware on `/api/`, `bams user add|list|passwd|remove|unlock`.
- **Security** (`security.py`, `netflow.py`): sign-in log (`security.db`), per-account wait after wrong passwords
  (1 s doubling) and lockout (default 5), admin lock/unlock, IP allow/block lists (`security.Gate`, outermost
  middleware), traffic log of every request (10 GB cap, folder/size settable), `bams security allow-all`.
- **Watch state:** `watch.py`: progress (watched at 90% / started after 30 s by default; admin settings), watched flags for movie/episode/season/show, per-user counts on
  every item list, Continue Watching (resume + next episode), next episode for up-next.
- **Subtitles:** `subtitles.py`: embedded + sidecar tracks with language labels, WebVTT conversion (cached, any sidecar
  encoding, `?shift=` for live streams), picture subtitles burned in with a 30 s lead, VobSub `.idx/.sub` sidecars
  (one track per language) burned in too.
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
  filter), Title page (show: season tabs + episodes; movie: tech info + Download), Player (real `<video>`,
  remux-aware seeking, converted video over HLS (hls.js, loaded on demand), switches to the conversion when the
  browser can't decode the video, quality menu, keyboard shortcuts), Search, Settings (libraries with folder picker,
  scan status; Unrecognized files (identify by hand: link or fields with suggestions); TMDB key card; Playback card:
  encoder in use + conversion limit; Watched and Continue Watching thresholds). Library pages have an Unrecognized
  tab for admins. Player: speed 0.1x–3x. Music queue: drag (or arrow keys) to reorder. Show-password buttons,
  confirm-new-password. Settings → Home page (per person): banner on/off, rows on/off and order (drag, arrow keys, ▲▼), reset. Playback card: encoder choice (CPU/GPU). Library cards:
  live scan progress (N of M, size, time left, bar) and ▲▼ order buttons. Sidebar: admins drag libraries into order.
- Music: library page (Artists/Albums/Playlists tabs, sort, genres), artist page (bio, photo credit, albums), album page
  (tracklist by disc, format note, Wikipedia/MusicBrainz links), playlist page (`/playlist/:id`, cover mosaic, missing
  entries), Fix match (goes to the kept album after a merge), a now-playing bar with queue that keeps playing across
  pages (media keys via Media Session) and pauses when a video starts; gapless hand-over between tracks and CUE
  tracks played as stretches of one file; music in Home and Search; Music library type + identification toggle +
  converted-music format (AAC/FLAC) in Settings.
- Settings → Security (`SecuritySettings.tsx`, admins): wrong-password threshold, account locks (lock/unlock), who can
  connect (mode + allow/block lists, "Allow my address"), sign-in log (filter, older), traffic log (folder, size, usage,
  search, older).
- Sign-in / first-admin screens (`auth.tsx`), account menu, Settings → Accounts (password, users); viewers see only
  their account. Continue Watching row, watched ticks / unwatched counts / progress bars, mark watched on movie,
  show, season and episode, Resume / Start over; Continue Watching cards link the show and the episode's season. Player:
  resume, progress reports, up-next countdown (at the end and 30 s before it), next-episode button, skip +30 / −10 s, sound menu
  (tracks, Surround, Dolby pass-through on/off), subtitles menu (text via `<track>`, picture incl. VobSub = burned in),
  quality Original / Auto / sizes, remux over HLS with fallback to the live remux.
- TMDB-missing banner (admins) on every page → `/settings#tmdb`. "Can't reach server" banner.
- Brand: logo files in `branding/logo/` + `web/public/brand/`; palette as CSS tokens in `web/src/styles.css`.

### Samsung TV app (`tv/`, Tizen web app, React + Vite + TS)
- Finds the server (TV's /24 from Tizen system info, else common home ranges, or typed), links with a code + QR or
  name/password, Home (hero of the focused title, Continue Watching, Recently added, per-library rows), library grids
  (sorts), detail (seasons/episodes, resume/start over/mark watched), search, settings (server, sign out, always
  convert, "TV plays DTS"). Remote: spatial navigation (`nav.ts`), Back, media and colour keys registered.
- Player (`screens/Player.tsx`, `engine.ts`): AVPlay on the TV (`<video>` + hls.js in a browser); copy-HLS in TS for
  what the TV decodes (`plan.ts`), full conversion otherwise or after a failure; resume, ±skip, progress every 10 s,
  sound/subtitle menus (text subtitles drawn by the app from the server's WebVTT, with a timing control; picture
  subtitles burned in), up-next countdown. Packaging: `npm run package` (`scripts/wgt.mjs`) signs with the Tizen
  Studio profile `BAMS`, `--install --run` puts it on the TV, `--release` copies `dist/BAMS-SamsungTV-<v>.wgt`.
- Web: Settings → Your TVs (`TvSettings.tsx`) and `/link` (`LinkTv.tsx`).
- More servers (0.7.0): Settings → Other BAMS servers (add with the find/link screens, link again, remove, show/hide
  each library); their libraries in the menu under the server's name; Home and Search combined with the web's rows
  (`web/src/everywhere.ts`). Music (0.7.0): music libraries, artist/album/playlist pages, a music bar, media keys.

### More servers (0.7.0, web + TV)
- Clients keep their own server lists: web `servers.tsx` (`bams.servers` in localStorage; `/r/<rid>/…` pages are the
  same page components scoped to that server), TV `api.ts` extras. Server name setting (Settings → This server).

### Docs
README.md, CLAUDE.md, docs/PLAN.md, docs/STATUS.md, docs/CODEBASE.md, docs/FORMATS.md, docs/READ-ONLY.md,
docs/INSTALL.md, deploy/README.md, server/README.md.

## 5. Not built yet / next

Roughly in priority order:
1. **Playback leftovers (minor):** all-GPU filters on real Intel/AMD/VAAPI hardware (built, untested); Dolby
   pass-through on a real Dolby device (tested only with a faked "supported"); Dolby Vision profile 5 without
   libplacebo/Vulkan fails to convert (zscale can't read it); text MicroDVD `.sub` sidecars (no `.idx`) aren't listed.
2. **Music leftovers (minor):** sample-perfect gapless (Media Source Extensions); un-merging an album; making and
   editing playlists in BAMS (only imported today); `.cue` entries inside playlists.
3. **ISO / DVD / Blu-ray folders** (phase 3).
4. **Packaging leftovers**: code-signing the `.exe` (SmartScreen warning).
5. **TV app leftovers:** the TV's music has no queue view/reorder and no gapless hand-over; renaming other servers'
   libraries is web-only (the TV only hides them); Samsung TVs other than the owner's 2022 Frame untested (codec table in
   `tv/src/plan.ts` from Samsung's specs); the released `.wgt` is signed for the owner's TV only (others re-sign it,
   README); no store build; Settings → Your TVs shows TVs of your own account only (admins can't see others').
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
