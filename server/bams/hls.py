"""HLS sessions: a video as short segments made on demand, so the browser seeks by itself.

The plain fMP4 streams (`/remux?t=`, `/transcode?t=`) are one live stream each: seeking means starting a new one.
With HLS the player gets every segment listed up front (VOD playlists) and asks for whichever it needs:

- A session has one or more *variants*. A converted video (H.264) can have several sizes: the player's
  "Auto" quality lists them all in a master playlist and hls.js picks one by measured throughput, which here
  includes how fast the server converts (a server that can't keep up drops to a smaller size too).
  A fixed quality is a single variant. A *copy* variant is the audio-only remux: video copied, audio -> AAC,
  cut at the file's own keyframes (listed once with ffprobe and cached).
- FFmpeg makes segments on demand. A request for a segment that isn't on disk and isn't about to be made
  (re)starts that variant's FFmpeg there. `stream.hls_cmd` / `hls_copy_cmd` keep the timestamps and cut on fixed
  boundaries, so segments from different FFmpeg runs line up.
- FFmpeg is stopped once it's AHEAD seconds past the last segment requested (a paused film doesn't keep
  converting) and restarted when the player gets there; a variant the player switched away from stops after
  SWITCHED seconds. Segments more than KEEP seconds from the playhead are deleted.
- A session nobody has asked anything of for IDLE seconds is closed (the player also closes it).
- Everything lives in data/transcode/<session>/ (wiped at startup), never in a media folder.

`Transcodes` also counts the plain fMP4 transcodes, so one limit covers every video conversion.
"""

from __future__ import annotations

import bisect
import json
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

AHEAD = 60.0       # seconds made past the last segment requested before FFmpeg is stopped
SOON = 24.0        # a missing segment this close to what FFmpeg is making is waited for, not restarted
KEEP = 300.0       # seconds of segments kept either side of the playhead, for seeking back
SWITCHED = 10.0    # a variant nothing was asked of for this long, while another one was, stops its FFmpeg
IDLE = 90.0        # seconds without a request before a session is closed
WAIT = 60.0        # longest a request waits for its segment
POLL = 0.05
LADDER = (1080, 720, 480)  # sizes under the full one that "Auto" offers


class Busy(Exception):
    """The limit on simultaneous video conversions is reached."""


class SegmentGone(Exception):
    """The player moved on (seeked elsewhere, or closed the session) before this segment was made."""


@dataclass(eq=False)
class Variant:
    index: int
    bounds: list[float]          # start time of each segment; segment k covers bounds[k] up to the next
    duration: float
    dir: Path
    copy: bool = False           # video copied (audio-only remux) instead of converted
    height: int | None = None    # conversion: largest height (None = as large as the encoder allows)
    bandwidth: int = 0           # bits/s, for the master playlist
    resolution: tuple[int, int] | None = None
    gpu: bool = True             # the all-GPU path may be used (off after an FFmpeg run failed)
    seek: float = 0.0            # copy: the input seek of the current run (see stream.hls_copy_cmd)
    proc: subprocess.Popen | None = None
    job_start: int = 0           # the segment the current FFmpeg run started at
    wanted: int = 0              # the segment asked for last (where the player is)
    killed: bool = False         # the current FFmpeg run was stopped by us, not by an error
    last_access: float = 0.0

    @property
    def ext(self) -> str:
        return "m4s" if self.copy else "ts"

    @property
    def segments(self) -> int:
        return len(self.bounds)

    def time(self, k: int) -> float:
        return self.bounds[min(max(k, 0), self.segments - 1)] if k < self.segments else self.duration

    def at(self, t: float) -> int:
        """The segment playing at `t` seconds."""
        return max(0, bisect.bisect_right(self.bounds, t + 0.001) - 1)

    def file(self, k: int) -> Path:
        return self.dir / f"{k}.{self.ext}"

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def made_up_to(self) -> int:
        """The first segment from `job_start` on that isn't on disk yet."""
        k = self.job_start
        while self.file(k).exists():
            k += 1
        return k

    def playlist(self) -> str:
        n = self.segments
        lengths = [self.time(k + 1) - self.bounds[k] for k in range(n)]
        lines = ["#EXTM3U", f"#EXT-X-VERSION:{7 if self.copy else 3}",
                 f"#EXT-X-TARGETDURATION:{math.ceil(max(lengths, default=1)) + (0 if self.copy else 1)}",
                 "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-PLAYLIST-TYPE:VOD"]
        if self.copy:
            lines.append('#EXT-X-MAP:URI="init.mp4"')
        for k, d in enumerate(lengths):
            lines += [f"#EXTINF:{max(d, 0.001):.3f},", f"{k}.{self.ext}"]
        lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines) + "\n"


