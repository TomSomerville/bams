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

Linux: the same, with `.venv/bin/python`. Then open http://127.0.0.1:8484/docs for the interactive API.

`BAMS_DATA_DIR` (or `--data-dir`) chooses where the database, image cache and logs go.
Optional: install FFmpeg (`sudo apt install ffmpeg` / `winget install Gyan.FFmpeg`) for codec and
resolution detection. BAMS never bundles it.

## CLI

| Command | |
|---|---|
| `bams serve [--host --port]` | API + scheduled scans. Localhost-only by default: there's no login yet |
| `bams library add NAME --type show\|movie\|music --path DIR [--path DIR] [--interval HOURS]` | |
| `bams library list` / `bams library remove NAME` | remove only forgets; media is untouched |
| `bams scan NAME [--no-match] [--rematch]` | scan now, in the foreground (`--no-match` also skips MusicBrainz) |
| `bams tmdb-key [--clear]` | paste your TMDB Read Access Token / API key (hidden prompt, verified first) |
| `bams status` | |

## API (v0)

| | |
|---|---|
| `GET /api/status` | version, ffprobe, TMDB configured, guard, running/queued scans |
| `GET /api/settings` · `PUT/DELETE /api/settings/tmdb-key` | the key is verified before saving and never returned (last 4 only) |
| `GET/POST /api/libraries` · `GET/PATCH/DELETE /api/libraries/{id}` | |
| `POST /api/libraries/{id}/scan[?rematch=true]` · `GET /api/scans` | |
| `GET /api/libraries/{id}/items?sort=title\|year\|added\|rating\|artist&kind=&match_status=&q=` | shows, movies, or artists/albums/tracks (`kind=`) |
| `GET /api/items/{id}` | detail + children (seasons / episodes / albums / tracks) + files (probe, playback method) |
| `GET /api/items/{id}/tracks` | play queue of an artist, album or track |
| `GET /api/musicbrainz/search?kind=album\|artist&q=&artist=` · `POST /api/items/{id}/music-match {mbid}` | music fix match |
| `PUT /api/settings/music-lookup {enabled}` | music identification on/off |
| `GET /api/libraries/{id}/unrecognized` | files the parser couldn't place |
| `GET /api/tmdb/search?kind=show\|movie&q=` · `POST /api/items/{id}/match {tmdb_id}` | fix match |
| `GET /api/files/{id}/stream` · `/download` | original file, Range-capable |
| `GET /api/files/{id}/remux?t=` · `/seek?t=` | video copied + AC3/EAC3/DTS audio converted to AAC (fragmented MP4) for browsers; `/seek` says where a stream started at `t` really begins |
| `GET /api/files/{id}/audio?t=` | music converted to AAC (fragmented MP4) for formats browsers can't play |
| `GET /api/images/{path}` | cached artwork |

## Tests

```bash
.venv/Scripts/python -m pytest      # Windows
.venv/bin/python -m pytest          # Linux
```
