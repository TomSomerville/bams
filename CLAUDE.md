# BAMS — Bad Ass Media Server

Self-hosted Plex/Netflix-style server for the owner's own video and music files.
Python server (`server/`) + React web UI (`web/`). MIT licensed. Runs on **Windows and Debian/Ubuntu/Mint**.

## Multiple agents work on this repo: read this first

Several Claude sessions work on BAMS, sometimes at the same time. **Your context is incomplete by default.**
Files may have changed since you last looked, and work may exist that you never saw. So:

1. **Before planning, decide what you need to read.** If the task touches existing behaviour, shared code,
   the data model, the API, or anything you haven't verified this session, read the relevant parts of
   [docs/STATUS.md](docs/STATUS.md) (requirements, decisions, the **Work log**) and
   [docs/CODEBASE.md](docs/CODEBASE.md) *before* you plan. Skip it only for small, self-contained changes.
   Then check `git status` / `git log` and re-read any file before editing it. The docs can lag the code; when they
   disagree, trust the code and fix the doc.
2. **Don't assume an unexpected change is a mistake.** A file you didn't touch may have been changed on purpose by
   another agent. Don't revert or "clean up" work you don't recognise. Ask the owner, or work around it.
3. **When your work is finished and the owner has signed it off, document it**, in the same session, before
   moving on:
   - add an entry to the **Work log** in [docs/STATUS.md](docs/STATUS.md) (what, why, files, how it was verified,
     anything left open);
   - update STATUS.md's "Built" / "Not built yet" lists and decisions log if they changed;
   - update [docs/CODEBASE.md](docs/CODEBASE.md) for new or changed files, flows, API routes, tables, or
     "where to change X" entries;
   - add new pitfalls to the list below.
   Don't log work that's still in progress or was rejected. Mention unfinished work only as "left open" in your entry.

**Read before working:**
- [docs/STATUS.md](docs/STATUS.md): what's built, what isn't, decisions and their reasons, requirements, dev environment.
- [docs/CODEBASE.md](docs/CODEBASE.md): every file and what it does, data flow, DB schema, API, "where to change X".
- [docs/PLAN.md](docs/PLAN.md) (architecture, phases, licensing) · [docs/FORMATS.md](docs/FORMATS.md) (all formats and handling) · [docs/READ-ONLY.md](docs/READ-ONLY.md).

## Non-negotiable rules

1. **Media folders are read-only to BAMS.** Never write, rename, delete, chmod, touch, or drop sidecar files
   (artwork, .nfo, thumbnails) in a library folder. Everything BAMS creates goes in the data dir. Media access
   goes through `server/bams/readonly.py`. A process-wide audit hook enforces this. Don't weaken it, and keep
   `tests/test_readonly.py` passing. **One exception, the owner's (2026-10-12):** `readonly.create_sidecar` may create
   a *new* `.srt` next to a video, when someone presses "Download locally" on an OpenSubtitles download (0.15.0;
   0.14.0 did it after every download). Exclusive create only:
   never overwrite, rename or delete, never another file type, and no other code path may write. Don't add more
   exceptions without the owner.
2. **Cross-platform.** Every server feature must work on Windows *and* Debian/Ubuntu/Mint: `pathlib`, no
   hard-coded separators, file paths stored relative to their library root, no Windows-only or Linux-only
   calls without a fallback. Minimum Python is **3.11** (Debian 12).
3. **Licensing.**
   - Everything in the project must be open-licensed and legal.
   - **No IMDb scraping** (their terms forbid it). IMDb IDs come via TMDB.
   - **MusicBrainz** (music identification): no key, but keep to **1 request/second** (the shared throttle in
     `musicbrainz.py`) and send `USER_AGENT`. Use only its CC0 core data (its genres/tags are CC BY-NC-SA).
     Wikipedia text and Commons photos must keep their credit/link in the UI (`pages/Music.tsx` `About`).
   - **TMDB:** each user pastes their **own** key in Settings. There is **no shared/project key** (user decision).
     Attribution text must stay, and cached TMDB data/images must be refreshed within 6 months
     (`matcher.REFRESH_AFTER`).
   - **OpenSubtitles:** each server's admin pastes their **own** API key too (owner's decision, 2026-10-11), although
     OpenSubtitles' terms ask for one key per app and say they may ban apps whose users bring their own. Send the
     `USER_AGENT` ("BAMS v<version>"), stay under 5 requests/second (`opensubtitles._throttle`), never retry a login
     they refused. Keep the "Subtitles from OpenSubtitles.com" credit in the UI.
   - **FFmpeg is never bundled.** It's found on the system (`probe.ffprobe_path`, `stream.ffmpeg_path`).
   - Don't copy Jellyfin code (GPL).
   - The repo ships no copyrighted posters.