@dataclass(eq=False)
class Session:
    id: str
    file_id: int
    path: Path
    video: dict | None
    audio: int
    duration: float
    dir: Path
    variants: list[Variant]
    channels: int = 2
    burn: int | tuple | None = None  # image subtitle painted on: n-th subtitle stream, or (sidecar .idx, n)
    video_codec: str | None = None
    copy_audio: bool = False     # copy variant: Dolby audio passed through as-is (the player's device decodes it)
    closed: bool = False
    last_access: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def playlist(self) -> str:
        """The master playlist: one entry per variant, largest first."""
        lines = ["#EXTM3U", f"#EXT-X-VERSION:{7 if any(v.copy for v in self.variants) else 3}",
                 "#EXT-X-INDEPENDENT-SEGMENTS"]
        for v in self.variants:
            attrs = f"BANDWIDTH={max(v.bandwidth, 100_000)}"
            if v.resolution:
                attrs += f",RESOLUTION={v.resolution[0]}x{v.resolution[1]}"
            lines += [f"#EXT-X-STREAM-INF:{attrs}", f"{v.index}/index.m3u8"]
        return "\n".join(lines) + "\n"


def uniform_bounds(duration: float) -> list[float]:
    return [k * stream.SEGMENT for k in range(max(1, math.ceil(duration / stream.SEGMENT)))]


def copy_bounds(keyframes: list[float]) -> list[float]:
    """Segment starts for a copy variant: every keyframe, the first one counted from 0."""
    return [0.0, *keyframes[1:]] if keyframes else [0.0]


def output_size(video: dict | None, encoder: str | None, height: int | None) -> tuple[int, int] | None:
    """The frame size a conversion makes (what `transcode_filters` scales to), for the master playlist."""
    return stream.output_size(video, encoder, height) if encoder else None


def ladder(video: dict | None, encoder: str | None) -> list[int | None]:
    """Heights for "Auto": the full size, then each LADDER size below it."""
    full = (output_size(video, encoder, None) or (0, 0))[1]
    return [None, *(h for h in LADDER if h < full - 8)]


class Keyframes:
    """Keyframe lists for copy variants, cached in the data dir per file version (size + mtime)."""

    def __init__(self, root: Path, read: Callable = stream.keyframes):
        self.root, self._read = root, read
        self._lock = threading.Lock()
        self._mem: dict[str, list[float]] = {}

    def get(self, file_id: int, path: Path, size: int, mtime_ns: int) -> list[float] | None:
        key = f"{file_id}-{size}-{mtime_ns}"
        with self._lock:
            if key in self._mem:
                return self._mem[key]
        f = self.root / f"{key}.json"
        try:
            kf = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            t = time.monotonic()
            kf = self._read(path)
            if kf is None:
                return None
            log.info("keyframes of file %s: %d in %.1f s", file_id, len(kf), time.monotonic() - t)
            self.root.mkdir(parents=True, exist_ok=True)
            for old in self.root.glob(f"{file_id}-*.json"):  # an older version of the same file
                old.unlink(missing_ok=True)
            f.write_text(json.dumps(kf), encoding="utf-8")
        with self._lock:
            self._mem[key] = kf
        return kf


def _default_cmd(s: Session, v: Variant, k: int) -> list[str]:
    if v.copy:
        return stream.hls_copy_cmd(s.path, k, v.seek, s.video_codec, v.dir, s.audio, s.channels, s.copy_audio)
    return stream.hls_cmd(s.path, k, s.video, v.dir, s.audio, max_height=v.height, channels=s.channels,
                          burn=s.burn, gpu=v.gpu)


