# BAMS codebase map

What each file does, how the pieces connect, and where to change things. For *why* things are the way they
are, see [STATUS.md](STATUS.md) §3 (decisions) and [PLAN.md](PLAN.md). For *who did what recently*, see the
STATUS.md §8 Work log.

> Several agents edit this repo. This map can lag the code; when they disagree, trust the code and update this
> file as part of finishing your work (see CLAUDE.md, "Multiple agents work on this repo").

---

## 1. Tree

```
bams/
├── CLAUDE.md                  Rules + pitfalls for Claude sessions (auto-loaded)
├── README.md                  Project intro, how to run
├── LICENSE                    MIT
├── .gitignore / .gitattributes   (LF line endings everywhere; data/, .venv/, node_modules/, dist/ ignored)
├── .claude/launch.json        Dev-server config for the desktop app's preview pane (Vite on :5173)
│
├── docs/
│   ├── PLAN.md                Architecture, how Plex works, metadata licensing, phases
│   ├── STATUS.md              Build status, requirements, decisions log, dev environment
│   ├── CODEBASE.md            ← this file
│   ├── FORMATS.md             Every container/codec/subtitle/music format: browser support + BAMS handling
│   └── READ-ONLY.md           How media folders are kept read-only (code + OS setup per platform)
│
├── server/                    ── Python server (FastAPI + SQLite) ──────────────────────────
│   ├── pyproject.toml         Package "bams"; deps: fastapi, uvicorn, httpx, guessit; dev: pytest
│   ├── README.md              Server usage, CLI, API table
│   ├── bams/
│   │   ├── __main__.py        CLI entry (`python -m bams …` / `bams …`): serve, library, scan, tmdb-key, status
│   │   ├── app.py             FastAPI app: bootstrap, JSON serialisers, ALL HTTP routes, SPA static hosting
│   │   ├── config.py          Data-dir resolution, Paths, ports, VIDEO_EXTS, AUDIO_EXTS, art file names, skip-folder lists
│   │   ├── db.py              SQLite schema (v1 + migration steps to v3), connect(), migrate(), Tx, settings, JSON helpers
│   │   ├── readonly.py        Read-only media access + the audit-hook guard + walker + quick_hash
│   │   ├── library.py         Library CRUD, folder validation, guard refresh, describe() for the API
│   │   ├── scanner.py         scan_library(): walk → diff → parse → link → probe (music: probe before parse/link)
│   │   ├── parse.py           Filename/folder → Parsed (show/season/episode or movie). Pure functions
│   │   ├── items.py           Item graph: get-or-create show/season/episode/movie, link files, merge, cleanup
│   │   ├── matcher.py         TMDB matching + metadata/artwork fill + refresh + merge duplicates
│   │   ├── tmdb.py            TMDB HTTP client (Bearer or api_key), throttle/retry, image cache download
│   │   ├── probe.py           ffprobe discovery + JSON → compact summary (codecs, resolution, HDR + DV profile, tracks)
│   │   ├── stream.py          Playback plan (direct play / direct stream file|remux / transcode), FFmpeg remux,
│   │   │                      video transcode (encoder detection, GPU decode, filter chain, tone-mapping,
│   │   │                      transcode_cmd, hls_cmd);
│   │   │                      music: plan_audio() + audio_cmd() (any audio → AAC fMP4)
│   │   ├── music.py           Music: parse_track() (tags + folder layout), link_track(), rollup(), fill_artwork()
│   │   ├── music_match.py     Music identification: match_album/match_artist/match_music_library (MusicBrainz & co.)
│   │   ├── musicbrainz.py     HTTP clients: MusicBrainz (1 req/s, shared), Cover Art Archive, Wikidata/Wikipedia/Commons
│   │   ├── hls.py             HLS conversion sessions: segments on demand, FFmpeg restarts, reaper, conversion limit
│   │   ├── jobs.py            run_scan() (scan + match/identify + record) and the Scheduler (worker + timer threads)
│   │   └── fsbrowse.py        Server-side folder listing for the UI folder picker (names only)
│   └── tests/                 pytest: 142 tests, see §7
│
├── web/                       ── React 19 + Vite + TypeScript UI ──────────────────────────
│   ├── index.html · vite.config.ts (port 5173, /api proxy → :8484, polling watcher) · tsconfig.json
│   ├── public/                favicon.png, brand/ (logo cut-outs used by the sidebar)
│   └── src/
│       ├── main.tsx           Mount: BrowserRouter > SettingsProvider > App; font import
│       ├── App.tsx            Routes + layout (Sidebar, ConfigBanner, TopBar); /play/:id is full-screen
│       ├── api.ts             fetch wrapper (ApiError) + TypeScript types for every server shape
│       ├── useApi.ts          useApi<T>(path) → {data, error, loading, reload}
│       ├── settings.tsx       SettingsProvider: server TMDB status (configured/last4), serverError
│       ├── music.tsx          MusicProvider/useMusic: the one <audio>, queue, play/seek (file vs transcode), Media Session
│       ├── tmdb.ts            keyKind() (token vs api key), TMDB signup URL
│       ├── format.ts          sxe(), fmtRuntime(), fmtSize(), seasonsLabel(), subLabel(), PLAY_LABEL
│       ├── styles.css         Whole theme: palette tokens (from the logo), layout, every component
│       ├── components/
│       │   ├── Sidebar.tsx    Logo, Home, one link per real library, Settings
│       │   ├── TopBar.tsx     Search box (live → /search), "Scanning…" pill from /api/status
│       │   ├── ConfigBanner.tsx  "TMDB key not configured" → /settings#tmdb; "can't reach server"
│       │   ├── Row.tsx        Horizontal shelf with arrow buttons
│       │   ├── Cards.tsx      PosterCard, AlbumCard (square, hover-play), ArtistCard (round), ItemCard, PlayBadge
│       │   ├── NowPlaying.tsx Bottom bar: track, prev/play/next, seek, volume, queue panel, stop
│       │   ├── MusicFixMatch.tsx  Modal: MusicBrainz search → POST /api/items/{id}/music-match
│       │   ├── MusicSettings.tsx  Music identification on/off card
│       │   ├── TranscodeSettings.tsx  Playback card: encoder in use, conversion limit
│       │   ├── Art.tsx        Poster / Backdrop with gradient fallback when there's no artwork
│       │   ├── FolderPicker.tsx  Modal: browse server folders via /api/fs/browse
│       │   ├── FixMatch.tsx   Modal: TMDB search → POST /api/items/{id}/match
│       │   ├── TmdbSettings.tsx  TMDB key card (save = server-verified; test; replace; remove)
│       │   └── Icon.tsx       Inline SVG icon set
│       └── pages/
│           ├── Home.tsx       Hero + rows built from /api/items and /api/libraries; empty states
│           ├── Library.tsx    /library/:id grid, sort, genre chips (music libraries → MusicLibrary)
│           ├── Detail.tsx     /title/:id: show (season tabs → episodes) or movie (TechInfo, Download); music → MusicDetail
│           ├── Music.tsx      MusicLibrary (Artists/Albums tabs), artist page, album page + TrackList, Fix match
│           ├── Player.tsx     /play/:id: <video>, file/remux/transcode modes, HLS (hls.js on demand), canDecode() fallback, quality menu, controls, keyboard
│           ├── Search.tsx     /search?q= (shows & movies, artists, albums, tracks)
│           └── Settings.tsx   Libraries (add/edit/scan/remove, unrecognised files) + TMDB card + music identification
│
├── deploy/linux/bams.service  Hardened systemd unit (ProtectSystem=strict → media read-only by kernel)
├── branding/logo/             Owner-supplied logo + transparent cut-outs (re-rendered by tools/brand_art)
├── branding/archive/          Old comic-style concept logos (PNGs gitignored, contact sheet kept)
├── tools/brand_art/rework.py  Redraws the logo set via local ComfyUI (render candidates → finalize picks)
└── data/                      (gitignored) dev data dir: bams.db, images/, logs/, transcode/ (HLS segments, wiped at start)
```

