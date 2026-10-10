"""Apps on other devices (the Samsung TV app): linking them to an account, and media tickets.

Linking, like "enter this code on the web" for streaming apps: the TV asks for a code (`LinkCodes.start`), shows
it, and polls with a secret only it knows. Someone signed in to the web UI enters the code (`approve`), and the
TV's next poll gets a session token for that account. The TV then sends it as `Authorization: Bearer <token>`.
It's an ordinary session (auth.sessions), so signing out, password changes and admin locks end it too.

Media tickets: the TV's video player and its <img> tags can't send headers. They load
`/api/t/<ticket>/files/...` instead, where the ticket stands for the session that asked for it, is signed with
a key that lives only in this process, and runs out after TICKET_TTL. `LoginRequired` checks it and rewrites the
path. HLS playlists name their segments relatively, so they inherit the ticket by themselves.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

TV_AGENT = "BAMS TV"           # sessions made by linking start their user_agent with this
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I: read off a TV across the room
CODE_LEN = 6
CODE_TTL = 600.0               # seconds a code waits to be entered
MAX_PENDING = 50               # codes waiting at once (each costs a little memory; this is a home server)
TICKET_TTL = 24 * 3600         # seconds; the TV asks for a fresh ticket at every start and every few hours
MEDIA_PREFIXES = ("/api/files/", "/api/hls/", "/api/images/")  # all a ticket can open


class LinkError(ValueError):
    """Shown to the person: a code that's wrong, used or expired, or too many waiting."""


class LinkCodes:
    """Codes waiting to be entered, in memory (a restart just means asking for a new one)."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._by_code: dict[str, dict] = {}

    def _tidy(self) -> None:
        t = self._clock()
        for code in [c for c, p in self._by_code.items() if p["expires"] < t]:
            del self._by_code[code]

    def start(self, name: str) -> dict:
        """A new code for the device called `name`: {code, secret, expires_in}."""
        with self._lock:
            self._tidy()
            if len(self._by_code) >= MAX_PENDING:
                raise LinkError("Too many devices are waiting to be linked. Try again in a few minutes.")
            while (code := "".join(secrets.choice(CODE_CHARS) for _ in range(CODE_LEN))) in self._by_code:
                pass
            secret = secrets.token_urlsafe(32)
            self._by_code[code] = {"secret": secret, "name": name, "user_id": None,
                                   "expires": self._clock() + CODE_TTL}
        return {"code": code, "secret": secret, "expires_in": int(CODE_TTL)}

    @staticmethod
    def clean(code: str) -> str:
        """What the person typed, as stored: upper case, spaces and dashes dropped."""
        return "".join(ch for ch in (code or "").upper() if ch.isalnum())

    def approve(self, code: str, user_id: int) -> str:
        """Link the waiting device to `user_id`; returns its name."""
        with self._lock:
            self._tidy()
            p = self._by_code.get(self.clean(code))
            if not p:
                raise LinkError("That code isn't right, or it ran out. Check the TV: it shows a new one after ten "
                                "minutes.")
            if p["user_id"] is not None and p["user_id"] != user_id:
                raise LinkError("That code was already used.")
            p["user_id"] = user_id
            return p["name"]

    def poll(self, secret: str) -> tuple[str, int | None, str | None]:
        """("waiting", None, None), ("expired", None, None) or ("linked", user_id, name). A linked code is
        handed out once, then forgotten."""
        with self._lock:
            self._tidy()
            for code, p in self._by_code.items():
                if hmac.compare_digest(p["secret"], secret or ""):
                    if p["user_id"] is None:
                        return "waiting", None, None
                    del self._by_code[code]
                    return "linked", p["user_id"], p["name"]
        return "expired", None, None


class Tickets:
    """Signed, expiring stand-ins for a session, for URLs. `{digest}.{expiry}.{signature}`: the session's
    stored digest (not the token itself, so a ticket in a log can't sign anyone in), when it runs out, and an
    HMAC with a key made at start-up (tickets die with the process; the TV just asks again)."""

    def __init__(self, clock=time.time, key: bytes | None = None):
        self._clock = clock
        self._key = key or secrets.token_bytes(32)

    def _sign(self, body: str) -> str:
        return hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()[:32]

    def make(self, digest: str, ttl: float = TICKET_TTL) -> str:
        body = f"{digest}.{int(self._clock() + ttl)}"
        return f"{body}.{self._sign(body)}"

    def check(self, ticket: str) -> str | None:
        """The session digest a valid, unexpired ticket stands for; else None."""
        try:
            digest, exp, sig = ticket.split(".")
            expires = int(exp)
        except ValueError:
            return None
        if len(digest) != 64 or not hmac.compare_digest(sig, self._sign(f"{digest}.{exp}")):
            return None
        return digest if expires > self._clock() else None


def split_ticket_path(path: str) -> tuple[str, str] | None:
    """"/api/t/<ticket>/files/3/stream" -> ("<ticket>", "/api/files/3/stream"); None if it isn't a ticket path
    or points anywhere but media."""
    if not path.startswith("/api/t/"):
        return None
    ticket, sep, rest = path[len("/api/t/"):].partition("/")
    if not sep or not ticket:
        return None
    real = "/api/" + rest
    return (ticket, real) if real.startswith(MEDIA_PREFIXES) and ".." not in rest.split("/") else None
