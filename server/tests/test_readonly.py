"""The media folders must never be modified. These tests try hard to, and must fail."""

import hashlib
import os
import shutil
import sqlite3

import pytest

from bams import library, readonly
from bams.readonly import ReadOnlyViolation
from bams.scanner import scan_library
from conftest import make_tree

SHOW_FILES = [
    "Family Guy S15 1080p DSNP WEB-DL AAC2 0 H 264-OldT/Family.Guy.S15E01.The.the.Band.1080p.DSNP.WEB-DL.AAC2.0.H.264-OldT.mkv",
    "Family Guy S15 1080p DSNP WEB-DL AAC2 0 H 264-OldT/Family Guy S15 1080p DSNP WEB-DL AAC2 0 H 264-OldT.nfo",
    "Some Show/Some Show - Season 00 - 'S00E01-Episode name'.mkv",
]


def snapshot(root):
    """Every path (files and dirs) with size, mtime and content hash."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            p = os.path.join(dirpath, d)
            out[os.path.relpath(p, root)] = ("dir", os.stat(p).st_mtime_ns)
        for f in filenames:
            p = os.path.join(dirpath, f)
            st = os.stat(p)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = (st.st_size, st.st_mtime_ns, hashlib.sha256(fh.read()).hexdigest())
    return out


@pytest.fixture
def guarded(env):
    paths, media, con = env
    make_tree(media, SHOW_FILES)
    library.create(con, paths.root, "TV", "show", [str(media)])  # registers the root with the guard
    return paths, media, con


@pytest.mark.parametrize("attempt", [
    lambda m: open(m / "new.txt", "w"),
    lambda m: open(m / "Some Show" / "x.nfo", "a"),
    lambda m: open(m / "Some Show" / "Some Show - Season 00 - 'S00E01-Episode name'.mkv", "r+b"),
    lambda m: os.open(str(m / "fd.txt"), os.O_WRONLY | os.O_CREAT),
    lambda m: (m / "poster.jpg").write_bytes(b"x"),
    lambda m: os.remove(m / "Some Show" / "Some Show - Season 00 - 'S00E01-Episode name'.mkv"),
    lambda m: os.rename(m / "Some Show", m / "Renamed"),
    lambda m: os.replace(m / "Some Show", m / "Renamed"),
    lambda m: os.mkdir(m / "metadata"),
    lambda m: os.rmdir(m / "Some Show"),
    lambda m: os.utime(m / "Some Show", None),
    lambda m: os.chmod(m / "Some Show", 0o777),
    lambda m: shutil.copyfile(__file__, m / "copied.py"),
    lambda m: shutil.rmtree(m / "Some Show"),
    lambda m: sqlite3.connect(m / "cache.db"),
], ids=["open-w", "open-a", "open-r+", "os.open-wronly", "write_bytes", "remove", "rename", "replace",
        "mkdir", "rmdir", "utime", "chmod", "copyfile", "rmtree", "sqlite"])
def test_guard_blocks_writes(guarded, attempt):
    _, media, _ = guarded
    before = snapshot(media)
    with pytest.raises(ReadOnlyViolation):
        attempt(media)
    assert snapshot(media) == before


def test_guard_allows_reads_and_writes_elsewhere(guarded, tmp_path):
    paths, media, _ = guarded
    f = media / "Some Show" / "Some Show - Season 00 - 'S00E01-Episode name'.mkv"
    with readonly.open_ro(f) as fh:
        assert fh.read(10)
    (tmp_path / "outside.txt").write_text("fine")       # outside the media root
    (paths.root / "images" / "ok.txt").write_text("ok")  # BAMS data dir
    assert readonly.is_protected(f)
    assert not readonly.is_protected(paths.db)


def test_guard_is_case_and_form_insensitive(guarded):
    _, media, _ = guarded
    variant = str(media / "Some Show" / ".." / "new.txt")
    with pytest.raises(ReadOnlyViolation):
        open(variant, "w")
    if os.name == "nt":
        with pytest.raises(ReadOnlyViolation):
            open(str(media).upper() + "\\NEW.TXT", "w")


def test_full_scan_leaves_media_untouched(guarded):
    paths, media, con = guarded
    before = snapshot(media)
    lib_id = library.get(con, "TV")["id"]
    stats = scan_library(con, lib_id)
    assert stats.added == 2  # the .nfo isn't media
    stats = scan_library(con, lib_id)  # a rescan too
    assert stats.added == 0
    assert snapshot(media) == before


def test_media_root_cannot_contain_data_dir(env, tmp_path):
    paths, media, con = env
    with pytest.raises(library.LibraryError):
        library.create(con, paths.root, "Bad", "movie", [str(paths.root.parent)])  # tmp_path holds data/
    with pytest.raises(library.LibraryError):
        library.create(con, paths.root, "Bad2", "movie", [str(paths.root / "images")])


def test_nested_roots_rejected(env):
    paths, media, con = env
    (media / "a").mkdir()
    library.create(con, paths.root, "One", "show", [str(media)])
    with pytest.raises(library.LibraryError):
        library.create(con, paths.root, "Two", "movie", [str(media / "a")])