## 2. Architecture

```
 Browser (React, web/dist served by the server at :8484, or Vite :5173 with /api proxy)
     │  JSON over /api/*     media bytes: /stream (Range) · /remux · /transcode (FFmpeg pipes) · /api/hls (segments)
     ▼
 app.py (FastAPI) ── per-request SQLite connection (db.connect)
     │                                   │
     │ library.py (CRUD, validation)     │ Scheduler (jobs.py)
     │ matcher.py (Fix match)            │   timer thread: every 30 s, queue libraries that are due
     │ stream.py, hls.py (playback)      │   worker thread: run_scan() one library at a time
     ▼                                   ▼
 SQLite (data/bams.db)  ◄──────  run_scan = scanner.scan_library → matcher.match_library (if TMDB key)
 Image cache (data/images/tmdb/…,      music: → music.fill_artwork → music_match (MusicBrainz, CAA, Wikimedia)
              data/images/music/…)  ◄── tmdb.image() / music._store_image()   │
                                                                    ▼
 Media folders (READ-ONLY) ◄── readonly.walk / open_ro / quick_hash · probe (ffprobe) · stream (ffmpeg)
                               audit hook blocks any write inside them
```

**Startup** (`app.bootstrap`): create the data dir → migrate the schema → install the audit hook → register
library roots as protected. Then `create_app` starts the Scheduler in the FastAPI lifespan.

