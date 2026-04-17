"""Authentication routes."""
from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from tb.audit import log_audit
from tb.security import (
    LOGIN_LOCKOUT_SECONDS,
    MAX_LOGIN_ATTEMPTS,
    clear_login_attempts,
    is_login_locked,
    load_staff_accounts,
    login_attempt_count,
    record_login_failure,
)

bp = Blueprint("auth", __name__)


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
        accounts = load_staff_accounts()
        _hash = accounts.get(username)
        if _hash and check_password_hash(_hash, password):
            clear_login_attempts(ip)
            session.permanent = True
            session["staff_logged_in"] = True
            session["staff_user"] = username
            log_audit("LOGIN", detail=f"IP: {ip}")
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
    flash("ออกจากระบบเรียบร้อย", "info")
    return redirect(url_for("index"))
