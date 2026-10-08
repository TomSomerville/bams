"""Security: sign-in lockout, the sign-in log, and the IP allow/block lists.

- Every wrong password makes that account wait before the next try: 1 s after the first, then doubling
  (2, 4, 8 s...). After `lockout_threshold` wrong passwords in a row (default 5) the account is locked until
  an admin unlocks it (Settings -> Security, or `bams user unlock NAME`). A right password resets the count.
  Names that aren't accounts get the same treatment, so the answers don't tell which names exist.
- Admins can also lock an account by hand; that signs it out everywhere.
- The sign-in log (successes, failures and why, locks/unlocks) lives in `security.db` in the data dir, next to
  the main DB but separate from it: it's written on every sign-in and never needed by anything else.
- IP lists: "allow everyone except the block list" (default) or "block everyone except the allow list". The
  block list always wins. The server's own loopback address is always let in, so the owner can't lock
  themselves out of the machine BAMS runs on. Entries are addresses or CIDR ranges (IPv4 or IPv6).
- `Gate` is the outermost middleware: it refuses blocked addresses and writes every request to the traffic
  log (netflow.py), blocked or not.
"""

from __future__ import annotations

import ipaddress
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import anyio

from .db import get_setting, jdump, jload, now, set_setting

DEFAULT_THRESHOLD = 5
MAX_THRESHOLD = 50
MAX_WAIT = 86400.0          # a wait never grows past a day
AUTH_LOG_KEEP = 100_000     # newest sign-in log entries kept
IP_MODES = ("allow_all", "allowlist")
MAX_IP_ENTRIES = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS login_state (
    key        TEXT PRIMARY KEY,   -- 'u<id>' for an account, 'n:<name, casefolded>' for a name that isn't one
    failures   INTEGER NOT NULL DEFAULT 0,  -- wrong passwords in a row
    last_fail  REAL,
    locked_at  REAL,
    locked_by  TEXT                -- NULL: wrong passwords; else the admin who locked it
);
CREATE TABLE IF NOT EXISTS auth_log (
    id         INTEGER PRIMARY KEY,
    at         REAL NOT NULL,
    event      TEXT NOT NULL,      -- 'sign-in' | 'lock' | 'unlock'
    result     TEXT NOT NULL,      -- 'ok' | 'failed' | 'admin'
    name       TEXT,               -- as typed (sign-in) or the account's name
    user_id    INTEGER,
    ip         TEXT,
    reason     TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS auth_log_result ON auth_log(result, id);
"""


class SecurityError(ValueError):
    """A rejected security setting; the message is shown to the admin."""


def wait_after(failures: int) -> float:
    """Seconds an account waits after `failures` wrong passwords in a row: 0, 1, 2, 4, 8..."""
    return 0.0 if failures <= 0 else min(MAX_WAIT, 2.0 ** (failures - 1))


def account_key(user_id: int | None, name: str) -> str:
    return f"u{user_id}" if user_id is not None else "n:" + (name or "").strip().casefold()[:100]


def threshold(con: sqlite3.Connection) -> int:
    try:
        n = int(get_setting(con, "lockout_threshold", str(DEFAULT_THRESHOLD)))
    except ValueError:
        n = DEFAULT_THRESHOLD
    return max(1, min(MAX_THRESHOLD, n))


class Security:
    """The sign-in state and log (security.db), plus the IP policy (from the main DB's settings)."""

    def __init__(self, path: Path, main_db: Path):
        self.path, self.main_db = path, main_db
        con = self.connect()
        try:
            con.executescript(SCHEMA)
        finally:
            con.close()
        self._stripes = [threading.Lock() for _ in range(64)]
        self.policy = IpPolicy.empty()
        self._policy_at = -1e9
        self._policy_lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
        return con

    # -- sign-in attempts

    @contextmanager
    def attempt(self, key: str):
        """One sign-in attempt per account at a time, so parallel guesses can't all slip into one wait."""
        lock = self._stripes[hash(key) % len(self._stripes)]
        with lock:
            yield

    def state(self, key: str) -> sqlite3.Row | None:
        con = self.connect()
        try:
            return con.execute("SELECT * FROM login_state WHERE key=?", (key,)).fetchone()
        finally:
            con.close()

    def refusal(self, key: str) -> tuple[str, float] | None:
        """Why this account can't try now: ("locked", 0) or ("wait", seconds left); None if it can."""
        s = self.state(key)
        if not s:
            return None
        if s["locked_at"]:
            return "locked", 0.0
        left = (s["last_fail"] or 0) + wait_after(s["failures"]) - now()
        return ("wait", left) if left > 0 else None

    def failed(self, key: str, limit: int) -> tuple[int, bool]:
        """Count a wrong password. Returns (wrong passwords in a row, locked now)."""
        con = self.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("""INSERT INTO login_state(key, failures, last_fail) VALUES (?, 1, ?)
                           ON CONFLICT(key) DO UPDATE SET failures=failures+1, last_fail=excluded.last_fail""",
                        (key, now()))
            n = con.execute("SELECT failures FROM login_state WHERE key=?", (key,)).fetchone()[0]
            locked = n >= limit
            if locked:
                con.execute("UPDATE login_state SET locked_at=?, locked_by=NULL WHERE key=? AND locked_at IS NULL",
                            (now(), key))
            con.execute("COMMIT")
            return n, locked
        except BaseException:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def succeeded(self, key: str) -> None:
        con = self.connect()
        try:
            con.execute("DELETE FROM login_state WHERE key=? AND locked_at IS NULL", (key,))
        finally:
            con.close()

    def lock(self, user_id: int, by: str) -> None:
        con = self.connect()
        try:
            con.execute("""INSERT INTO login_state(key, failures, locked_at, locked_by) VALUES (?, 0, ?, ?)
                           ON CONFLICT(key) DO UPDATE SET locked_at=excluded.locked_at, locked_by=excluded.locked_by""",
                        (account_key(user_id, ""), now(), by))
        finally:
            con.close()

    def unlock(self, user_id: int) -> None:
        """Unlocked with a clean slate: no wait, no wrong passwords counted."""
        self.forget(user_id)

    def forget(self, user_id: int) -> None:
        con = self.connect()
        try:
            con.execute("DELETE FROM login_state WHERE key=?", (account_key(user_id, ""),))
        finally:
            con.close()

    def forget_name(self, name: str) -> None:
        """A new account takes over a name: wrong guesses at it before it existed don't count against it."""
        con = self.connect()
        try:
            con.execute("DELETE FROM login_state WHERE key=?", (account_key(None, name),))
            # names nobody has tried for a day are dropped too
            con.execute("DELETE FROM login_state WHERE key LIKE 'n:%' AND locked_at IS NULL AND last_fail < ?",
                        (now() - 86400,))
        finally:
            con.close()

    def accounts(self, users: list[sqlite3.Row]) -> list[dict]:
        """Each account's sign-in state, for Settings -> Security."""
        con = self.connect()
        try:
            states = {r["key"]: r for r in con.execute("SELECT * FROM login_state WHERE key LIKE 'u%'")}
        finally:
            con.close()
        out = []
        for u in users:
            s = states.get(account_key(u["id"], ""))
            wait_until = (s["last_fail"] or 0) + wait_after(s["failures"]) if s and not s["locked_at"] else None
            out.append({"id": u["id"], "name": u["name"], "is_admin": bool(u["is_admin"]),
                        "last_login_at": u["last_login_at"], "failures": s["failures"] if s else 0,
                        "locked": bool(s and s["locked_at"]), "locked_at": s["locked_at"] if s else None,
                        "locked_by": s["locked_by"] if s else None,
                        "wait_until": wait_until if wait_until and wait_until > now() else None})
        return out

    # -- the sign-in log

    def log(self, event: str, result: str, *, name: str | None = None, user_id: int | None = None,
            ip: str | None = None, reason: str | None = None, user_agent: str | None = None) -> None:
        con = self.connect()
        try:
            rid = con.execute("""INSERT INTO auth_log(at, event, result, name, user_id, ip, reason, user_agent)
                                 VALUES (?,?,?,?,?,?,?,?)""",
                              (now(), event, result, (name or "")[:100] or None, user_id, ip, reason,
                               (user_agent or "")[:300] or None)).lastrowid
            if rid % 1000 == 0:
                con.execute("DELETE FROM auth_log WHERE id <= ?", (rid - AUTH_LOG_KEEP,))
        finally:
            con.close()

    def auth_log(self, result: str | None = None, before: int | None = None, limit: int = 100) -> dict:
        where, args = [], []
        if result:
            where.append("result=?")
            args.append(result)
        if before:
            where.append("id<?")
            args.append(before)
        sql = "SELECT * FROM auth_log" + (" WHERE " + " AND ".join(where) if where else "")
        con = self.connect()
        try:
            rows = [dict(r) for r in con.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit + 1))]
        finally:
            con.close()
        more = len(rows) > limit
        rows = rows[:limit]
        return {"entries": rows, "next": rows[-1]["id"] if more and rows else None}

    # -- IP policy

    def load_policy(self) -> "IpPolicy":
        from .db import connect
        con = connect(self.main_db)
        try:
            p = IpPolicy.from_settings(con)
        finally:
            con.close()
        with self._policy_lock:
            self.policy, self._policy_at = p, time.monotonic()
        return p

    def policy_stale(self) -> bool:
        """Re-read now and then, so a change made with the CLI reaches a running server."""
        return time.monotonic() - self._policy_at > 10


