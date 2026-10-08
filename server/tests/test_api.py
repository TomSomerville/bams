"""API smoke tests through FastAPI's TestClient (no network, scheduler off)."""

from fastapi.testclient import TestClient

from bams import readonly
from bams.app import create_app
from bams.config import Paths
from conftest import make_tree, signed_in


def client(tmp_path, web_dir=None):
    return signed_in(create_app(Paths(tmp_path / "data"), start_scheduler=False, web_dir=web_dir))


def test_library_crud_and_validation(tmp_path):
    media = tmp_path / "media"
    make_tree(media, ["Show/Season 1/Show - S01E01.mkv"])
    c = client(tmp_path)
    try:
        r = c.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(media)]})
        assert r.status_code == 201, r.text
        lib = r.json()
        assert lib["roots"][0]["exists"] and lib["roots"][0]["readable"]

        # bad folder: clear 400 with a reason, nothing created
        r = c.post("/api/libraries", json={"name": "X", "type": "movie", "paths": [str(tmp_path / "nope")]})
        assert r.status_code == 400 and "not found" in r.json()["detail"]
        r = c.post("/api/libraries", json={"name": "Y", "type": "movie", "paths": [str(media / "Show")]})
        assert r.status_code == 400 and "overlaps" in r.json()["detail"]

        r = c.patch(f"/api/libraries/{lib['id']}", json={"scan_interval_hours": 2, "name": "Television"})
        assert r.json()["scan_interval_hours"] == 2 and r.json()["name"] == "Television"

        assert c.delete(f"/api/libraries/{lib['id']}").status_code == 204
        assert c.get("/api/libraries").json() == []
        assert (media / "Show/Season 1/Show - S01E01.mkv").is_file()  # media untouched
    finally:
        readonly.set_protected_roots([])


def test_movie_in_tv_library_is_flagged(tmp_path):
    """The real-world mistake: a movies folder added to a TV library. It must be visible, with a hint."""
    from bams import jobs
    media = tmp_path / "media"
    make_tree(media, ["Happy Gilmore 2/Happy.Gilmore.2.2025.1080p.WEB.h264-ETHEL.mkv", "Show/Show - S01E01.mkv"])
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(media)]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        assert c.get(f"/api/libraries/{lib['id']}").json()["files"]["unrecognized"] == 1
        [f] = c.get(f"/api/libraries/{lib['id']}/unrecognized").json()
        assert "Looks like a movie (Happy Gilmore 2, 2025)" in f["hint"]
    finally:
        readonly.set_protected_roots([])


def test_fs_browse(tmp_path):
    (tmp_path / "media" / "TV").mkdir(parents=True)
    (tmp_path / "media" / ".hidden").mkdir()
    c = client(tmp_path)
    start = c.get("/api/fs/browse").json()
    assert start["path"] is None and start["dirs"]
    r = c.get("/api/fs/browse", params={"path": str(tmp_path / "media")}).json()
    assert [d["name"] for d in r["dirs"]] == ["TV"]
    assert r["parent"] == str(tmp_path)
    assert c.get("/api/fs/browse", params={"path": "relative/path"}).status_code == 400


def test_spa_fallback(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>BAMS</html>")
    c = client(tmp_path, web_dir=web)
    r = c.get("/settings")
    assert "BAMS" in r.text                            # client-side route -> index.html
    assert r.headers["cache-control"] == "no-cache"    # re-checked, so a rebuilt UI is picked up
    assert c.get("/api/nope").status_code == 404       # API 404s stay 404s
    assert c.get("/assets/index-old.js").status_code == 404  # a script from an older build isn't the page


def test_connection_usable_from_another_thread(tmp_path):
    """FastAPI opens a request's connection in one threadpool thread and may run the endpoint in another."""
    import threading

    from bams.db import connect
    con = connect(tmp_path / "x.db")
    out = []
    t = threading.Thread(target=lambda: out.append(con.execute("SELECT 1").fetchone()[0]))
    t.start()
    t.join()
    assert out == [1]


def test_tmdb_key_never_returned(tmp_path):
    c = client(tmp_path)
    assert c.put("/api/settings/tmdb-key", json={"key": "not a key"}).status_code == 400
    s = c.get("/api/settings").json()["tmdb"]
    assert s == {"configured": False, "kind": None, "last4": None, "verified_at": None}
