import os
from pathlib import Path

import pytest

from bams import readonly
from bams.app import bootstrap
from bams.config import Paths
from bams.db import connect


def make_tree(root: Path, rels: list[str], size: int = 4096) -> None:
    for i, rel in enumerate(rels):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(os.urandom(size) + i.to_bytes(4, "little"))  # unique content per file


@pytest.fixture
def env(tmp_path):
    """A data dir and an (empty) media dir, side by side, plus a DB connection."""
    paths = Paths(tmp_path / "data")
    media = tmp_path / "media"
    media.mkdir()
    bootstrap(paths)
    con = connect(paths.db)
    yield paths, media, con
    con.close()
    readonly.set_protected_roots([])  # the audit hook is process-wide; don't leak roots between tests


@pytest.fixture
def unguarded():
    """Temporarily lift the guard so a test can change the media tree (simulating the user)."""
    class _U:
        def __enter__(self):
            self.saved = readonly.protected_roots()
            readonly.set_protected_roots([])

        def __exit__(self, *a):
            readonly._roots = self.saved  # noqa: SLF001
    return _U()


PASSWORD = "correct horse"


def signed_in(app, name: str = "admin", admin: bool = True):
    """A TestClient for `app`, signed in as a new account (an admin by default)."""
    from fastapi.testclient import TestClient

    from bams import auth
    c = TestClient(app)
    con = connect(app.state.paths.db)
    try:
        auth.create_user(con, name, PASSWORD, admin)
    finally:
        con.close()
    r = c.post("/api/auth/login", json={"name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return c
