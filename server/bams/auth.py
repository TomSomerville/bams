"""User accounts and login sessions.

- Passwords are stored as scrypt hashes (stdlib `hashlib.scrypt`, no extra dependency).
- Signing in sets an HttpOnly cookie holding a random token. The DB keeps only its SHA-256, so a copy of the
  database can't be used to sign in. Sessions last SESSION_DAYS after their last use.
- The very first account (an admin) is created from the web UI only by a browser on the server itself
  (loopback), so nobody else on the network can claim a fresh server; `bams user add` works anywhere.
- Repeated wrong passwords from one address are slowed down (Throttle).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import threading
import time

from .db import jdump, jload, now

COOKIE = "bams_session"
SESSION_DAYS = 30
MIN_PASSWORD = 8
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}  # ~50 ms and 16 MB per hash


class AuthError(ValueError):
    """A rejected account change; the message is shown to the user."""


# ------------------------------------------------------------------ passwords

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b64(salt)}${b64(h)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(h)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(want))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


# A hash to check against when the name doesn't exist, so a wrong name takes as long as a wrong password.
_DUMMY = hash_password(secrets.token_hex(8))


def _check_name(name: str) -> str:
    name = (name or "").strip()
    if not 1 <= len(name) <= 40:
        raise AuthError("Names are 1 to 40 characters long.")
    if any(c in name for c in "\r\n\t") or not name.isprintable():
        raise AuthError("Names can't contain control characters.")
    return name


def _check_password(password: str) -> str:
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"Passwords need at least {MIN_PASSWORD} characters.")
    if len(password) > 1024:
        raise AuthError("That password is too long.")
    return password


# ------------------------------------------------------------------ users

def user_count(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# Each user's display preferences: name -> default. Unknown names are ignored when saving.
PREFS: dict[str, bool] = {"home_hero": True}   # the rotating "Recently added" banner at the top of Home


def prefs(u: sqlite3.Row) -> dict:
    saved = jload(u["prefs"]) or {}
    return {k: saved.get(k, default) for k, default in PREFS.items()}


def set_prefs(con: sqlite3.Connection, user_id: int, changes: dict) -> dict:
    u = get_user(con, user_id)
    new = {**prefs(u), **{k: v for k, v in changes.items() if k in PREFS and isinstance(v, type(PREFS[k]))}}
    con.execute("UPDATE users SET prefs=? WHERE id=?", (jdump(new), user_id))
    return new


def public(u: sqlite3.Row) -> dict:
    return {"id": u["id"], "name": u["name"], "is_admin": bool(u["is_admin"]),
            "created_at": u["created_at"], "last_login_at": u["last_login_at"], "prefs": prefs(u)}


def get_user(con: sqlite3.Connection, ref: int | str) -> sqlite3.Row | None:
    col = "id" if isinstance(ref, int) else "name"
    return con.execute(f"SELECT * FROM users WHERE {col}=?", (ref,)).fetchone()


def create_user(con: sqlite3.Connection, name: str, password: str, is_admin: bool = False) -> int:
    name = _check_name(name)
    _check_password(password)
    if get_user(con, name):
        raise AuthError(f"There's already a user called {name!r}.")
    return con.execute("INSERT INTO users(name, password, is_admin, created_at) VALUES (?,?,?,?)",
                       (name, hash_password(password), int(is_admin), now())).lastrowid


def update_user(con: sqlite3.Connection, user_id: int, *, name: str | None = None, password: str | None = None,
                is_admin: bool | None = None) -> None:
    u = get_user(con, user_id)
    if not u:
        raise AuthError("No such user.")
    if name is not None:
        name = _check_name(name)
        other = get_user(con, name)
        if other and other["id"] != user_id:
            raise AuthError(f"There's already a user called {name!r}.")
        con.execute("UPDATE users SET name=? WHERE id=?", (name, user_id))
    if is_admin is not None and not is_admin and u["is_admin"] and _admins(con) <= 1:
        raise AuthError("BAMS needs at least one admin. Make someone else an admin first.")
    if is_admin is not None:
        con.execute("UPDATE users SET is_admin=? WHERE id=?", (int(is_admin), user_id))
    if password is not None:
        con.execute("UPDATE users SET password=? WHERE id=?", (hash_password(_check_password(password)), user_id))
        con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))  # signed out everywhere


def delete_user(con: sqlite3.Connection, user_id: int) -> None:
    u = get_user(con, user_id)
    if not u:
        raise AuthError("No such user.")
    if u["is_admin"] and _admins(con) <= 1:
        raise AuthError("BAMS needs at least one admin, so the last one can't be removed.")
    con.execute("DELETE FROM users WHERE id=?", (user_id,))  # sessions and watch state cascade


def _admins(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]


def authenticate(con: sqlite3.Connection, name: str, password: str) -> sqlite3.Row | None:
    u = get_user(con, (name or "").strip())
    if not u:
        verify_password(password or "", _DUMMY)
        return None
    return u if verify_password(password or "", u["password"]) else None


# ------------------------------------------------------------------ sessions

def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(con: sqlite3.Connection, user_id: int, user_agent: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    t = now()
    con.execute("INSERT INTO sessions(token, user_id, created_at, last_seen_at, user_agent) VALUES (?,?,?,?,?)",
                (_digest(token), user_id, t, t, (user_agent or "")[:300]))
    con.execute("UPDATE users SET last_login_at=? WHERE id=?", (t, user_id))
    con.execute("DELETE FROM sessions WHERE last_seen_at < ?", (t - SESSION_DAYS * 86400,))  # tidy up
    return token


def session_user(con: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    """The signed-in user for a cookie value, or None. Sliding expiry: last_seen_at is refreshed at most
    hourly, so a stream's many requests don't each write to the DB."""
    if not token or len(token) > 100:
        return None
    d = _digest(token)
    r = con.execute("""SELECT u.*, s.last_seen_at AS seen FROM sessions s JOIN users u ON u.id=s.user_id
                       WHERE s.token=?""", (d,)).fetchone()
    t = now()
    if not r or r["seen"] < t - SESSION_DAYS * 86400:
        return None
    if r["seen"] < t - 3600:
        con.execute("UPDATE sessions SET last_seen_at=? WHERE token=?", (t, d))
    return r


def end_session(con: sqlite3.Connection, token: str | None) -> None:
    if token:
        con.execute("DELETE FROM sessions WHERE token=?", (_digest(token),))


# ------------------------------------------------------------------ throttle

class Throttle:
    """At most MAX failed sign-ins per address per WINDOW seconds."""

    MAX = 10
    WINDOW = 600.0

    def __init__(self):
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked(self, addr: str) -> bool:
        with self._lock:
            t = time.monotonic()
            fails = [f for f in self._fails.get(addr, []) if f > t - self.WINDOW]
            self._fails[addr] = fails
            return len(fails) >= self.MAX

    def fail(self, addr: str) -> None:
        with self._lock:
            self._fails.setdefault(addr, []).append(time.monotonic())

    def ok(self, addr: str) -> None:
        with self._lock:
            self._fails.pop(addr, None)


def is_loopback(host: str | None) -> bool:
    return host in ("127.0.0.1", "::1", "localhost") or bool(host and host.startswith("127."))