## 3. Data model (`db.py`, schema v3)

| Table | Holds | Key columns |
|---|---|---|
| `settings` | key/value | `tmdb_key`, `tmdb_verified_at`, `language`, `music_lookup` ("1"/"0", default on), `max_transcodes` (0 = automatic) |
| `libraries` | a library | `name` (unique), `type` movie\|show\|music, `scan_interval_hours`, `last_scan_at/status` |
| `library_roots` | its folders | `library_id`, `path` (absolute, as given) |
| `items` | **what something is** | `kind` movie\|show\|season\|episode\|artist\|album\|track, `parent_id` (season→show, episode→season, album→artist, track→album), music: `sort_title`, `disc_number`, `track_number`, `artist` (track performer if not the album artist), `duration` (s), `mbid` (MusicBrainz release/artist/recording), `extra` (JSON: release group, type, Wikipedia link, photo credit…); `title`, `parsed_title`, `title_key`, `year`, `season_number`, `episode_number`, metadata (`overview`, `genres` JSON, `rating`, `runtime`, `air_date`, `tagline`), ids (`tmdb_id`, `imdb_id`, `tvdb_id`), art (`poster`, `backdrop`, `still` = paths under data/images), `match_status` pending\|matched\|unmatched\|manual, `match_score`, `metadata_at` |
| `item_keys` | grouping aliases | (`library_id`, `kind`, `title_key`, `year`) → `item_id`; survives merges so renamed folders keep joining the same show |
| `files` | **actual files** | `root_id` + `rel_path` ('/'-separated, relative to root), `size`, `mtime_ns`, `quick_hash`, `parse` JSON (incl. `v` = parser version), `probe` JSON, `available`, `missing_since` |
| `file_items` | file ↔ items | many-to-many: one file can be several episodes; a movie can have several files (versions) |
| `scans` | scan history | `trigger`, `status` ok\|partial\|error, `stats` JSON |

Schema changes: bump `SCHEMA_VERSION` and add a step to `db.MIGRATIONS` (`{version: fn}`). New databases are
created at v1 and run every step too, so each step is exercised by every test. Before migrating an existing DB,
`migrate()` copies it to `data/backups/bams-schema-v{N}-{time}.db`. v2 rebuilt `items` (SQLite can't change a
CHECK constraint) with foreign keys off; v3 only adds columns. Music items: tracks are 1:1 with files (Plex-style);
albums are found by `(parent_id=artist, title_key)` from the *parsed* title, so renaming an album to its
MusicBrainz title doesn't break grouping; artists use `item_keys` (`kind='artist'`).

## 4. Key flows

### 4.1 Scan (`jobs.run_scan` → `scanner.scan_library`)
1. For each root: `readonly.root_status`. If it's offline → skip it (its files are **not** marked missing).
2. `readonly.walk` (no symlinked dirs, skips OS junk and nested extras folders) → `FileEntry(rel, size, mtime)`.
3. Diff against `files`: unchanged → touch `last_seen` (and re-parse if `PARSER_VERSION` is newer). Changed →
   reset probe and re-parse. New → `quick_hash`. If it can't be opened, it's counted as "busy" and retried next scan.
