"""Staff account management routes (admin only)."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from tb.audit import log_audit
from tb.constants import STAFF_ROLES
from tb.extensions import db
from tb.models import StaffAccount
from tb.security import role_required, staff_required

bp = Blueprint("staff_admin", __name__, url_prefix="/staff")

MIN_PASSWORD_LENGTH = 8


def _validate_new_password(password: str) -> str | None:
    """Return a Thai error message, or None when the password is acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"รหัสผ่านต้องยาวอย่างน้อย {MIN_PASSWORD_LENGTH} ตัวอักษร"
    return None


@bp.route("/")
@role_required("admin")
def list_staff():
    accounts = StaffAccount.query.order_by(StaffAccount.username).all()
    return render_template(
        "staff_list.html", accounts=accounts, staff_roles=STAFF_ROLES,
    )


@bp.route("/new", methods=["GET", "POST"])
@role_required("admin")
def new_staff():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "nurse")
        if not username or role not in STAFF_ROLES:
            flash("กรุณากรอกข้อมูลให้ครบและเลือกบทบาทที่ถูกต้อง", "danger")
            return render_template("staff_form.html", staff_roles=STAFF_ROLES, account=None)
        error = _validate_new_password(password)
        if error:
            flash(error, "danger")
            return render_template("staff_form.html", staff_roles=STAFF_ROLES, account=None)
        if StaffAccount.query.filter_by(username=username).first():
            flash("ชื่อผู้ใช้นี้มีอยู่แล้ว", "danger")
            return render_template("staff_form.html", staff_roles=STAFF_ROLES, account=None)
        account = StaffAccount(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
        )
        db.session.add(account)
        db.session.commit()
        log_audit("CREATE_STAFF", detail=f"username={username}, role={role}")
        flash(f"เพิ่มบัญชี {username} เรียบร้อย", "success")
        return redirect(url_for("staff_admin.list_staff"))
    return render_template("staff_form.html", staff_roles=STAFF_ROLES, account=None)


@bp.route("/<int:id>/edit", methods=["GET", "POST"])
@role_required("admin")
def edit_staff(id: int):
    account = db.get_or_404(StaffAccount, id)
    if request.method == "POST":
        role = request.form.get("role", account.role)
        is_active = request.form.get("is_active") == "on"
        if role not in STAFF_ROLES:
            flash("บทบาทไม่ถูกต้อง", "danger")
            return render_template(
                "staff_form.html", staff_roles=STAFF_ROLES, account=account,
            )
        if (
            account.username == session.get("staff_user")
            and not is_active
        ):
            flash("ไม่สามารถปิดใช้งานบัญชีของตัวเองได้", "danger")
            return redirect(url_for("staff_admin.edit_staff", id=id))
        account.role = role
        account.is_active = is_active
        db.session.commit()
        log_audit(
            "EDIT_STAFF",
            detail=f"username={account.username}, role={role}, active={is_active}",
        )
        flash(f"แก้ไขบัญชี {account.username} เรียบร้อย", "success")
        return redirect(url_for("staff_admin.list_staff"))
    return render_template(
        "staff_form.html", staff_roles=STAFF_ROLES, account=account,
    )


@bp.route("/<int:id>/reset_password", methods=["POST"])
@role_required("admin")
def reset_password(id: int):
    account = db.get_or_404(StaffAccount, id)
    password = request.form.get("password", "")
    error = _validate_new_password(password)
    if error:
        flash(error, "danger")
        return redirect(url_for("staff_admin.edit_staff", id=id))
    account.password_hash = generate_password_hash(password)
    db.session.commit()
    log_audit("RESET_STAFF_PASSWORD", detail=f"username={account.username}")
    flash(f"รีเซ็ตรหัสผ่านของ {account.username} เรียบร้อย", "success")
    return redirect(url_for("staff_admin.list_staff"))


@bp.route("/password", methods=["GET", "POST"])
@staff_required
def change_own_password():
    account = StaffAccount.query.filter_by(
        username=session.get("staff_user")
    ).first()
    if request.method == "POST":
        if account is None:
            flash(
                "บัญชีนี้ตั้งค่าผ่าน environment variables "
                "ต้องเปลี่ยนรหัสผ่านที่การตั้งค่าเซิร์ฟเวอร์",
                "warning",
            )
            return redirect(url_for("staff_admin.change_own_password"))
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        if not check_password_hash(account.password_hash, current):
            flash("รหัสผ่านปัจจุบันไม่ถูกต้อง", "danger")
            return render_template("change_password.html", account=account)
        error = _validate_new_password(new)
        if error:
            flash(error, "danger")
            return render_template("change_password.html", account=account)
        account.password_hash = generate_password_hash(new)
        db.session.commit()
        log_audit("CHANGE_PASSWORD", detail=f"username={account.username}")
        flash("เปลี่ยนรหัสผ่านเรียบร้อย", "success")
        return redirect(url_for("staff_admin.change_own_password"))
    return render_template("change_password.html", account=account)
