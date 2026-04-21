"""QR code and patient scan routes."""
from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO

from flask import Blueprint, redirect, render_template, request, send_file, session, url_for

from tb.adherence import get_adherence_stats
from tb.extensions import csrf, db
from tb.models import INJECTABLE_DRUGS, MedicationDose, Patient
from tb.qr_utils import create_qr_code
from tb.security import staff_required
from tb.time_utils import TZ_THAI, today_th

bp = Blueprint("scan", __name__)


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
            today_dose.taken = True
            today_dose.taken_time = datetime.now(TZ_THAI)
            db.session.commit()
            session[cooldown_key] = now_ts
        return redirect(url_for("scan_patient", token=token))

    week_ago = today - timedelta(days=6)
    recent_doses = MedicationDose.query.filter(
        MedicationDose.patient_id == patient.id,
        MedicationDose.date >= week_ago,
        MedicationDose.date <= today,
    ).order_by(MedicationDose.date.desc()).all()

    stats = get_adherence_stats(patient)

    total_days = stats["total_all"]
    taken_days = stats["taken"]
    treatment_day = (today - patient.start_date).days + 1

    return render_template(
        "scan.html",
        patient=patient,
        today_dose=today_dose,
        today=today,
        recent_doses=recent_doses,
        stats=stats,
        total_days=total_days,
        taken_days=taken_days,
        treatment_day=treatment_day,
        injectable_drugs=INJECTABLE_DRUGS,
    )
