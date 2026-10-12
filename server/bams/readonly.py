"""Read-only access to media folders.

BAMS must never modify a media folder: no writes, renames, deletes, permission or timestamp
changes, and no sidecar files (artwork, .nfo, thumbnails). One exception, the owner's decision of 2026-10-12:
`create_sidecar` may create a NEW subtitle file next to a video (OpenSubtitles downloads, a setting that's on by
default). It creates only (an existing file is never opened for writing), only `.srt`, only in the video's own
folder; every other write stays refused, even while it runs. Three layers enforce the rest:

1. Every media read goes through this module, which only opens files read-only.
2. A process-wide audit hook (sys.addaudithook) refuses any write-type operation whose target is
   inside a registered media root, wherever in the process it comes from: our code, a library,
   or a future bug. Audit hooks can't be removed once installed.
3. The OS: run the service as an account that only has read permission on the media folders
   (see docs/READ-ONLY.md). This is the real wall. Layers 1 and 2 make sure BAMS never even tries.

Subprocesses (ffprobe) are outside the audit hook's reach. ffprobe only reads, and layer 3
still applies to it.
"""

from __future__ import annotations

import logging
import os
import stat
import struct
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_lock = threading.Lock()
_roots: tuple[str, ...] = ()  # normcased absolute paths, replaced atomically
_installed = False

# Audit events that change the filesystem, and which of their arguments are target paths.
_PATH_EVENTS: dict[str, tuple[int, ...]] = {
    "os.remove": (0,), "os.rmdir": (0,), "os.mkdir": (0,), "os.chmod": (0,), "os.chown": (0,),
    "os.chflags": (0,), "os.lchflags": (0,), "os.utime": (0,), "os.truncate": (0,),
    "os.setxattr": (0,), "os.removexattr": (0,), "os.rename": (0, 1), "os.link": (0, 1),
    "os.symlink": (1,), "shutil.rmtree": (0,), "shutil.copyfile": (1,), "shutil.copymode": (1,),
    "shutil.copystat": (1,), "shutil.copytree": (1,), "shutil.move": (0, 1),
    "tempfile.mkstemp": (0,), "tempfile.mkdtemp": (0,), "sqlite3.connect": (0,),
}


class ReadOnlyViolation(PermissionError):
    pass


def _norm(p: object) -> str | None:
    if isinstance(p, int) or p is None:  # file descriptors: the open that made them was checked
        return None
    try:
        s = os.fsdecode(os.fspath(p))  # type: ignore[arg-type]
    except TypeError:
        return None
    if s in ("", ":memory:"):
        return None
    return os.path.normcase(os.path.abspath(s))


def is_protected(path: object) -> bool:
    p = _norm(path)
    if p is None:
        return False
    return any(p == r or p.startswith(r + os.sep) for r in _roots)


def _is_write_open(mode: object, flags: object) -> bool:
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return True
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


# The one write create_sidecar is making on this thread right now: its target, normalised. Nothing else is let through.
_allowed = threading.local()


def _sidecar_write(event: str, args: tuple) -> bool:
    """Is this create_sidecar's own write: an exclusive create ("x" mode) of its target, or removing that same file
    after a failed write? Only on the thread making it."""
    target = getattr(_allowed, "target", None)
    if target is None or not args or _norm(args[0]) != target:
        return False
    if event == "open":
        return len(args) >= 2 and isinstance(args[1], str) and "x" in args[1]
    return event == "os.remove"


def _hook(event: str, args: tuple) -> None:
    if not _roots:
        return
    if event == "open":
        if len(args) >= 3 and _is_write_open(args[1], args[2]) and is_protected(args[0]) \
                and not _sidecar_write(event, args):
            raise ReadOnlyViolation(f"BAMS is read-only on media folders; refused to write {args[0]!r}")
        return
    if event == "os.remove" and _sidecar_write(event, args):
        return
    idx = _PATH_EVENTS.get(event)
    if idx is not None:
        for i in idx:
            if i < len(args) and is_protected(args[i]):
                raise ReadOnlyViolation(f"BAMS is read-only on media folders; refused {event} on {args[i]!r}")


def install_guard() -> None:
    global _installed
    with _lock:
        if not _installed:
            sys.addaudithook(_hook)
            _installed = True


def set_protected_roots(paths: list[str] | list[Path]) -> None:
    """Replace the set of protected media roots (both the given and the symlink-resolved form)."""
    global _roots
    out: set[str] = set()
    for p in paths:
        for form in (os.path.abspath(p), os.path.realpath(p)):
            out.add(os.path.normcase(form).rstrip("\\/") or os.sep)
    with _lock:
        _roots = tuple(sorted(out))


def protected_roots() -> tuple[str, ...]:
    return _roots


SIDECAR_EXTS = (".srt",)


