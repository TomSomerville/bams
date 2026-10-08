"""TMDB client. Each BAMS install uses its owner's own key (stored in the settings table).

Accepts both TMDB credentials: the API Read Access Token (Bearer header) and the older
32-character API key (api_key query parameter).

Terms that shape this code (https://www.themoviedb.org/api-terms-of-use):
  - attribution in the UI ("This product uses the TMDB API but is not endorsed or certified by TMDB")
  - don't keep cached data/images longer than 6 months -> items carry metadata_at and get refreshed
  - roughly 40 requests/second max -> we stay well under and back off on HTTP 429
"""

from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

API = "https://api.themoviedb.org/3"
IMAGES = "https://image.tmdb.org/t/p"
_MIN_INTERVAL = 1 / 20  # 20 req/s ceiling across all threads


class TmdbError(Exception):
    pass


class InvalidKey(TmdbError):
    pass


def key_kind(key: str) -> str | None:
    k = key.strip()
    if re.fullmatch(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", k):
        return "token"
    if re.fullmatch(r"[0-9a-fA-F]{32}", k):
        return "apikey"
    return None


class Tmdb:
    def __init__(self, key: str, language: str = "en-US", transport: httpx.BaseTransport | None = None):
        self.key = key.strip()
        self.kind = key_kind(self.key)
        if not self.kind:
            raise InvalidKey("not a TMDB API key or Read Access Token")
        self.language = language
        headers = {"accept": "application/json", "user-agent": "BAMS/0.1 (self-hosted media server)"}
        if self.kind == "token":
            headers["authorization"] = f"Bearer {self.key}"
        self.http = httpx.Client(timeout=20, headers=headers, transport=transport, follow_redirects=True)
        # images come from a public CDN: separate client so the key is never sent there
        self.img_http = httpx.Client(timeout=30, headers={"user-agent": headers["user-agent"]},
                                     transport=transport, follow_redirects=True)
        self._lock = threading.Lock()
        self._last = 0.0

    def close(self) -> None:
        self.http.close()
        self.img_http.close()

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last + _MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def get(self, path: str, **params) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        params.setdefault("language", self.language)
        if self.kind == "apikey":
            params["api_key"] = self.key
        for attempt in range(5):
            self._throttle()
            try:
                r = self.http.get(API + path, params=params)
            except httpx.HTTPError as e:
                if attempt == 4:
                    raise TmdbError(f"TMDB unreachable: {e}") from e
                time.sleep(1 + attempt)
                continue
            if r.status_code == 429:
                time.sleep(float(r.headers.get("retry-after", 2)))
                continue
            if r.status_code == 401:
                raise InvalidKey("TMDB rejected the API key (401)")
            if r.status_code == 404:
                raise TmdbError(f"TMDB: not found {path}")
            if r.status_code >= 500 and attempt < 4:
                time.sleep(1 + attempt)
                continue
            r.raise_for_status()
            return r.json()
        raise TmdbError("TMDB kept rate-limiting; giving up for now")

    # -- endpoints
    def check(self) -> None:
        self.get("/authentication")

    def search_tv(self, query: str, year: int | None = None) -> list[dict]:
        return self.get("/search/tv", query=query, first_air_date_year=year).get("results", [])

    def search_movie(self, query: str, year: int | None = None) -> list[dict]:
        return self.get("/search/movie", query=query, year=year).get("results", [])

    def tv(self, tv_id: int) -> dict:
        return self.get(f"/tv/{tv_id}", append_to_response="external_ids")

    def season(self, tv_id: int, number: int) -> dict:
        return self.get(f"/tv/{tv_id}/season/{number}")

    def movie(self, movie_id: int) -> dict:
        return self.get(f"/movie/{movie_id}", append_to_response="external_ids")

    def find(self, external_id: str, source: str) -> dict:
        return self.get(f"/find/{external_id}", external_source=source)

    def image(self, tmdb_path: str | None, size: str, cache_dir: Path) -> str | None:
        """Download an image into the cache (once). Returns its path relative to cache_dir."""
        if not tmdb_path:
            return None
        rel = f"tmdb/{size}{tmdb_path}"
        dest = cache_dir / rel
        if dest.exists():
            return rel
        try:
            r = self.img_http.get(f"{IMAGES}/{size}{tmdb_path}")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("image download failed %s: %s", tmdb_path, e)
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(r.content)
        tmp.replace(dest)
        return rel
