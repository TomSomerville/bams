"""SQLite storage. One file in the data directory, WAL mode, one connection per thread/request.

Data model (same shape as Plex's):
  items    what something IS: movie | show > season > episode | artist > album > track
           (title, plot, art, TMDB/IMDb ids)
  files    the actual media files on disk (path relative to a library root, size, probe info)
  file_items  which items a file holds (a multi-episode file holds several episodes)
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 8

# The first schema. New databases are created at v1 and then migrated like any old one, so every
# migration step runs on every install (and in every test).
SCHEMA = """
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE libraries (
    id                  INTEGER PRIMARY KEY,
    name                TEXT NOT NULL UNIQUE,
    type                TEXT NOT NULL CHECK (type IN ('movie', 'show', 'music')),
    scan_interval_hours REAL NOT NULL DEFAULT 6,
    created_at          REAL NOT NULL,
    last_scan_at        REAL,
    last_scan_status    TEXT
);

CREATE TABLE library_roots (
    id          INTEGER PRIMARY KEY,
    library_id  INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    UNIQUE (library_id, path)
);

CREATE TABLE items (
    id               INTEGER PRIMARY KEY,
    library_id       INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    kind             TEXT NOT NULL CHECK (kind IN ('movie', 'show', 'season', 'episode')),
    parent_id        INTEGER REFERENCES items(id) ON DELETE CASCADE,
    title            TEXT NOT NULL,
    parsed_title     TEXT,             -- what the filename said, kept after matching
    title_key        TEXT,             -- normalised title used to group files into one show/movie
    year             INTEGER,
    season_number    INTEGER,
    episode_number   INTEGER,
    overview         TEXT,
    tagline          TEXT,
    genres           TEXT,             -- JSON list
    rating           REAL,
    runtime          INTEGER,          -- minutes
    air_date         TEXT,
    tmdb_id          INTEGER,
    imdb_id          TEXT,
    tvdb_id          INTEGER,
    poster           TEXT,             -- image cache path relative to data/images
    backdrop         TEXT,
    still            TEXT,
    match_status     TEXT NOT NULL DEFAULT 'pending'
                     CHECK (match_status IN ('pending', 'matched', 'unmatched', 'manual')),
    match_score      REAL,
    metadata_at      REAL,             -- when TMDB data was fetched (TMDB terms: refresh < 6 months)
    added_at         REAL NOT NULL,
    updated_at       REAL NOT NULL
);
CREATE INDEX items_parent ON items(parent_id);
CREATE INDEX items_lib_kind ON items(library_id, kind);
CREATE INDEX items_tmdb ON items(library_id, kind, tmdb_id);
CREATE UNIQUE INDEX items_season ON items(parent_id, season_number) WHERE kind = 'season';
CREATE UNIQUE INDEX items_episode ON items(parent_id, episode_number) WHERE kind = 'episode';

-- Every (title_key, year) that has been seen for a show/movie. When two folders turn out to be
-- the same TMDB title and get merged, both keys point at the surviving item, so the next scan
-- files new episodes under it instead of re-creating the duplicate.
CREATE TABLE item_keys (
    library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    title_key  TEXT NOT NULL,
    year       INTEGER NOT NULL DEFAULT 0,   -- 0 = unknown
    item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    PRIMARY KEY (library_id, kind, title_key, year)
);

CREATE TABLE files (
    id            INTEGER PRIMARY KEY,
    library_id    INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    root_id       INTEGER NOT NULL REFERENCES library_roots(id) ON DELETE CASCADE,
    rel_path      TEXT NOT NULL,       -- '/'-separated, relative to the root
    size          INTEGER NOT NULL,
    mtime_ns      INTEGER NOT NULL,
    quick_hash    TEXT,
    parse         TEXT,                -- JSON: what the filename parser saw
    probe         TEXT,                -- JSON: ffprobe summary
    probed_at     REAL,
    available     INTEGER NOT NULL DEFAULT 1,
    missing_since REAL,
    first_seen    REAL NOT NULL,
    last_seen     REAL NOT NULL,
    UNIQUE (root_id, rel_path)
);
CREATE INDEX files_lib ON files(library_id);
CREATE INDEX files_hash ON files(size, quick_hash);

CREATE TABLE file_items (
    file_id  INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    PRIMARY KEY (file_id, item_id)
);
CREATE INDEX file_items_item ON file_items(item_id);