4. New file whose hash and size match a vanished file → **moved**: the row is updated in place.
5. Each parse → `parse.parse(rel, lib_type)` → `items.link_file` (get-or-create show/season/episode or movie
   through `item_keys`). Unrecognised files stay indexed, unlinked (and are listed by `/unrecognized` with a hint).
6. Vanished files → `available=0` (never deleted). `items.cleanup_orphans`.
7. ffprobe every unprobed available file (4 threads) → `files.probe`.
8. If a TMDB key exists → `matcher.match_library`.

### 4.1b Music scan (`scanner.scan_library` with a music library)
Walk with `AUDIO_EXTS` (no extras-folder skipping) → diff as above, but new/changed/moved files are **not** linked
yet → ffprobe (8 threads) → `music.parse_track(rel, probe)` (tags first, then the folder layout) →
`music.link_track` (artist/album get-or-create, the track row is reused per file) → `cleanup_orphans` →
`music.rollup` (album year/duration/genres, artist genres; matched albums keep MusicBrainz's year). Then in
`jobs.run_scan`: `music.fill_artwork` (folder images, else the embedded picture via FFmpeg to a pipe; only albums
whose tracks changed since `metadata_at`), then `music_match.match_music_library` if `music_lookup` is on.
`music.PARSER_VERSION` is separate from `parse.PARSER_VERSION`.

### 4.2 Match (`matcher.match_title`)
1. Explicit id in path (`{tmdb-}` / `{imdb-}` / `{tvdb-}`) → `/find`; else `search_tv`/`search_movie`, retried
   without the year → `best_match` (title similarity + year ±, threshold `ACCEPT=0.80`).
2. Below threshold → `match_status='unmatched'`, stop.
3. Details (+external_ids) → images downloaded **before** the DB transaction → `_apply_title`.
4. `_merge_duplicate`: if another item already has this TMDB id, `items.merge_titles` folds this one in.
5. Shows: `_apply_seasons` (season + episode titles, overviews, stills; missing episodes → 'unmatched').
6. Later scans refresh only what's pending or older than `REFRESH_AFTER` (150 days, under TMDB's 6-month limit).

