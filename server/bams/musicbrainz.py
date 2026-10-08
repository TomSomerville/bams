"""Online music metadata: MusicBrainz, Cover Art Archive, and Wikidata/Wikipedia/Wikimedia Commons.

No keys or accounts: all of these are open services. What their terms ask of us:
  - MusicBrainz (musicbrainz.org/doc/MusicBrainz_API): at most ~1 request/second, and a User-Agent naming
    the application and a contact URL. Core data (ids, names, titles, dates, track lists) is CC0. BAMS uses
    only core data; MusicBrainz's tags/genres are CC BY-NC-SA, so genres keep coming from the files' own tags.
  - Cover Art Archive: images belong to their rights holders; BAMS caches them for the owner's own library,
    the same way it caches TMDB posters. Nothing is redistributed (the repo ships no artwork).
  - Wikipedia text is CC BY-SA and Commons photos carry their own licences: the UI shows a link to the
    article and the photo's author + licence next to them.
"""

from __future__ import annotations

import logging
import re
import threading
import time

import httpx

from .config import VERSION

log = logging.getLogger(__name__)

MB = "https://musicbrainz.org/ws/2"
CAA = "https://coverartarchive.org"
USER_AGENT = f"BAMS/{VERSION} ( https://github.com/TomSomerville/bams )"
_MB_INTERVAL = 1.1  # seconds between MusicBrainz requests (their limit is 1/s per client IP)
VARIOUS_ARTISTS_MBID = "89ad4ac3-39f7-470e-963a-56509c546377"  # MusicBrainz's special "Various Artists"
# The limit is per IP, so it's shared by every client in the process (scan worker + Fix match requests).
_mb_lock = threading.Lock()
_mb_last = [0.0]


class MusicLookupError(Exception):
    """A metadata service couldn't be reached or answered with an error (try again on a later scan)."""


def lucene(s: str) -> str:
    """Escape a value for a MusicBrainz (Lucene) search query."""
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", s)


class MusicBrainz:
    def __init__(self, transport: httpx.BaseTransport | None = None, min_interval: float = _MB_INTERVAL):
        headers = {"user-agent": USER_AGENT, "accept": "application/json"}
        self.http = httpx.Client(timeout=30, headers=headers, transport=transport, follow_redirects=True)
        self.min_interval = min_interval

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "MusicBrainz":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------- MusicBrainz

    def _mb(self, path: str, **params) -> dict | None:
        """GET a MusicBrainz resource. None for 404; MusicLookupError when it keeps failing."""
        params["fmt"] = "json"
        r: httpx.Response | None = None
        err: Exception | None = None
        for attempt in range(4):
            with _mb_lock:  # one request at a time, spaced out
                wait = _mb_last[0] + self.min_interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                try:
                    r, err = self.http.get(MB + path, params=params), None
                except httpx.HTTPError as e:
                    r, err = None, e
                _mb_last[0] = time.monotonic()
            if r is not None:
                if r.status_code == 404:
                    return None
                if r.status_code < 400:
                    return r.json()
                if r.status_code < 500 and r.status_code != 429:
                    raise MusicLookupError(f"MusicBrainz said {r.status_code} for {path}")
            # 503 = rate limited, other 5xx = busy, or a network error: back off and retry
            time.sleep(min(8, 2 ** attempt) * self.min_interval)
        raise MusicLookupError(f"MusicBrainz unreachable or busy ({err or (r.status_code if r is not None else 'no response')})")

    def search_releases(self, album: str, artist: str | None = None, limit: int = 10) -> list[dict]:
        q = f'release:"{lucene(album)}"'
        if artist:
            q += f' AND artist:"{lucene(artist)}"'
        return (self._mb("/release", query=q, limit=limit) or {}).get("releases", [])

    def release(self, mbid: str) -> dict | None:
        # release-group-level-rels: the album's (release group's) links, e.g. its Wikidata page
        return self._mb(f"/release/{mbid}",
                        inc="recordings+artist-credits+release-groups+url-rels+release-group-level-rels")

    def search_artists(self, name: str, limit: int = 5) -> list[dict]:
        return (self._mb("/artist", query=f'artist:"{lucene(name)}"', limit=limit) or {}).get("artists", [])

    def artist(self, mbid: str) -> dict | None:
        return self._mb(f"/artist/{mbid}", inc="url-rels")

    # ------------------------------------------------------------- Cover Art Archive

    def _bytes(self, url: str, **params) -> bytes | None:
        try:
            r = self.http.get(url, params=params or None, headers={"accept": "*/*"})
        except httpx.HTTPError as e:
            log.info("download failed %s: %s", url, e)
            return None
        return r.content if r.status_code == 200 and r.content else None

    def cover(self, release_mbid: str, release_group_mbid: str | None = None) -> bytes | None:
        """The front cover (500 px) of this release, else of any release of the same album."""
        data = self._bytes(f"{CAA}/release/{release_mbid}/front-500")
        if not data and release_group_mbid:
            data = self._bytes(f"{CAA}/release-group/{release_group_mbid}/front-500")
        return data

    # ------------------------------------------------------------- Wikidata / Wikipedia / Commons

    def _json(self, url: str, **params) -> dict | None:
        try:
            r = self.http.get(url, params=params or None)
        except httpx.HTTPError as e:
            log.info("lookup failed %s: %s", url, e)
            return None
        return r.json() if r.status_code == 200 else None

    def wikidata(self, qid: str) -> dict | None:
        d = self._json(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
        return ((d or {}).get("entities") or {}).get(qid) if d else None

    def wikipedia_summary(self, lang: str, title: str) -> dict | None:
        """{'extract', 'url', 'title'} for an article, or None."""
        d = self._json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}")
        if not d or d.get("type") == "disambiguation" or not d.get("extract"):
            return None
        return {"extract": d["extract"], "title": d.get("title") or title,
                "url": ((d.get("content_urls") or {}).get("desktop") or {}).get("page")}

    def commons_image(self, filename: str, width: int = 600) -> tuple[bytes, dict] | None:
        """A Commons photo scaled to `width`, with its credit {author, license, url}."""
        d = self._json("https://commons.wikimedia.org/w/api.php", action="query", titles=f"File:{filename}",
                       prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=width, format="json")
        try:
            info = next(iter(d["query"]["pages"].values()))["imageinfo"][0]
        except (TypeError, KeyError, StopIteration, IndexError):
            return None
        data = self._bytes(info.get("thumburl") or info["url"])
        if not data:
            return None
        md = info.get("extmetadata") or {}
        author = re.sub(r"<[^>]+>", "", (md.get("Artist") or {}).get("value") or "").strip()
        return data, {"author": re.sub(r"\s+", " ", author)[:200] or None,
                      "license": (md.get("LicenseShortName") or {}).get("value"),
                      "url": info.get("descriptionurl")}


def wikidata_id(entity: dict | None) -> str | None:
    """The Wikidata Q-id among a MusicBrainz entity's URL relationships."""
    for rel in (entity or {}).get("relations") or []:
        url = (rel.get("url") or {}).get("resource") or ""
        if rel.get("type") == "wikidata" and (m := re.search(r"/(Q\d+)$", url)):
            return m.group(1)
    return None