def create_sidecar(video: Path, name: str, data: bytes) -> Path:
    """The one write BAMS makes in a media folder (owner, 2026-10-12): a NEW subtitle file `name` in `video`'s own
    folder. Exclusive create: if the name is taken, nothing is written (FileExistsError) and the file there is never
    opened for writing. `name` must be a plain file name ending in .srt; ValueError otherwise. A write that fails
    half-way removes its own new file. Everything else stays refused by the audit hook while it runs. The OS can
    still say no (a read-only mount, the Linux service's sandbox): that OSError is the caller's to report."""
    if (not name.lower().endswith(SIDECAR_EXTS) or os.path.basename(name) != name or "/" in name or "\\" in name
            or name.startswith(".")):
        raise ValueError(f"not a subtitle file name: {name!r}")
    target = Path(video).parent / name
    _allowed.target = _norm(target)
    try:
        with open(target, "xb") as f:
            try:
                f.write(data)
            except BaseException:
                f.close()
                os.remove(target)  # our own half-written file, nothing else
                raise
    finally:
        _allowed.target = None
    return target


# ---------------------------------------------------------------- read helpers

@dataclass(frozen=True)
class FileEntry:
    path: Path      # absolute
    rel: str        # relative to the root, '/'-separated (portable across OSes)
    size: int
    mtime_ns: int


def walk(root: Path, exts: frozenset[str], skip_dirs: frozenset[str],
         nested_skip_dirs: frozenset[str] = frozenset(), side_exts: frozenset[str] = frozenset(),
         side: list[FileEntry] | None = None) -> Iterator[FileEntry]:
    """Yield media files under root. Never follows symlinked directories (loops, escapes).
    `nested_skip_dirs` are only skipped below the top level (extras folders inside a title).
    Files with a `side_exts` extension (cue sheets, cover images, playlists) are appended to `side` instead:
    they come from the same directory listing, so finding them costs nothing extra."""
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            it = os.scandir(d)
        except OSError as e:
            log.warning("cannot list %s: %s", d, e)
            continue
        with it:
            for ent in it:
                name = ent.name
                try:
                    if ent.is_dir(follow_symlinks=False):
                        key = name.casefold()
                        if (key not in skip_dirs and not name.startswith(".")
                                and not (depth >= 1 and key in nested_skip_dirs)):
                            stack.append((Path(ent.path), depth + 1))
                        continue
                    ext = os.path.splitext(name)[1].casefold()
                    is_side = side is not None and ext in side_exts
                    if (ext not in exts and not is_side) or name.startswith("._"):
                        continue
                    st = ent.stat()  # follows file symlinks: a linked file is still media
                    if not stat.S_ISREG(st.st_mode):
                        continue
                except OSError as e:
                    log.warning("cannot stat %s: %s", ent.path, e)
                    continue
                p = Path(ent.path)
                fe = FileEntry(p, p.relative_to(root).as_posix(), st.st_size, st.st_mtime_ns)
                if is_side:
                    side.append(fe)  # type: ignore[union-attr]
                else:
                    yield fe


def open_ro(path: Path):
    """Open a media file for reading. The only way BAMS code opens media files."""
    return open(path, "rb", buffering=0)


def read_text(path: Path, limit: int = 1_000_000) -> str | None:
    """A small text file next to the media (cue sheet, playlist) in whatever encoding it came in: UTF-8 (with
    or without BOM), UTF-16, else Windows-1252. None if it's unreadable or bigger than `limit` bytes."""
    try:
        with open_ro(path) as f:
            data = f.read(limit + 1)
    except OSError as e:
        log.warning("can't read %s: %s", path, e)
        return None
    if len(data) > limit:
        log.warning("not reading %s: bigger than %d bytes", path, limit)
        return None
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def root_status(root: Path) -> dict:
    """Is the root reachable and listable? Never probes write access by writing."""
    ok = root.is_dir()
    listable = False
    if ok:
        try:
            with os.scandir(root) as it:
                next(it, None)
            listable = True
        except OSError:
            pass
    # os.access(W_OK) is accurate on Linux; on Windows it only sees the read-only attribute, not ACLs.
    writable = os.access(root, os.W_OK) if ok and sys.platform != "win32" else None
    return {"exists": ok, "readable": listable, "os_write_access": writable}


def quick_hash(path: Path, size: int) -> str:
    """OpenSubtitles-style hash: size + 64-bit sums of the first and last 64 KiB.
    Lets a scan recognise a moved/renamed file without reading the whole thing."""
    chunk = 65536
    h = size
    with open_ro(path) as f:
        head = f.read(chunk)
        if size > chunk:
            f.seek(max(0, size - chunk))
        tail = f.read(chunk)
    for buf in (head, tail):
        buf = buf[: len(buf) - len(buf) % 8]
        for (v,) in struct.iter_unpack("<Q", buf):
            h = (h + v) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"
