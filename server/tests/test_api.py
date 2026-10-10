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


def test_files_play_but_are_never_offered_for_download(tmp_path):
    """Owner's decision: BAMS has no downloads. A file is streamed for playing only, with no name to save it under."""
    from bams import jobs
    media = tmp_path / "media"
    make_tree(media, ["Film (2001)/Film (2001).mkv"])
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Films", "type": "movie", "paths": [str(media)]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        item = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
        f = c.get(f"/api/items/{item['id']}").json()["files"][0]
        assert "download_url" not in f
        assert c.get(f"/api/files/{f['id']}/download").status_code == 404
        r = c.get(f["stream_url"])
        assert r.status_code == 200 and "content-disposition" not in r.headers
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


def test_saving_tmdb_key_queues_video_libraries(tmp_path, monkeypatch):
    """Titles scanned before the key existed are matched right away, not at the next scheduled scan."""
    from bams import app as app_mod, library
    from bams.db import connect

    class FakeTmdb:
        def __init__(self, key, **kw):
            self.key = key

        def check(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(app_mod, "Tmdb", FakeTmdb)
    tv, music = tmp_path / "tv", tmp_path / "music"
    make_tree(tv, ["Show/Season 1/Show - S01E01.mkv"])
    make_tree(music, ["Artist/Album/01 - Song.mp3"])
    c = client(tmp_path)
    try:
        con = connect(tmp_path / "data" / "bams.db")
        tv_id = library.create(con, tmp_path / "data", "TV", "show", [str(tv)], 6)
        library.create(con, tmp_path / "data", "Music", "music", [str(music)], 6)
        con.close()
        r = c.put("/api/settings/tmdb-key", json={"key": "0123456789abcdef0123456789abcdef"})
        assert r.status_code == 200 and r.json()["configured"]
        assert c.get("/api/scans").json()["current"]["queued"] == [{"library_id": tv_id, "trigger": "tmdb-key+rematch"}]
    finally:
        readonly.set_protected_roots([])


def test_library_order(tmp_path):
    """Tester request: arrange the libraries in the sidebar. New ones go last; admins only."""
    for d in ("tv", "films", "music"):
        (tmp_path / d).mkdir()
    c = client(tmp_path)
    try:
        ids = [c.post("/api/libraries", json={"name": n, "type": t, "paths": [str(tmp_path / d)]}).json()["id"]
               for n, t, d in (("TV", "show", "tv"), ("Movies", "movie", "films"), ("Anime", "show", "music"))]
        names = lambda: [x["name"] for x in c.get("/api/libraries").json()]  # noqa: E731
        assert names() == ["TV", "Movies", "Anime"]  # in the order they were added
        assert c.put("/api/libraries/order", json={"ids": [ids[2], ids[0]]}).json() == [ids[2], ids[0], ids[1]]
        assert names() == ["Anime", "TV", "Movies"]  # the ones left out keep their place after
        assert c.put("/api/libraries/order", json={"ids": [999, ids[1]]}).status_code == 200  # unknown ids ignored
        assert names()[0] == "Movies"
        kid = signed_in(c.app, "Kid", admin=False)
        assert kid.put("/api/libraries/order", json={"ids": ids}).status_code == 403
    finally:
        readonly.set_protected_roots([])


def test_migration_orders_existing_libraries_by_name(tmp_path):
    import sqlite3

    from bams import db, library
    con = sqlite3.connect(tmp_path / "old.db", isolation_level=None)
    con.row_factory = sqlite3.Row
    con.executescript("BEGIN;" + db.SCHEMA + "PRAGMA user_version = 1; COMMIT;")
    for n in ("zebra", "Alpha", "middle"):
        con.execute("INSERT INTO libraries (name, type, scan_interval_hours, created_at) VALUES (?, 'show', 6, 0)", (n,))
    db.migrate(con)
    assert [r["name"] for r in library.listed(con)] == ["Alpha", "middle", "zebra"]
