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
├── .claude/launch.json        Preview-pane servers: "web" (Vite :5173), "bams-test" (a scratch server on :8485)
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
│   │   ├── __main__.py        CLI entry (`python -m bams …` / `bams …`): serve, library, scan, tmdb-key, user, status
│   │   ├── app.py             FastAPI app: bootstrap, serialisers, LoginRequired middleware, ALL HTTP routes, SPA hosting
│   │   ├── auth.py            Accounts: scrypt hashes, users CRUD (last-admin rules), sessions (hashed tokens), Throttle
│   │   ├── devices.py         Apps on other devices (the TV): LinkCodes (code + secret, approve, poll), Tickets (signed
│   │   │                      media-path tickets), split_ticket_path, TV_AGENT
│   │   ├── security.py        Sign-in waits/lockout + sign-in log (security.db), IP allow/block policy, Gate middleware (IP check + traffic record)
│   │   ├── netflow.py         Traffic log: background writer of JSON-lines files under a size cap, backwards reader/search, folder check
│   │   ├── watch.py           Watch state: record_progress, set_watched, annotate (counts), next_episode, continue_watching, thresholds (admin settings)
│   │   ├── subtitles.py       Subtitle tracks (embedded + sidecars incl. VobSub .idx/.sub, language labels), WebVTT
│   │   │                      conversion + cache, shift(), burn_source() (what stream paints on)
│   │   ├── config.py          Data-dir resolution, Paths, ports, VIDEO_EXTS, AUDIO_EXTS, art file names, skip-folder lists
│   │   ├── db.py              SQLite schema (v1 + migration steps to v8), connect(), migrate(), Tx, settings, JSON helpers
│   │   ├── readonly.py        Read-only media access + the audit-hook guard + walker (+ side files) + quick_hash + read_text
│   │   ├── library.py         Library CRUD, folder validation, guard refresh, describe() for the API, order (ORDER, listed, reorder)
│   │   ├── scanner.py         scan_library(): walk → diff → parse → link → probe (music: probe before parse/link)
│   │   ├── parse.py           Filename/folder → Parsed (show/season/episode or movie). Pure functions; `_show_dir` picks the folder that names the show
│   │   ├── items.py           Item graph: get-or-create show/season/episode/movie, link files, merge, cleanup
│   │   ├── identify.py        Files identified by hand (files.manual): parsed_for() (scanner), store(), TMDB/IMDb link lookup, names for suggestions
│   │   ├── matcher.py         TMDB matching + metadata/artwork fill + refresh + merge duplicates
│   │   ├── tmdb.py            TMDB HTTP client (Bearer or api_key), throttle/retry, image cache download
│   │   ├── probe.py           ffprobe discovery + JSON → compact summary (codecs, resolution, HDR + DV profile, sar +
│   │   │                      field_order via geometry(), tracks); video_geometry() for older probes
│   │   ├── stream.py          Playback plan (direct play / direct stream file|remux / transcode), FFmpeg remux,
│   │   │                      video transcode (encoder detection, GPU decode, all-GPU filters for NVENC/QSV/
│   │   │                      VAAPI/AMF + failure memory, output_size, filter chain, tone-mapping, subtitle burn-in,
│   │   │                      transcode_cmd, hls_cmd), keyframes() + hls_copy_cmd; Dolby pass-through (PASSTHROUGH_AUDIO);
│   │   │                      music: plan_audio() + audio_cmd() (any audio → AAC fMP4, or FLAC)
│   │   ├── music.py           Music: parse_track() (tags + folder layout), parse_cue_tracks(), link_tracks(), album_alias(),
│   │   │                      rollup(), fill_artwork() (folder art wins, picked up when added later; poster_src)
│   │   ├── cue.py             CUE sheets: parse() → CueSheet/CueFile/CueTrack (start/end s), file_for(), splits()
│   │   ├── playlists.py       Imported .m3u/.m3u8/.pls: parse(), import_files() (per root, follows the files), resolve() (entries → tracks)
│   │   ├── music_match.py     Music identification: match_album/match_artist/match_music_library (MusicBrainz & co.),
│   │   │                      merge_same_release/merge_albums, refresh after REFRESH_AFTER
│   │   ├── musicbrainz.py     HTTP clients: MusicBrainz (1 req/s, shared), Cover Art Archive, Wikidata/Wikipedia/Commons
│   │   ├── hls.py             HLS sessions of variants (sizes / copy): segments on demand, restarts, reaper, limit, Keyframes cache
│   │   ├── jobs.py            run_scan() (scan + match/identify + record) and the Scheduler (worker + timer threads, scan progress)
│   │   └── fsbrowse.py        Server-side folder listing for the UI folder picker (names only)
│   └── tests/                 pytest: 268 tests, see §7
│
├── web/                       ── React 19 + Vite + TypeScript UI ──────────────────────────
│   ├── index.html · vite.config.ts (port 5173, /api proxy → :8484, polling watcher) · tsconfig.json
│   ├── public/                favicon.png, brand/ (logo cut-outs used by the sidebar)
│   └── src/
│       ├── main.tsx           Mount: BrowserRouter > AuthProvider > SettingsProvider > MusicProvider > App; font import
│       ├── auth.tsx           AuthProvider/useAuth: sign-in + first-admin screens until signed in; re-keyed per user
│       ├── App.tsx            Routes + layout (Sidebar, ConfigBanner, TopBar); /play/:id is full-screen
│       ├── api.ts             fetch wrapper (ApiError; a 401 fires SIGNED_OUT) + TypeScript types for every server shape
│       ├── useApi.ts          useApi<T>(path) → {data, error, loading, reload}
│       ├── settings.tsx       SettingsProvider: server TMDB status (configured/last4), serverError
│       ├── music.tsx          MusicProvider/useMusic: the one <audio>, queue, play/seek (file vs transcode), Media Session
│       ├── tmdb.ts            keyKind() (token vs api key), TMDB signup URL
│       ├── homeRows.ts        Home's rows: defaultRows(libs, genres) (default order, labels; one `genre:<name>` row per genre) + homeRows(saved, libs, genres) (user order merged with what exists; an old `genres` entry expands in place)
│       ├── format.ts          sxe(), fmtRuntime(), fmtSize(), seasonsLabel(), subLabel(), PLAY_LABEL
│       ├── styles.css         Whole theme: palette tokens (from the logo), layout, every component
│       ├── components/
│       │   ├── Sidebar.tsx    Logo, Home, one link per library in the admin's order (admins drag to reorder), Settings
│       │   ├── useReorder.ts  Drag-to-reorder hook (pointer + arrow keys, drop line): music queue, sidebar libraries, Home rows
│       │   ├── TopBar.tsx     Search box (live → /search), "Scanning…" pill from /api/status, account menu
│       │   ├── AccountSettings.tsx  Your account (password + confirm, sign out) + admins' "Who can sign in" (users CRUD)
│       │   ├── HomeSettings.tsx  Your Home page: banner pref + rows on/off and order (drag/arrow keys/▲▼), reset → `home_rows` pref
│       │   ├── PasswordInput.tsx  Password field with a show/hide button (sign-in, setup, accounts)
│       │   ├── WatchSettings.tsx  Playback card: "started after" seconds and "watched at" %
│       │   ├── SecuritySettings.tsx  Settings → Security: wrong-password threshold, account locks, IP lists, sign-in log, traffic log
│       │   ├── Identify.tsx   UnrecognizedFiles list (all libraries or one) + IdentifyForm (link lookup, fields with suggestions, undo)
│       │   ├── Combo.tsx      Text field with as-you-type suggestions (keyboard + mouse)
│       │   ├── ConfigBanner.tsx  "TMDB key not configured" (admins) → /settings#tmdb; "can't reach server"
│       │   ├── Row.tsx        Horizontal shelf with arrow buttons
│       │   ├── Cards.tsx      PosterCard (+ WatchMarks), ContinueCard (picture → play, name → show, episode line →
│       │   │                  its season), AlbumCard, ArtistCard, ItemCard, PlayBadge
│       │   ├── NowPlaying.tsx Bottom bar: track, prev/play/next, seek, volume, queue panel (drag/arrow-key reorder), stop
│       │   ├── MusicFixMatch.tsx  Modal: MusicBrainz search → POST /api/items/{id}/music-match
│       │   ├── MusicSettings.tsx  Music identification on/off + converted-music format (AAC/FLAC) card
│       │   ├── TranscodeSettings.tsx  Playback card: encoder in use, CPU/GPU choice (EncoderChoice), conversion limit
│       │   ├── Art.tsx        Poster / Backdrop with gradient fallback when there's no artwork
│       │   ├── FolderPicker.tsx  Modal: browse server folders via /api/fs/browse
│       │   ├── FixMatch.tsx   Modal: TMDB search → POST /api/items/{id}/match
│       │   ├── TmdbSettings.tsx  TMDB key card (save = server-verified; test; replace; remove)
│       │   └── Icon.tsx       Inline SVG icon set
│       └── pages/
│           ├── Home.tsx       Hero + rows (Continue Watching, Recently Added, libraries, Top Rated, one row per genre from /api/genres) in the user's order (homeRows.ts)
│           ├── Library.tsx    /library/:id grid, sort, genre chips; admins: Unrecognized tab (?tab=unrecognized) (music libraries → MusicLibrary)
│           ├── Detail.tsx     /title/:id[?season=<season id>]: show (season tabs → episodes, watched toggles) or movie (Resume, TechInfo); music → MusicDetail
│           ├── Music.tsx      MusicLibrary (Artists/Albums/Playlists tabs), artist page, album page + TrackList, Fix match,
│           │                  PlaylistPage (/playlist/:id), PlaylistCard + cover Mosaic
│           ├── Player.tsx     /play/:id (keyed by id): file/remux/transcode, HLS (copy remux, Auto ABR), resume + progress, up-next
│           │                  (at the end and CREDITS = 30 s before it; next-episode button), skip +30 / −10 s (SKIP_*),
│           │                  sound / subtitles / quality menus, canDecode() fallback, keyboard
│           ├── Search.tsx     /search?q= (shows & movies, artists, albums, tracks)
│           └── Settings.tsx   Admins: libraries, unrecognized files, TMDB, music, playback, accounts. Viewers: their account only
│
├── tv/                       ── Samsung TV app (Tizen web app, React + Vite + TS; tv/README.md) ─────────
│   ├── tizen/config.xml       Manifest (app id BAMSmedia1.BAMS, privileges, pointing-device-support off) + icon.png
│   ├── vite.config.ts         Build as ONE classic deferred script (IIFE, ES2019): Tizen loads it from file://
│   ├── scripts/wgt.mjs        Stage dist + manifest, sign with Tizen Studio profile (TIZEN_PROFILE, "BAMS"), --install/--run/--release
│   └── src/
│       ├── App.tsx            Phases (connect → link → main), screen stack + focus restore, the one keydown handler
│       ├── api.ts             Server address, bearer token, fetch wrapper, media ticket + media() URL rewriting
│       ├── nav.ts             Spatial navigation (arrows → nearest focusable; rows remember focus; [data-group]/[data-entry]/[data-trap])
│       ├── tizen.ts           Key codes, registerKeys, exit, device name, the TV's IP (webapis, else tizen.systeminfo)
│       ├── engine.ts          AvplayEngine (webapis.avplay) / VideoEngine (<video> + hls.js) behind one interface
│       ├── plan.ts            What the TV decodes (TV caps vs BROWSER caps) → direct / remux / convert; pickFile, pickAudio
│       ├── prefs.ts           Per-TV settings (always convert, DTS, languages, subtitle delay)
│       ├── Rail.tsx · Cards.tsx · Icon.tsx · format.ts · keys.ts · styles.css (1920×1080 10-foot UI)
│       └── screens/           Connect, Link (code + QR / password), Home, Library, Detail, Search, Settings, Player
├── web/public/help/tmdb.html   TMDB key guide with screenshots (img/), served at /help/tmdb.html; linked from TmdbSettings
├── deploy/                    Installers (see deploy/README.md; user guide docs/INSTALL.md)
│   ├── build.py               `build.py windows|deb|all [--skip-web] [--version X]` → dist/BAMS-Setup-<v>.exe, dist/bams_<v>_all.deb
│   ├── pins.json              pinned downloads + SHA-256: embeddable Python, WinSW, FFmpeg (fetched by the .exe, never bundled)
│   ├── requirements.txt       locked Python packages with hashes (uv pip compile --universal); used by both installers
│   ├── windows/bams.iss       Inno Setup script: install/update/uninstall, FFmpeg download, WinSW service, firewall, data-dir ACL
│   ├── windows/bams.cmd       installed CLI wrapper (BAMS_DATA_DIR=%ProgramData%\BAMS); bams.ico, wizard-small.png
│   ├── linux/debian/          control, postinst (user pick, /etc/default/bams, drop-in, venv from wheels, ufw), prerm, postrm
│   ├── linux/bams             /usr/bin/bams wrapper (runs as the service account); bams.desktop, bams.png
│   └── linux/bams.service     Hardened systemd unit (ProtectSystem=strict → media read-only by kernel), settings from /etc/default/bams
├── branding/logo/             Owner-supplied logo + transparent cut-outs (re-rendered by tools/brand_art)
├── branding/archive/          Old comic-style concept logos (PNGs gitignored, contact sheet kept)
├── tools/brand_art/rework.py  Redraws the logo set via local ComfyUI (render candidates → finalize picks)
└── data/                      (gitignored) dev data dir: bams.db, images/, logs/, backups/, cache/ (subtitles, keyframes),
                               transcode/ (HLS segments, wiped at start)
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