# ------------------------------------------------------------------ IP lists

def parse_entry(text: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    t = (text or "").strip()
    try:
        return ipaddress.ip_network(t, strict=False)
    except ValueError:
        raise SecurityError(f"{t!r} isn't an IP address or range (like 192.168.1.20 or 192.168.1.0/24).") from None


def client_ip(host: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        a = ipaddress.ip_address((host or "").split("%")[0])
    except ValueError:
        return None
    return a.ipv4_mapped or a if isinstance(a, ipaddress.IPv6Address) else a


class IpPolicy:
    def __init__(self, mode: str, allow: list[dict], block: list[dict]):
        self.mode, self.allow, self.block = mode, allow, block
        self._allow = [parse_entry(e["cidr"]) for e in allow]
        self._block = [parse_entry(e["cidr"]) for e in block]

    @classmethod
    def empty(cls) -> "IpPolicy":
        return cls("allow_all", [], [])

    @classmethod
    def from_settings(cls, con: sqlite3.Connection) -> "IpPolicy":
        mode = get_setting(con, "ip_mode", "allow_all")
        try:
            return cls(mode if mode in IP_MODES else "allow_all", jload(get_setting(con, "ip_allow")) or [],
                       jload(get_setting(con, "ip_block")) or [])
        except (SecurityError, ValueError, TypeError, KeyError):
            return cls.empty()  # a hand-edited, broken list never locks everyone out

    @staticmethod
    def _in(a, nets) -> bool:
        return any(a.version == n.version and a in n for n in nets)

    def allowed(self, host: str | None) -> bool:
        a = client_ip(host)
        if a is not None and a.is_loopback:
            return True  # the server's own machine is always let in
        if a is not None and self._in(a, self._block):
            return False
        if self.mode == "allowlist":
            return a is not None and self._in(a, self._allow)
        return True

    def public(self) -> dict:
        return {"mode": self.mode, "allow": self.allow, "block": self.block}


def clean_entries(entries: list[dict]) -> list[dict]:
    """Validated, normalised ("192.168.1.7/24" -> "192.168.1.0/24"), duplicates dropped."""
    if len(entries) > MAX_IP_ENTRIES:
        raise SecurityError(f"A list can hold at most {MAX_IP_ENTRIES} entries.")
    out, seen = [], set()
    for e in entries:
        net = parse_entry(e.get("cidr", ""))
        cidr = str(net.network_address) if net.num_addresses == 1 else str(net)
        if cidr not in seen:
            seen.add(cidr)
            out.append({"cidr": cidr, "note": (e.get("note") or "").strip()[:100]})
    return out


def save_policy(con: sqlite3.Connection, mode: str, allow: list[dict], block: list[dict],
                me_ip: str | None) -> IpPolicy:
    """Save the IP lists, refusing a change that would shut out the admin making it."""
    if mode not in IP_MODES:
        raise SecurityError("Unknown mode.")
    p = IpPolicy(mode, clean_entries(allow), clean_entries(block))
    if not p.allowed(me_ip):
        raise SecurityError(f"That would block your own address ({me_ip}), and you'd be shut out. Add it to the "
                            "allow list (and keep it off the block list) first.")
    set_setting(con, "ip_mode", mode)
    set_setting(con, "ip_allow", jdump(p.allow))
    set_setting(con, "ip_block", jdump(p.block))
    return p


# ------------------------------------------------------------------ the gate

_BLOCKED = json.dumps({"detail": "This address isn't allowed to use this BAMS server."}).encode()


class Gate:
    """ASGI middleware, outermost: refuses addresses the IP lists keep out, and writes every request
    (allowed or not) to the traffic log. Plain ASGI so streams pass straight through."""

    def __init__(self, app, security: Security, flows):
        self.app, self.security, self.flows = app, security, flows

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        sec = self.security
        if sec.policy_stale():
            await anyio.to_thread.run_sync(sec.load_policy)
        client = scope.get("client") or (None, None)
        allowed = sec.policy.allowed(client[0])
        scope.setdefault("state", {})
        t0, mono = time.time(), time.monotonic()
        flow = {"status": None, "in": 0, "out": 0}

        async def recv():
            msg = await receive()
            if msg["type"] == "http.request":
                flow["in"] += len(msg.get("body", b""))
            return msg

        async def snd(msg):
            if msg["type"] == "http.response.start":
                flow["status"] = msg["status"]
            elif msg["type"] == "http.response.body":
                flow["out"] += len(msg.get("body", b""))
            elif msg["type"] == "websocket.accept":
                flow["status"] = 101
            elif msg["type"] == "websocket.close" and flow["status"] is None:
                flow["status"] = 403
            await send(msg)

        try:
            if not allowed:
                if scope["type"] == "websocket":
                    await snd({"type": "websocket.close", "code": 1008})
                else:
                    await snd({"type": "http.response.start", "status": 403,
                               "headers": [(b"content-type", b"application/json"),
                                           (b"content-length", str(len(_BLOCKED)).encode())]})
                    await snd({"type": "http.response.body", "body": _BLOCKED})
                return
            await self.app(scope, recv, snd)
        except BaseException:
            if flow["status"] is None:
                flow["status"] = 500
            raise
        finally:
            user = (scope.get("state") or {}).get("user")
            headers = dict(scope.get("headers") or [])
            server = scope.get("server") or (None, None)
            self.flows.record({
                "time": round(t0, 3), "duration_ms": round((time.monotonic() - mono) * 1000, 1),
                "client": client[0], "client_port": client[1],
                "server": f"{server[0]}:{server[1]}" if server[0] else None,
                "scheme": scope.get("scheme"), "http": scope.get("http_version"),
                "method": scope.get("method", "WS" if scope["type"] == "websocket" else None),
                "path": scope.get("path"), "query": (scope.get("query_string") or b"").decode("latin-1") or None,
                "status": flow["status"], "bytes_in": flow["in"], "bytes_out": flow["out"],
                "user": user["name"] if isinstance(user, dict) else None,
                "user_agent": headers.get(b"user-agent", b"").decode("latin-1")[:300] or None,
                "action": "allow" if allowed else "block",
            })
