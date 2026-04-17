"""Staff authentication helpers and brute-force protection."""
from __future__ import annotations

import os
import time
from collections import defaultdict
from functools import wraps

from flask import redirect, request, session, url_for

_login_attempts: dict[str, list[float]] = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60


def is_login_locked(ip: str) -> bool:
    now = time.time()
    _login_attempts[ip] = [
        t for t in _login_attempts[ip] if now - t < LOGIN_LOCKOUT_SECONDS
    ]
    return len(_login_attempts[ip]) >= MAX_LOGIN_ATTEMPTS


def record_login_failure(ip: str) -> None:
    _login_attempts[ip].append(time.time())


def clear_login_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)


def login_attempt_count(ip: str) -> int:
    return len(_login_attempts.get(ip, []))


def reset_login_state() -> None:
    """Used by tests to reset in-memory lockout state."""
    _login_attempts.clear()


def load_staff_accounts() -> dict[str, str]:
    """Read staff accounts from env vars.

    Format: STAFF_USER / STAFF_PASS_HASH (primary),
    STAFF_USER_2 / STAFF_PASS_HASH_2, etc.
    """
    primary_user = os.environ.get("STAFF_USER")
    primary_hash = os.environ.get("STAFF_PASS_HASH")
    if not primary_user or not primary_hash:
        raise RuntimeError("Missing staff credentials")
    accounts = {primary_user: primary_hash}
    i = 2
    while True:
        u = os.environ.get(f"STAFF_USER_{i}")
        h = os.environ.get(f"STAFF_PASS_HASH_{i}")
        if not u or not h:
            break
        accounts[u] = h
        i += 1
    return accounts


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("staff_logged_in"):
            return redirect(url_for("staff_login", next=request.url))
        return f(*args, **kwargs)
    return decorated
