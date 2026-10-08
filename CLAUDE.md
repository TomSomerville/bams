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
server\.venv\Scripts\python -m pytest -q                      # 142 tests, all must pass
server\.venv\Scripts\python -m bams --data-dir C:\Users\Beached\bams\data serve   # http://127.0.0.1:8484, API docs /docs
# web (served by the server from web/dist — rebuild after UI changes)
cd web && npm install && npx tsc -p . && npm run build
```

## Pitfalls already hit (don't repeat them)

- **The user runs their own server on :8484** with the real data dir. To test changes, run a *separate* instance
  on **:8485** with a **copy** of the DB (`sqlite3 backup`) in the scratchpad. Never mutate the user's libraries or
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
- **Commit/push only when the user asks.** Repo: github.com/TomSomerville/bams (private).