**Every request** first passes `security.Gate` (outermost ASGI middleware): addresses the IP lists keep out get 403,
and every request, allowed or blocked, goes to the traffic log (`netflow.Netflow.record`, written by a background
thread) when it finishes.

**Every request to `/api/`** passes `LoginRequired` (plain ASGI middleware): the `bams_session` cookie, else an
`Authorization: Bearer` token (the TV app), else a media ticket path `/api/t/<ticket>/files|hls|images/…` (GET only;
the path is rewritten to the real one, so routes and the traffic log never see the ticket) → `lookup_digest()`
(cached a minute per token, cleared on sign-out / password / user changes) → `auth.session_user` → the user dict in
`request.state.user` (+ `state.session` = the session's digest), else 401. Non-GET cookie requests whose Origin isn't this
host get 403 (bearer requests can't be forged by another site). `CORSMiddleware` (`*`, no credentials) sits between
`LoginRequired` and `Gate`. Routes take
`me=Depends(current_user)`; admin routes have `dependencies=ADMIN`. Public: `/api/auth/state|login|setup`, the
web UI, `/docs`.

## 3. Data model (`db.py`, schema v8)

| Table | Holds | Key columns |
|---|---|---|
| `settings` | key/value | `tmdb_key`, `tmdb_verified_at`, `language`, `music_lookup` ("1"/"0", default on), `music_output` ("aac" default \| "flac": what unplayable music is converted to), `max_transcodes` (0 = automatic), `watched_percent` (default 90), `resume_after` (s, default 30), `video_encoder` (an `stream.ENCODERS` id; absent = automatic) |
| `libraries` | a library | `name` (unique), `type` movie\|show\|music, `scan_interval_hours`, `last_scan_at/status`, `sort_order` (v7: the admin's order; `library.ORDER`) |
| `library_roots` | its folders | `library_id`, `path` (absolute, as given) |
| `items` | **what something is** | `kind` movie\|show\|season\|episode\|artist\|album\|track, `parent_id` (season→show, episode→season, album→artist, track→album), music: `sort_title`, `disc_number`, `track_number`, `artist` (track performer if not the album artist), `duration` (s), `mbid` (MusicBrainz release/artist/recording), `extra` (JSON: release group, type, Wikipedia link, photo credit, `matched_by` tag\|search\|manual…), `poster_src` (v8, JSON: where the poster came from: `{from: folder, file, size, mtime_ns}` \| `embedded` \| `caa` \| `commons`, or `{from: null, checked}`); `title`, `parsed_title`, `title_key`, `year`, `season_number`, `episode_number`, metadata (`overview`, `genres` JSON, `rating`, `runtime`, `air_date`, `tagline`), ids (`tmdb_id`, `imdb_id`, `tvdb_id`), art (`poster`, `backdrop`, `still` = paths under data/images), `match_status` pending\|matched\|unmatched\|manual, `match_score`, `metadata_at` |
| `item_keys` | grouping aliases | (`library_id`, `kind`, `title_key`, `year`) → `item_id`; survives merges so renamed folders keep joining the same show. Merged albums: `kind='album'`, `title_key` = `music.album_alias(artist, album)` ("artistkey\|albumkey", names not ids) |
| `files` | **actual files** | `root_id` + `rel_path` ('/'-separated, relative to root), `size`, `mtime_ns`, `quick_hash`, `parse` JSON (incl. `v` = parser version; `manual: true` when identified by hand; music: `cues` = the folder's cue sheets as [rel, size, mtime], `cue` = {sheet, tracks} when split), `probe` JSON (`pv` = `probe.PROBE_VERSION`; `cuesheet` when the tags hold one), `available`, `missing_since`, `manual` (v6: JSON identification entered by hand, used instead of the name) |
| `file_items` | file ↔ items | many-to-many: one file can be several episodes; a movie can have several files (versions); a CUE image is several tracks, `cue_start`/`cue_end` (v8, s; end NULL = to the end of the file); a merged album's track can have several files |
| `playlists` | imported playlists (v8) | `library_id`, `root_id` + `rel_path` of the playlist file, `name`, `size`/`mtime_ns` (re-read when they change), `entries` JSON as written ({path, title, duration}), `missing` |
| `playlist_items` | playlist → tracks (v8) | (`playlist_id`, `position`) → `item_id`; rebuilt by `playlists.resolve` after every scan |
| `scans` | scan history | `trigger`, `status` ok\|partial\|error, `stats` JSON |
| `users` | accounts | `name` (unique, NOCASE), `password` (scrypt string from `auth.hash_password`), `is_admin`, `last_login_at`, `prefs` (v5: JSON display preferences, `auth.PREFS`) |
| `sessions` | signed-in browsers | `token` = SHA-256 of the cookie value, `user_id`, `last_seen_at` (sliding 30 days, refreshed hourly) |
| `watch_state` | a user's state of a movie/episode | (`user_id`, `item_id`), `position` (s; 0 = start/finished), `duration`, `watched`, `play_count`, `last_watched_at` |

Schema changes: bump `SCHEMA_VERSION` and add a step to `db.MIGRATIONS` (`{version: fn}`). New databases are
created at v1 and run every step too, so each step is exercised by every test. Before migrating an existing DB,
`migrate()` copies it to `data/backups/bams-schema-v{N}-{time}.db`. v2 rebuilt `items` (SQLite can't change a
CHECK constraint) with foreign keys off; v3 only adds columns; v4 adds `users`, `sessions`, `watch_state`. v8 adds CUE columns, `poster_src`, playlists. Music items: tracks are 1:1 with files (Plex-style) except CUE images
(one file, many tracks) and merged albums (one track, several files);
albums are found by `(parent_id=artist, title_key)` from the *parsed* title, so renaming an album to its
MusicBrainz title doesn't break grouping; artists use `item_keys` (`kind='artist'`).

## 4. Key flows

### 4.1 Scan (`jobs.run_scan` → `scanner.scan_library`)
1. For each root: `readonly.root_status`. If it's offline → skip it (its files are **not** marked missing).
2. `readonly.walk` (no symlinked dirs, skips OS junk and nested extras folders) → `FileEntry(rel, size, mtime)`.
3. Diff against `files`: unchanged → touch `last_seen` (and re-parse if `PARSER_VERSION` is newer). Changed →
   reset probe and re-parse. New → `quick_hash`. If it can't be opened, it's counted as "busy" and retried next scan.
4. New file whose hash and size match a vanished file → **moved**: the row is updated in place.
5. Each parse → `identify.parsed_for` (the file's `manual` identification, else `parse.parse(rel, lib_type)`) →
   `items.link_file` (get-or-create show/season/episode or movie through `item_keys`; an unnumbered file in a season
   folder becomes an episode with no number, found again by title). Unrecognised files stay indexed, unlinked
   (listed by `/unrecognized` with a hint). Walking and hashing happen **outside** transactions; writes go in
   batches of 200, so other writers (logins, adding a library) never wait on the disks.
6. Vanished files → `available=0` (never deleted). `items.cleanup_orphans`.
7. ffprobe every unprobed available file (4 threads) → `files.probe`, saved in batches of 200 as results arrive.
   Every step reports `progress(step, done, total, bytes_done, bytes_total)` ("Looking for files", "Adding new
   files", "Reading file details", "Reading tags", then "Matching on TMDB" / "Identifying albums…"); the Scheduler
   keeps it in `/api/status` → `scans.running` with `step_elapsed`, and Settings shows N of M, size and time left.
8. If a TMDB key exists → `matcher.match_library`.

### 4.1b Music scan (`scanner.scan_library` with a music library)
Walk with `AUDIO_EXTS` (no extras-folder skipping) → diff as above, but new/changed/moved files are **not** linked
yet → ffprobe (8 threads) → `music.parse_track(rel, probe)` (tags first, then the folder layout) →
`music.link_tracks` (artist/album get-or-create via `_album`, which checks merge aliases first; track rows reused per
file, by track number for CUE files) → `cleanup_orphans` → `music.rollup` (album year/duration/genres, artist genres;
matched albums keep MusicBrainz's year) → `playlists.resolve`. The walk also collects **side files** (`.cue`, images,
playlists: `readonly.walk(side_exts, side)`, kept in `ScanStats.side` by folder): `sheet_for` picks the cue sheet
that splits a file (`.cue` next to it, else a CUESHEET tag) → `music.parse_cue_tracks`; an unchanged file whose
folder's cue sheets changed (`parse.cues`) is re-read; files ≥ 10 min probed before `PROBE_VERSION` 2 are probed
again; `playlists.import_files` per root. Then in `jobs.run_scan`: `music.fill_artwork(side)` (each album's best
folder image vs `poster_src`: new/changed → replaces any art; else the embedded picture via FFmpeg, only when a track
changed since the last look; same for `artist.jpg`, which drops a Commons credit), then
`music_match.match_music_library` if `music_lookup` is on.
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
`file_info()` embeds `playback = {method, mode, url, transcode_url, video_codec, audio_codec, duration}`. A movie's/episode's
files that no scan has probed yet are probed when `GET /api/items/{id}` is asked (`app._probe_now`), so playback never
runs on the file-name guess with no duration (no HLS, no timeline, no saved position):
- `mode:"file"` → `<video src=/api/files/{id}/stream>`: the original bytes; the browser seeks with Range.
- `mode:"remux"` (browser-OK video, but AC3/EAC3/DTS/TrueHD/PCM… audio, or a container the browser can't open; the
  player also uses it for another audio track than the first) → **HLS with the video copied** (4.3c, `remux:true`),
  else (no MSE/native HLS, or keyframes unreadable → 409) the live stream `<video src=/api/files/{id}/remux?t=X>`. FFmpeg runs `-noaccurate_seek -ss X -c:v copy -c:a aac -ac 2` (`-noaccurate_seek`: the audio starts at the same keyframe as the copied video, not exactly at X, or the picture runs behind) (or `-c:a copy`
  with `passthrough`, + `delay_moov`, see Dolby below) → fragmented MP4 on
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
- Audio: `file_info.audio_tracks` (labels via `subtitles.language`); every converting endpoint takes the track
  (`audio`) and a channel wish (`ch`/`channels` 6 → `stream.audio_channels`: 5.1 AAC 384k if the track has ≥ 6
  channels, else stereo 192k). The player picks: remembered language → browser language → default-flagged track.
- GPU: `stream.gpu_filters()` keeps SDR, non-burn conversions of GPU-decodable codecs on the GPU. NVENC:
  `-hwaccel cuda` + `bwdif_cuda`/`scale_cuda` (size and pixel shape worked out per frame). Quick Sync: `-hwaccel qsv`
  + `vpp_qsv`; VAAPI: `-hwaccel vaapi` + `deinterlace_vaapi=auto=1`/`scale_vaapi`; AMF (Windows): `-hwaccel d3d11va
  -hwaccel_output_format d3d11` + `vpp_amf` (`_GPU_DECODER`, `_GPU_SCALER`, `_gpu_filter_chain`). Those three get the
  size as numbers (`stream.output_size`, from the probe's `sar`) and a deinterlacer only when `stream.interlaced()`
  says so; they need `sar`/`field_order` in the probe (`app._video` reads them with `probe.video_geometry` for older
  probes). Interlaced on AMF and unknown scan type on QSV → hybrid. A failed HLS run sets `Variant.gpu=False`, retries
  on the hybrid path, and `stream.gpu_failed()` remembers that encoder + codec/profile/bit depth until restart
  (`_gpu_broken`). The live `/transcode` uses only NVIDIA's all-GPU path (it can't retry). QSV/AMF/VAAPI untested on
  real hardware.
- **Dolby pass-through:** `Player.tsx` `canPassThrough()` asks `MediaSource.isTypeSupported('audio/mp4;
  codecs="ac-3"|"ec-3"')`; if yes (and `bams.passthrough` isn't "0") a remux sends `passthrough` →
  `app._copy_audio` (track codec in `stream.PASSTHROUGH_AUDIO` = AC3/EAC3) → `-c:a copy` in `remux_cmd` /
  `hls_copy_cmd` (`Session.copy_audio`). A media error then → `passFailed`, the same stream with AAC from there.
  Conversions always output AAC.

### 4.3c HLS sessions (`hls.py`)
`POST /api/files/{id}/hls {remux?, auto?, height?, audio?, channels?, burn?, passthrough?, start?}` → `Transcodes.create` →
a `Session` (`data/transcode/<sid>/`) of one or more **variants** (`Variant`, folder `<sid>/<v>/`), each with its own
FFmpeg, `bounds` (segment start times), `wanted`, `job_start`:
- a fixed size → one conversion variant; `auto` → `hls.ladder()`: full size + 1080/720/480 below it (hls.js ABR,
  `capLevelToPlayerSize`); `burn` (track id or embedded stream number → `app._burn`) → `stream._transcode_parts(burn=)`;
- `remux` → one **copy** variant (`ts`: MPEG-TS segments `{k}.ts`, no `init.mp4`; the TV app asks for it, Samsung's AVPlay
  plays no fMP4 HLS): bounds = every keyframe (`Keyframes.get` → `stream.keyframes`, cached as
  `data/cache/keyframes/{file}-{size}-{mtime}.json`), segments `{k}.m4s` + `init.mp4`, made by `hls_copy_cmd`. Before
  each run `_restart` dry-runs the seek (`remux_start(zero=True)`) and numbers from where it lands. Copy sessions don't
  count against the limit. `passthrough` (AC3/EAC3 track) → `Session.copy_audio`: audio copied too.
`GET /api/hls/{sid}/index.m3u8` = master playlist (one `STREAM-INF` per variant) → `/{v}/index.m3u8` (VOD, every
segment listed up front) → `/{v}/{k}.ts|m4s` → `Transcodes.segment(s, v, k)` (blocking, thread pool):
- on disk → served. Missing but within `SOON` of what the running FFmpeg is making → waited for. Otherwise FFmpeg
  is restarted at k: `stream.hls_cmd` (`-ss k*4 -copyts -start_at_zero`, keyframes forced every 4 s from there,
  scene-cut/periodic keyframes off, `-output_ts_offset 10`, hls muxer with `-start_number k`, `temp_file`). Kept
  timestamps + aligned keyframes = segments from different runs line up.
- `wanted` = the last segment asked for. A request superseded by a seek (wanted moved, its segment not coming)
  gives up with 409 rather than restarting FFmpeg and fighting the newer request.
- The reaper thread (every 2 s, `reap`): stops a variant's FFmpeg once it's `AHEAD` (60 s) past `wanted` (restarted
  when the player gets there) or when another variant was asked for and this one not for `SWITCHED` (10 s), deletes
  segments more than `KEEP` (300 s) from `wanted`, closes sessions idle for `IDLE` (90 s). The player DELETEs its session when it leaves (also on `pagehide`).
- The limit (`settings.max_transcodes`, 0 = automatic: 4 GPU / 2 CPU) counts open sessions + running fMP4
  transcodes (`add_pipe`). A session keeps its place however often FFmpeg restarts.
- `data/transcode/` is wiped at startup and on shutdown. The player loads hls.js with a dynamic `import()` only
  when it needs it; Safari without MSE gets the playlist natively.

### 4.3d Subtitles (`subtitles.py`)
`file_info(with_subtitles=True)` (a movie's/episode's own page) lists `subtitles.tracks()`: embedded streams `e{n}`
then sidecars `x{n}` (`Name.srt`, `Name.en.forced.srt`… in the video's folder, listed with `os.scandir`). A VobSub
pair (`Name.idx` with `Name.sub` beside it) gives one picture track per `id:` line of the .idx (`x{n}-{k}`,
`vobsub_streams`, read with `readonly.open_ro`; language from the .idx, else the file name). Text tracks
have a `url` → `GET /api/files/{id}/subtitles/{track}.vtt?shift=` → `subtitles.webvtt` (FFmpeg → WebVTT, cached in
`data/cache/subtitles/`; sidecars decoded UTF-8/UTF-16/cp1252 and copied as UTF-8 into the cache first) → `shift()`
for live streams. The player adds a `<track>` and sets its mode. Image tracks (`image:true`) are burned in: the player
sends the track id as `burn` (HLS) / `sub` (`/transcode`); `app._burn` → `subtitles.burn_source` = the embedded
stream number, or `(sidecar .idx, k)`. The overlay reads `[1:s:n]` from a second input: the same file seeked
`SUB_LEAD` (30 s) earlier, or the .idx (always, even from 0). Both outputs keep the file's clock with `-copyts
-start_at_zero` (the fMP4 transcode then `-output_ts_offset -t`); the .idx has no start time, so it needs no offset.

### 4.3e Watch state (`watch.py`)
The player PUTs `/api/items/{id}/progress {position, duration}` every 10 s, on pause, on leaving (keepalive) and at
the end; only after playback really started (`duration` null if unknown). Until something played, the player's position is
the start it's about to resume from (`startAt`), so a stream that fails early (copy-HLS → live remux) keeps the resume point. `record_progress`: ≥ 90% → watched, position 0, `play_count` +1 once
per viewing; else position (< 10 s → 0). `PUT …/watched` marks a movie/episode or all episodes of a season/show.
`watch.annotate` adds `progress` to movies/episodes and `episodes`/`unwatched` to shows/seasons in every item list
(batched). `/api/continue` = `continue_watching()` (recent activity: resume ≥ 30 s; per show, the most recent activity
decides: resume it, or the next unwatched episode via `next_episode`; episodes carry `show` and `season_id` for the
card's links). `get_item` adds `next_id` for episodes (the player's up-next countdown, shown at the end and from 30 s
before it, and its next-episode button; leaving from the countdown or "Play now" reports the episode as finished). `items.merge_titles` moves watch state to the kept item.

### 4.3b Music playback (`stream.plan_audio` → `music.tsx`)
`GET /api/items/{id}/tracks` (and `/api/playlists/{id}` → `tracks`) returns a play queue built by `app._queue`:
one file per track (available, then playable as-is, then biggest), `start`/`end` for CUE tracks, `playback` per
track: `mode:"file"` (MP3, AAC, FLAC, Ogg Vorbis/Opus/FLAC, WAV: `/api/files/{id}/stream`) or `mode:"transcode"`
(`/api/files/{id}/audio?t=X`: FFmpeg → AAC 256k stereo fMP4 ≤48 kHz, or with `music_output=flac` FLAC (24-bit kept,
≤96 kHz, channels kept), `playback.output` says which). Audio seeks are sample-accurate, so the player restarts at
`?t=` and offsets its clock. `MusicProvider` (in `main.tsx`, above the router) keeps **two** `<audio>` elements alive
across pages: the next track is loaded into the idle one `PRELOAD_BEFORE` (20 s) before the end and started at the
end (a timer armed `ARM_BEFORE` from the element's clock where the end is known: CUE end or a file's duration;
`ended` otherwise); only the active element's events count. CUE tracks: seek to `start`, move on at `end`;
consecutive CUE tracks of one file (`continuous()`) keep the same stream. `App.tsx` pauses music when `/play/:id`
(video) opens.

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
After an album match, `merge_same_release` folds other albums of the library with the same release into the oldest,
when both are pinned (`_pinned`: Fix match, `extra.matched_by` tag/manual, or score ≥ `MERGE_SCORE` 0.95):
`merge_albums` moves tracks (same disc + number + similar title → one track with both files), adds the
`album_alias`, deletes an emptied artist. Then up to `REFRESH_PER_SCAN` (50) matched albums/artists older than
`REFRESH_AFTER` (120 days) are looked up again (`refresh=True`: keeps status, score, `matched_by`; re-downloads art
only when `poster_src` is caa/commons; a 404 just bumps `metadata_at`). A merged-away MusicBrainz id is replaced by
the id MusicBrainz answers with.

### 4.4c Accounts (`auth.py`)
`GET /api/auth/state` → `{user, setup, setup_here}`. No users → the UI shows "create your admin account", which
`POST /api/auth/setup` accepts only from loopback (else `bams user add NAME --admin`). `POST /api/auth/login` →
`authenticate` (constant-ish time for unknown names) → `new_session` → cookie `bams_session` (HttpOnly, Lax,
30 days, Secure on https). `Throttle`: 10 failures / 10 min per address → 429. Password changes and resets delete the
user's sessions. Last admin can't be demoted/removed; nobody removes themselves.

### 4.4e Security (`security.py`, `netflow.py`)
Outside `bams.db`: `security.db` (data dir) has `login_state` (`key` = `u<id>` or `n:<casefolded name>`,
`failures`, `last_fail`, `locked_at`, `locked_by` NULL = wrong passwords / admin name) and `auth_log` (`event`
sign-in|lock|unlock, `result` ok|failed|admin, name, user_id, ip, reason, user_agent; newest `AUTH_LOG_KEEP` kept).
Settings in `bams.db` `settings`: `lockout_threshold`, `ip_mode`, `ip_allow`, `ip_block`, `netflow_dir`,
`netflow_max_bytes`.
Login (`app.auth_login`): same-origin → `Throttle` (per address) → `Security.attempt(key)` lock → `refusal()`
(locked → 403, waiting → 429 + Retry-After; neither counted) → `authenticate` → wrong: `failed()` (count, lock at the
threshold) → 401/403; right: `succeeded()` (count back to 0). Every outcome → `Security.log`. `wait_after(n)` = 2^(n-1) s.
IP policy: `IpPolicy.allowed(host)`: loopback always; block list wins; `allowlist` mode needs an allow match.
`Security.load_policy()` on save and every 10 s from `Gate`. `save_policy` refuses to block the saver.
Traffic log: `Netflow` files `netflow-<ms>.jsonl`, rotated at `segment_size(cap)` (cap/10, 1–256 MB), `_trim` deletes the
oldest past the cap; `read(q, before, limit)` walks backwards (`_lines_backwards`), cursor `"<file>:<offset>"`.
Recovery CLI: `bams user unlock NAME`, `bams security allow-all`.

### 4.4d Identify by hand (`identify.py`)
Settings → Unrecognized files (`GET /api/unrecognized`) and a library's Unrecognized tab list unplaced files (hint +
the parser's `guess`) and hand-identified ones (`manual`). The form loads `GET /api/libraries/{id}/names` once for its
suggestions (`Combo.tsx`). A pasted link → `POST /api/identify/lookup` → `identify.lookup`: TMDB URLs carry the id
(+ season/episode), IMDb ids go through TMDB `/find` (episode → show + numbers); wrong library type refused.
`PUT /api/files/{id}/identify` → `identify.store` (in one transaction: `files.manual`, `parse` rewritten from it incl.
`ids.tmdb`, relink, orphan cleanup) → `matcher.match_title` with the TMDB id (or a search if the title is still
pending). `DELETE` clears it and re-parses from the name.

### 4.5 TMDB key
UI `TmdbSettings` → `PUT /api/settings/tmdb-key` (server verifies with `/3/authentication`; a 401 → 400 and it isn't
saved) → `settings.tmdb_key`. `GET /api/settings` returns only `{configured, kind, last4, verified_at}`.
CLI alternative: `bams tmdb-key` (hidden prompt). Images are fetched with a separate client that never sends the key.
Saving a key queues a scan of every TV/movie library (`tmdb-key+rematch`), so titles indexed before the key get matched
at once. The how-to-get-a-key guide is a static page, `web/public/help/tmdb.html` (built into `dist/help/`).

### 4.6 Installed copies (`deploy/`)
**Windows** (`{app}` = `C:\Program Files\BAMS`): `python\` (embeddable; `._pth` = `python313.zip`, `.`, `..\lib`,
`..pp`), `lib\` (locked packages), `appams\` (+ `web\`), `ffmpegin\` (downloaded by the installer;
`probe.app_ffmpeg_dir` finds it next to the interpreter), `serviceams-service.exe` (WinSW 2.12) + `bams-service.xml`
(written by the installer, read at every service start: `python -m bams serve --host … --port 8484`,
`BAMS_DATA_DIR=C:\ProgramData\BAMS`). Service `BAMS`, LocalSystem, automatic. **Linux:** `/opt/bams/lib/bams` (+ `web`),
`/opt/bams/wheels`, venv `/opt/bams/venv` (made by `postinst`, `bams.pth` → `/opt/bams/lib`), unit
`/usr/lib/systemd/system/bams.service` + drop-in `/etc/systemd/system/bams.service.d/10-user.conf` (User/Group from
`/etc/default/bams`), data `/var/lib/bams`. Updates: see deploy/README.md "How updates keep everything".

## 5. HTTP API (`app.py`)

| Route | Purpose | Used by (web) |
|---|---|---|
| `GET /api/auth/state` · `POST /api/auth/login {name,password}` · `POST /api/auth/logout` · `POST /api/auth/setup` · `PUT /api/auth/password {current,new}` | signing in, first admin (loopback), own password | auth.tsx, AccountSettings |
| `GET /api/hello` (public) · `POST /api/auth/token {name,password,device}` (public) → `{token, user}` | find a BAMS server; sign an app in (bearer token, no cookie) | tv |
| `POST /api/devices/link {name}` (public) → `{code, secret, expires_in}` · `POST /api/devices/link/poll {secret}` (public) → `{status}` or `{status: linked, token, user}` · `POST /api/devices/approve {code}` · `GET /api/devices` · `DELETE /api/devices/{id}` | TV link codes; your linked TVs, sign one out | tv, TvSettings, LinkTv |
| `GET /api/media-ticket` → `{prefix, expires_in}` | `/api/t/<ticket>`: media URLs for players and `<img>` that can't send headers | tv |
| `GET/POST /api/users` · `PATCH/DELETE /api/users/{id}` (admin) | accounts | AccountSettings |
| `GET /api/security` (admin) → `{lockout_threshold, ip{mode,allow,block}, your_ip, netflow{folder,default_folder,custom,max_bytes,bytes,files,oldest,dropped}}` | security settings + traffic-log usage | SecuritySettings |
| `PUT /api/security/lockout {threshold 1–50}` · `PUT /api/security/ip {mode, allow[{cidr,note}], block[…]}` (400 if it would block you) · `PUT /api/security/netflow {folder?, max_bytes?}` (`""` = default folder) (admin) | change them | SecuritySettings |
| `GET /api/security/accounts` · `PUT /api/security/accounts/{id}/lock {locked}` (admin) | lock state per account / lock (signs out) or unlock | SecuritySettings |
| `GET /api/security/auth-log?result=ok\|failed\|admin&before=&limit=` · `GET /api/security/netflow/entries?q=&before=&limit=` (admin) → `{entries, next}` | sign-in log / traffic log, newest first | SecuritySettings |
| `PUT /api/items/{id}/progress {position,duration}` · `PUT /api/items/{id}/watched {watched}` · `GET /api/continue` | watch state of the signed-in user | Player, Detail, Home |
| `GET /api/status` | version, data dir, ffprobe/ffmpeg paths, `video_encoder` `{id,name,hardware,hw_decode}`, `transcodes` `{running,limit}`, TMDB configured, guard, scan running/queued | TopBar, Settings |
| `GET /api/settings` | TMDB status (never the key) | SettingsProvider |
| `PUT /api/settings/tmdb-key` · `DELETE` · `POST …/test` | save (verified) / remove / re-check | TmdbSettings |
| `GET /api/fs/browse?path=` | list server folders (drives/mounts when no path) | FolderPicker |
| `PUT /api/libraries/order {ids}` (admin) → ids in the new order | library order (omitted ids keep their place after, unknown ignored) | Sidebar, Settings |
| `GET/POST /api/libraries` · `GET/PATCH/DELETE /api/libraries/{id}` | CRUD (listed in the admin's order); PATCH with add/remove paths triggers a scan | Settings, Sidebar, Home |
| `POST /api/libraries/{id}/scan[?rematch=true]` → `{accepted, running, queued}` | queue a scan | Settings |
| `GET /api/scans?library_id=` | current + history | — |
| `GET /api/libraries/{id}/items?sort=&kind=&q=&match_status=` | shows, movies, or (music) `kind=artist\|album\|track`; `sort=artist` for albums | Library, MusicLibrary |
| `GET /api/genres` | every show/movie genre `[{name, count}]`, most titles first | Home, HomeSettings (genre rows) |
| `GET /api/items?kind=show,movie&sort=&q=&genre=&limit=` | across all libraries; `kind` may also list artist/album/track | Home, Search, Detail ("more like this") |
| `GET /api/items/{id}` | detail + `ancestors` + `children` (with `child_count`) + `files` (probe, playback; a movie's/episode's unprobed files are probed now) + `ids.musicbrainz` + `extra` | Detail, Player, Music pages |
| `GET /api/items/{id}/tracks` | play queue of an artist/album/track, each with `playback`, `start`/`end` (CUE) | Music pages, NowPlaying |
| `GET /api/libraries/{id}/playlists` · `GET /api/playlists/{id}` | imported playlists (`track_count`, `duration`, `missing`, `covers`) · one with its `tracks` (queue) | MusicLibrary, PlaylistPage |
| `GET /api/musicbrainz/search?kind=album\|artist&q=&artist=` · `POST /api/items/{id}/music-match {mbid}` | music Fix match | MusicFixMatch |
| `PUT /api/settings/music-lookup {enabled}` (state in `GET /api/settings` → `music_lookup`) | identification on/off | MusicSettings |
| `PUT /api/settings/music-output {output: aac\|flac}` (admin; state in `GET /api/settings` → `music_output`) | what unplayable music is converted to | MusicSettings |
| `GET /api/settings/encoders` · `PUT /api/settings/encoder {encoder\|null}` (admin) → `{choice, active, automatic, forced, options[{id,name,hardware}]}` | CPU/GPU choice (only encoders that pass a test encode; 400 otherwise) | TranscodeSettings |
| `PUT /api/settings/transcoding {max_transcodes}` (state in `GET /api/settings` → `max_transcodes`, `max_transcodes_auto`) | conversion limit | TranscodeSettings |
| `GET /api/unrecognized` · `GET /api/libraries/{id}/unrecognized` (admin) | unplaced files (`hint`, `guess`) + hand-identified ones (`manual`), with `library_*` | Identify.tsx |
| `PUT /api/files/{id}/identify {title, year, season, episodes, episode_title, edition, tmdb_id}` · `DELETE` (admin) | identify a file by hand / forget it → `{item_id, title_id, note}` / `{recognized}` | Identify.tsx |
| `POST /api/identify/lookup {link, library_id}` · `GET /api/libraries/{id}/names` (admin) | TMDB/IMDb link → fields (409 without a key, 400 wrong type/unreadable) · names in a library for suggestions | Identify.tsx |
| `PUT /api/me/prefs {home_hero?, home_rows?: [{id, show}]}` | the signed-in user's display prefs (returned in `/api/auth/state` → `user.prefs`); only sent fields change | auth.tsx, HomeSettings |
| `PUT /api/settings/watch {watched_percent 50–100, resume_after 0–600}` (admin; state in `GET /api/settings` → `watch`) | when titles count as watched / started | WatchSettings |
| `GET /api/tmdb/search?kind=&q=` · `POST /api/items/{id}/match {tmdb_id}` | Fix match | FixMatch |
| `GET /api/files/{id}/stream` · `/download` | original bytes (Range) / attachment | Player, Detail |
| `GET /api/files/{id}/remux?t=&audio=&ch=&passthrough=` · `/seek?t=` | audio-converting live stream (fallback; `passthrough`: AC3/EAC3 copied) / its real start | Player |
| `GET /api/files/{id}/transcode?t=&audio=&h=&ch=&sub=` | video → H.264 + audio → AAC (fMP4), starting exactly at `t` (fallback; 503 at the limit). `sub` = picture track id or embedded stream number | Player |
| `POST /api/files/{id}/hls {remux?, auto?, height?, audio?, channels?, burn?, passthrough?, start?}` → `{id, playlist, variants, copy, channels, passthrough}` | open an HLS session (503 at the limit, 409 if not probed / no keyframes, 422 unknown `burn` track) | Player |
| `GET /api/hls/{sid}/index.m3u8` · `/{v}/index.m3u8` · `/{v}/init.mp4` · `/{v}/{k}.ts\|m4s` · `DELETE /api/hls/{sid}` | master / variant playlist / copy header / segment (made on demand; 409 superseded, 504 too slow) / close | Player (hls.js) |
| `GET /api/files/{id}/subtitles/{track}.vtt?shift=` | a text subtitle track as WebVTT (400 for picture tracks) | Player |
| `GET /api/files/{id}/audio?t=` | music converted to AAC (fMP4, `audio/mp4`) or FLAC (`audio/flac`, per `music_output`) from `t` | music.tsx |
| `GET /api/images/{path}` | cached artwork (path-traversal checked) | everywhere |
| everything else | `web/dist` with SPA fallback (`SpaFiles`) | — |

Every `/api/` route needs a session except `/api/auth/state|login|setup` (401 otherwise; the UI then shows the
sign-in screen). Admin-only: library changes, scans list, settings changes, fs browse, unrecognised files, TMDB/
MusicBrainz search + Fix match, users. `/api/status` hides server paths from viewers.
Errors: `library.LibraryError` → 400 `{detail}`; the UI shows `detail` verbatim, so write messages for humans.

## 6. Configuration

| Setting | Where |
|---|---|
| Data dir | `--data-dir` > `BAMS_DATA_DIR` > systemd `STATE_DIRECTORY` > `%LOCALAPPDATA%\BAMS` / `~/.local/share/bams` (`config.default_data_dir`) |
| Host/port | `bams serve --host --port` (default 127.0.0.1:8484; `0.0.0.0` for the LAN, login required) |
| Accounts | web UI (Settings → Accounts), or `bams user add NAME [--admin] \| list \| passwd NAME \| remove NAME \| unlock NAME`; session length `auth.SESSION_DAYS`, `auth.MIN_PASSWORD` |
| Security | Settings → Security: `settings.lockout_threshold` (default 5), `ip_mode`/`ip_allow`/`ip_block`, `netflow_dir` (default `data/netflow`), `netflow_max_bytes` (default 10 GB); `bams security allow-all` |
| ffprobe / ffmpeg | `BAMS_FFPROBE` / `BAMS_FFMPEG`, then the Windows installer's `<install>fmpegin` (`probe.app_ffmpeg_dir`), PATH, winget package folder |
| Video encoder | Settings → Playback (`settings.video_encoder`, `stream.set_preferred`), else auto-detected (`stream.ENCODERS`); `BAMS_VIDEO_ENCODER=h264_nvenc\|h264_qsv\|h264_amf\|h264_vaapi\|libx264\|h264_mf`; VAAPI device `BAMS_VAAPI_DEVICE` (default `/dev/dri/renderD128`) |
| GPU decoding | on with a GPU encoder (`stream.hwaccel_args`); `BAMS_HWACCEL=none` turns it off, or names a method (`cuda`, `d3d11va`, `vaapi`…) |
| All-GPU filters (NVIDIA, Quick Sync, VAAPI, AMF) | on for SDR GPU-decodable codecs (`stream.gpu_filters`); `BAMS_GPU_FILTERS=0` turns them off; `BAMS_HWACCEL` other than auto / the encoder's own method turns them off too |
| Conversion limit | Settings → Playback (`settings.max_transcodes`); HLS tuning constants at the top of `hls.py` |
| Web UI dir | `bams/web` inside the package (installed copies), else `../web/dist` (repo checkout); `__main__._web_dir` |
| Installed service settings | Windows: tasks in the installer (rewritten into `serviceams-service.xml`); Linux: `/etc/default/bams` (`BAMS_USER`, `BAMS_HOST`, `BAMS_PORT`) + `sudo dpkg-reconfigure bams` |
| Indexed extensions | `config.VIDEO_EXTS` (FORMATS.md §1), `config.AUDIO_EXTS` (FORMATS.md §5) |
| Music art file names | `config.ALBUM_ART_NAMES`, `ARTIST_ART_NAMES`, `ART_EXTS` |
| Music identification | `settings.music_lookup`; MusicBrainz User-Agent in `musicbrainz.USER_AGENT` |
| Skipped folders | `config.SKIP_DIRS` (anywhere), `config.EXTRAS_DIRS` (only inside a title folder) |

## 7. Tests (`server/tests/`)

| File | Covers |
|---|---|
| `conftest.py` | `env` fixture (data dir + media dir + connection; resets guard roots), `unguarded` (temporarily lift the guard to mutate a media tree), `make_tree()`, `signed_in(app, name, admin)` (a TestClient with an account, signed in: every API test needs it) |
| `test_devices.py` | /api/hello, link codes (approve, used/wrong codes, throttle, expiry), token sign-in, bearer requests, cookie cross-site still refused, CORS without credentials, media tickets (media-only, GET-only, forged/expired, end with the session), traffic log shows the real path |
| `test_auth.py` | hashing, 401 everywhere, first admin only from loopback, sign in/out, throttle, viewer 403s, users CRUD + last-admin rules, own password, cross-site refusal, v4 migration |
| `test_security.py` | waits doubling + 429 not counted, lockout + unlock (API, CLI), reset on success, threshold, unknown names alike, admin lock signs out, sign-in log filter/paging, IP rules (v4/v6/mapped) + API + self-block refusal + `allow-all`, traffic log (every/blocked request, user, bytes), size cap + paging + search, folder/size settings. A `clock` fixture patches `security.now` |
| `test_watch.py` | progress / 90% rule / play count, mark show watched, Continue Watching + next episode (seasons, specials, `season_id`), per user, merges keep state, threshold settings, per-user prefs, Home rows pref (order, dedupe, validation) |
| `test_identify.py` | unrecognised list + names, identify (episode / extra), rescan keeps it, undo, validation + viewer 403, TMDB/IMDb link lookup against a fake TMDB |
| `test_subtitles.py` | language names, sidecar matching + labels, VobSub sidecar listing (languages from the .idx, lone .idx/.sub ignored), shift, real SRT/cp1252 sidecar through the API (media untouched), a hand-written PGS track and a VobSub sidecar burned in (HLS from 0 and mid-line, live stream mid-line) |
| `vobsub.py` (helper) | writes `.idx` + `.sub` pairs from 2-bit bitmaps (pictures split over 2048-byte packs), for tests and test media |
| `test_readonly.py` | 15 write attempts must all raise and leave the tree byte-identical; reads allowed; full scan leaves media untouched; root validation |
| `test_parse.py` | real-world names: scene packs, nested packs (megapack/show/S03/release/…), Plex layout, friend's quoted format, multi-ep, ranges, id tags, release-tag brackets, extras with the season in their name, Series-N folders, movies |
| `test_scanner.py` | grouping, idempotent rescan, moved file keeps its row, deleted → flagged, offline root, movie versions, no write lock while walking/hashing, unnumbered extras in season folders (+ merge), progress reports (done/total/bytes) + Scheduler record |
| `test_matcher.py` | fake TMDB (httpx.MockTransport): match, merge of two folders, episode fill, unmatched, no key sent to the image CDN, exact title beats a wrong year, franchise-prefix tail rule |
| `test_api.py` | library CRUD/validation, fs browse, SPA fallback, key never returned, saving a key queues TV/movie libraries, cross-thread connection, movie-in-TV-library hint, library order + v7 migration |
| `test_stream.py` | audio channels, burn-in + GPU filter commands (NVENC; QSV/VAAPI/AMF chains, interlaced/unknown, failure memory), output_size with SAR, probe sar/field_order, copy-HLS command (temp_file, audio copy), a real remux over HLS (+ AC3 pass-through over HLS and live) through the API (5.1 AAC, segments from two runs line up); playback plan table (incl. transcode cases, Hi10P, no FFmpeg); encoder detection (order, platform, override, cache), encoder choice (fallback, env wins, API, restart); transcode filter chain + command, tone-map choice, GPU decode args, HLS command, DV profile from ffprobe; a real FFmpeg remux of a generated AC3 file, the live remux's audio starting at the keyframe (correlation with the original), an unprobed file probed when its episode is opened, and a real Xvid → H.264 transcode through the API (skipped if FFmpeg/an encoder is missing) |
| `test_hls.py` | playlists (master, copy), ladder; sessions against a fake FFmpeg (on-demand restarts, start position, superseded requests, failure → GPU-less retry, stop-ahead + pruning, Auto switch, copy numbering from the dry run, idle close, limit), keyframe cache, a real Xvid HLS conversion through the API, settings API |
| `test_music.py` | music path/tag parsing, tag normalisation, codec names, scanning/moves/parser bumps, a real FLAC/ALAC/MP3 album (tags, embedded + folder art, transcode stream, media untouched), `plan_audio`, v1→v3 migration |
| `test_music_extras.py` | cue parsing, CUE image split / sheet edited or removed, queue `start`/`end`, real FLAC with an embedded sheet; playlist parsing, import, follow-the-file; a cover/artist image added later vs CAA/Commons; album merge + rescan + best file, unsure matches not merged; refresh; FLAC command + API |
| `test_music_match.py` | identification against fake MusicBrainz/CAA/Wikimedia (`httpx.MockTransport`): matching, tag ids, unmatched/ambiguous, rescans keep data, local art wins, service down, settings toggle + Fix match API |

## 8. Where to change X

| I want to… | Go to |
|---|---|
| Recognise a new naming pattern | `parse.py` (+ a case in `test_parse.py`, bump `PARSER_VERSION`) |
| Change how files group into shows | `items.get_or_create_title`, `parse.title_key` |
| Tune TMDB matching | `matcher.score` (tail-of-ours rule), `matcher.best_match`, `matcher.choose` (exact title vs wrong year), `ACCEPT`, `EXACT` |
| Make failed TMDB matches get retried | bump `matcher.MATCHER_VERSION` (per-library setting `matcher_version:<id>`, `jobs.should_rematch`); one-off: `POST /api/libraries/{id}/scan?rematch=true` |
| Change which folder names the show | `parse._show_dir` (season folder → the folder above; else deepest season-pack folder), `parse._folder_year` |
| Add an API field the UI needs | serialiser in `app.py` (`item_summary`/`item_detail`/`file_info`) + type in `web/src/api.ts` |
| Add a page | `web/src/pages/*.tsx` + route in `App.tsx` (+ Sidebar link) |
| Change playback rules or codecs | `stream.plan` / `stream.video_copyable` (+ `test_stream.py`, FORMATS.md) |
| Tune transcode quality / size / encoders | `stream._encoder_args`, `_max_bitrate`, `_box`, `QUALITIES`, `ENCODERS`, `transcode_filters` |
| Change how libraries are ordered | `library.ORDER` / `listed` / `reorder`; UI `Sidebar.tsx`, Settings ▲▼ |
| Add a scan step to the progress display | call `progress(step, done, total, bytes_done, bytes_total)`; units per step in `unitOf()` (`Settings.tsx`) |
| Tune HLS segment length | `stream.SEGMENT` (conversions; copies follow the file's keyframes) |
| Which codecs the browser is asked about | `canDecode()` in `web/src/pages/Player.tsx` |
| Which audio may pass through untouched | `stream.PASSTHROUGH_AUDIO` + `PASS_TYPES` in `Player.tsx` (must go into MP4 cleanly) |
| All-GPU path for an encoder | `stream._GPU_DECODER`, `_GPU_SCALER`, `gpu_filters`, `_gpu_filter_chain` (+ `test_all_gpu_filters_…`) |
| How the TV app signs in / opens media | `devices.py` (`LinkCodes`, `Tickets`, `MEDIA_PREFIXES`), `LoginRequired` in `app.py`; TV side `tv/src/api.ts` |
| What the TV plays as-is / how | `tv/src/plan.ts` (`TV` caps), `tv/src/screens/Player.tsx` `begin` (copy-HLS in TS on the TV) |
| TV remote navigation | `tv/src/nav.ts` (`move`, `reveal`), key handling in `tv/src/App.tsx`, player keys in `Player.tsx` |
| Build / sign / install the TV app | `tv/README.md`, `tv/scripts/wgt.mjs`, `tv/tizen/config.xml` |
| Who may call a route | `dependencies=ADMIN` / `me=Depends(current_user)` in `app.py`; public routes in `PUBLIC_API` |
| Password / session rules | `auth.py` (`MIN_PASSWORD`, `SESSION_DAYS`, `_SCRYPT`, `Throttle`) |
| Wrong-password waits / lockout / sign-in log | `security.py` (`wait_after`, `MAX_WAIT`, `DEFAULT_THRESHOLD`, `AUTH_LOG_KEEP`), login flow `app.auth_login` |
| IP list rules | `security.IpPolicy` (`allowed`), `clean_entries`, `save_policy`; UI `SecuritySettings.tsx` `IpCard` |
| What the traffic log records / how it rotates | record dict in `security.Gate`; `netflow.py` (`segment_size`, `SCAN_BUDGET`, `DEFAULT_MAX_BYTES`) |
| When something counts as watched, what Continue Watching offers | admin settings via `watch.thresholds` (defaults `WATCHED_PERCENT`, `RESUME_AFTER`), `continue_watching`, `next_episode` |
| What a hand identification can say / how links are read | `identify.py` (`manual_parsed`, `lookup`, `_TMDB_URL`), `IdentifyIn` in `app.py`, `Identify.tsx` |
| Add a per-user preference | `auth.PREFS` (+ `auth._valid` if it isn't a bool) + `PrefsIn` in `app.py` + `Prefs` in `web/src/api.ts` / `DEFAULT_PREFS` in `auth.tsx` |
| Add or change a Home row | `web/src/homeRows.ts` `defaultRows` (id, label, default place) + its rendering in `pages/Home.tsx` and in the TV app's `tv/src/screens/Home.tsx` (which imports `homeRows.ts`); ids are saved in users' `home_rows`, so keep old ids stable |
| Recognise more sidecar subtitle names / languages | `subtitles.sidecars`, `subtitles.tracks` (`_FLAGS`), `subtitles.language`; VobSub: `vobsub_streams` |
| Auto quality sizes | `hls.LADDER`, `hls.ladder` |
| How far ahead / behind HLS works | `AHEAD`, `SOON`, `KEEP`, `SWITCHED`, `IDLE` in `hls.py` (seconds) |
| Add a file type to index | `config.VIDEO_EXTS` / `config.AUDIO_EXTS` + FORMATS.md |
| Recognise a new music folder/file layout | `music.parse_track` / `_clean_title` (+ a case in `test_music.py`, bump `music.PARSER_VERSION`) |
| Which music formats play as-is | `stream.BROWSER_AUDIO_FILES` (+ `test_plan_audio`, FORMATS.md §5) |
| Tune music matching | `music_match.score_release`, `ACCEPT`; artist rule in `match_artist` |
| When albums merge / how often music refreshes | `music_match._pinned`, `MERGE_SCORE`; `REFRESH_AFTER`, `REFRESH_PER_SCAN` |
| CUE sheet reading / which sheet applies | `cue.parse`, `cue.file_for`; `scanner.scan_library` → `sheet_for` |
| Playlist formats / entry matching | `playlists.parse_*`, `playlists.resolve` (`find`) |
| Gapless timing / music player behaviour | `web/src/music.tsx` (`PRELOAD_BEFORE`, `ARM_BEFORE`, `advance`, `tick`) |
| Converted-music formats | `stream.MUSIC_OUTPUTS`, `stream.audio_cmd`; setting in `app.put_music_output` |
| Add a music metadata source | `musicbrainz.py` (client) + `music_match.py` (apply) + credit in `pages/Music.tsx` `About` |
| Add a DB column/table | `db.SCHEMA` + `SCHEMA_VERSION` + migration step |
| Anything that touches media files | **only** through `readonly.py`; never write; keep `test_readonly.py` green |
| Theme / colours | `:root` tokens at the top of `web/src/styles.css` |
| Release a new version | bump `config.VERSION`, `deploy/build.py all` (deploy/README.md) |
| Change what the installers install / ask | Windows `deploy/windows/bams.iss`; Linux `deploy/linux/debian/postinst` (+ `prerm`/`postrm`) |
| Bump Python, WinSW or the downloaded FFmpeg | `deploy/pins.json` (url + version + sha256 together) |
| Change Python dependencies | `server/pyproject.toml`, then re-lock `deploy/requirements.txt` (command in deploy/README.md) |
| The TMDB key guide | `web/public/help/tmdb.html` (+ screenshots in `help/img/`) |

## 9. Conventions

- Tests never touch the network: real-service code gets a `transport=` (`httpx.MockTransport`), and music
  `run_scan` calls in tests pass `do_match=False`.
- Server: stdlib `sqlite3` (no ORM). Explicit `Tx` for multi-statement writes. Network calls happen **outside**
  transactions. Comment the *why*. Type hints throughout. No new dependency without checking its license.
- Web: function components + hooks. No state library, no CSS framework. Fetch via `api.ts`/`useApi`. All
  colours come from CSS tokens. Real data only, with empty states.
- Cross-platform: `pathlib`/`os.path`, POSIX-style `rel_path` in the DB, `normcase` comparisons for roots.