CREATE TABLE scans (
    id          INTEGER PRIMARY KEY,
    library_id  INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    trigger     TEXT NOT NULL,          -- 'schedule' | 'manual' | 'startup'
    started_at  REAL NOT NULL,
    finished_at REAL,
    status      TEXT NOT NULL,          -- 'running' | 'ok' | 'error'
    stats       TEXT,                   -- JSON counters
    error       TEXT
);
"""


def connect(path: Path) -> sqlite3.Connection:
    # autocommit (explicit BEGIN where needed). check_same_thread=False: FastAPI may open a request's
    # connection in one worker thread and run the endpoint in another. Each connection still serves
    # exactly one request/job at a time, it's just handed between threads.
    con = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


# v2: music libraries. items gains the artist > album > track kinds and their columns. SQLite can't
# change a CHECK constraint in place, so the table is rebuilt (sqlite.org/lang_altertable.html, "other
# kinds of table schema changes"): create the new table, copy, drop the old one, rename.
_ITEMS_V1_COLUMNS = (
    "id, library_id, kind, parent_id, title, parsed_title, title_key, year, season_number, episode_number, "
    "overview, tagline, genres, rating, runtime, air_date, tmdb_id, imdb_id, tvdb_id, poster, backdrop, still, "
    "match_status, match_score, metadata_at, added_at, updated_at")

_ITEMS_V2 = """
CREATE TABLE items_v2 (
    id               INTEGER PRIMARY KEY,
    library_id       INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    kind             TEXT NOT NULL CHECK (kind IN ('movie', 'show', 'season', 'episode', 'artist', 'album', 'track')),
    parent_id        INTEGER REFERENCES items(id) ON DELETE CASCADE,
    title            TEXT NOT NULL,
    parsed_title     TEXT,
    title_key        TEXT,
    sort_title       TEXT,             -- artists: "Beatles, The" sorts under B
    year             INTEGER,
    season_number    INTEGER,
    episode_number   INTEGER,
    disc_number      INTEGER,          -- tracks
    track_number     INTEGER,          -- tracks
    artist           TEXT,             -- tracks: the performing artist when it isn't the album artist
    duration         REAL,             -- tracks: seconds
    overview         TEXT,
    tagline          TEXT,
    genres           TEXT,
    rating           REAL,
    runtime          INTEGER,
    air_date         TEXT,
    tmdb_id          INTEGER,
    imdb_id          TEXT,
    tvdb_id          INTEGER,
    poster           TEXT,             -- albums: the cover; artists: their own image if the folder has one
    backdrop         TEXT,
    still            TEXT,
    match_status     TEXT NOT NULL DEFAULT 'pending'
                     CHECK (match_status IN ('pending', 'matched', 'unmatched', 'manual')),
    match_score      REAL,
    metadata_at      REAL,
    added_at         REAL NOT NULL,
    updated_at       REAL NOT NULL
)"""

_ITEMS_V2_INDEXES = (
    "CREATE INDEX items_parent ON items(parent_id)",
    "CREATE INDEX items_lib_kind ON items(library_id, kind)",
    "CREATE INDEX items_tmdb ON items(library_id, kind, tmdb_id)",
    "CREATE UNIQUE INDEX items_season ON items(parent_id, season_number) WHERE kind = 'season'",
    "CREATE UNIQUE INDEX items_episode ON items(parent_id, episode_number) WHERE kind = 'episode'",
    "CREATE INDEX items_album ON items(parent_id, title_key) WHERE kind = 'album'",
)


def _v2(con: sqlite3.Connection) -> None:
    con.execute(_ITEMS_V2)
    con.execute(f"INSERT INTO items_v2 ({_ITEMS_V1_COLUMNS}) SELECT {_ITEMS_V1_COLUMNS} FROM items")
    con.execute("DROP TABLE items")
    con.execute("ALTER TABLE items_v2 RENAME TO items")
    for stmt in _ITEMS_V2_INDEXES:
        con.execute(stmt)


def _v3(con: sqlite3.Connection) -> None:
    """v3: music identification. mbid = MusicBrainz id (release for albums, artist for artists, recording for
    tracks); extra = JSON for source-specific bits (release group, Wikipedia link, photo credit...)."""
    con.execute("ALTER TABLE items ADD COLUMN mbid TEXT")
    con.execute("ALTER TABLE items ADD COLUMN extra TEXT")


_V4 = (
    """CREATE TABLE users (
        id            INTEGER PRIMARY KEY,
        name          TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password      TEXT NOT NULL,             -- scrypt hash (auth.hash_password), never the password
        is_admin      INTEGER NOT NULL DEFAULT 0,
        created_at    REAL NOT NULL,
        last_login_at REAL)""",
    """CREATE TABLE sessions (
        token        TEXT PRIMARY KEY,           -- sha256 of the cookie value: a copied DB can't log anyone in
        user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at   REAL NOT NULL,
        last_seen_at REAL NOT NULL,
        user_agent   TEXT)""",
    "CREATE INDEX sessions_user ON sessions(user_id)",
    """CREATE TABLE watch_state (
        user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        item_id         INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,  -- a movie or an episode
        position        REAL NOT NULL DEFAULT 0,  -- seconds; 0 = from the start (or finished)
        duration        REAL,
        watched         INTEGER NOT NULL DEFAULT 0,
        play_count      INTEGER NOT NULL DEFAULT 0,
        last_watched_at REAL,                     -- when it was last finished
        updated_at      REAL NOT NULL,
        PRIMARY KEY (user_id, item_id))""",
    "CREATE INDEX watch_recent ON watch_state(user_id, updated_at)",
)


def _v4(con: sqlite3.Connection) -> None:
    """v4: user accounts, login sessions, and each user's watch state (resume position, watched flags)."""
    for stmt in _V4:
        con.execute(stmt)


