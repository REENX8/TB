"""QR code and patient scan routes."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from io import BytesIO

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from tb.adherence import get_adherence_stats
from tb.audit import log_audit
from tb.constants import SYMPTOM_CATEGORIES, SYMPTOM_SEVERE_WARNING
from tb.extensions import csrf, db
from tb.models import MedicationDose, Patient, SymptomReport
from tb.qr_utils import create_qr_code
from tb.security import is_rate_limited, staff_required
from tb.time_utils import TZ_THAI, today_th

bp = Blueprint("scan", __name__)

SCAN_RATE_LIMIT = 30  # requests per IP
SCAN_RATE_WINDOW = 60  # seconds
MAX_SYMPTOM_REPORTS_PER_DAY = 3
SYMPTOM_DETAIL_MAX_LENGTH = 500


def build_auto_response(category: str) -> str:
    """Render the stored Thai guidance snapshot for a symptom category."""
    info = SYMPTOM_CATEGORIES[category]
    if info["severe"]:
        return f"{SYMPTOM_SEVERE_WARNING}\n{info['advice']}"
    return info["advice"]


@bp.route("/qr/patient/<int:patient_id>.png")
@staff_required
def qr_code_patient(patient_id: int):
    patient = db.get_or_404(Patient, patient_id)
    scan_url = url_for("scan_patient", token=patient.scan_token, _external=True)
    img_bytes = create_qr_code(scan_url)
    return send_file(
        BytesIO(img_bytes),
        mimetype="image/png",
        as_attachment=False,
        download_name=f"qr_patient_{patient.id}.png",
    )


@bp.route("/qr_page/<int:patient_id>")
@staff_required
def qr_code_page(patient_id: int):
    patient = db.get_or_404(Patient, patient_id)
    return render_template("qr.html", patient=patient)


@bp.route("/scan/<token>", methods=["GET", "POST"])
@csrf.exempt
def scan_patient(token: str):
    """Mobile page opened when patient scans their QR code."""
    if is_rate_limited(
        f"scan:{request.remote_addr}", SCAN_RATE_LIMIT, SCAN_RATE_WINDOW
    ):
        return "คำขอมากเกินไป กรุณารอสักครู่", 429

    patient = Patient.query.filter_by(scan_token=token).first_or_404()
    today = today_th()

    today_dose = MedicationDose.query.filter_by(
        patient_id=patient.id, date=today
    ).first()

    if request.method == "POST" and today_dose and not today_dose.taken:
        cooldown_key = f"scan_last_{token}"
        last_ts = session.get(cooldown_key, 0)
        now_ts = datetime.now(TZ_THAI).timestamp()
        if now_ts - last_ts >= 30:
            # Atomic conditional UPDATE so concurrent confirms cannot
            # double-mark or overwrite taken_time.
            updated = db.session.query(MedicationDose).filter(
                MedicationDose.id == today_dose.id,
                MedicationDose.taken == False,  # noqa: E712
            ).update(
                {
                    "taken": True,
                    "taken_time": datetime.now(TZ_THAI).replace(tzinfo=None),
                },
                synchronize_session=False,
            )
            db.session.commit()
            if updated:
                session[cooldown_key] = now_ts
        return redirect(url_for("scan_patient", token=token))

    stats = get_adherence_stats(patient)

    recent_cutoff = datetime.combine(today - timedelta(days=14), time.min)
    recent_reports = (
        SymptomReport.query
        .filter(
            SymptomReport.patient_id == patient.id,
            SymptomReport.reported_at >= recent_cutoff,
        )
        .order_by(SymptomReport.reported_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "scan.html",
        patient=patient,
        today_dose=today_dose,
        today=today,
        stats=stats,
        recent_reports=recent_reports,
        symptom_categories=SYMPTOM_CATEGORIES,
    )


# CSRF-exempt like scan_patient: the unguessable token in the URL is the
# auth secret, and the daily report cap bounds any forged submissions.
@bp.route("/scan/<token>/report", methods=["POST"])
@csrf.exempt
def scan_report(token: str):
    if is_rate_limited(
        f"scan:{request.remote_addr}", SCAN_RATE_LIMIT, SCAN_RATE_WINDOW
    ):
        return "คำขอมากเกินไป กรุณารอสักครู่", 429

    patient = Patient.query.filter_by(scan_token=token).first_or_404()
    today = today_th()

    category = request.form.get("category", "")
    if category not in SYMPTOM_CATEGORIES:
        flash("กรุณาเลือกอาการที่ต้องการแจ้ง", "danger")
        return redirect(url_for("scan_patient", token=token))

    today_start = datetime.combine(today, time.min)
    reports_today = SymptomReport.query.filter(
        SymptomReport.patient_id == patient.id,
        SymptomReport.reported_at >= today_start,
    ).count()
    if reports_today >= MAX_SYMPTOM_REPORTS_PER_DAY:
        flash(
            f"ส่งรายงานได้สูงสุด {MAX_SYMPTOM_REPORTS_PER_DAY} ครั้งต่อวัน "
            "หากอาการรุนแรงกรุณาติดต่อคลินิกโดยตรง",
            "warning",
        )
        return redirect(url_for("scan_patient", token=token))

    detail = request.form.get("detail", "").strip()[:SYMPTOM_DETAIL_MAX_LENGTH]
    report = SymptomReport(
        patient_id=patient.id,
        reported_at=datetime.now(TZ_THAI).replace(tzinfo=None),
        category=category,
        detail=detail or None,
        auto_response=build_auto_response(category),
    )
    db.session.add(report)
    db.session.commit()
    log_audit(
        "SYMPTOM_REPORT", patient=patient,
        detail=SYMPTOM_CATEGORIES[category]["label"],
    )
    flash("บันทึกการแจ้งอาการแล้ว กรุณาอ่านคำแนะนำเบื้องต้นด้านล่าง", "success")
    return redirect(url_for("scan_patient", token=token))
