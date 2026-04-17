"""Audit log helper."""
from __future__ import annotations

from datetime import datetime

from flask import session

from tb.extensions import db
from tb.models import AuditLog
from tb.time_utils import TZ_THAI


def log_audit(action: str, patient=None, detail: str | None = None) -> None:
    """Write an audit log entry. Pulls staff_user from session."""
    try:
        entry = AuditLog(
            timestamp=datetime.now(TZ_THAI),
            staff_user=session.get("staff_user", "system"),
            action=action,
            patient_id=patient.id if patient else None,
            patient_name=patient.name if patient else None,
            detail=detail,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        print("Audit log error:", e)