def _v5(con: sqlite3.Connection) -> None:
    """v5: each user's own display preferences (JSON, see auth.PREFS)."""
    con.execute("ALTER TABLE users ADD COLUMN prefs TEXT")


def _v6(con: sqlite3.Connection) -> None:
    """v6: a file's identification entered by hand (JSON, see identify.py), used instead of its name."""
    con.execute("ALTER TABLE files ADD COLUMN manual TEXT")


def _v7(con: sqlite3.Connection) -> None:
    """v7: libraries in the admin's order (sidebar, Home, Settings); existing ones keep their alphabetical order."""
    con.execute("ALTER TABLE libraries ADD COLUMN sort_order INTEGER")
    con.execute("""UPDATE libraries SET sort_order = (SELECT COUNT(*) FROM libraries l2
                   WHERE l2.name COLLATE NOCASE < libraries.name COLLATE NOCASE)""")


_V8 = (
    # CUE sheets: one file holds several tracks, each a stretch of it (seconds; NULL end = to the end of the file)
    "ALTER TABLE file_items ADD COLUMN cue_start REAL",
    "ALTER TABLE file_items ADD COLUMN cue_end REAL",
    # music art: where the poster came from (JSON: {"from": "folder"|"embedded"|"caa"|"commons", "path", "size",
    # "mtime_ns"} or {"from": null, "checked": t}), so a cover.jpg added later replaces embedded/downloaded art
    "ALTER TABLE items ADD COLUMN poster_src TEXT",
    # playlists imported from .m3u/.m3u8/.pls files in a music library (read there, never written)
    """CREATE TABLE playlists (
        id          INTEGER PRIMARY KEY,
        library_id  INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
        root_id     INTEGER REFERENCES library_roots(id) ON DELETE CASCADE,
        rel_path    TEXT,                  -- the playlist file, relative to its root
        name        TEXT NOT NULL,
        size        INTEGER,
        mtime_ns    INTEGER,
        entries     TEXT NOT NULL,         -- JSON: the file's entries as written ({path, title, duration})
        missing     INTEGER NOT NULL DEFAULT 0,  -- entries not found in the library
        added_at    REAL NOT NULL,
        updated_at  REAL NOT NULL,
        UNIQUE (root_id, rel_path))""",
    """CREATE TABLE playlist_items (
        playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
        position    INTEGER NOT NULL,
        item_id     INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,  -- a track
        PRIMARY KEY (playlist_id, position))""",
    "CREATE INDEX playlist_items_item ON playlist_items(item_id)",
)


def _v8(con: sqlite3.Connection) -> None:
    """v8: CUE-sheet tracks, where music art came from, imported playlists."""
    for stmt in _V8:
        con.execute(stmt)


MIGRATIONS = {2: _v2, 3: _v3, 4: _v4, 5: _v5, 6: _v6, 7: _v7, 8: _v8}  # target version -> step


def migrate(con: sqlite3.Connection, backup_dir: Path | None = None) -> None:
    """Bring the schema up to SCHEMA_VERSION. An existing database is copied into `backup_dir` first."""
    v = con.execute("PRAGMA user_version").fetchone()[0]
    if v == SCHEMA_VERSION:
        return
    if v > SCHEMA_VERSION:
        raise RuntimeError(f"database schema v{v} is newer than this BAMS (v{SCHEMA_VERSION})")
    if v == 0:
        con.executescript("BEGIN;" + SCHEMA + "PRAGMA user_version = 1; COMMIT;")
        v = 1
    elif backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(backup_dir / f"bams-schema-v{v}-{int(time.time())}.db")
        try:
            con.backup(dest)
        finally:
            dest.close()
    # Table rebuilds need foreign keys off: with them on, DROP TABLE items would cascade-delete every
    # file_items row. The pragma is ignored inside a transaction, so it's set around each step.
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        for target in range(v + 1, SCHEMA_VERSION + 1):
            con.execute("BEGIN IMMEDIATE")
            try:
                MIGRATIONS[target](con)
                if con.execute("PRAGMA foreign_key_check").fetchone():
                    raise RuntimeError(f"schema migration to v{target} broke foreign keys")
                con.execute(f"PRAGMA user_version = {target}")
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")


class Tx:
    """`with Tx(con):` -> BEGIN IMMEDIATE ... COMMIT / ROLLBACK."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con

    def __enter__(self) -> sqlite3.Connection:
        self.con.execute("BEGIN IMMEDIATE")
        return self.con

    def __exit__(self, exc_type, *_):
        self.con.execute("ROLLBACK" if exc_type else "COMMIT")


def now() -> float:
    return time.time()


def get_setting(con: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(con: sqlite3.Connection, key: str, value: str | None) -> None:
    if value is None:
        con.execute("DELETE FROM settings WHERE key = ?", (key,))
    else:
        con.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def jdump(v) -> str | None:
    return None if v is None else json.dumps(v, separators=(",", ":"))


def jload(s: str | None):
    return None if s is None else json.loads(s)
