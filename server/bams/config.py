"""Where BAMS keeps its own data, and process-wide constants.

BAMS never writes inside a media folder. Everything it creates (database, image cache,
logs) lives in the data directory chosen here.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "BAMS"
VERSION = "0.4.0"
DEFAULT_HOST = "127.0.0.1"  # this computer only; `serve --host 0.0.0.0` opens it to the network (login required)
DEFAULT_PORT = 8484

# Keep in step with docs/FORMATS.md section 1.
VIDEO_EXTS = frozenset({
    ".mkv", ".mp4", ".m4v", ".mov", ".webm", ".avi", ".divx", ".ts", ".m2ts", ".mts",
    ".mpg", ".mpeg", ".mpe", ".wmv", ".asf", ".wtv", ".dvr-ms", ".flv", ".f4v", ".ogv",
    ".3gp", ".3g2", ".rm", ".rmvb", ".iso",
})
# Music libraries. Keep in step with docs/FORMATS.md section 5.
AUDIO_EXTS = frozenset({
    ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav", ".aif", ".aiff", ".aifc",
    ".wma", ".ape", ".wv", ".dsf", ".dff", ".mka", ".ac3", ".dts", ".mp2",
})
# Images BAMS looks for next to the music (read, then copied into the data dir; never written there).
ALBUM_ART_NAMES = ("cover", "folder", "front", "album", "albumart", "albumartsmall")
ARTIST_ART_NAMES = ("artist", "folder", "poster")
ART_EXTS = (".jpg", ".jpeg", ".png", ".webp")
# Read next to the music too: cue sheets (one file = a whole album) and playlists to import.
CUE_EXTS = frozenset({".cue"})
PLAYLIST_EXTS = frozenset({".m3u", ".m3u8", ".pls"})
# Folders skipped anywhere: OS / NAS housekeeping.
SKIP_DIRS = frozenset(name.casefold() for name in {
    "$RECYCLE.BIN", "System Volume Information", "@eaDir", ".@__thumb", "#recycle", ".Trash-1000",
    "lost+found", ".grab",
})
# Plex-style extras folders, skipped only INSIDE a show/movie folder (a show could be called "Shorts").
EXTRAS_DIRS = frozenset(name.casefold() for name in {
    "Sample", "Samples", "Extras", "Featurettes", "Behind The Scenes", "Deleted Scenes",
    "Interviews", "Scenes", "Shorts", "Trailers", "Other",
})


def default_data_dir() -> Path:
    """BAMS_DATA_DIR wins; systemd's StateDirectory= next; else a per-user location."""
    if env := os.environ.get("BAMS_DATA_DIR"):
        return Path(env)
    if env := os.environ.get("STATE_DIRECTORY"):  # set by systemd for StateDirectory=bams
        return Path(env.split(":")[0])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "BAMS"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "bams"


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def db(self) -> Path:
        return self.root / "bams.db"

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def transcode(self) -> Path:
        """HLS segments being served (wiped at startup)."""
        return self.root / "transcode"

    @property
    def security_db(self) -> Path:
        """The sign-in log and lockout state (security.py), apart from the main DB."""
        return self.root / "security.db"

    @property
    def netflow(self) -> Path:
        """Where the traffic log goes unless the admin picks another folder."""
        return self.root / "netflow"

    @property
    def cache(self) -> Path:
        """Things BAMS can make again: converted subtitles, keyframe lists."""
        return self.root / "cache"

    def ensure(self) -> "Paths":
        for p in (self.root, self.images, self.logs):
            p.mkdir(parents=True, exist_ok=True)
        return self
