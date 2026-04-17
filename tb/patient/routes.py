"""Patient management and dose schedule routes."""
from __future__ import annotations

import csv
import json
from calendar import monthrange
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from tb.adherence import get_adherence_stats, get_adherence_stats_bulk
from tb.audit import log_audit
from tb.constants import OUTCOME_LABELS
from tb.extensions import db
from tb.models import MedicationDose, Patient
from tb.qr_utils import make_patient_token
from tb.regimen import calculate_regimen, parse_count
from tb.schedule import build_calendar, generate_schedule
from tb.security import staff_required
from tb.time_utils import today_th

bp = Blueprint("patient", __name__)


@bp.route("/")
@staff_required
def index():
    today = today_th()
    patients = Patient.query.filter_by(archived=False).order_by(Patient.id).all()
    patient_ids = [p.id for p in patients]
    stats_map = get_adherence_stats_bulk(patient_ids, today)
    today_doses = {}
    if patient_ids:
        today_doses = {
            d.patient_id: d for d in MedicationDose.query.filter(
                MedicationDose.patient_id.in_(patient_ids),
                MedicationDose.date == today,
            ).all()
        }
    patient_stats = [
        {"patient": p, "stats": stats_map[p.id], "today_dose": today_doses.get(p.id)}
        for p in patients
    ]
    archived_patients = Patient.query.filter_by(archived=True).order_by(Patient.id).all()
    return render_template(
        "index.html",
        patient_stats=patient_stats,
        archived_patients=archived_patients,
    )


@bp.route("/patient/new", methods=["GET", "POST"])
@staff_required
def new_patient():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        hn = request.form.get("hn", "").strip()
        age = request.form.get("age", "0").strip()
        tb_no = request.form.get("tb_no", "").strip()
        weight = request.form.get("weight", "0").strip()
        tb_type = request.form.get("tb_type", "").strip()
        start_date_str = request.form.get("start_date", "").strip()
        days_str = request.form.get("days_of_medication", "180").strip()
        use_custom = request.form.get("custom_regimen") == "on"

        phone = request.form.get("phone", "").strip()
        if not all([name, hn, age, tb_no, weight, tb_type, start_date_str]):
            flash("กรุณากรอกข้อมูลให้ครบทุกช่อง", "danger")
            return render_template("create_patient.html")
        try:
            start_date_obj = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("รูปแบบวันที่ไม่ถูกต้อง", "danger")
            return render_template("create_patient.html")
        try:
            age_val = int(age)
            weight_val = float(weight)
            if weight_val <= 0:
                raise ValueError
            days_of_medication = int(days_str)
        except ValueError:
            flash("ค่าตัวเลขไม่ถูกต้อง", "danger")
            return render_template("create_patient.html")

        patient = Patient(
            name=name, hn=hn, age=age_val, tb_no=tb_no,
            weight=weight_val, tb_type=tb_type,
            start_date=start_date_obj, custom_regimen=use_custom,
            phone=phone or None,
        )
        db.session.add(patient)
        db.session.commit()
        patient.scan_token = make_patient_token(patient.id)
        db.session.commit()

        if use_custom:
            custom = {}
            drug_names = request.form.getlist("drug_name")
            drug_counts = request.form.getlist("drug_count")
            for dname, dcount in zip(drug_names, drug_counts):
                dname = dname.strip()
                if dname and dcount.strip():
                    try:
                        custom[dname] = parse_count(dcount)
                    except ValueError:
                        pass
            if not custom:
                flash("กรุณาระบุยาอย่างน้อย 1 รายการ", "danger")
                db.session.delete(patient)
                db.session.commit()
                return render_template("create_patient.html")
            generate_schedule(patient, days_of_medication, regimen=custom)
        else:
            generate_schedule(patient, days_of_medication)

        log_audit("NEW_PATIENT", patient=patient,
                  detail=f"HN: {patient.hn}, weight: {patient.weight} kg")
        flash("เพิ่มผู้ป่วยสำเร็จ", "success")
        return redirect(url_for("view_patient", id=patient.id))
    return render_template("create_patient.html")


