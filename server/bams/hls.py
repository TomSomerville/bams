"""HLS transcode sessions: a converted video as 4-second segments, so the browser seeks by itself.

The plain fMP4 transcode (`/api/files/{id}/transcode?t=`) is one live stream: seeking means starting a new
one. With HLS the player gets a playlist of every segment up front (VOD) and asks for whichever it needs:

- FFmpeg makes segments on demand. A request for a segment that isn't on disk and isn't about to be made
  (re)starts FFmpeg at that segment. `stream.hls_cmd` keeps timestamps and forces keyframes on segment
  boundaries, so segments from different FFmpeg runs line up.
- FFmpeg is stopped once it's AHEAD segments past the last one requested (a paused film doesn't keep
  converting) and restarted when the player gets there. Segments more than KEEP_BEHIND either side of the
  playhead are deleted, so disk use stays at a few hundred MB per viewer.
- A session nobody has asked anything of for IDLE seconds is closed (the player also closes it).
- Everything lives in data/transcode/<session>/ (wiped at startup), never in a media folder.

`Transcodes` also counts the plain fMP4 streams, so one limit covers every video conversion.
"""

from __future__ import annotations

import logging
import math
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import stream

log = logging.getLogger(__name__)

AHEAD = 15         # segments made past the last one requested before FFmpeg is stopped (60 s)
SOON = 6           # a missing segment this close to what FFmpeg is making is waited for, not restarted
KEEP_BEHIND = 75   # segments kept either side of the playhead for seeking back (5 min)
IDLE = 90.0        # seconds without a request before a session is closed
WAIT = 60.0        # longest a request waits for its segment
POLL = 0.05


class Busy(Exception):
    """The limit on simultaneous video conversions is reached."""


class SegmentGone(Exception):
    """The player moved on (seeked elsewhere, or closed the session) before this segment was made."""


@dataclass(eq=False)
class Session:
    id: str
    file_id: int
    path: Path
    video: dict | None
    audio: int
    height: int | None
    duration: float
    dir: Path
    proc: subprocess.Popen | None = None
    job_start: int = 0      # the segment the current FFmpeg run started at
    wanted: int = 0         # the segment asked for last (where the player is)
    killed: bool = False    # the current FFmpeg run was stopped by us, not by an error
    closed: bool = False
    last_access: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def segments(self) -> int:
        return max(1, math.ceil(self.duration / stream.SEGMENT))

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def made_up_to(self) -> int:
        """The first segment from `job_start` on that isn't on disk yet."""
        k = self.job_start
        while (self.dir / f"{k}.ts").exists():
            k += 1
        return k

    def playlist(self) -> str:
        n, seg = self.segments, stream.SEGMENT
        lines = ["#EXTM3U", "#EXT-X-VERSION:3", f"#EXT-X-TARGETDURATION:{math.ceil(seg) + 1}",
                 "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-PLAYLIST-TYPE:VOD"]
        for k in range(n):
            d = self.duration - k * seg if k == n - 1 else seg
            lines += [f"#EXTINF:{max(d, 0.1):.3f},", f"{k}.ts"]
        lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines) + "\n"


