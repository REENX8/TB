"""Staff authentication helpers and brute-force protection."""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from functools import wraps

from flask import abort, redirect, request, session, url_for

logger = logging.getLogger(__name__)

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


_rate_buckets: dict[str, list[float]] = defaultdict(list)


def is_rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
    """Sliding-window rate limiter (in-memory, per worker process).

    Records the request and returns True when the caller should be rejected.
    """
    now = time.time()
    bucket = [t for t in _rate_buckets[key] if now - t < window_seconds]
    limited = len(bucket) >= max_requests
    if not limited:
        bucket.append(now)
    _rate_buckets[key] = bucket
    return limited


def reset_rate_limits() -> None:
    """Used by tests to reset in-memory rate limiter state."""
    _rate_buckets.clear()


def load_staff_accounts() -> dict[str, str]:
    """Read staff accounts from env vars.

    Format: STAFF_USER / STAFF_PASS_HASH (primary),
    STAFF_USER_2 / STAFF_PASS_HASH_2, etc.

    Env accounts are the bootstrap mechanism; database StaffAccount rows
    are the primary mechanism, so missing env vars are not an error.
    """
    primary_user = os.environ.get("STAFF_USER")
    primary_hash = os.environ.get("STAFF_PASS_HASH")
    if not primary_user or not primary_hash:
        logger.warning(
            "No env staff credentials configured; relying on database accounts"
        )
        return {}
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


def role_required(*roles: str):
    """Require a logged-in staff member with one of the given roles.

    Sessions created before roles existed have no staff_role; they are
    treated as admin for backward compatibility (previously every staff
    session had full access).
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("staff_logged_in"):
                return redirect(url_for("staff_login", next=request.url))
            if session.get("staff_role", "admin") not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator
