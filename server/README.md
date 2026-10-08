# BAMS server

Python 3.11+ · FastAPI · SQLite · guessit · TMDB · MusicBrainz. Runs on Windows and Debian / Ubuntu / Mint.

What it does today:

- Libraries of TV shows, movies or music, each with one or more folders. Folders are **read-only** to
  BAMS ([docs/READ-ONLY.md](../docs/READ-ONLY.md)).
- Scans: on demand and every N hours per library. Each scan does walk → diff → parse filenames →
  group into show/season/episode or movie → ffprobe (if installed). Moved files are recognised
  by fingerprint and keep their identity. Missing files are flagged, never auto-deleted.
  Offline drives are skipped rather than marked missing. Files still being copied are retried
  on the next scan.
- TMDB matching with **your own key**: titles, plots, genres, ratings, IMDb/TVDB ids, posters,
  backdrops, season posters, episode titles and stills, cached in the data folder and refreshed
  before TMDB's 6-month limit. Low-confidence matches are left "unmatched" instead of guessed.
  Use "Fix match" to pin one.
- Music: artist > album > track from the files' tags (read by ffprobe), the folder layout as a fallback; covers
  from `cover.jpg`/`folder.jpg` or the embedded picture, `artist.jpg` for artists. Identification on MusicBrainz
  (no key; on by default, Settings toggle), covers from the Cover Art Archive, artist bios/photos from
  Wikipedia/Wikimedia Commons. Your own tags and art always win.
- Streaming of original files with seeking (HTTP Range), and downloads. Music in formats browsers can't play
  (ALAC, AIFF, WMA, APE, DSD…) is converted to AAC while streaming.

## Run it (development)

```bash
cd server
uv venv --python 3.11 .venv
uv pip install --python .venv -e ".[dev]"
```

Windows:

```bash
.venv\Scripts\python -m bams tmdb-key
.venv\Scripts\python -m bams library add "TV Shows" --type show --path C:\Users\you\Shows
.venv\Scripts\python -m bams serve
```

Linux: the same, with `.venv/bin/python`. Then open http://127.0.0.1:8484 **on the server itself** and create the
admin account (or run `bams user add NAME --admin`). Everyone signs in; the admin adds the others' accounts in
Settings → Accounts. The interactive API is at http://127.0.0.1:8484/docs (its calls need a signed-in browser).

`BAMS_DATA_DIR` (or `--data-dir`) chooses where the database, image cache and logs go.
Optional: install FFmpeg (`sudo apt install ffmpeg` / `winget install Gyan.FFmpeg`) for codec and
resolution detection. BAMS never bundles it.

## CLI

| Command | |
|---|---|
| `bams serve [--host --port]` | API + scheduled scans. This computer only by default; `--host 0.0.0.0` for the network (everyone signs in). For the internet, put it behind an HTTPS reverse proxy |
| `bams user add NAME [--admin]` · `bams user list` · `bams user passwd NAME` · `bams user remove NAME` | accounts (passwords asked for, hidden). `passwd` signs the user out everywhere |
| `bams library add NAME --type show\|movie\|music --path DIR [--path DIR] [--interval HOURS]` | |
| `bams library list` / `bams library remove NAME` | remove only forgets; media is untouched |
| `bams scan NAME [--no-match] [--rematch]` | scan now, in the foreground (`--no-match` also skips MusicBrainz) |
| `bams tmdb-key [--clear]` | paste your TMDB Read Access Token / API key (hidden prompt, verified first) |
| `bams status` | |

## API (v0)

Every `/api/` route except signing in needs the session cookie that signing in sets. Routes that change libraries,
settings or accounts (and Fix match, folder browsing) are for admins.

| | |
|---|---|
| `GET /api/auth/state` · `POST /api/auth/login {name, password}` · `POST /api/auth/logout` · `POST /api/auth/setup` (first admin, from the server itself) · `PUT /api/auth/password {current, new}` | signing in |
| `GET/POST /api/users` · `PATCH/DELETE /api/users/{id}` | accounts (admins) |
| `PUT /api/items/{id}/progress {position, duration}` · `PUT /api/items/{id}/watched {watched}` · `GET /api/continue` | watch state of the signed-in user |
| `PUT /api/me/prefs {home_hero}` | your own display preferences (also in `GET /api/auth/state` → `user.prefs`) |
| `GET /api/settings/encoders` · `PUT /api/settings/encoder {encoder}` | which H.264 encoders work; convert on the CPU or a GPU (null = automatic) |
| `PUT /api/settings/watch {watched_percent, resume_after}` | when a title counts as watched / started, for everyone (admins; in `GET /api/settings` → `watch`) |
| `GET /api/status` | version, ffprobe, TMDB configured, guard, running/queued scans (the running one with step, done/total, bytes, `step_elapsed`) |
| `GET /api/settings` · `PUT/DELETE /api/settings/tmdb-key` | the key is verified before saving and never returned (last 4 only) |
| `GET/POST /api/libraries` · `GET/PATCH/DELETE /api/libraries/{id}` · `PUT /api/libraries/order {ids}` | listed in the admin's order |
| `POST /api/libraries/{id}/scan[?rematch=true]` · `GET /api/scans` | |
| `GET /api/libraries/{id}/items?sort=title\|year\|added\|rating\|artist&kind=&match_status=&q=` | shows, movies, or artists/albums/tracks (`kind=`) |
| `GET /api/items/{id}` | detail + children (seasons / episodes / albums / tracks) + files (probe, playback method) |
| `GET /api/items/{id}/tracks` | play queue of an artist, album or track |
| `GET /api/musicbrainz/search?kind=album\|artist&q=&artist=` · `POST /api/items/{id}/music-match {mbid}` | music fix match |
| `PUT /api/settings/music-lookup {enabled}` | music identification on/off |
| `GET /api/unrecognized` · `GET /api/libraries/{id}/unrecognized` | files the parser couldn't place (with a hint) and files identified by hand |
| `PUT /api/files/{id}/identify {title, year, season, episodes, episode_title, edition, tmdb_id}` · `DELETE` | say what a file is (kept across rescans) / forget it |
| `POST /api/identify/lookup {link, library_id}` · `GET /api/libraries/{id}/names` | a TMDB/IMDb link → those fields; names already in a library (suggestions) |
| `GET /api/tmdb/search?kind=show\|movie&q=` · `POST /api/items/{id}/match {tmdb_id}` | fix match |
| `GET /api/files/{id}/stream` · `/download` | original file, Range-capable |
| `GET /api/files/{id}/remux?t=&audio=&ch=` · `/seek?t=` | video copied + audio converted to AAC (fragmented MP4) for browsers; `/seek` says where a stream started at `t` really begins |
| `GET /api/files/{id}/transcode?t=&audio=&h=&ch=&sub=` | video converted to H.264 too (fragmented MP4) |
| `POST /api/files/{id}/hls {remux?, auto?, height?, audio?, channels?, burn?, start?}` · `GET /api/hls/{sid}/index.m3u8` | HLS: the remux or a conversion, segments made on demand |
| `GET /api/files/{id}/subtitles/{track}.vtt?shift=` | a text subtitle track (embedded or sidecar) as WebVTT |
| `GET /api/files/{id}/audio?t=` | music converted to AAC (fragmented MP4) for formats browsers can't play |
| `GET /api/images/{path}` | cached artwork |

## Tests

```bash
.venv/Scripts/python -m pytest      # Windows
.venv/bin/python -m pytest          # Linux
```
