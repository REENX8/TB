"""Authentication routes."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from tb.audit import log_audit
from tb.extensions import db
from tb.models import StaffAccount
from tb.security import (
    LOGIN_LOCKOUT_SECONDS,
    MAX_LOGIN_ATTEMPTS,
    clear_login_attempts,
    is_login_locked,
    load_staff_accounts,
    login_attempt_count,
    record_login_failure,
)
from tb.time_utils import TZ_THAI

bp = Blueprint("auth", __name__)


def _authenticate(username: str, password: str) -> str | None:
    """Check credentials against DB accounts first, then env accounts.

    Returns the staff role on success, None on failure. Env-var accounts
    are the bootstrap mechanism and are treated as admin.
    """
    try:
        account = StaffAccount.query.filter_by(
            username=username, is_active=True
        ).first()
    except Exception:
        # staff_accounts table missing (migration not applied yet) must
        # not lock staff out — fall back to env accounts.
        db.session.rollback()
        current_app.logger.exception(
            "StaffAccount lookup failed; falling back to env accounts"
        )
        account = None
    if account and check_password_hash(account.password_hash, password):
        account.last_login = datetime.now(TZ_THAI).replace(tzinfo=None)
        db.session.commit()
        return account.role
    env_hash = load_staff_accounts().get(username)
    if env_hash and check_password_hash(env_hash, password):
        return "admin"
    return None


@bp.route("/login", methods=["GET", "POST"])
def staff_login():
    if session.get("staff_logged_in"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if is_login_locked(ip):
            wait_min = LOGIN_LOCKOUT_SECONDS // 60
            flash(
                f"พยายามเข้าสู่ระบบหลายครั้งเกินไป กรุณารอ {wait_min} นาทีแล้วลองใหม่",
                "danger",
            )
            return render_template("login.html")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = _authenticate(username, password)
        if role is not None:
            clear_login_attempts(ip)
            session.permanent = True
            session["staff_logged_in"] = True
            session["staff_user"] = username
            session["staff_role"] = role
            log_audit("LOGIN", detail=f"IP: {ip}, role: {role}")
            flash("เข้าสู่ระบบสำเร็จ", "success")
            next_url = request.args.get("next") or ""
            parsed = urlparse(next_url)
            if (
                not next_url
                or parsed.scheme
                or parsed.netloc
                or not parsed.path.startswith("/")
            ):
                next_url = url_for("dashboard")
            return redirect(next_url)
        record_login_failure(ip)
        remaining = MAX_LOGIN_ATTEMPTS - login_attempt_count(ip)
        flash(
            f"ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง (เหลืออีก {remaining} ครั้ง)",
            "danger",
        )
    return render_template("login.html")


@bp.route("/logout")
def staff_logout():
    log_audit("LOGOUT")
    session.pop("staff_logged_in", None)
    session.pop("staff_user", None)
    session.pop("staff_role", None)
    flash("ออกจากระบบเรียบร้อย", "info")
    return redirect(url_for("index"))
