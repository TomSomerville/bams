"""Scan jobs: a single worker thread runs scans one at a time; a timer queues libraries that are due.

One worker (not one per library) on purpose: scans are disk/network bound, and running several
against the same NAS at once just makes them all slower.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from . import library, matcher, music, music_match, scanner
from .config import Paths
from .db import connect, get_setting, jdump, now
from .musicbrainz import MusicBrainz
from .tmdb import InvalidKey, Tmdb, TmdbError

log = logging.getLogger(__name__)
TICK = 30  # seconds between "is any library due?" checks


def tmdb_client(con) -> Tmdb | None:
    key = get_setting(con, "tmdb_key")
    if not key:
        return None
    try:
        return Tmdb(key, language=get_setting(con, "language", "en-US"))
    except InvalidKey:
        return None


def music_lookup_enabled(con) -> bool:
    """Online music identification (MusicBrainz & co.) is on unless the owner turned it off."""
    return get_setting(con, "music_lookup", "1") == "1"


def language(con) -> str:
    """'en-US' -> 'en' (Wikipedia language)."""
    return (get_setting(con, "language", "en-US") or "en").split("-")[0].lower()


def run_scan(paths: Paths, lib_id: int, trigger: str = "manual", *, do_match: bool = True,
             retry_unmatched: bool = False, progress=None) -> dict:
    """Scan one library, then match it on TMDB if a key is configured. Records a row in `scans`."""
    con = connect(paths.db)
    started = now()
    scan_id = con.execute("INSERT INTO scans (library_id, trigger, started_at, status) VALUES (?,?,?,'running')",
                          (lib_id, trigger, started)).lastrowid
    result: dict = {}
    status, error = "ok", None
    try:
        lib = library.get(con, lib_id)
        name = lib["name"]
        log.info("scan start: %s (%s)", name, trigger)
        result["scan"] = scanner.scan_library(con, lib_id, progress=progress).as_dict()
        if lib["type"] == "music":
            # Music is identified from its own tags (TMDB has no music); covers come from the files/folders.
            if progress:
                progress("Reading album art")
            result["artwork"] = music.fill_artwork(con, paths.images, lib_id).as_dict()
            if do_match and music_lookup_enabled(con):
                with MusicBrainz() as mb:
                    result["identify"] = music_match.match_music_library(
                        con, mb, paths.images, lib_id, retry_unmatched=retry_unmatched, lang=language(con),
                        progress=progress).as_dict()
            elif do_match:
                result["identify"] = "skipped: online music identification is turned off"
        elif do_match:
            tmdb = tmdb_client(con)
            if tmdb is None:
                result["match"] = "skipped: no TMDB key configured"
            else:
                try:
                    result["match"] = matcher.match_library(con, tmdb, paths.images, lib_id,
                                                            retry_unmatched=retry_unmatched, progress=progress).as_dict()
                except InvalidKey:
                    result["match"] = "skipped: TMDB rejected the configured key"
                except TmdbError as e:
                    result["match"] = f"failed: {e}"
                finally:
                    tmdb.close()
        if result["scan"]["roots_offline"]:
            status = "partial"
        log.info("scan done: %s %s", name, result)
    except Exception as e:  # noqa: BLE001 - a failed scan must not kill the worker
        log.exception("scan failed for library %s", lib_id)
        status, error = "error", str(e)
    finally:
        con.execute("UPDATE scans SET finished_at=?, status=?, stats=?, error=? WHERE id=?",
                    (now(), status, jdump(result), error, scan_id))
        con.execute("UPDATE libraries SET last_scan_at=?, last_scan_status=? WHERE id=?", (started, status, lib_id))
        con.close()
    return {"scan_id": scan_id, "status": status, "error": error, **result}


class Scheduler:
    def __init__(self, paths: Paths):
        self.paths = paths
        self._q: deque[tuple[int, str]] = deque()
        self._cv = threading.Condition()
        self._running: dict | None = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for target, name in ((self._worker, "bams-scan-worker"), (self._timer, "bams-scan-timer")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        with self._cv:
            self._cv.notify_all()

    def request(self, lib_id: int, trigger: str = "manual", retry_unmatched: bool = False) -> bool:
        """Queue a scan. False if that library is already queued or running."""
        with self._cv:
            if (self._running and self._running["library_id"] == lib_id) or any(q[0] == lib_id for q in self._q):
                return False
            self._q.append((lib_id, trigger if not retry_unmatched else trigger + "+rematch"))
            self._cv.notify()
            return True

    def status(self) -> dict:
        with self._cv:
            running = dict(self._running) if self._running else None
            if running:  # seconds into the current step, by the server's clock (for "time left")
                running["step_elapsed"] = now() - running["step_started_at"]
            return {"running": running,
                    "queued": [{"library_id": i, "trigger": t} for i, t in self._q]}

    def _progress(self, step: str, done: int | None = None, total: int | None = None,
                  bytes_done: int | None = None, bytes_total: int | None = None) -> None:
        """What the running scan is doing and how far it is (Settings shows it: N of M, size, time left)."""
        with self._cv:
            if self._running:
                r = self._running
                if r["step"] != step:
                    r["step_started_at"] = now()  # time left = this step's pace so far
                r.update(step=step, done=done, total=total, bytes_done=bytes_done, bytes_total=bytes_total)

    def _worker(self) -> None:
        while not self._stop.is_set():
            with self._cv:
                while not self._q and not self._stop.is_set():
                    self._cv.wait()
                if self._stop.is_set():
                    return
                lib_id, trigger = self._q.popleft()
                self._running = {"library_id": lib_id, "trigger": trigger, "started_at": now(), "step": "Starting",
                                 "step_started_at": now(), "done": None, "total": None, "bytes_done": None,
                                 "bytes_total": None}
            try:
                run_scan(self.paths, lib_id, trigger.replace("+rematch", ""),
                         retry_unmatched=trigger.endswith("+rematch"), progress=self._progress)
            finally:
                with self._cv:
                    self._running = None

    def _timer(self) -> None:
        # first pass right away, so a library that's overdue (server was off) scans at startup
        while not self._stop.is_set():
            try:
                con = connect(self.paths.db)
                try:
                    t = time.time()
                    for lib in con.execute("SELECT id, last_scan_at, scan_interval_hours FROM libraries"):
                        due = lib["last_scan_at"] is None or t - lib["last_scan_at"] >= lib["scan_interval_hours"] * 3600
                        if due:
                            self.request(lib["id"], "schedule" if lib["last_scan_at"] else "startup")
                finally:
                    con.close()
            except Exception:  # noqa: BLE001
                log.exception("scheduler tick failed")
            self._stop.wait(TICK)