@bp.route("/patient/<int:id>")
@staff_required
def view_patient(id: int):
    patient = db.get_or_404(Patient, id)
    today = today_th()

    try:
        cal_year = int(request.args.get("year", today.year))
        cal_month = int(request.args.get("month", today.month))
    except ValueError:
        cal_year, cal_month = today.year, today.month

    calendar = build_calendar(patient, cal_year, cal_month)

    if cal_month == 1:
        prev_year, prev_month = cal_year - 1, 12
    else:
        prev_year, prev_month = cal_year, cal_month - 1
    if cal_month == 12:
        next_year, next_month = cal_year + 1, 1
    else:
        next_year, next_month = cal_year, cal_month + 1

    filter_start = request.args.get("from")
    filter_end = request.args.get("to")
    query = MedicationDose.query.filter_by(patient_id=patient.id)

    if filter_start:
        try:
            fs = datetime.strptime(filter_start, "%Y-%m-%d").date()
            query = query.filter(MedicationDose.date >= fs)
        except ValueError:
            pass
    if filter_end:
        try:
            fe = datetime.strptime(filter_end, "%Y-%m-%d").date()
            query = query.filter(MedicationDose.date <= fe)
        except ValueError:
            pass

    page = request.args.get("page", 1, type=int)
    per_page = 30
    pagination = query.order_by(MedicationDose.date).paginate(
        page=page, per_page=per_page, error_out=False
    )
    doses = pagination.items

    today_dose = MedicationDose.query.filter_by(
        patient_id=patient.id, date=today
    ).first()

    stats = get_adherence_stats(patient)

    return render_template(
        "patient.html",
        patient=patient, doses=doses, pagination=pagination,
        calendar=calendar, calendar_year=cal_year, calendar_month=cal_month,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        today_dose=today_dose, today=today, stats=stats,
        filter_start=filter_start or None, filter_end=filter_end or None,
        outcome_labels=OUTCOME_LABELS,
    )