4. **Never handle the user's TMDB or OpenSubtitles key (or OpenSubtitles password) yourself.** Don't read them from
   the browser or DB and replay them. The user enters them in Settings (or `bams tmdb-key`). Test against a fake
   (`app.state.opensubtitles_transport`, see `tests/test_opensubtitles.py`).
5. **No placeholder data in the UI.** Every page shows real server data, with empty states when there's none.

## Run / test

```bash
# server (Windows paths shown; Linux: .venv/bin/python)
cd server && uv venv --python 3.11 .venv && uv pip install --python .venv -e ".[dev]"
server\.venv\Scripts\python -m pytest -q                      # 330 tests, all must pass
server\.venv\Scripts\python -m bams --data-dir C:\Users\owner\bams\data serve   # http://127.0.0.1:8484, API docs /docs
# web (served by the server from web/dist — rebuild after UI changes)
cd web && npm install && npx tsc -p . && npm run build
# Samsung TV app (tv/README.md): Tizen Studio in C:	izen-studio, signing profile "BAMS", TV at 192.168.1.150
cd tv && npm install && npx tsc -p . && npm test && npm run build && npm run package -- --install --run   # --release: dist/BAMS-SamsungTV-<v>.wgt
# Fire TV app (firetv/README.md): JDK 17 + Android SDK 35; release key C:\Users\owner\bams-firetv.jks via firetv/keystore.properties
cd tv && npm run build && npm run firetv -- --install --device <fire-tv-ip>   # --release: dist/BAMS-FireTV-<v>.apk
# installers (deploy/README.md): bump server/bams/config.py VERSION first
server\.venv\Scripts\python deploy\build.py all               # dist\BAMS-Setup-<v>.exe + dist\bams_<v>_all.deb
```

## Pitfalls already hit (don't repeat them)

- **The user runs their own server on :8484** with the real data dir. To test changes, run a *separate* instance
  on **:8485** with a **copy** of the DB (`sqlite3 backup`) in the scratchpad (`.claude/launch.json` → `bams-test`;
  point its `--data-dir` at your scratchpad). The copy has accounts: create your own test account (first-admin
  setup from localhost works on a copy without users) and keep its password in the scratchpad, not in chat. Never mutate the user's libraries or
  settings without asking. Server code changes need the user to **restart** their server; UI changes need
  `npm run build` plus a browser reload.
- **Vite on Windows missed file changes** and served stale modules. `web/vite.config.ts` uses polling; if the UI
  looks stale, restart Vite with `--force`.
- **SQLite + FastAPI:** sync endpoints may open a connection in one thread and use it in another, so `db.connect`
  uses `check_same_thread=False`. Don't remove it.
- **The audit hook is process-wide and permanent.** Tests must reset protected roots (`conftest.py`). To mutate
  a media tree in a test, use the `unguarded` fixture.
- **Parser changes:** bump `parse.PARSER_VERSION` so the next scan re-parses existing files.
- **Shells:** PowerShell mangles `npm run dev -- --port X`; use `npx vite`. Git Bash `curl` mangles Windows
  backslash paths in JSON bodies; send API requests from Python (`httpx`) instead.
- **Browsers can't decode AC3/EAC3/DTS/TrueHD** (silent video). `stream.plan()` routes those files to the
  `/remux` endpoint, which converts the audio to AAC. Seeking a remux restarts it; `/seek` returns the real start.
- **Movies added to a TV library** are "unrecognized" (no SxxEyy). The library card in Settings shows them with a
  hint. Libraries are single-type, like Plex.
- **Tests must not touch the network.** HTTP clients take a `transport=` (use `httpx.MockTransport`); music
  `run_scan` calls in tests pass `do_match=False` (identification is on by default and would hit MusicBrainz).
- **`SELECT a.*, p.title AS artist` is a trap:** `items` has its own `artist` column (track performer), which
  shadows the alias. Name aliases so they can't collide (`album_artist`).
