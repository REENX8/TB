"""Staff-side symptom report review routes."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from tb.audit import log_audit
from tb.constants import SYMPTOM_CATEGORIES, SYMPTOM_STATUS_LABELS
from tb.extensions import db
from tb.models import SymptomReport
from tb.security import role_required, staff_required
from tb.time_utils import TZ_THAI

bp = Blueprint("symptom", __name__, url_prefix="/symptoms")


@bp.route("/")
@staff_required
def list_symptoms():
    status = request.args.get("status", "")
    query = SymptomReport.query
    if status in SYMPTOM_STATUS_LABELS:
        query = query.filter(SymptomReport.status == status)
    else:
        status = ""
        query = query.filter(SymptomReport.status.in_(["new", "replied"]))
    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(SymptomReport.reported_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template(
        "symptoms.html",
        pagination=pagination,
        reports=pagination.items,
        status=status,
        symptom_categories=SYMPTOM_CATEGORIES,
        status_labels=SYMPTOM_STATUS_LABELS,
    )


@bp.route("/<int:id>/reply", methods=["POST"])
@role_required("admin", "pharmacist")
def reply_symptom(id: int):
    report = db.get_or_404(SymptomReport, id)
    reply = request.form.get("reply", "").strip()
    if not reply:
        flash("กรุณากรอกข้อความตอบกลับ", "danger")
        return redirect(url_for("symptom.list_symptoms"))
    report.pharmacist_reply = reply
    report.replied_by = session.get("staff_user", "system")
    report.replied_at = datetime.now(TZ_THAI).replace(tzinfo=None)
    report.status = "replied"
    db.session.commit()
    log_audit(
        "REPLY_SYMPTOM", patient=report.patient,
        detail=f"report_id={report.id}",
    )
    flash("ตอบกลับการแจ้งอาการเรียบร้อย", "success")
    return redirect(url_for("symptom.list_symptoms"))


@bp.route("/<int:id>/resolve", methods=["POST"])
@staff_required
def resolve_symptom(id: int):
    report = db.get_or_404(SymptomReport, id)
    report.status = "resolved"
    db.session.commit()
    log_audit(
        "RESOLVE_SYMPTOM", patient=report.patient,
        detail=f"report_id={report.id}",
    )
    flash("ปิดเรื่องการแจ้งอาการเรียบร้อย", "success")
    return redirect(url_for("symptom.list_symptoms"))