class Transcodes:
    """Every running video conversion: HLS sessions, plus a count of plain fMP4 transcode streams."""

    def __init__(self, root: Path, limit: Callable[[], int], spawn: Callable = stream.spawn,
                 cmd: Callable = stream.hls_cmd):
        self.root = root
        self.limit = limit  # 0 or less = no limit
        self._spawn, self._cmd = spawn, cmd
        self._sessions: dict[str, Session] = {}
        self._pipes: set[subprocess.Popen] = set()  # plain fMP4 transcodes (counted while they run)
        self._lock = threading.Lock()  # guards _sessions/_pipes; never held while taking a session lock
        self._stop = threading.Event()
        self._reaper: threading.Thread | None = None
        shutil.rmtree(root, ignore_errors=True)  # segments left by a previous run
        root.mkdir(parents=True, exist_ok=True)

    # -- lifecycle
    def start(self) -> None:
        self._reaper = threading.Thread(target=self._reap_loop, name="hls-reaper", daemon=True)
        self._reaper.start()

    def shutdown(self) -> None:
        self._stop.set()
        for sid in list(self._sessions):
            self.close(sid)

    # -- the limit
    def running(self) -> int:
        with self._lock:
            return self._count()

    def _count(self) -> int:
        """Open sessions count whether or not their FFmpeg is running right now (it's stopped while far
        enough ahead), so a viewer never loses their place to a newcomer and gets "busy" mid-film."""
        self._pipes = {p for p in self._pipes if p.poll() is None}
        return len(self._pipes) + len(self._sessions)

    def _check(self) -> None:
        limit = self.limit()
        if limit > 0 and self._count() >= limit:
            raise Busy(f"BAMS is already converting {limit} video{'' if limit == 1 else 's'} at once (the limit "
                       "is in Settings). Try again when one of them stops.")

    def check(self) -> None:
        """Raise Busy if another conversion would go over the limit."""
        with self._lock:
            self._check()

    def add_pipe(self, proc: subprocess.Popen) -> None:
        """A plain fMP4 transcode started; it counts towards the limit until its FFmpeg exits."""
        with self._lock:
            self._pipes.add(proc)

    # -- sessions
    def create(self, file_id: int, path: Path, video: dict | None, duration: float,
               audio: int = 0, height: int | None = None) -> Session:
        with self._lock:
            self._check()  # the session holds its place until closed, however often FFmpeg restarts
            sid = secrets.token_urlsafe(9)
            d = self.root / sid
            d.mkdir()
            s = Session(sid, file_id, path, video, audio, height, duration, d)
            self._sessions[sid] = s
        log.info("HLS %s: file %s, %.0f s, %s", sid, file_id, duration, f"{height}p" if height else "full size")
        return s

    def get(self, sid: str) -> Session:
        with self._lock:
            return self._sessions[sid]

    def close(self, sid: str) -> None:
        with self._lock:
            s = self._sessions.pop(sid, None)
        if s is None:
            return
        with s.lock:
            s.closed = True
            self._kill(s)
        shutil.rmtree(s.dir, ignore_errors=True)

    def segment(self, s: Session, k: int) -> Path:
        """The file of segment k, made (or waited for) if it isn't there yet. Blocking: run it in a thread."""
        if not 0 <= k < s.segments:
            raise KeyError(k)
        f = s.dir / f"{k}.ts"
        s.last_access = time.monotonic()
        with s.lock:
            if s.closed:
                raise SegmentGone(k)
            s.wanted = k
            if not f.exists() and not self._coming(s, k):
                self._restart(s, k)
        deadline = time.monotonic() + WAIT
        while time.monotonic() < deadline:
            if f.exists():
                return f
            with s.lock:
                if s.closed or (s.wanted != k and not self._coming(s, k)):
                    raise SegmentGone(k)  # superseded by a seek; don't fight over FFmpeg
                if not s.running():
                    if f.exists():
                        return f
                    p = s.proc
                    if p is not None and not s.killed and s.job_start <= k:
                        if p.returncode == 0:
                            raise KeyError(k)  # FFmpeg reached the real end before this segment
                        raise RuntimeError(f"FFmpeg stopped with exit code {p.returncode} (see the server log)")
                    self._restart(s, k)  # stopped for being far ahead, and the player caught up
            time.sleep(POLL)
        raise TimeoutError(k)

    # -- internals (callers hold s.lock)
    def _coming(self, s: Session, k: int) -> bool:
        return s.running() and s.job_start <= k <= s.made_up_to() + SOON

    def _restart(self, s: Session, k: int) -> None:
        self._kill(s)  # no limit check: the session took its place when it was created
        s.proc = self._spawn(self._cmd(s.path, k, s.video, s.dir, s.audio, max_height=s.height))
        s.job_start, s.killed = k, False
        log.debug("HLS %s: FFmpeg from segment %d", s.id, k)

    def _kill(self, s: Session) -> None:
        if s.running():
            s.killed = True
            s.proc.kill()
            try:
                s.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log.warning("HLS %s: FFmpeg didn't stop", s.id)
        for tmp in s.dir.glob("*.tmp"):  # the segment it was writing
            try:
                tmp.unlink()
            except OSError:
                pass

    def _prune(self, s: Session) -> None:
        for f in s.dir.glob("*.ts"):
            try:
                if abs(int(f.stem) - s.wanted) > KEEP_BEHIND:
                    f.unlink()
            except (ValueError, OSError):  # not a segment, or being served (Windows)
                pass

    def reap(self) -> None:
        """Close idle sessions, stop FFmpeg runs that are far enough ahead, delete far-away segments."""
        now = time.monotonic()
        with self._lock:
            sessions = list(self._sessions.values())
        for s in sessions:
            if now - s.last_access > IDLE:
                log.info("HLS %s: idle, closed", s.id)
                self.close(s.id)
                continue
            with s.lock:
                if s.running() and s.made_up_to() > s.wanted + AHEAD:
                    self._kill(s)
                self._prune(s)

    def _reap_loop(self) -> None:
        while not self._stop.wait(2.0):
            try:
                self.reap()
            except Exception:  # never let the reaper die
                log.exception("HLS reaper")
