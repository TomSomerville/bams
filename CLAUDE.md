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
   `tests/test_readonly.py` passing.
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
   - **FFmpeg is never bundled.** It's found on the system (`probe.ffprobe_path`, `stream.ffmpeg_path`).
   - Don't copy Jellyfin code (GPL).
   - The repo ships no copyrighted posters.
4. **Never handle the user's TMDB key yourself.** Don't read it from the browser or DB and replay it. The user
   enters it in Settings or with `bams tmdb-key`.
5. **No placeholder data in the UI.** Every page shows real server data, with empty states when there's none.

## Run / test

```bash
# server (Windows paths shown; Linux: .venv/bin/python)
cd server && uv venv --python 3.11 .venv && uv pip install --python .venv -e ".[dev]"
server\.venv\Scripts\python -m pytest -q                      # 271 tests, all must pass
server\.venv\Scripts\python -m bams --data-dir C:\Users\Beached\bams\data serve   # http://127.0.0.1:8484, API docs /docs
# web (served by the server from web/dist — rebuild after UI changes)
cd web && npm install && npx tsc -p . && npm run build
# Samsung TV app (tv/README.md): Tizen Studio in C:	izen-studio, signing profile "BAMS", TV at 192.168.1.211
cd tv && npm install && npx tsc -p . && npm test && npm run build && npm run package -- --install --run   # --release: dist/BAMS-SamsungTV-<v>.wgt
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
  `movflags=+frag_discont` or every run's decode times start at 0; the init file name must be absolute or it lands
  in FFmpeg's working dir; serve `init.mp4` only once a segment exists (it's written gradually). ffprobe applies the
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
  per-encoder test cache (`_works`) besides `_detected`; the `fake_ffmpeg` fixture resets all three. A test that sets a
  choice and leaks it changes every later conversion test.
- **Hand identifications win over file names:** the scanner goes through `identify.parsed_for`, never `parse.parse`
  directly, or a rescan would undo what an admin entered (`files.manual`).
- **The owner's :8484 is the installed Windows service** (`C:\Program Files\BAMS`, data `C:\ProgramData\BAMS`), not
  this checkout: restarting it doesn't load repo changes; a new installer does, and running it needs the owner.
- **Home row ids are stored in users' prefs** (`home_rows`: `continue`, `recent`, `lib:<id>`, `top_rated`, `genre:<name>`; older saves have one `genres`
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
- **All-GPU paths other than NVIDIA are untested on hardware** (QSV, VAAPI, AMF: the owner's PC has only NVIDIA;
  `scale_d3d11` can't create textures on the NVIDIA driver, VAAPI didn't work through WSL/Docker). Keep the hybrid
  fallback and `stream.gpu_failed` memory; tests that touch `gpu_filters` reset `stream._gpu_broken`.
- **The show is named by the folder above the season folder**, not the top folder (`parse._show_dir`): packs hold
  several shows ("Megapack/Star.Trek.DS9/S03/…"). A file with a season in its name but no episode, under a season
  folder, is an unnumbered extra. Years that follow "Series N" in a folder are the season's. New layout? Add the real
  path to `test_parse.py` and dry-run the parser over a DB **copy** of the owner's library before shipping.
- **Changing matching rules?** Bump `matcher.MATCHER_VERSION` or titles that failed once are never retried (scans only try `pending` titles otherwise). Parser bumps retry them by themselves.
- **Two `test_stream.py` encoder tests fail on a machine with NVENC** (`test_encoder_choice_api`,
  `test_remux_over_hls_lines_up_across_runs`); they expect a CPU-only box. Not a regression.
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
  must be signed with the same author certificate (`C:UsersBeachedSamsungCertificateBAMS`) or the TV treats
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
- **Commit/push only when the user asks.** Repo: github.com/TomSomerville/bams (private).
