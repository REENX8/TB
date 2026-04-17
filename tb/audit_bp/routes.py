"""Audit log view route."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, render_template, request

from tb.extensions import db
from tb.models import AuditLog
from tb.security import staff_required

bp = Blueprint("audit", __name__)


@bp.route("/audit")
@staff_required
def audit_log():
    page = request.args.get("page", 1, type=int)
    action_filter = request.args.get("action", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()

    query = AuditLog.query.order_by(AuditLog.timestamp.desc())
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)
    if date_from:
        try:
            query = query.filter(
                AuditLog.timestamp >= datetime.strptime(date_from, "%Y-%m-%d")
            )
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(AuditLog.timestamp < dt_to)
        except ValueError:
            pass

    pagination = query.paginate(page=page, per_page=50, error_out=False)
    all_actions = [
        r[0] for r in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    ]
    return render_template(
        "audit.html",
        logs=pagination.items, pagination=pagination,
        action_filter=action_filter, date_from=date_from, date_to=date_to,
        all_actions=all_actions,
    )
