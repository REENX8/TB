"""Dose marking routes."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from tb.audit import log_audit
from tb.extensions import db
from tb.models import MedicationDose, Patient
from tb.regimen import parse_count
from tb.security import staff_required
from tb.time_utils import TZ_THAI

bp = Blueprint("dose", __name__)


@bp.route("/patient/<int:id>/mark/<int:dose_id>", methods=["POST"])
@staff_required
def mark_dose(id: int, dose_id: int):
    db.get_or_404(Patient, id)
    dose = MedicationDose.query.filter_by(
        id=dose_id, patient_id=id
    ).first_or_404()
    if not dose.taken:
        dose.taken = True
        dose.taken_time = datetime.now(TZ_THAI).replace(tzinfo=None)
        db.session.commit()
        log_audit("MARK_DOSE", patient=dose.patient, detail=f"วันที่ {dose.date}")
        flash(
            f"บันทึกการกินยาวันที่ {dose.date.strftime('%Y-%m-%d')} เรียบร้อย",
            "success",
        )
    else:
        flash("บันทึกการกินยาไปแล้ว", "info")
    return redirect(url_for("view_patient", id=id))


@bp.route("/patient/<int:id>/unmark/<int:dose_id>", methods=["POST"])
@staff_required
def unmark_dose(id: int, dose_id: int):
    db.get_or_404(Patient, id)
    dose = MedicationDose.query.filter_by(id=dose_id, patient_id=id).first_or_404()
    dose.taken = False
    dose.taken_time = None
    db.session.commit()
    log_audit("UNMARK_DOSE", patient=dose.patient, detail=f"วันที่ {dose.date}")
    flash(
        f"ยกเลิกการกินยาวันที่ {dose.date.strftime('%Y-%m-%d')} เรียบร้อย",
        "success",
    )
    return redirect(url_for("view_patient", id=id))


@bp.route("/patient/<int:id>/edit_dose/<int:dose_id>", methods=["GET", "POST"])
@staff_required
def edit_dose(id: int, dose_id: int):
    patient = db.get_or_404(Patient, id)
    dose = MedicationDose.query.filter_by(
        id=dose_id, patient_id=id
    ).first_or_404()

    if request.method == "POST":
        new_meds = {}
        drug_names = request.form.getlist("drug_name")
        drug_counts = request.form.getlist("drug_count")
        for dname, dcount in zip(drug_names, drug_counts):
            dname = dname.strip()
            if dname and dcount.strip():
                try:
                    new_meds[dname] = parse_count(dcount)
                except ValueError:
                    pass
        if new_meds:
            dose.medications = new_meds
            db.session.commit()
            log_audit(
                "EDIT_DOSE", patient=patient,
                detail=f"วันที่ {dose.date}, ยา: {new_meds}",
            )
            flash(f"แก้ไขยาวันที่ {dose.date.strftime('%Y-%m-%d')} เรียบร้อย", "success")
        else:
            flash("กรุณาระบุยาอย่างน้อย 1 รายการ", "danger")
            return render_template("edit_dose.html", patient=patient, dose=dose)
        return redirect(url_for("view_patient", id=id))

    return render_template("edit_dose.html", patient=patient, dose=dose)
