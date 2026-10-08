"""Folder picker for the web UI: lists directories on the server (names only, read-only).

A browser can't open a native folder dialog on the server's disks, so the Add Library form
browses through this instead (Plex does the same).
"""

from __future__ import annotations

import os
import string
import sys
from pathlib import Path


class BrowseError(ValueError):
    pass


def _starts() -> list[dict]:
    """Where browsing starts: drives on Windows; / and the usual mount points on Linux."""
    out: list[dict] = []
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            d = f"{letter}:\\"
            if os.path.isdir(d):
                out.append({"name": d, "path": d})
    else:
        out.append({"name": "/", "path": "/"})
        for d in ("/mnt", "/media", "/srv", "/home"):
            if os.path.isdir(d):
                out.append({"name": d, "path": d})
    home = str(Path.home())
    if os.path.isdir(home):
        out.append({"name": f"Home ({home})", "path": home})
    return out


def browse(path: str | None) -> dict:
    if not path:
        return {"path": None, "parent": None, "dirs": _starts()}
    if not os.path.isabs(path):
        raise BrowseError("path must be absolute")
    p = os.path.abspath(path)
    if not os.path.isdir(p):
        raise BrowseError(f"not a folder (or not mounted): {p}")
    dirs = []
    try:
        with os.scandir(p) as it:
            for e in it:
                if e.name.startswith((".", "$")) or e.name in ("System Volume Information", "@eaDir", "lost+found"):
                    continue
                try:
                    if e.is_dir():
                        dirs.append({"name": e.name, "path": e.path})
                except OSError:
                    continue
    except PermissionError:
        raise BrowseError(f"BAMS has no permission to list {p}") from None
    except OSError as e:
        raise BrowseError(f"can't list {p}: {e.strerror or e}") from None
    dirs.sort(key=lambda d: d["name"].casefold())
    parent = str(Path(p).parent)  # a drive / UNC share / "/" is its own parent: no "up" from there
    return {"path": p, "parent": None if parent == p else parent, "dirs": dirs}
