"""Refuse commits that carry personal or security-sensitive content (docs/SECURITY-PRACTICES.md).

    python tools/privacy_check.py           # the staged changes (what the next commit would add)
    python tools/privacy_check.py --all     # every tracked file as it is on disk

Exit code 1 lists each finding. The owner's own names, addresses and paths are read from `.privacy-patterns`
(git-ignored, one literal string per line, `re:` for a regex, `#` for comments), so they never have to be in git.
A line that holds a reviewed, made-up value (a fake token in a test) can carry the comment `privacy-check: ok`.
Runs as the pre-commit hook (.githooks/pre-commit; `git config core.hooksPath .githooks` once per clone).
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_PATTERNS = ROOT / ".privacy-patterns"

# Files that must never be committed, whatever is in them.
FORBIDDEN_FILES = [
    re.compile(p, re.I) for p in (
        r"(^|/)CLAUDE\.local\.md$", r"(^|/)\.privacy-patterns$", r"^\.claude/launch\.json$", r"^\.claude/skills/",
        r"(^|/)\.claude/settings\.local\.json$", r"(^|/)keystore\.properties$", r"\.(jks|keystore|p12|pfx|pem|key|pwd)$",
        r"\.(db|sqlite|db-wal|db-shm)$", r"\.(log|jsonl)$", r"(^|/)\.env(\..*)?$", r"(^|/)id_(rsa|ed25519|ecdsa)(\.pub)?$",
    )
]

# Made-up addresses the code, tests and docs use as examples. A new private address must be made up too: add it here.
EXAMPLE_IPS = {
    "192.168.1.0", "192.168.1.2", "192.168.1.5", "192.168.1.7", "192.168.1.10", "192.168.1.11", "192.168.1.20",
    "192.168.1.30", "192.168.1.42", "192.168.1.50", "192.168.1.66", "192.168.1.80", "192.168.1.99", "192.168.1.100",
    "192.168.1.150", "192.168.1.151", "192.168.2.7", "10.0.0.0", "10.0.0.1", "10.0.0.5", "10.0.0.7", "10.0.0.8",
    "10.0.0.9", "10.0.0.10", "10.0.0.20", "10.1.2.3", "10.9.9.9", "10.0.2.2",
}
LAN = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
IP = re.compile(r"(?<![\d.])(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?![\d.])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_OK = re.compile(r"(@example\.(com|org|net)$|noreply|no-reply|^this@|@users\.noreply\.github\.com$)", re.I)

# Things that are never fine in a tracked file.
RULES = [
    ("Windows user folder", re.compile(r"[A-Za-z]:\\{1,2}Users\\{1,2}(?!<|(you|owner|me|Public|Default)\b)[^\\\s`'\"]+", re.I)),
    ("Linux home folder", re.compile(r"/home/(?!<|(you|owner|me|user)\b)[a-z_][a-z0-9_-]*")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}")),
    ("API key", re.compile(r"\b(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[abp]-[A-Za-z0-9-]{10,})")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}")),
    ("Claude session path", re.compile(r"[\\/]Temp[\\/]+claude[\\/]|/tmp/claude-\d+/", re.I)),
]


def local_rules() -> list[tuple[str, re.Pattern]]:
    if not LOCAL_PATTERNS.exists():
        return []
    out = []
    for line in LOCAL_PATTERNS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rx = re.compile(line[3:], re.I) if line.startswith("re:") else re.compile(re.escape(line), re.I)
        out.append(("owner's personal detail (.privacy-patterns)", rx))
    return out


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True).stdout


def staged() -> tuple[list[str], list[tuple[str, int, str]]]:
    names = [n for n in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0") if n]
    lines, path, num = [], None, 0
    for row in git("diff", "--cached", "-U0", "--no-color", "--diff-filter=ACMR").splitlines():
        if row.startswith("+++ "):
            path = row[6:] if row.startswith("+++ b/") else None
        elif row.startswith("@@"):
            num = int(re.search(r"\+(\d+)", row).group(1))
        elif row.startswith("+") and path:
            lines.append((path, num, row[1:]))
            num += 1
    return names, lines


def tracked() -> tuple[list[str], list[tuple[str, int, str]]]:
    names = [n for n in git("ls-files", "-z").split("\0") if n]
    lines = []
    for n in names:
        try:
            text = (ROOT / n).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines += [(n, i, l) for i, l in enumerate(text.splitlines(), 1)]
    return names, lines


def check(names: list[str], lines: list[tuple[str, int, str]]) -> list[str]:
    found = [f"{n}: this file must never be committed" for n in names if any(r.search(n) for r in FORBIDDEN_FILES)]
    rules = RULES + local_rules()
    for path, num, text in lines:
        if path == "tools/privacy_check.py" or "privacy-check: ok" in text:   # a reviewed, made-up value
            continue
        where = f"{path}:{num}"
        for label, rx in rules:
            m = rx.search(text)
            if m:
                found.append(f"{where}: {label}: {m.group(0)!r}")
        for m in IP.finditer(text):
            ip = m.group(1)
            try:
                a = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if any(a in n for n in LAN) and ip not in EXAMPLE_IPS:
                found.append(f"{where}: real-looking private IP {ip!r} (use a made-up example from EXAMPLE_IPS)")
        for m in EMAIL.finditer(text):
            if not EMAIL_OK.search(m.group(0)):
                found.append(f"{where}: email address {m.group(0)!r}")
    email = subprocess.run(["git", "config", "user.email"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if email and not EMAIL_OK.search(email):
        found.append(f"git config user.email is {email!r}: commits would publish it; use the GitHub noreply address")
    return found


def main() -> int:
    names, lines = tracked() if "--all" in sys.argv else staged()
    found = check(names, lines)
    if not LOCAL_PATTERNS.exists():
        print("note: no .privacy-patterns file here; only the generic checks ran (see docs/SECURITY-PRACTICES.md)")
    if found:
        print("privacy check FAILED: personal or sensitive content (docs/SECURITY-PRACTICES.md):")
        for f in found:
            print("  " + f)
        return 1
    print("privacy check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
