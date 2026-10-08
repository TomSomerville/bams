"""The traffic log: one JSON line per request that reaches the server (security.Gate records them).

- Written by a background thread, so a request never waits on the disk. If the disk can't keep up, entries are
  dropped and counted rather than slowing playback.
- Files are `netflow-<ms since 1970>.jsonl` in one folder (data dir/netflow by default; the admin can move
  it). A file is closed at a tenth of the size cap and a new one started; the oldest files are deleted so all
  of them together stay under the cap (10 GB by default). So the log is trimmed from its old end.
- Reading goes backwards from the newest entry, a bounded amount per call, with a cursor for older ones.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 10 * 1024**3
MIN_MAX_BYTES = 10 * 1024**2
MAX_MAX_BYTES = 100 * 1024**4
SEGMENT_MAX = 256 * 1024**2
SCAN_BUDGET = 64 * 1024**2   # bytes read per search call before handing back a cursor
_PREFIX, _SUFFIX = "netflow-", ".jsonl"


def segment_size(max_bytes: int) -> int:
    return max(1024**2, min(SEGMENT_MAX, max_bytes // 10))


class Netflow:
    def __init__(self, folder: Path, max_bytes: int = DEFAULT_MAX_BYTES):
        self.folder, self.max_bytes = Path(folder), int(max_bytes)
        self.dropped = 0
        self._q: queue.Queue = queue.Queue(maxsize=50_000)
        self._lock = threading.Lock()   # the open file, folder and cap
        self._fh = None
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    # -- writing

    def record(self, entry: dict) -> None:
        if self._thread is None:
            self._start()
        try:
            self._q.put_nowait(entry)
        except queue.Full:
            self.dropped += 1

    def _start(self) -> None:
        with self._start_lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="netflow", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while True:
            batch = [self._q.get()]
            while len(batch) < 1000:
                try:
                    batch.append(self._q.get_nowait())
                except queue.Empty:
                    break
            try:
                self._write(batch)
            except Exception as e:  # noqa: BLE001 - a full or missing disk mustn't kill the thread
                self.dropped += len(batch)
                log.warning("traffic log: couldn't write to %s: %s", self.folder, e)
                time.sleep(1)
            finally:
                for _ in batch:
                    self._q.task_done()

    def _write(self, batch: list[dict]) -> None:
        lines = [(json.dumps(e, separators=(",", ":"), ensure_ascii=False) + "\n").encode() for e in batch]
        with self._lock:
            seg = segment_size(self.max_bytes)
            while lines:
                fh = self._open()
                room, n = seg - fh.tell(), 0
                while n < len(lines) and (room > 0 or n == 0):
                    room -= len(lines[n])
                    n += 1
                fh.write(b"".join(lines[:n]))
                fh.flush()
                del lines[:n]
                if fh.tell() >= seg:
                    fh.close()
                    self._fh = None
                    self._trim()

    def _open(self):
        if self._fh is None:
            self.folder.mkdir(parents=True, exist_ok=True)
            files = self.files()
            seg = segment_size(self.max_bytes)
            if files and files[-1].stat().st_size < seg:
                path = files[-1]
            else:  # named by the time, and always after the newest one, so the names sort oldest first
                ms = time.time_ns() // 1_000_000
                if files:
                    ms = max(ms, int(files[-1].name[len(_PREFIX):-len(_SUFFIX)]) + 1)
                path = self.folder / f"{_PREFIX}{ms:015d}{_SUFFIX}"
            self._fh = open(path, "ab")  # noqa: SIM115 - kept open between batches
            self._trim()
        return self._fh

    def _trim(self) -> None:
        """Delete the oldest files until all of them fit under the cap (the one being written stays)."""
        files = self.files()
        sizes = {f: f.stat().st_size for f in files}
        total = sum(sizes.values())
        current = Path(self._fh.name) if self._fh else None
        for f in files:
            if total <= self.max_bytes:
                break
            if f == current:
                continue
            try:
                f.unlink()
                total -= sizes[f]
            except OSError as e:
                log.warning("traffic log: couldn't delete %s: %s", f, e)

    def flush(self, timeout: float = 5.0) -> None:
        """Wait until everything recorded so far is on disk (tests, and before moving the log)."""
        end = time.monotonic() + timeout
        while self._q.unfinished_tasks and time.monotonic() < end:
            time.sleep(0.01)

    def configure(self, folder: Path | None = None, max_bytes: int | None = None) -> None:
        """Move to another folder (files already written stay where they are) and/or change the cap."""
        self.flush()
        with self._lock:
            if self._fh:
                self._fh.close()
                self._fh = None
            if folder is not None:
                self.folder = Path(folder)
            if max_bytes is not None:
                self.max_bytes = int(max_bytes)
            if self.folder.is_dir():
                self._trim()

    # -- reading

    def files(self) -> list[Path]:
        try:
            return sorted(p for p in self.folder.iterdir()
                          if p.name.startswith(_PREFIX) and p.name.endswith(_SUFFIX)
                          and p.name[len(_PREFIX):-len(_SUFFIX)].isdigit() and p.is_file())
        except OSError:
            return []

    def usage(self) -> dict:
        files = self.files()
        size = 0
        for f in files:
            try:
                size += f.stat().st_size
            except OSError:
                pass
        oldest = None
        if files:
            try:
                oldest = int(files[0].name[len(_PREFIX):-len(_SUFFIX)]) / 1000
            except ValueError:
                pass
        return {"bytes": size, "files": len(files), "oldest": oldest, "dropped": self.dropped}

    def read(self, q: str | None = None, before: str | None = None, limit: int = 200) -> dict:
        """Newest entries first (only lines containing `q`, any case). `before` is the cursor a previous call
        returned. `next` is where to go on for older ones (None at the very start of the log)."""
        needle = (q or "").strip().lower().encode()
        files = self.files()
        names = [f.name for f in files]
        start_file, start_off = len(files) - 1, None
        if before:
            name, _, off = before.rpartition(":")
            if name in names:
                start_file, start_off = names.index(name), int(off)
            else:  # that file has been trimmed away since: carry on from the newest one older than it
                start_file = sum(1 for n in names if n < name) - 1
        out: list[dict] = []
        budget = SCAN_BUDGET
        for i in range(start_file, -1, -1):
            f = files[i]
            try:
                end = start_off if i == start_file and start_off is not None else f.stat().st_size
                for off, line in _lines_backwards(f, end):
                    budget -= len(line) + 1
                    if needle and needle not in line.lower():
                        if budget <= 0:
                            return {"entries": out, "next": f"{f.name}:{off}"}
                        continue
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue  # a line still being written
                    if len(out) >= limit or budget <= 0:
                        return {"entries": out, "next": f"{f.name}:{off}" if off or i else None}
            except OSError:
                continue
        return {"entries": out, "next": None}


def _lines_backwards(path: Path, end: int, block: int = 1024**2):
    """(offset, line) for each whole line in path[:end], last line first."""
    with open(path, "rb") as fh:
        pos, tail = end, b""
        while pos > 0:
            n = min(block, pos)
            pos -= n
            fh.seek(pos)
            chunk = fh.read(n) + tail
            parts = chunk.split(b"\n")
            tail = parts[0]  # may continue in the previous block
            off = pos + len(chunk)
            for part in reversed(parts[1:]):
                off -= len(part) + 1
                if part:
                    yield off + 1, part
        if tail:
            yield 0, tail


def check_folder(folder: str, forbidden: list[Path]) -> Path:
    """A folder the traffic log may be written to: absolute, not inside a media folder or a folder BAMS wipes,
    creatable and writable. Raises ValueError with a message for the admin."""
    from . import readonly
    p = Path(folder.strip()).expanduser()
    if not folder.strip() or not p.is_absolute():
        raise ValueError("Give a full path, like D:\\BAMS logs or /var/log/bams.")
    if readonly.is_protected(p) or readonly.is_protected(p / "x"):
        raise ValueError("That's inside a media library folder, which BAMS never writes to.")
    if any(p.resolve().is_relative_to(bad.resolve()) for bad in forbidden):
        raise ValueError("BAMS empties that folder when it starts; pick another one.")
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / f".bams-write-test-{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as e:
        raise ValueError(f"BAMS can't write there: {e.strerror or e}") from None
    return p
