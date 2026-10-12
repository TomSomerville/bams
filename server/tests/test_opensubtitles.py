"""OpenSubtitles (test session 3): search while watching, download one into the data dir, use it as a track.
Against a fake OpenSubtitles (httpx.MockTransport): tests never touch the network."""

import base64
import json
import time

import httpx
import pytest

from bams import jobs, opensubtitles, readonly, stream
from bams.app import create_app
from bams.config import Paths
from bams.db import connect
from conftest import make_tree, signed_in

KEY = "TestKey0123456789abcdef"  # the server admin's own OpenSubtitles API key (Settings)
SRT = "1\n00:00:01,000 --> 00:00:02,500\nHello there\n\n2\n00:00:03,000 --> 00:00:04,000\nGeneral Kenobi\n"


def _token() -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 86400}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{claims}.sig"


class FakeOpenSubtitles:
    """What BAMS asks and what it gets: an account "tom"/"right", two subtitles (one made for the file's hash)."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.downloads = 0
        self.quota_left = 19

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        assert req.headers["user-agent"].startswith("BAMS v")
        path = req.url.path
        if req.url.host == "www.opensubtitles.com":  # the temporary download link
            return httpx.Response(200, content=SRT.encode())
        if req.headers.get("api-key") != KEY:  # what they answer a key they don't know
            return httpx.Response(403, json={"message": "You cannot consume this service"})
        if path == "/api/v1/login":
            body = json.loads(req.content)
            if body != {"username": "tom", "password": "right"}:
                return httpx.Response(401, json={"message": "Error, invalid username/password", "status": 401})
            return httpx.Response(200, json={"token": _token(), "base_url": "vip-api.opensubtitles.com", "status": 200,
                                             "user": {"allowed_downloads": 20, "level": "Sub leecher", "vip": False}})
        if path == "/api/v1/logout":
            return httpx.Response(200, json={"message": "token successfully destroyed"})
        if path == "/api/v1/subtitles":
            p = dict(req.url.params)
            if "query" in p or "tmdb_id" in p or "parent_tmdb_id" in p:
                return httpx.Response(200, json={"total_count": 3, "data": [
                    self._sub(111, "en", "Catch-22.S01E01.WEB.x264-GRP", hash_match=True),
                    self._sub(222, "en", "Catch-22.S01E01.720p.HDTV", hi=True),
                    {**self._sub(333, "en", "two CDs"), "attributes": {**self._sub(333, "en", "x")["attributes"],
                                                                      "files": [{"file_id": 3}, {"file_id": 4}]}},
                ]})
            return httpx.Response(200, json={"total_count": 0, "data": []})
        if path == "/api/v1/download":
            if req.headers.get("authorization") == "Bearer stale":
                return httpx.Response(500, json={"message": "invalid token"})
            if self.quota_left <= 0:
                return httpx.Response(406, json={"message": "You have downloaded your allowed 20 subtitles for 24h."})
            self.downloads += 1
            self.quota_left -= 1
            fid = json.loads(req.content)["file_id"]
            return httpx.Response(200, json={"link": f"https://www.opensubtitles.com/download/ABC/subfile/{fid}.srt",
                                             "file_name": f"{fid}.srt", "requests": self.downloads,
                                             "remaining": self.quota_left, "message": "Your quota will be renewed"})
        return httpx.Response(404, json={"message": "unknown"})

    @staticmethod
    def _sub(fid: int, lang: str, release: str, hash_match: bool = False, hi: bool = False) -> dict:
        return {"id": str(fid), "type": "subtitle", "attributes": {
            "language": lang, "release": release, "hearing_impaired": hi, "download_count": 1000 - fid,
            "from_trusted": hash_match, "moviehash_match": hash_match, "fps": 23.976,
            "uploader": {"name": "someone"}, "files": [{"file_id": fid, "cd_number": 1, "file_name": release}]}}


@pytest.fixture
def os_env(tmp_path, monkeypatch):
    monkeypatch.setattr(opensubtitles, "_MIN_INTERVAL", 0)
    monkeypatch.setattr(opensubtitles, "_LOGIN_INTERVAL", 0)
    opensubtitles.reset()
    media = tmp_path / "media"
    make_tree(media, ["Catch-22/Season 1/Catch-22 S01E01.mkv"], size=200_000)
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    fake = FakeOpenSubtitles()
    c.app.state.opensubtitles_transport = httpx.MockTransport(fake)
    lib = c.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(media)]}).json()
    jobs.run_scan(paths, lib["id"], do_match=False)
    assert c.put("/api/settings/opensubtitles-key", json={"key": KEY}).status_code == 200
    con = connect(paths.db)
    con.execute("UPDATE items SET tmdb_id=73021 WHERE kind='show'")  # as if matched on TMDB
    ep = con.execute("SELECT id FROM items WHERE kind='episode'").fetchone()["id"]
    con.close()
    f = c.get(f"/api/items/{ep}").json()["files"][0]
    try:
        yield c, fake, paths, media, ep, f["id"]
    finally:
        opensubtitles.reset()
        readonly.set_protected_roots([])


def test_search_by_the_titles_ids_and_the_files_hash(os_env):
    c, fake, paths, media, ep, fid = os_env
    assert c.get(f"/api/items/{ep}").json()["opensubtitles"] is True  # the player offers it
    r = c.get(f"/api/files/{fid}/opensubtitles?languages=en")
    assert r.status_code == 200, r.text
    d = r.json()
    q = fake.calls[-1].url.params
    assert list(q.keys()) == sorted(q.keys())  # sorted and lowercase: their advice for cached answers
    assert dict(q) == {"episode_number": "1", "languages": "en", "moviehash": dict(q)["moviehash"],
                       "parent_tmdb_id": "73021", "season_number": "1", "type": "episode"}
    con = connect(paths.db)
    assert dict(q)["moviehash"] == con.execute("SELECT quick_hash FROM files WHERE id=?", (fid,)).fetchone()[0]
    con.close()
    assert d["by"] == "ids" and d["account"] is False
    assert d["what"] == {"kind": "episode", "title": "Episode 1", "year": None, "show": "Catch-22", "season": 1,
                         "episode": 1}
    assert [(x["file_id"], x["hash_match"], x["hearing_impaired"]) for x in d["results"]] == [(111, True, False),
                                                                                           (222, False, True)]
    assert c.get(f"/api/files/{fid}/opensubtitles?languages=en;drop").status_code == 422


def test_each_server_has_its_own_key_like_tmdb(os_env):
    """Owner's decision: the admin pastes their own OpenSubtitles API key. It's checked before it's kept, never sent
    back, and without one the feature is off."""
    c, fake, paths, media, ep, fid = os_env
    st = c.get("/api/settings").json()["opensubtitles"]
    assert st["configured"] and st["last4"] == KEY[-4:] and st["verified_at"] and KEY not in json.dumps(st)
    assert c.post("/api/settings/opensubtitles-key/test").json()["ok"] is True

    # a key OpenSubtitles refuses isn't kept; neither is something that isn't a key
    r = c.put("/api/settings/opensubtitles-key", json={"key": "WrongKey0123456789abcdef"})
    assert r.status_code == 400 and "didn't accept the API key" in r.json()["detail"]
    assert c.put("/api/settings/opensubtitles-key", json={"key": "not a key"}).status_code == 400
    # what a key looks like is up to OpenSubtitles: long, with dots and underscores, it's still theirs to judge
    calls = len(fake.calls)
    r = c.put("/api/settings/opensubtitles-key", json={"key": "Ab_c-d." * 20 + "x.y.z.w"})
    assert r.status_code == 400 and "didn't accept the API key" in r.json()["detail"] and len(fake.calls) == calls + 1
    # a sign-in token pasted by mistake (owner, 0.13.0): told what it is, not sent anywhere
    for exp, word in ((time.time() + 86400, "expires"), (time.time() - 7200, "expired")):
        claims = base64.urlsafe_b64encode(json.dumps({"id": 1, "exp": int(exp)}).encode()).decode().rstrip("=")
        r = c.put("/api/settings/opensubtitles-key", json={"key": f"eyJhbGciOiJIUzI1NiJ9.{claims}.n-sOft_wSU-x"})
        assert r.status_code == 400 and f"sign-in token (it {word}" in r.json()["detail"], r.text
        assert "opensubtitles.com/en/consumers" in r.json()["detail"]
    assert len(fake.calls) == calls + 1
    assert c.get("/api/settings").json()["opensubtitles"]["last4"] == KEY[-4:]
    viewer = signed_in(c.app, "Kid", admin=False)
    assert viewer.put("/api/settings/opensubtitles-key", json={"key": KEY}).status_code == 403

    # removed: off everywhere, nothing asked
    assert c.delete("/api/settings/opensubtitles-key").json()["configured"] is False
    calls = len(fake.calls)
    assert c.get(f"/api/items/{ep}").json()["opensubtitles"] is False
    r = c.get(f"/api/files/{fid}/opensubtitles")
    assert r.status_code == 409 and "No OpenSubtitles API key" in r.json()["detail"]
    assert c.put("/api/settings/opensubtitles", json={"username": "tom", "password": "right"}).status_code == 409
    assert len(fake.calls) == calls


def test_download_becomes_a_track_in_the_data_dir(os_env):
    c, fake, paths, media, ep, fid = os_env
    before = sorted((p.relative_to(media), p.stat().st_mtime_ns) for p in media.rglob("*"))
    r = c.post(f"/api/files/{fid}/opensubtitles",
               json={"file_id": 111, "language": "en", "release": "Catch-22.S01E01.WEB.x264-GRP"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["remaining"] == 18 and d["track"]["id"] == "d1" and d["track"]["source"] == "download"
    assert d["track"]["label"] == "English · Catch-22.S01E01.WEB.x264-GRP" and d["track"]["language"] == "en"
    assert (paths.root / "subtitles" / "opensubtitles" / "111.srt").read_text(encoding="utf-8") == SRT
    assert sorted((p.relative_to(media), p.stat().st_mtime_ns) for p in media.rglob("*")) == before  # media untouched
    # listed with the file's tracks, for everyone; the search marks it as already here
    subs = c.get(f"/api/items/{ep}").json()["files"][0]["subtitles"]
    assert [s["id"] for s in subs] == ["d1"]
    assert c.get(f"/api/files/{fid}/opensubtitles?languages=en").json()["results"][0]["track"] == "d1"
    # picking it again doesn't download it again (the daily quota is small)
    assert c.post(f"/api/files/{fid}/opensubtitles", json={"file_id": 111}).json()["track"]["id"] == "d1"
    assert fake.downloads == 1
    if stream.ffmpeg_path():
        vtt = c.get(f"/api/files/{fid}/subtitles/d1.vtt")
        assert vtt.status_code == 200 and vtt.text.startswith("WEBVTT") and "General Kenobi" in vtt.text


def test_account_sign_in_quota_and_removal(os_env):
    c, fake, paths, media, ep, fid = os_env
    r = c.put("/api/settings/opensubtitles", json={"username": "tom", "password": "wrong"})
    assert r.status_code == 400 and "didn't accept" in r.json()["detail"]
    assert c.get("/api/settings").json()["opensubtitles"]["user"] is None  # a refused account isn't kept
    r = c.put("/api/settings/opensubtitles", json={"username": "tom", "password": "right"})
    assert r.status_code == 200, r.text
    st = c.get("/api/settings").json()["opensubtitles"]
    assert st["user"] == "tom" and st["account"]["allowed_downloads"] == 20 and "right" not in json.dumps(st)
    viewer = signed_in(c.app, "Kid", admin=False)
    assert viewer.put("/api/settings/opensubtitles", json={"username": "x", "password": "y"}).status_code == 403

    # signed in: requests go to the account's API host with its token
    assert viewer.post(f"/api/files/{fid}/opensubtitles", json={"file_id": 222, "language": "en",
                                                                "hearing_impaired": True}).status_code == 200
    dl = next(x for x in fake.calls if x.url.path == "/api/v1/download")
    assert dl.url.host == "vip-api.opensubtitles.com" and dl.headers["authorization"].startswith("Bearer ")
    logins = sum(x.url.path == "/api/v1/login" for x in fake.calls)
    c.get(f"/api/files/{fid}/opensubtitles")
    assert sum(x.url.path == "/api/v1/login" for x in fake.calls) == logins  # the token is kept, not re-made
    # a token OpenSubtitles stopped accepting before its day was up: signed in again once, the download goes through
    opensubtitles._session["token"] = "stale"
    assert c.post(f"/api/files/{fid}/opensubtitles", json={"file_id": 333}).status_code == 200
    assert sum(x.url.path == "/api/v1/login" for x in fake.calls) == logins + 1

    fake.quota_left = 0
    r = c.post(f"/api/files/{fid}/opensubtitles", json={"file_id": 111})
    assert r.status_code == 429 and "allowed 20 subtitles" in r.json()["detail"]

    # removing: whoever downloaded it, or an admin
    track = c.get(f"/api/items/{ep}").json()["files"][0]["subtitles"][0]["id"]
    other = signed_in(c.app, "Other", admin=False)
    assert other.delete(f"/api/files/{fid}/subtitles/{track}").status_code == 403
    assert viewer.delete(f"/api/files/{fid}/subtitles/{track}").status_code == 204
    assert not (paths.root / "subtitles" / "opensubtitles" / "222.srt").exists()
    assert [s["ext_id"] for s in c.get(f"/api/items/{ep}").json()["files"][0]["subtitles"]] == ["333"]  # the admin's stays
    assert c.delete(f"/api/files/{fid}/subtitles/e0").status_code == 404  # the file's own: never

    assert c.delete("/api/settings/opensubtitles").json()["user"] is None
    assert any(x.url.path == "/api/v1/logout" for x in fake.calls)


def test_a_movie_without_ids_is_searched_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(opensubtitles, "_MIN_INTERVAL", 0)
    opensubtitles.reset()
    media = tmp_path / "media"
    make_tree(media, ["Ant-Man (2015)/ant-man.2015.mkv"], size=200_000)
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    fake = FakeOpenSubtitles()
    c.app.state.opensubtitles_transport = httpx.MockTransport(fake)
    try:
        lib = c.post("/api/libraries", json={"name": "Films", "type": "movie", "paths": [str(media)]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        c.put("/api/settings/opensubtitles-key", json={"key": KEY})
        movie = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
        fid = c.get(f"/api/items/{movie['id']}").json()["files"][0]["id"]
        d = c.get(f"/api/files/{fid}/opensubtitles").json()
        q = dict(fake.calls[-1].url.params)
        assert q["query"] == "ant-man" and q["year"] == "2015" and q["type"] == "movie" and "moviehash" in q
        assert d["by"] == "name" and len(d["results"]) == 2
    finally:
        readonly.set_protected_roots([])