### 4.3 Playback (`stream.plan` → `Player.tsx`)
`file_info()` embeds `playback = {method, mode, url, transcode_url, video_codec, audio_codec, duration}`:
- `mode:"file"` → `<video src=/api/files/{id}/stream>`: the original bytes; the browser seeks with Range.
- `mode:"remux"` (browser-OK video, but AC3/EAC3/DTS/TrueHD/PCM… audio, or a container the browser can't open)
  → `<video src=/api/files/{id}/remux?t=X>`. FFmpeg runs `-ss X -c:v copy -c:a aac -ac 2` → fragmented MP4 on
  stdout, streamed by an async generator. The process is killed when the client disconnects. To seek, the
  player asks `/seek?t=X` for the real start (an FFmpeg dry run reports the first keyframe it lands on), sets
  `offset`, and reloads `src`. The clock shows `offset + currentTime` and the duration comes from the probe.
- `mode:"transcode"` (video no browser decodes: `stream.video_copyable()` is false for Xvid, MPEG-2, VC-1, 10-bit
  H.264…). Both outputs share `stream._transcode_parts`: `hwaccel_args` (GPU decoding with a GPU encoder) +
  `transcode_filters` (bwdif for interlaced frames → square pixels + size cap: 4K on a GPU encoder, 1080p on the
  CPU, lower with `max_height` from the quality menu → `tonemap_mode`: libplacebo for Dolby Vision, zscale/tonemap
  for HDR10/HLG → the encoder's pixel format) + `video_encoder()` with quality-based settings capped by
  `quality_bitrate`. Two outputs:
  - **HLS (what the player uses)**, see 4.3c.
  - **fMP4 fallback** (no MSE and no native HLS, or no duration known): `<video src=/api/files/{id}/transcode?t=X&h=>`,
    `transcode_cmd` → fragmented MP4 on stdout, a keyframe every 2 s. Re-encoding makes the seek exact, so the player
    just restarts at `?t=` (no `/seek`).
- `video_encoder()` test-encodes a tiny clip with each of `ENCODERS` (NVENC, QSV, AMF, VAAPI on Linux, libx264,
  Media Foundation on Windows) once per FFmpeg and caches the first that works; `BAMS_VIDEO_ENCODER` forces one.
  The app warms it in a thread at startup; `/api/status.video_encoder` reports it. `has_libplacebo()` likewise
  test-runs libplacebo once (it needs Vulkan).
- HEVC/AV1/VP9 are pass-through on the server (only the browser knows if it decodes them). `Player.tsx`
  `canDecode()` asks `MediaSource.isTypeSupported` (and `dvh1` for Dolby Vision profile 5); if no, or the video
  errors / has no picture, it switches to the conversion from the current position. Picking a size in the quality
  menu converts any video (choice kept in `localStorage` `bams.quality`).
- No FFmpeg → every mode falls back to `"file"` (best effort). FFmpeg's stderr (`-loglevel error`) is logged.

### 4.3c HLS conversions (`hls.py`)
`POST /api/files/{id}/hls {height?}` → `Transcodes.create` (refuses with `Busy` → 503 at the limit) → a `Session`
with a folder `data/transcode/<id>/` → `{id, playlist}`. The playlist (`Session.playlist`) lists every
`SEGMENT`-second (4 s) segment `k.ts` up front (VOD), from the probed duration. `GET /api/hls/{id}/{k}.ts` →
`Transcodes.segment` (blocking, runs in the thread pool):
- on disk → served. Missing but within `SOON` of what the running FFmpeg is making → waited for. Otherwise FFmpeg
  is restarted at k: `stream.hls_cmd` (`-ss k*4 -copyts -start_at_zero`, keyframes forced every 4 s from there,
  scene-cut/periodic keyframes off, `-output_ts_offset 10`, hls muxer with `-start_number k`, `temp_file`). Kept
  timestamps + aligned keyframes = segments from different runs line up.
- `wanted` = the last segment asked for. A request superseded by a seek (wanted moved, its segment not coming)
  gives up with 409 rather than restarting FFmpeg and fighting the newer request.
- The reaper thread (every 2 s, `reap`): stops FFmpeg once it has made `AHEAD` (15) segments past `wanted`
  (restarted when the player gets there), deletes segments more than `KEEP_BEHIND` (75) from `wanted`, closes
  sessions idle for `IDLE` (90 s). The player DELETEs its session when it leaves (also on `pagehide`).
- The limit (`settings.max_transcodes`, 0 = automatic: 4 GPU / 2 CPU) counts open sessions + running fMP4
  transcodes (`add_pipe`). A session keeps its place however often FFmpeg restarts.
- `data/transcode/` is wiped at startup and on shutdown. The player loads hls.js with a dynamic `import()` only
  when it needs it; Safari without MSE gets the playlist natively.

### 4.3b Music playback (`stream.plan_audio` → `music.tsx`)
`GET /api/items/{id}/tracks` returns the play queue of an artist/album/track with `playback` per track:
`mode:"file"` (MP3, AAC, FLAC, Ogg Vorbis/Opus/FLAC, WAV: `/api/files/{id}/stream`) or `mode:"transcode"`
(`/api/files/{id}/audio?t=X`: FFmpeg → AAC 256k stereo, fragmented MP4; ≤48 kHz). Audio seeks are sample-accurate,
so the player just restarts at `?t=` and offsets its clock. `MusicProvider` (in `main.tsx`, above the router)
keeps one `<audio>` alive across pages; `App.tsx` pauses it when `/play/:id` (video) opens.

### 4.4 Read-only guard (`readonly.py`)
`install_guard()` adds `sys.addaudithook(_hook)`, which raises `ReadOnlyViolation` for write-mode `open`,
`os.remove/rename/mkdir/rmdir/chmod/chown/utime/truncate/link/symlink…`, `shutil.copy*/move/rmtree`,
`tempfile.mk*`, `sqlite3.connect` targeting a path inside any root in `_roots` (normcased abspath + realpath).
`library.refresh_guard()` updates the roots after every library change. FFmpeg/ffprobe subprocesses are outside
the hook but only read (output goes to a pipe). The OS layer is in deploy/ and docs/READ-ONLY.md.

### 4.4b Music identification (`music_match.py`)
Albums (pending, or unmatched on a rematch scan) first: a `musicbrainz_albumid` tag → lookup; else
`search_releases(album, artist)` (retried without the artist) → `best_release` (title 0.6 + artist 0.4, ± track
count, + year, + official; `ACCEPT=0.85`) → `release` lookup (recordings + release-group url-rels) → CAA cover only
if no local art → Wikidata → Wikipedia summary → one transaction: title, original year, overview, `mbid`, `extra`,
track `mbid`s, titles for tracks whose `parse.source=="path"`, and the artist's MusicBrainz id when the credit is
clearly them. Then artists: that id, or an exact, unambiguous name search → artist lookup (url-rels) → Wikidata
(P18 photo, sitelinks) → Wikipedia summary + Commons photo with credit (only if no local art) → `sort_title` =
MusicBrainz sort name. "Various Artists"/"Unknown Artist" are never looked up. Five service errors in a row stop
the run (rest waits for the next scan). All network calls happen outside transactions. MusicBrainz is throttled
process-wide (`_mb_lock`), so Fix match and the scan worker together stay at 1 request/second.
`link_track` keeps a matched track's title when the file has no title tag; `rollup` keeps a matched album's year.

### 4.5 TMDB key
UI `TmdbSettings` → `PUT /api/settings/tmdb-key` (server verifies with `/3/authentication`; a 401 → 400 and it isn't
saved) → `settings.tmdb_key`. `GET /api/settings` returns only `{configured, kind, last4, verified_at}`.
CLI alternative: `bams tmdb-key` (hidden prompt). Images are fetched with a separate client that never sends the key.

## 5. HTTP API (`app.py`)

| Route | Purpose | Used by (web) |
|---|---|---|
| `GET /api/status` | version, data dir, ffprobe/ffmpeg paths, `video_encoder` `{id,name,hardware,hw_decode}`, `transcodes` `{running,limit}`, TMDB configured, guard, scan running/queued | TopBar, Settings |
| `GET /api/settings` | TMDB status (never the key) | SettingsProvider |
| `PUT /api/settings/tmdb-key` · `DELETE` · `POST …/test` | save (verified) / remove / re-check | TmdbSettings |
| `GET /api/fs/browse?path=` | list server folders (drives/mounts when no path) | FolderPicker |
| `GET/POST /api/libraries` · `GET/PATCH/DELETE /api/libraries/{id}` | CRUD; PATCH with add/remove paths triggers a scan | Settings, Sidebar, Home |
| `POST /api/libraries/{id}/scan[?rematch=true]` → `{accepted, running, queued}` | queue a scan | Settings |
| `GET /api/scans?library_id=` | current + history | — |
| `GET /api/libraries/{id}/items?sort=&kind=&q=&match_status=` | shows, movies, or (music) `kind=artist\|album\|track`; `sort=artist` for albums | Library, MusicLibrary |
| `GET /api/items?kind=show,movie&sort=&q=&genre=&limit=` | across all libraries; `kind` may also list artist/album/track | Home, Search, Detail ("more like this") |
| `GET /api/items/{id}` | detail + `ancestors` + `children` (with `child_count`) + `files` (probe, playback) + `ids.musicbrainz` + `extra` | Detail, Player, Music pages |
| `GET /api/items/{id}/tracks` | play queue of an artist/album/track, each with `playback` | Music pages, NowPlaying |
| `GET /api/musicbrainz/search?kind=album\|artist&q=&artist=` · `POST /api/items/{id}/music-match {mbid}` | music Fix match | MusicFixMatch |
| `PUT /api/settings/music-lookup {enabled}` (state in `GET /api/settings` → `music_lookup`) | identification on/off | MusicSettings |
| `PUT /api/settings/transcoding {max_transcodes}` (state in `GET /api/settings` → `max_transcodes`, `max_transcodes_auto`) | conversion limit | TranscodeSettings |
| `GET /api/libraries/{id}/unrecognized` | unplaced files + `hint` | Settings |
| `GET /api/tmdb/search?kind=&q=` · `POST /api/items/{id}/match {tmdb_id}` | Fix match | FixMatch |
| `GET /api/files/{id}/stream` · `/download` | original bytes (Range) / attachment | Player, Detail |
| `GET /api/files/{id}/remux?t=&audio=` · `/seek?t=` | audio-converting stream / its real start | Player |
| `GET /api/files/{id}/transcode?t=&audio=&h=` | video → H.264 + audio → AAC (fMP4), starting exactly at `t` (fallback; 503 at the limit) | Player |
| `POST /api/files/{id}/hls {height?, audio?}` → `{id, playlist}` | open an HLS conversion (503 at the limit, 409 if not probed) | Player |
| `GET /api/hls/{sid}/index.m3u8` · `GET /api/hls/{sid}/{k}.ts` · `DELETE /api/hls/{sid}` | playlist / segment (made on demand; 409 superseded, 504 too slow) / close | Player (hls.js) |
| `GET /api/files/{id}/audio?t=` | music converted to AAC (fMP4) from `t` | music.tsx |
| `GET /api/images/{path}` | cached artwork (path-traversal checked) | everywhere |
| everything else | `web/dist` with SPA fallback (`SpaFiles`) | — |

Errors: `library.LibraryError` → 400 `{detail}`; the UI shows `detail` verbatim, so write messages for humans.

## 6. Configuration

| Setting | Where |
|---|---|
| Data dir | `--data-dir` > `BAMS_DATA_DIR` > systemd `STATE_DIRECTORY` > `%LOCALAPPDATA%\BAMS` / `~/.local/share/bams` (`config.default_data_dir`) |
| Host/port | `bams serve --host --port` (default 127.0.0.1:8484; warns on non-localhost because there's no auth) |
| ffprobe / ffmpeg | PATH, winget package folder, `BAMS_FFPROBE` / `BAMS_FFMPEG` |
| Video encoder | auto-detected (`stream.ENCODERS`); `BAMS_VIDEO_ENCODER=h264_nvenc\|h264_qsv\|h264_amf\|h264_vaapi\|libx264\|h264_mf`; VAAPI device `BAMS_VAAPI_DEVICE` (default `/dev/dri/renderD128`) |
| GPU decoding | on with a GPU encoder (`stream.hwaccel_args`); `BAMS_HWACCEL=none` turns it off, or names a method (`cuda`, `d3d11va`, `vaapi`…) |
| Conversion limit | Settings → Playback (`settings.max_transcodes`); HLS tuning constants at the top of `hls.py` |
| Web UI dir | `../web/dist` relative to the package (repo checkout) |
| Indexed extensions | `config.VIDEO_EXTS` (FORMATS.md §1), `config.AUDIO_EXTS` (FORMATS.md §5) |
| Music art file names | `config.ALBUM_ART_NAMES`, `ARTIST_ART_NAMES`, `ART_EXTS` |
| Music identification | `settings.music_lookup`; MusicBrainz User-Agent in `musicbrainz.USER_AGENT` |
| Skipped folders | `config.SKIP_DIRS` (anywhere), `config.EXTRAS_DIRS` (only inside a title folder) |

## 7. Tests (`server/tests/`)

| File | Covers |
|---|---|
| `conftest.py` | `env` fixture (data dir + media dir + connection; resets guard roots), `unguarded` (temporarily lift the guard to mutate a media tree), `make_tree()` |
| `test_readonly.py` | 15 write attempts must all raise and leave the tree byte-identical; reads allowed; full scan leaves media untouched; root validation |
| `test_parse.py` | real-world names: scene packs, Plex layout, friend's quoted format, multi-ep, ranges, id tags, release-tag brackets, movies |
| `test_scanner.py` | grouping, idempotent rescan, moved file keeps its row, deleted → flagged, offline root, movie versions |
| `test_matcher.py` | fake TMDB (httpx.MockTransport): match, merge of two folders, episode fill, unmatched, no key sent to the image CDN |
| `test_api.py` | library CRUD/validation, fs browse, SPA fallback, key never returned, cross-thread connection, movie-in-TV-library hint |
| `test_stream.py` | playback plan table (incl. transcode cases, Hi10P, no FFmpeg); encoder detection (order, platform, override, cache); transcode filter chain + command, tone-map choice, GPU decode args, HLS command, DV profile from ffprobe; a real FFmpeg remux of a generated AC3 file and a real Xvid → H.264 transcode through the API (skipped if FFmpeg/an encoder is missing) |
| `test_hls.py` | HLS sessions against a fake FFmpeg (on-demand restarts, superseded requests, failures, stop-ahead + pruning, idle close, limit), a real Xvid HLS conversion through the API (segments from two FFmpeg runs line up), settings API |
| `test_music.py` | music path/tag parsing, tag normalisation, codec names, scanning/moves/parser bumps, a real FLAC/ALAC/MP3 album (tags, embedded + folder art, transcode stream, media untouched), `plan_audio`, v1→v3 migration |
| `test_music_match.py` | identification against fake MusicBrainz/CAA/Wikimedia (`httpx.MockTransport`): matching, tag ids, unmatched/ambiguous, rescans keep data, local art wins, service down, settings toggle + Fix match API |

## 8. Where to change X

| I want to… | Go to |
|---|---|
| Recognise a new naming pattern | `parse.py` (+ a case in `test_parse.py`, bump `PARSER_VERSION`) |
| Change how files group into shows | `items.get_or_create_title`, `parse.title_key` |
| Tune TMDB matching | `matcher.score`, `matcher.best_match`, `ACCEPT` |
| Add an API field the UI needs | serialiser in `app.py` (`item_summary`/`item_detail`/`file_info`) + type in `web/src/api.ts` |
| Add a page | `web/src/pages/*.tsx` + route in `App.tsx` (+ Sidebar link) |
| Change playback rules or codecs | `stream.plan` / `stream.video_copyable` (+ `test_stream.py`, FORMATS.md) |
| Tune transcode quality / size / encoders | `stream._encoder_args`, `_max_bitrate`, `_box`, `QUALITIES`, `ENCODERS`, `transcode_filters` |
| Tune HLS (segment length, read-ahead, disk window, idle time) | `stream.SEGMENT`; `AHEAD`, `SOON`, `KEEP_BEHIND`, `IDLE`, `WAIT` in `hls.py` |
| Which codecs the browser is asked about | `canDecode()` in `web/src/pages/Player.tsx` |
| Add a file type to index | `config.VIDEO_EXTS` / `config.AUDIO_EXTS` + FORMATS.md |
| Recognise a new music folder/file layout | `music.parse_track` / `_clean_title` (+ a case in `test_music.py`, bump `music.PARSER_VERSION`) |
| Which music formats play as-is | `stream.BROWSER_AUDIO_FILES` (+ `test_plan_audio`, FORMATS.md §5) |
| Tune music matching | `music_match.score_release`, `ACCEPT`; artist rule in `match_artist` |
| Add a music metadata source | `musicbrainz.py` (client) + `music_match.py` (apply) + credit in `pages/Music.tsx` `About` |
| Add a DB column/table | `db.SCHEMA` + `SCHEMA_VERSION` + migration step |
| Anything that touches media files | **only** through `readonly.py`; never write; keep `test_readonly.py` green |
| Theme / colours | `:root` tokens at the top of `web/src/styles.css` |

## 9. Conventions

- Tests never touch the network: real-service code gets a `transport=` (`httpx.MockTransport`), and music
  `run_scan` calls in tests pass `do_match=False`.
- Server: stdlib `sqlite3` (no ORM). Explicit `Tx` for multi-statement writes. Network calls happen **outside**
  transactions. Comment the *why*. Type hints throughout. No new dependency without checking its license.
- Web: function components + hooks. No state library, no CSS framework. Fetch via `api.ts`/`useApi`. All
  colours come from CSS tokens. Real data only, with empty states.
- Cross-platform: `pathlib`/`os.path`, POSIX-style `rel_path` in the DB, `normcase` comparisons for roots.