- **Schema changes go through `db.MIGRATIONS`.** A CHECK-constraint change means a table rebuild with foreign keys
  OFF (or `DROP TABLE items` cascades into `file_items`). New DBs run every step from v1.
- **Music scans link files after probing** (tags come from ffprobe). Matched albums keep MusicBrainz's year in
  `music.rollup`, and matched tracks keep MusicBrainz titles when the file has no title tag: don't undo either.
  Music parser changes bump `music.PARSER_VERSION` (separate from `parse.PARSER_VERSION`).
- **CUE tracks are stretches of one file** (`file_items.cue_start/cue_end`): don't assume one track = one file or
  one file = one track (merged albums give a track several files; `app._queue` picks one). Queries joining tracks to
  files must expect both. The player plays `start`..`end`; never cut a copy of the file.
- **Music art: `items.poster_src` says where a poster came from.** Any code that sets a music poster must set it
  too, or a later `cover.jpg` can't replace it (or a refresh re-downloads over the owner's art). `match_album` used
  to overwrite `extra` wholesale; it now writes `matched_by` into it, which merges rely on.
- **Album merges are remembered by name** (`music.album_alias`, artist + album name in `item_keys`), not ids: the
  merged-away artist is deleted and a rescan would re-create it with a new id. `_album` checks the alias first.
- **The music player has two `<audio>` elements** (gapless). Only the active one's events count; the other only
  preloads. Calling `load()` after setting `src` resets a CUE track's start position: don't.
- **Generated test clips:** lavfi `testsrc` + libx264 defaults to 4:4:4 ("High 4:4:4"), which `stream.plan()`
  rightly sends to the transcoder. Add `-pix_fmt yuv420p` when a test needs browser-playable H.264.
- **HEVC/AV1/VP9 stay pass-through on the server.** Only the browser knows whether it decodes them;
  `Player.tsx` `canDecode()` switches to the conversion. Don't move them to `mode:"transcode"` in `plan()`.
- **HLS segments must line up across FFmpeg runs** (`stream.hls_cmd`): keep `-copyts -start_at_zero`,
  `-output_ts_offset 10` (without it a run from 0 gets negative timestamps and is shifted alone), no scene-cut
  keyframes, and `-force_key_frames expr:gte(t,n_forced*4)`. With `-copyts`, `t` there counts from the run's start,
  not the file's, and an output-side `-t` stops at once. `test_hls_through_the_api` checks the alignment.
- **The conversion limit counts open sessions, not FFmpeg processes.** HLS FFmpeg is stopped while far ahead;
  counting processes let a newcomer take a paused viewer's place and the viewer got "busy" mid-film.