class Transcodes:
    """Every running video conversion: HLS sessions, plus a count of plain fMP4 transcode streams."""

    def __init__(self, root: Path, limit: Callable[[], int], spawn: Callable = stream.spawn,
                 cmd: Callable = _default_cmd, copy_start: Callable = stream.remux_start):
        self.root = root
        self.limit = limit  # 0 or less = no limit
        self._spawn, self._cmd, self._copy_start = spawn, cmd, copy_start
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
        enough ahead), so a viewer never loses their place to a newcomer and gets "busy" mid-film.
        Copy sessions (audio-only remux) cost little and aren't counted."""
        self._pipes = {p for p in self._pipes if p.poll() is None}
        return len(self._pipes) + sum(1 for s in self._sessions.values() if not s.variants[0].copy)

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
    def create(self, file_id: int, path: Path, video: dict | None, duration: float, audio: int = 0,
               heights: list[int | None] | None = None, *, channels: int = 2, burn: int | tuple | None = None,
               keyframes: list[float] | None = None, video_codec: str | None = None, start: float = 0.0,
               encoder: str | None = None, bitrate: int | None = None, copy_audio: bool = False) -> Session:
        """A conversion (`heights`: one or more sizes; None = full size) or, with `keyframes`, a copy of the
        video with converted audio. `start`: where the player begins, so the first FFmpeg run starts there."""
        copy = keyframes is not None
        with self._lock:
            if not copy:
                self._check()  # the session holds its place until closed, however often FFmpeg restarts
            sid = secrets.token_urlsafe(9)
            d = self.root / sid
            d.mkdir()
        variants = []
        if copy:
            (d / "0").mkdir()
            w, h = (video or {}).get("width"), (video or {}).get("height")
            variants.append(Variant(0, copy_bounds(keyframes), duration, d / "0", copy=True,
                                    bandwidth=bitrate or 8_000_000, resolution=(w, h) if w and h else None))
        else:
            for i, height in enumerate(heights or [None]):
                (d / str(i)).mkdir()
                size = output_size(video, encoder, height)
                kbps = stream.quality_bitrate(video, encoder, height) if encoder else 8000
                variants.append(Variant(i, uniform_bounds(duration), duration, d / str(i), height=height,
                                        bandwidth=kbps * 1000 + 200_000, resolution=size))
        for v in variants:
            v.wanted = v.at(start)
            v.job_start = v.wanted
        s = Session(sid, file_id, path, video, audio, duration, d, variants, channels=channels, burn=burn,
                    video_codec=video_codec, copy_audio=copy and copy_audio)
        with self._lock:
            self._sessions[sid] = s
        log.info("HLS %s: file %s, %.0f s, %s", sid, file_id, duration,
                 "video copied" if copy else ", ".join(f"{h}p" if h else "full size" for h in heights or [None]))
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
            for v in s.variants:
                self._kill(v)
        shutil.rmtree(s.dir, ignore_errors=True)

    def variant(self, s: Session, v: int) -> Variant:
        if not 0 <= v < len(s.variants):
            raise KeyError(v)
        return s.variants[v]

    def segment(self, s: Session, vi: int, k: int) -> Path:
        """The file of segment k of variant vi, made (or waited for) if it isn't there yet. Blocking: run it
        in a thread."""
        v = self.variant(s, vi)
        if not 0 <= k < v.segments:
            raise KeyError(k)
        f = v.file(k)
        s.last_access = v.last_access = time.monotonic()
        with s.lock:
            if s.closed:
                raise SegmentGone(k)
            v.wanted = k
            if not f.exists() and not self._coming(v, k):
                self._restart(s, v, k)
        deadline = time.monotonic() + WAIT
        while time.monotonic() < deadline:
            if f.exists():
                return f
            with s.lock:
                if s.closed or (v.wanted != k and not self._coming(v, k)):
                    raise SegmentGone(k)  # superseded by a seek; don't fight over FFmpeg
                if not v.running():
                    if f.exists():
                        return f
                    self._after_exit(s, v, k)
            time.sleep(POLL)
        raise TimeoutError(k)

    def init(self, s: Session, vi: int) -> Path:
        """A copy variant's fMP4 header (every FFmpeg run writes an identical one)."""
        v = self.variant(s, vi)
        if not v.copy:
            raise KeyError("init")
        s.last_access = v.last_access = time.monotonic()
        deadline = time.monotonic() + WAIT
        while time.monotonic() < deadline:
            # the header is complete once a segment is: FFmpeg creates the file first and fills it as it starts
            done = sorted((p for p in v.dir.glob("init_*.mp4") if p.stat().st_size and (
                any(v.dir.glob("*.m4s")) or not v.running())), key=lambda p: p.stat().st_mtime)
            if done:
                return done[-1]
            with s.lock:
                if s.closed:
                    raise SegmentGone("init")
                if not v.running():
                    self._after_exit(s, v, v.wanted, initial=v.proc is None)
            time.sleep(POLL)
        raise TimeoutError("init")

    # -- internals (callers hold s.lock)
    def _after_exit(self, s: Session, v: Variant, k: int, initial: bool = False) -> None:
        """FFmpeg isn't running while segment k is wanted: start it, or report why it can't be made."""
        p = v.proc
        if p is not None and not v.killed and v.job_start <= k and not initial:
            if p.returncode == 0:
                raise KeyError(k)  # FFmpeg reached the real end before this segment
            if v.gpu and not v.copy:
                log.warning("HLS %s: FFmpeg failed (exit code %s); retrying without GPU filters", s.id, p.returncode)
                v.gpu = False
                enc = stream.video_encoder()
                if enc and stream.gpu_filters(s.video, enc, stream.tonemap_mode(s.video), s.burn):
                    stream.gpu_failed(enc, s.video)  # (it was an all-GPU run): not again for this kind of video
            else:
                raise RuntimeError(f"FFmpeg stopped with exit code {p.returncode} (see the server log)")
        self._restart(s, v, k)  # first start, stopped for being far ahead, or retrying on the CPU path

    def _coming(self, v: Variant, k: int) -> bool:
        return v.running() and v.job_start <= k and v.time(k) <= v.time(v.made_up_to()) + SOON

    def _restart(self, s: Session, v: Variant, k: int) -> None:
        self._kill(v)  # no limit check: the session took its place when it was created
        if v.copy:
            # FFmpeg can only start a copy where the file's index lets it seek, which may be a keyframe or more
            # before the one asked for. A dry run of the very same seek says where: numbering starts there, or
            # every segment would be misnamed. (A hair past the keyframe, so rounding can't go one further back.)
            v.seek = v.bounds[k] + 0.001 if k > 0 else 0.0
            if k > 0:
                k = min(k, v.at(self._copy_start(s.path, v.seek, zero=True)))
        v.proc = self._spawn(self._cmd(s, v, k))
        v.job_start, v.killed = k, False
        log.debug("HLS %s/%d: FFmpeg from segment %d", s.id, v.index, k)

    def _kill(self, v: Variant) -> None:
        if v.running():
            v.killed = True
            v.proc.kill()
            try:
                v.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log.warning("HLS: FFmpeg didn't stop (%s)", v.dir)
        for tmp in v.dir.glob("*.tmp"):  # the segment it was writing
            try:
                tmp.unlink()
            except OSError:
                pass

    def _prune(self, v: Variant) -> None:
        here = v.time(v.wanted)
        for f in v.dir.glob(f"*.{v.ext}"):
            try:
                if abs(v.time(int(f.stem)) - here) > KEEP:
                    f.unlink()
            except (ValueError, OSError):  # not a segment, or being served (Windows)
                pass

    def reap(self) -> None:
        """Close idle sessions, stop FFmpeg runs that are far enough ahead or that the player switched away
        from, delete far-away segments."""
        now = time.monotonic()
        with self._lock:
            sessions = list(self._sessions.values())
        for s in sessions:
            if now - s.last_access > IDLE:
                log.info("HLS %s: idle, closed", s.id)
                self.close(s.id)
                continue
            with s.lock:
                latest = max(v.last_access for v in s.variants)
                for v in s.variants:
                    if v.running() and (v.time(v.made_up_to()) > v.time(v.wanted) + AHEAD
                                        or (now - v.last_access > SWITCHED and v.last_access < latest)):
                        self._kill(v)
                    self._prune(v)

    def _reap_loop(self) -> None:
        while not self._stop.wait(2.0):
            try:
                self.reap()
            except Exception:  # never let the reaper die
                log.exception("HLS reaper")