@bp.route("/patient/<int:id>/edit", methods=["GET", "POST"])
@staff_required
def edit_patient(id: int):
    patient = db.get_or_404(Patient, id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        hn = request.form.get("hn", "").strip()
        tb_no = request.form.get("tb_no", "").strip()
        tb_type = request.form.get("tb_type", "").strip()
        try:
            age_val = int(request.form.get("age", "0"))
        except ValueError:
            flash("ค่าตัวเลขไม่ถูกต้อง", "danger")
            return render_template("edit_patient.html", patient=patient)
        phone = request.form.get("phone", "").strip()
        notes = request.form.get("notes", "").strip()
        if not all([name, hn, tb_no, tb_type]):
            flash("กรุณากรอกข้อมูลให้ครบ", "danger")
            return render_template("edit_patient.html", patient=patient)
        patient.name = name
        patient.hn = hn
        patient.tb_no = tb_no
        patient.tb_type = tb_type
        patient.age = age_val
        patient.phone = phone or None
        patient.notes = notes or None
        outcome = request.form.get("outcome", "").strip()
        patient.outcome = outcome if outcome in OUTCOME_LABELS else ""
        db.session.commit()
        log_audit(
            "EDIT_PATIENT", patient=patient,
            detail=f"name={name}, HN={hn}, outcome={patient.outcome}",
        )
        flash("แก้ไขข้อมูลผู้ป่วยเรียบร้อย", "success")
        return redirect(url_for("view_patient", id=id))
    return render_template(
        "edit_patient.html", patient=patient, outcome_labels=OUTCOME_LABELS,
    )


@bp.route("/patient/<int:id>/archive", methods=["POST"])
@staff_required
def archive_patient(id: int):
    patient = db.get_or_404(Patient, id)
    patient.archived = True
    db.session.commit()
    log_audit("ARCHIVE", patient=patient)
    flash(
        f"เก็บประวัติผู้ป่วย {patient.name} เรียบร้อย (ยังสามารถคืนสถานะได้)",
        "info",
    )
    return redirect(url_for("index"))


@bp.route("/patient/<int:id>/restore", methods=["POST"])
@staff_required
def restore_patient(id: int):
    patient = db.get_or_404(Patient, id)
    patient.archived = False
    db.session.commit()
    log_audit("RESTORE", patient=patient)
    flash(f"คืนสถานะผู้ป่วย {patient.name} เรียบร้อย", "success")
    return redirect(url_for("index"))


@bp.route("/patient/<int:id>/delete", methods=["POST"])
@staff_required
def delete_patient(id: int):
    patient = db.get_or_404(Patient, id)
    name = patient.name
    log_audit("DELETE", detail=f"ลบผู้ป่วย {name} (HN: {patient.hn}) ถาวร")
    MedicationDose.query.filter_by(patient_id=id).delete()
    db.session.delete(patient)
    db.session.commit()
    flash(f"ลบข้อมูลผู้ป่วย {name} ถาวรเรียบร้อย", "success")
    return redirect(url_for("index"))


@bp.route("/patient/<int:id>/extend", methods=["GET", "POST"])
@staff_required
def extend_schedule(id: int):
    patient = db.get_or_404(Patient, id)

    last_dose = MedicationDose.query.filter_by(
        patient_id=patient.id
    ).order_by(MedicationDose.date.desc()).first()
    last_date = last_dose.date if last_dose else patient.start_date
    current_meds = (
        last_dose.medications if last_dose else calculate_regimen(patient.weight)
    )

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_days":
            extra_days_str = request.form.get("extra_days", "15").strip()
            try:
                extra_days = int(extra_days_str)
            except ValueError:
                flash("จำนวนวันไม่ถูกต้อง", "danger")
                return redirect(url_for("extend_schedule", id=id))

            use_custom = request.form.get("use_custom_meds") == "on"
            if use_custom:
                regimen = {}
                drug_names = request.form.getlist("drug_name")
                drug_counts = request.form.getlist("drug_count")
                for dname, dcount in zip(drug_names, drug_counts):
                    dname = dname.strip()
                    if dname and dcount.strip():
                        try:
                            regimen[dname] = parse_count(dcount)
                        except ValueError:
                            pass
                if not regimen:
                    regimen = current_meds
            else:
                regimen = current_meds

            start = last_date + timedelta(days=1)
            meds_json = json.dumps(regimen)
            rows = [
                {
                    "patient_id": patient.id,
                    "date": start + timedelta(days=i),
                    "medications_json": meds_json,
                    "taken": False,
                    "taken_time": None,
                }
                for i in range(extra_days)
            ]
            db.session.execute(MedicationDose.__table__.insert(), rows)
            db.session.commit()
            log_audit(
                "EXTEND_SCHEDULE", patient=patient,
                detail=f"เพิ่ม {extra_days} วัน ตั้งแต่ {start}",
            )
            flash(f"เพิ่ม {extra_days} วัน (ตั้งแต่ {start.strftime('%Y-%m-%d')})", "success")

        elif action == "remove_days":
            remove_days_str = request.form.get("remove_days", "1").strip()
            try:
                remove_days = int(remove_days_str)
                if remove_days < 1:
                    raise ValueError
            except ValueError:
                flash("จำนวนวันไม่ถูกต้อง", "danger")
                return redirect(url_for("extend_schedule", id=id))

            future_untaken = (
                MedicationDose.query
                .filter_by(patient_id=patient.id, taken=False)
                .filter(MedicationDose.date >= today_th())
                .order_by(MedicationDose.date.desc())
                .limit(remove_days)
                .all()
            )
            if not future_untaken:
                flash(
                    "ไม่มีวันที่สามารถลดได้ (ต้องเป็นวันที่ยังไม่ได้กินและยังไม่ถึง)",
                    "warning",
                )
                return redirect(url_for("extend_schedule", id=id))
            actual = len(future_untaken)
            for dose in future_untaken:
                db.session.delete(dose)
            db.session.commit()
            log_audit(
                "REMOVE_DAYS", patient=patient,
                detail=f"ลด {actual} วันออกจากตาราง",
            )
            flash(f"ลด {actual} วันออกจากตารางยาแล้ว", "success")

        elif action == "update_future":
            regimen = {}
            drug_names = request.form.getlist("drug_name")
            drug_counts = request.form.getlist("drug_count")
            for dname, dcount in zip(drug_names, drug_counts):
                dname = dname.strip()
                if dname and dcount.strip():
                    try:
                        regimen[dname] = parse_count(dcount)
                    except ValueError:
                        pass
            if regimen:
                today = today_th()
                updated = db.session.execute(
                    MedicationDose.__table__.update()
                    .where(MedicationDose.__table__.c.patient_id == patient.id)
                    .where(MedicationDose.__table__.c.date >= today)
                    .where(MedicationDose.__table__.c.taken == False)
                    .values(medications_json=json.dumps(regimen))
                )
                db.session.commit()
                log_audit(
                    "UPDATE_FUTURE", patient=patient,
                    detail=f"อัปเดตยา {updated.rowcount} วัน: {regimen}",
                )
                flash(f"อัปเดตยาสำหรับ {updated.rowcount} วันที่เหลือ", "success")
            else:
                flash("กรุณาระบุยาอย่างน้อย 1 รายการ", "danger")

        return redirect(url_for("view_patient", id=id))

    removable_days = MedicationDose.query.filter_by(
        patient_id=patient.id, taken=False
    ).filter(MedicationDose.date >= today_th()).count()

    return render_template(
        "extend_schedule.html",
        patient=patient,
        last_date=last_date,
        current_meds=current_meds,
        removable_days=removable_days,
    )


@bp.route("/patient/<int:id>/update_weight", methods=["POST"])
@staff_required
def update_weight(id: int):
    patient = db.get_or_404(Patient, id)
    try:
        new_weight = float(request.form.get("weight", "").strip())
        if new_weight <= 0:
            raise ValueError
    except ValueError:
        flash("น้ำหนักไม่ถูกต้อง", "danger")
        return redirect(url_for("view_patient", id=id))

    patient.weight = new_weight
    db.session.commit()

    if not patient.custom_regimen:
        today = today_th()
        new_regimen = calculate_regimen(new_weight)
        db.session.execute(
            MedicationDose.__table__.update()
            .where(MedicationDose.__table__.c.patient_id == patient.id)
            .where(MedicationDose.__table__.c.date >= today)
            .where(MedicationDose.__table__.c.taken == False)
            .values(medications_json=json.dumps(new_regimen))
        )
        db.session.commit()
        log_audit(
            "UPDATE_WEIGHT", patient=patient,
            detail=f"น้ำหนักใหม่ {new_weight} kg, คำนวณยาใหม่",
        )
        flash(f"อัปเดตน้ำหนัก {new_weight} kg และคำนวณยาใหม่เรียบร้อย", "success")
    else:
        log_audit(
            "UPDATE_WEIGHT", patient=patient,
            detail=f"น้ำหนักใหม่ {new_weight} kg (custom regimen)",
        )
        flash(f"อัปเดตน้ำหนัก {new_weight} kg (สูตรยาเฉพาะไม่เปลี่ยนแปลง)", "info")

    return redirect(url_for("view_patient", id=id))


@bp.route("/patient/<int:id>/export_csv")
@staff_required
def export_csv(id: int):
    patient = db.get_or_404(Patient, id)
    doses = MedicationDose.query.filter_by(patient_id=id).order_by(MedicationDose.date).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["วันที่", "รายการยา", "สถานะ", "เวลาที่กิน"])
    for dose in doses:
        meds_str = ", ".join(f"{k}: {v}" for k, v in dose.medications.items())
        status = "กินแล้ว" if dose.taken else "ยังไม่ได้กิน"
        taken_time = dose.taken_time.strftime("%Y-%m-%d %H:%M") if dose.taken_time else ""
        writer.writerow([dose.date.strftime("%Y-%m-%d"), meds_str, status, taken_time])
    output.seek(0)
    filename = f"patient_{patient.hn}_{today_th()}.csv"
    return send_file(
        BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@bp.route("/patient/<int:id>/print")
@staff_required
def print_schedule(id: int):
    patient = db.get_or_404(Patient, id)
    today = today_th()
    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)
    _, last_day = monthrange(year, month)
    doses = MedicationDose.query.filter(
        MedicationDose.patient_id == id,
        MedicationDose.date >= date(year, month, 1),
        MedicationDose.date <= date(year, month, last_day),
    ).order_by(MedicationDose.date).all()
    all_drugs = list(dict.fromkeys(k for d in doses for k in d.medications))
    return render_template(
        "print_schedule.html",
        patient=patient, doses=doses, all_drugs=all_drugs,
        year=year, month=month, today=today,
    )


@bp.route("/patient/<int:id>/regenerate_token", methods=["POST"])
@staff_required
def regenerate_token(id: int):
    patient = db.get_or_404(Patient, id)
    patient.scan_token = make_patient_token()
    db.session.commit()
    log_audit("REGEN_TOKEN", patient=patient)
    flash("สร้าง QR Code ใหม่เรียบร้อย — QR เก่าจะใช้ไม่ได้แล้ว", "success")
    return redirect(url_for("qr_code_page", patient_id=id))