- **hls.js is loaded with a dynamic `import()`** in `Player.tsx` (it's bigger than the rest of the UI). Keep the
  `import type` at the top type-only.
- **Git Bash heredocs** with backticks or unbalanced quotes inside (TSX template literals, prose) fail to parse,
  and so does probing with `python3 - || …` (the Windows Store alias waits on stdin). Use the Edit tool, or write the
  script to a file and run it with `server\.venv\Scripts\python`.
- **Everything under `/api/` needs a signed-in session** (`LoginRequired`). In tests use
  `conftest.signed_in(create_app(...))`, never a bare `TestClient` (401s). Endpoints that call `get_item()` directly
  must pass `me`. New admin-only routes get `dependencies=ADMIN`; new public ones go in `PUBLIC_API` (think twice).
- **Copy-HLS (remux) alignment:** FFmpeg's MKV seek lands on the index point *before* the target, so a run is
  numbered from where a dry run of the **same** `-ss` lands (`remux_start(zero=True)`); fMP4 needs
  `movflags=+frag_discont` or every run's decode times start at 0; the init file name is **bare and FFmpeg runs in the
  variant's folder** (`spawn(cwd=)`): FFmpeg ≤ 6.1 (Debian/Ubuntu) prefixes the playlist's folder even to an absolute
  name (ENOENT, every Ubuntu copy-HLS failed), FFmpeg 9 puts a bare name in the working dir; serve `init.mp4` only once a segment exists (it's written gradually). ffprobe applies the
  edit list, so compare segments by video packet pts or `tfdt`, not "first packet".
- **Burned-in subtitles** must be read with a lead (second input, `SUB_LEAD`) or a run starting mid-line loses it.
  Hand-made subtitle streams get their times rebased to their first packet when muxed: start test PGS with an empty
  display set at 0 (`test_subtitles.pgs`).
- **The web page must not be cached** (`SpaFiles` sends `no-cache` for HTML; missing `/assets/` 404): a cached page
  from an older build points at scripts that no longer exist → blank screen. When testing a rebuilt UI in the preview
  browser, add a query string once if it still shows an old page.
- **Never kill processes by name** (`taskkill /IM python.exe`, `pkill python`): the owner's own server (:8484), ComfyUI
  and other sessions are Python too. Stop only the PID you started.
- **Installers:** the installed copy finds its UI in `bams/web` and FFmpeg in `<install>\ffmpeg\bin`; keep both lookups
  (`__main__._web_dir`, `probe.app_ffmpeg_dir`). Python dependency changes must be re-locked in `deploy/requirements.txt`
  (hashes) or the installers ship the old set. Updates must never touch the data dir: on Windows only `python\`, `lib\`,
  `app\` are replaced; on Linux `/etc/default/bams` must stay a non-conffile (a conffile prompt blocks the upgrade).
- **Windows ACLs:** never `icacls <dir> /inheritance:r /grant … /T` on a folder with files in it: the files end up with an
  empty ACL (unreadable even to SYSTEM, the service then can't open its DB). Set the folder only, `/reset /T` its contents.
- **Testing the Windows installer installs a real service on :8484** and needs the owner's UAC click: ask first. Silent
  runs: `BAMS-Setup.exe /SILENT /SUPPRESSMSGBOXES /LOG=…` via `Start-Process -Verb RunAs -Wait`. `.deb` tests run in
  Docker (`debian:12`, `ubuntu:24.04`; a systemd image for service tests); Git Bash needs `MSYS_NO_PATHCONV=1` for `-v`.
- **Never hold a write transaction while touching the disk** (walking, hashing, probing, network). A first scan
  that walked inside `BEGIN IMMEDIATE` locked every other writer out for minutes: logins 500'd with "database is
  locked". Read first, then write in short batches (`scanner.py`; `test_scan_does_not_hold_the_write_lock…`).
- **Encoder tests must reset the caches:** `stream.video_encoder()` honours the admin's choice (`_preferred`) and a
  per-encoder test cache (`_works`) besides `_detected`, and VAAPI's constant-QP memory (`_vaapi_cqp`); the
  `fake_ffmpeg` fixture resets all four. A test that sets a choice and leaks it changes every later conversion test.
- **The encoder test must use the options conversions really use** (`_encoder_works` → `_encoder_args`): Ubuntu's free
  Intel driver (owner's HD 630) takes `h264_vaapi` at constant QP only, so an option-less test passed and every real
  conversion failed ("Driver does not support any RC mode"). VAAPI falls back to `-rc_mode CQP`; keep that fallback.
- **Hand identifications win over file names:** the scanner goes through `identify.parsed_for`, never `parse.parse`
  directly, or a rescan would undo what an admin entered (`files.manual`).
- **The owner's server is a remote Ubuntu 24.04 machine** (since 2026-10-10; before that the Windows service in
  `C:\Program Files\BAMS`, data `C:\ProgramData\BAMS`, unreadable without admin). `ssh <server>` (key
  `~/.ssh/<key>`, user `owner` = the account BAMS runs as, in `render`) reads `/var/lib/bams/logs/bams.log`,
  the DB (open it `?mode=ro`, or `sqlite3` backup into `/tmp`) and runs FFmpeg/VAAPI tests; write only to `/tmp` and
  clean up, change nothing else there without asking. It runs the released `.deb`, not this checkout: a fix reaches it
  with a new release, and installing needs the owner's sudo. Docs: STATUS.md §6.
- **Home row ids are stored in users' prefs** (`home_rows`: `continue`, `watchlist`, `recent`, `lib:<id>`, `top_rated`, `genre:<name>`; older saves have one `genres`
  entry, which `homeRows()` expands in place: keep that).
  Renaming an id silently resets that row for everyone who reordered; add new rows in `homeRows.ts` `defaultRows`.
- **Security state lives in `security.db`, not `bams.db`** (no migration; `CREATE TABLE IF NOT EXISTS`). Login tests
  that fail a password and retry within a second get 429 (the per-account wait): advance the `clock` fixture
  (`test_security.py`, patches `security.now`) or use a different name. `security.Gate` is added last in `create_app`
  so it stays the outermost middleware: keep it so, or blocked/401 requests vanish from the traffic log. A test with
  the IP lists in `allowlist` mode must give TestClient a real `client=(ip, port)` ("testclient" isn't an address).
- **AC3/EAC3 copied into streamed MP4** (Dolby pass-through) needs `+delay_moov` in `-movflags` or FFmpeg refuses
  ("Cannot write moov atom before AC3 packets"). The HLS fMP4 muxer copes by itself.
- **Live burn-in keeps the file's clock** (`-copyts -start_at_zero`, `-output_ts_offset -t`), like HLS. `-itsoffset`
  on the subtitle input lost a line already on screen. VobSub `.idx` inputs have no start time: no offset needed.
- **All-GPU paths other than NVIDIA and VAAPI are untested on hardware** (QSV, AMF: the owner's PC has only NVIDIA;
  `scale_d3d11` can't create textures on the NVIDIA driver). VAAPI works on the owner's Ubuntu server (Intel HD 630). Keep the hybrid
  fallback and `stream.gpu_failed` memory; tests that touch `gpu_filters` reset `stream._gpu_broken`.
- **The show is named by the folder above the season folder**, not the top folder (`parse._show_dir`): packs hold
  several shows ("Megapack/Star.Trek.DS9/S03/…"). A file with a season in its name but no episode, under a season
  folder, is an unnumbered extra. Years that follow "Series N" in a folder are the season's. New layout? Add the real
  path to `test_parse.py` and dry-run the parser over a DB **copy** of the owner's library before shipping.
- **Changing matching rules?** Bump `matcher.MATCHER_VERSION` or titles that failed once are never retried (scans only try `pending` titles otherwise). Parser bumps retry them by themselves.
- **Linux test runs** (Docker `ubuntu:24.04`, FFmpeg 6.1): `test_encoder_choice_api` fails there (it fakes
  `sys.platform = "win32"`, which breaks `shutil.which`). Not a regression; the rest of `test_stream.py`/`test_hls.py`
  passes there (the whole suite hasn't been run on Linux). Run the real-FFmpeg HLS tests there after touching FFmpeg
  commands, since Debian/Ubuntu ship older FFmpeg than Windows.
- **The live remux (`stream.remux_cmd`) needs `-noaccurate_seek`:** the copied video starts at the keyframe before `-ss`,
  but FFmpeg trims converted audio to the exact `-ss` and both start at 0, so the picture ran seconds behind the sound.
  A tone or mostly-silent test clip doesn't show it; `test_live_remux_keeps_sound_with_picture_after_a_seek` uses noise.
- **Samsung's AVPlay (owner's 2022 Frame, Tizen 6.5) can't seek in a progressively streamed file** (one `bytes=0-`
  request, then `PLAYER_ERROR_SEEK_FAILED`; `<video>` too) and **rejects fMP4 HLS**. The TV app plays everything it
  decodes as copy-HLS in **MPEG-TS** (`POST /hls {remux, ts, passthrough}`). Don't switch it back to direct file play.
- **TV app page layers must be transparent while playing** (`html.playing`, body, #root): AVPlay draws video *under* the
  page. Keep the `<object type="application/avplayer">` at 1×1 px: full size it drew a grey dot mid-screen.
- **TV app builds to one classic script** (`tv/vite.config.ts`: IIFE, ES2019, no module scripts, no `import.meta`):
  Tizen loads the app from file://. Static images live in `tv/public` and are referenced by relative paths.
- **`webapis.network.getIp()` throws on the owner's TV** ("pepper plugin"): the TV's address comes from
  `tizen.systeminfo` (ETHERNET/WIFI_NETWORK) with fallbacks (`tizen.ts` `localIp`).
- **Media tickets** (`/api/t/<ticket>/…`) are rewritten to the real path in `LoginRequired`; they open only
  `MEDIA_PREFIXES` and only GET/HEAD. New media routes the TV must load need their prefix there.
- **The released `.wgt` is signed for the owner's TV only** (Samsung distributor certificate = the TV's DUID). Updates
  must be signed with the same author certificate (`C:UsersownerSamsungCertificateBAMS`) or the TV treats
  them as another app. Certificate Manager 3.1.3 won't start on Tizen Studio's bundled Java 8 with `--add-modules` in
  `toolscertificate-managereclipse.ini` (removed on the owner's PC; original kept as `eclipse.ini.orig`).
- **`web/src/homeRows.ts` is shared with the TV app** (`tv/src/screens/Home.tsx` imports it): keep it free of browser,
  React Router and `web/`-only imports (types from `web/src/api.ts` are fine), and check `cd tv && npx tsc -p .` after
  changing it or the Home row ids.
- **Web and TV are clients of several servers** (0.7.0): each browser/TV keeps its own list and talks to each server
  directly; servers store nothing about other servers (an account-side proxy was built and dropped at the owner's
  request). Item ids are per server: key lists with `everywhere.keyOf`, link with the item's `rid` (web
  `useItemServer`/`scopeLink`, TV `ridOf`). Another server's 401 must never fire this server's `SIGNED_OUT`.
- **`web/src/everywhere.ts` is shared with the TV app** (Home rows, Search, merging): like `homeRows.ts`, no React,
  router or browser-only imports; the owner wants web and TV to show exactly the same thing, so change both through it.
- **Ticket paths:** GET/HEAD are opened by the ticket; any other method needs the cookie/bearer (the web POSTs
  `hls_url` and DELETEs sessions on another server's ticket URLs). Keep `test_media_tickets`.
- **sed with `#` as delimiter:** replacement text containing `#` ends the expression early and a following `w…` is the
  *write-to-file* flag (it created a stray file once). Use the Edit tool for anything with `#` or `/` in it.
- **TV navigation:** the rail is `[data-side]` (only Left enters it, Up/Down stay in it, Right returns to the last
  page element); bars over the page are `[data-group][data-cover]`. Screens get their first focus through
  `useFocusOnReady` → `nav.settleFocus` (content like Home's shelves arrives after "ready"). Add a case to
  `tv/test/nav.test.ts` for any navigation change (`cd tv && npm test`, headless Chrome/Edge).
- **Python text-mode writes on Windows turn LF into CRLF** (`open(p, 'w')` in an edit script): the whole file shows as
  changed. Pass `newline=''` when reading and writing, or `sed -i 's/\r$//'` afterwards.
- **Two-step sign-in:** the right password alone must neither count as a failure nor reset the wrong-password count
  (`_sign_in`), or someone with the password could try codes forever. Codes before `totp_last` never count: tests that
  sign in twice need a later step (`test_auth.later`).
- **Auto fill (`parse.guess`) is on by default:** a test that expects a file to stay *unrecognised* must turn it off
  (`set_setting(con, "autofill", "0")` or `PUT /api/settings/autofill`), as `test_identify.tv` and
  `test_groups_shows_seasons_episodes` do. Guesses must never turn a movie in its own folder into a fake show
  (`test_movie_in_tv_library_is_flagged`), but a film under a show's folder is that show's Specials, even in its own
  subfolder (`Daria Complete Series/Daria Is It College Yet 2002 …/…avi`). "Don't place" is `files.manual = {skip: true}`: code reading `manual` must
  expect it (no title). "Keep" adds `kept: true` to a hand identification (it then leaves the Unrecognized list).
- **guessit splits names at hyphens**: a folder "Catch-22" read as "Catch" + episode 22, "Ant-Man.2015" as release
  group "Ant" + "Man". In `parse.py` always read names through `parse._read(text, kind, folder=)`, never `guessit()`
  directly: it re-reads a hyphenated word the title was cut through with the hyphen protected (`_protect`). In a
  *file* name "Naruto-01" stays episode 1 and an all-lowercase "aaf-movie.name" keeps "aaf" as the group (folders
  don't get those exceptions). New cases go in `test_parse.py`; dry-run over the owner's paths before shipping.
- **Downloaded subtitles ("d<n>" tracks)** live in the data dir (`cache/subtitles/opensubtitles/` since 0.15.0;
  older rows keep `subtitles/opensubtitles/` in their `path`; nothing may empty `cache/`, re-downloading costs quota),
  table `subtitle_downloads`. "Download locally" (`POST …/subtitles/d<n>/local` → `opensubtitles.save_locally`) saves
  one next to the video as `<video stem>.srt` (taken → `<stem>.<lang>[.sdh].srt`, then `.2`…), recorded in
  `subtitle_downloads.sidecar`. `subtitles.tracks()` lists only the file's own tracks: the player's list is
  `opensubtitles.listing(con, file_id, own)` (own tracks minus BAMS's copies, plus the downloads); the `.vtt` route
  adds `opensubtitles.tracks()`. A removed download's copy stays and becomes an ordinary sidecar.
- **The sidecar door in the audit hook is thread-local and path-exact** (`readonly._allowed.target`): only an
  `open(target, "x…")` of that one path, or removing it after a failed write, passes. Never write a sidecar any
  other way (no temp file + rename: rename is blocked and could replace a file). A name that's taken is skipped
  (`_local_names`); an identical file already there is reused. `test_readonly.py` checks the door stays shut otherwise.
- **The Linux service can't write media even when the code may** (`ProtectSystem=strict`, `ReadWritePaths=/var/lib/bams`):
  subtitle copies need a drop-in `ReadWritePaths=-<library folder>` (`/etc/systemd/system/bams.service.d/20-subtitles.conf`,
  survives upgrades; postinst only writes `10-user.conf`). Settings shows the exact command (`opensubtitles.save_check`,
  `os.access` checks without writing). A refused save is a 409 with the reason (`SaveError`), shown in the dialog.
- **Don't guess the OpenSubtitles key's format**: their docs don't give one, and a 16–64 character check refused the
  owner's paste. `valid_key_format` only rules out spaces and silly lengths; a JWT with an `exp` (a sign-in token, 24 h)
  is refused with an explanation (`_sign_in_token`); everything else is OpenSubtitles' call (`Client.check`).
- **OpenSubtitles answers a wrong API key with 403 "You cannot consume this service"** on searches and on `/login`
  (before it reads the name and password: a failed account sign-in with that message is the *key*; `Client.request`
  says so). `/infos/formats` works with any key, so it can't check one. `Client.check()` uses a small search; searching never counts against
  the download limit, downloads do (also when picked from the TV).
- **`web/src/subtitleLangs.ts` is shared with the TV app** (OpenSubtitles' language list): no React, router or
  storage in it, like `everywhere.ts`.
- **Sleep mode's count rides in the navigation state** (web `location.state.sleep`, TV route `sleep`): both players
  are re-created for the next episode, so component state alone would forget it. `goNext`/`playNext` pass
  `sleep - 1`; going on by hand after it stopped turns it off.
- **Holding OK on the TV** (`tv/src/hold.ts`, `[data-hold]` → `contextmenu`): the Fire TV app passes OK's key-downs
  only, never a key-up, so a press must never wait for a key-up alone (repeats decide there); key-downs that keep
  coming after a hold must press nothing (the menu's first button has the focus by then). `tv/test/hold.test.ts`.
- **Python 3.11 on Windows: `time.time()` ticks every ~16 ms**, so writes in a row often get the same time. Tests that
  depend on the order of timestamps patch the clock (`monkeypatch.setattr(watch, "now", …)` in `test_watch.py`).
- **The Fire TV app is the `tv/` page in a WebView** (`firetv/`): change the page in `tv/`, rebuild it, then the APK
  (Gradle copies `tv/dist` in). Fire TV code paths are `hasExo()` / `fireInfo()` branches; keep the Samsung and browser
  paths untouched by them and add a case to `tv/test/firetv.test.ts`. OK on a text box must stay a simulated tap
  (`MainActivity.kt`): asking Android for the keyboard directly opened it on a dead input connection and it closed at once.
- **Fire TV releases need the release key** (`C:\Users\owner\bams-firetv.jks`, passwords in git-ignored
  `firetv/keystore.properties`, made at 0.12.0): an APK signed with any other key won't install over a released one.
  Never commit either; a lost key means every Fire TV reinstalls and signs in again. Debug and release builds don't
  install over each other (`adb uninstall media.bams.firetv` first).
- **A saved position of 0 doesn't mean playback was stuck:** `watch.record_progress` stores positions under
  `resume_after` as 0. To see whether a browser really played, read the traffic log (`netflow/*.jsonl`: how long each
  `/stream` request stayed open, and whether a second one followed), not `watch_state`.
- **The watch list lives on each item's own server** (`watchlist` table, per account); the apps merge every server's
  list (`everywhere.listedOrder`) and toggle an entry on its own server (`callFor(rid)`, TV `setListed`). Never store
  another server's items on this one (decisions log 10-10/10-11). Adding a pref changes the whole `prefs` dict some
  tests compare (`test_watch.py` prefs tests).
- **Buttons shown only on hover must not exist for touch** (`@media (hover: hover)`, the poster bookmark): an
  `opacity: 0` button still takes the tap that was meant to open the poster.
- **Commit/push only when the user asks.** Repo: github.com/TomSomerville/bams (private).
