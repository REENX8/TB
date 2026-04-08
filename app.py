"""
app.py — TB Medication Tracker

Features:
- 1 QR code per patient (scans to patient's dose page)
- Medication with mg dosages (INH 100mg, Rifampicin 300/450mg, PZA 500mg, EMB 400/500mg)
- Custom medication for allergic patients (pharmacist manual entry)
- Pharmacist can extend/add/edit doses and medications per patient
- Staff dashboard with login protection
"""

import csv
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from io import BytesIO, StringIO
from calendar import monthrange

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, case as sa_case
from werkzeug.security import check_password_hash
import qrcode


app = Flask(__name__)
_db_url = os.environ.get("DATABASE_URL", "sqlite:///tb.db")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret")
db = SQLAlchemy(app)

STAFF_USERNAME = os.environ.get("STAFF_USER", "REEN")
STAFF_PASSWORD_HASH = os.environ.get(
    "STAFF_PASS_HASH",
    "scrypt:32768:8:1$lYS9DAFUtGkNDbY5$10b7a5f05d5244417e8bb34c6848b6a016b9ae0cad769814db43d87d310b57b5910fabbb719c43d15e4b615791284c01d165bb0d74b38abd5db0468165a7c91d",
)

# Build list of valid staff accounts from env vars
# STAFF_USER_2, STAFF_PASS_HASH_2 (and so on) for additional accounts
STAFF_ACCOUNTS = {STAFF_USERNAME: STAFF_PASSWORD_HASH}
_i = 2
while True:
    _u = os.environ.get(f"STAFF_USER_{_i}")
    _h = os.environ.get(f"STAFF_PASS_HASH_{_i}")
    if not _u or not _h:
        break
    STAFF_ACCOUNTS[_u] = _h
    _i += 1


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("staff_logged_in"):
            return redirect(url_for("staff_login", next=request.url))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------

class Patient(db.Model):
    __tablename__ = "patients"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    hn = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    tb_no = db.Column(db.String(120), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    tb_type = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    scan_token = db.Column(db.String(64), unique=True, nullable=True)
    custom_regimen = db.Column(db.Boolean, default=False, nullable=False)
    doses = db.relationship(
        "MedicationDose", backref="patient", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Patient {self.id} {self.name}>"


class MedicationDose(db.Model):
    __tablename__ = "medication_doses"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer, db.ForeignKey("patients.id"), nullable=False
    )
    date = db.Column(db.Date, nullable=False)
    medications_json = db.Column(db.Text, nullable=False)
    taken = db.Column(db.Boolean, default=False, nullable=False)
    taken_time = db.Column(db.DateTime, nullable=True)

    @property
    def medications(self) -> dict:
        return json.loads(self.medications_json)

    @medications.setter
    def medications(self, value: dict) -> None:
        self.medications_json = json.dumps(value)

    def __repr__(self) -> str:
        return f"<Dose {self.id} {self.date} taken={self.taken}>"


with app.app_context():
    db.create_all()


# ---------------------------------------------------------------------------
# Medication regimen with mg dosages
# ---------------------------------------------------------------------------

def _parse_count(value: str):
    """Parse tablet count; returns int for whole numbers, float for halves (e.g. 1.5)."""
    v = float(value)
    return int(v) if v == int(v) else v


def calculate_regimen(weight: float) -> dict:
    """Return medication regimen with tablet counts per Thai TB guidelines (Table 6.1).

    Format: {"drug_name (mg)": count, ...}
    Weight groups:
      30–34 kg  : INH×2, Rifam300×1, PZA×1.5, EMB500×1
      35–49 kg  : INH×3, Rifam450×1, PZA×2,   EMB400×2
      50–69 kg  : INH×3, Rifam300×2, PZA×3,   EMB500×2
      ≥70 kg    : INH×3, Rifam300×2, PZA×4,   EMB400×3
      <30 kg    : คำนวณตามน้ำหนัก (H 5mg/kg, R 10mg/kg, Z 25mg/kg, E 17.5mg/kg)
    """
    if weight < 30:
        return {
            "INH 100mg": max(1, round(weight * 5 / 100)),
            "Rifampicin 300mg": max(1, round(weight * 10 / 300)),
            "PZA 500mg": max(1, round(weight * 25 / 500)),
            "EMB 400mg": max(1, round(weight * 17.5 / 400)),
        }
    elif weight < 35:  # 30–34 kg
        return {
            "INH 100mg": 2,
            "Rifampicin 300mg": 1,
            "PZA 500mg": 1.5,
            "EMB 500mg": 1,
        }
    elif weight < 50:  # 35–49 kg
        return {
            "INH 100mg": 3,
            "Rifampicin 450mg": 1,
            "PZA 500mg": 2,
            "EMB 400mg": 2,
        }
    elif weight < 70:  # 50–69 kg
        return {
            "INH 100mg": 3,
            "Rifampicin 300mg": 2,
            "PZA 500mg": 3,
            "EMB 500mg": 2,
        }
    else:  # ≥70 kg
        return {
            "INH 100mg": 3,
            "Rifampicin 300mg": 2,
            "PZA 500mg": 4,
            "EMB 400mg": 3,
        }


def make_patient_token(patient_id: int) -> str:
    """Generate a unique scan token for a patient."""
    raw = f"patient-{patient_id}-{app.secret_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_schedule(patient: Patient, days: int = 180,
                      regimen: dict = None) -> None:
    MedicationDose.query.filter_by(patient_id=patient.id).delete()
    if regimen is None:
        regimen = calculate_regimen(patient.weight)
    meds_json = json.dumps(regimen)
    rows = [
        {
            "patient_id": patient.id,
            "date": patient.start_date + timedelta(days=i),
            "medications_json": meds_json,
            "taken": False,
            "taken_time": None,
        }
        for i in range(days)
    ]
    db.session.execute(MedicationDose.__table__.insert(), rows)
    db.session.commit()


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def build_calendar(patient: Patient, year: int, month: int) -> list:
    first_of_month = date(year, month, 1)
    _, last_day = monthrange(year, month)

    doses_in_month = MedicationDose.query.filter(
        MedicationDose.patient_id == patient.id,
        MedicationDose.date >= first_of_month,
        MedicationDose.date <= date(year, month, last_day),
    ).all()
    doses_by_date = {dose.date: dose for dose in doses_in_month}

    today = date.today()
    calendar = []
    start_weekday = first_of_month.weekday()
    for _ in range(start_weekday):
        calendar.append(None)

    for day in range(1, last_day + 1):
        current_date = date(year, month, day)
        dose = doses_by_date.get(current_date)
        if dose is None:
            status = "no_schedule"
        elif dose.taken:
            status = "taken"
        elif current_date < today:
            status = "overdue"
        else:
            status = "pending"
        calendar.append({"date": current_date, "status": status, "day": day})

    return calendar


def create_qr_code(data: str) -> bytes:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


def get_adherence_stats(patient: Patient) -> dict:
    today = date.today()
    row = db.session.query(
        func.count(MedicationDose.id).label("total_all"),
        func.sum(sa_case((MedicationDose.date <= today, 1), else_=0)).label("total_past"),
        func.sum(sa_case(
            (db.and_(MedicationDose.date <= today, MedicationDose.taken == True), 1),
            else_=0,
        )).label("taken"),
    ).filter(MedicationDose.patient_id == patient.id).one()
    total_all = row.total_all or 0
    total_past = row.total_past or 0
    taken = row.taken or 0
    overdue = total_past - taken
    pct = round(taken / total_past * 100, 1) if total_past > 0 else 0
    return {
        "total_past": total_past,
        "taken": taken,
        "overdue": overdue,
        "total_all": total_all,
        "adherence_pct": pct,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
@staff_required
def index() -> str:
    patients = Patient.query.order_by(Patient.id).all()
    patient_stats = []
    today = date.today()
    for p in patients:
        stats = get_adherence_stats(p)
        today_dose = MedicationDose.query.filter_by(
            patient_id=p.id, date=today
        ).first()
        patient_stats.append({
            "patient": p,
            "stats": stats,
            "today_dose": today_dose,
        })
    return render_template("index.html", patient_stats=patient_stats)


@app.route("/patient/new", methods=["GET", "POST"])
@staff_required
def new_patient() -> str:
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
            days_of_medication = int(days_str)
        except ValueError:
            flash("ค่าตัวเลขไม่ถูกต้อง", "danger")
            return render_template("create_patient.html")

        patient = Patient(
            name=name, hn=hn, age=age_val, tb_no=tb_no,
            weight=weight_val, tb_type=tb_type,
            start_date=start_date_obj, custom_regimen=use_custom,
        )
        db.session.add(patient)
        db.session.commit()
        patient.scan_token = make_patient_token(patient.id)
        db.session.commit()

        # Build regimen
        if use_custom:
            custom = {}
            drug_names = request.form.getlist("drug_name")
            drug_counts = request.form.getlist("drug_count")
            for dname, dcount in zip(drug_names, drug_counts):
                dname = dname.strip()
                if dname and dcount.strip():
                    try:
                        custom[dname] = _parse_count(dcount)
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

        flash("เพิ่มผู้ป่วยสำเร็จ", "success")
        return redirect(url_for("view_patient", id=patient.id))
    return render_template("create_patient.html")


@app.route("/patient/<int:id>")
@staff_required
def view_patient(id: int) -> str:
    patient = db.get_or_404(Patient, id)
    today = date.today()

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
        filter_start=filter_start or "", filter_end=filter_end or "",
    )


@app.route("/patient/<int:id>/mark/<int:dose_id>", methods=["POST"])
@staff_required
def mark_dose(id: int, dose_id: int) -> str:
    db.get_or_404(Patient, id)
    dose = MedicationDose.query.filter_by(
        id=dose_id, patient_id=id
    ).first_or_404()
    if not dose.taken:
        dose.taken = True
        dose.taken_time = datetime.now(timezone.utc)
        db.session.commit()
        flash(f"บันทึกการกินยาวันที่ {dose.date.strftime('%Y-%m-%d')} เรียบร้อย", "success")
    else:
        flash("บันทึกการกินยาไปแล้ว", "info")
    return redirect(url_for("view_patient", id=id))


@app.route("/patient/<int:id>/delete", methods=["POST"])
@staff_required
def delete_patient(id: int) -> str:
    patient = db.get_or_404(Patient, id)
    MedicationDose.query.filter_by(patient_id=id).delete()
    db.session.delete(patient)
    db.session.commit()
    flash(f"ลบผู้ป่วย {patient.name} เรียบร้อย", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Pharmacist editing routes (staff only)
# ---------------------------------------------------------------------------

@app.route("/patient/<int:id>/edit_dose/<int:dose_id>", methods=["GET", "POST"])
@staff_required
def edit_dose(id: int, dose_id: int) -> str:
    """Pharmacist edits a single dose's medications."""
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
                    new_meds[dname] = _parse_count(dcount)
                except ValueError:
                    pass
        if new_meds:
            dose.medications = new_meds
            db.session.commit()
            flash(f"แก้ไขยาวันที่ {dose.date.strftime('%Y-%m-%d')} เรียบร้อย", "success")
        else:
            flash("กรุณาระบุยาอย่างน้อย 1 รายการ", "danger")
            return render_template("edit_dose.html", patient=patient, dose=dose)
        return redirect(url_for("view_patient", id=id))

    return render_template("edit_dose.html", patient=patient, dose=dose)


@app.route("/patient/<int:id>/extend", methods=["GET", "POST"])
@staff_required
def extend_schedule(id: int) -> str:
    """Pharmacist adds more days or adjusts medication for remaining doses."""
    patient = db.get_or_404(Patient, id)

    last_dose = MedicationDose.query.filter_by(
        patient_id=patient.id
    ).order_by(MedicationDose.date.desc()).first()
    last_date = last_dose.date if last_dose else patient.start_date
    current_meds = last_dose.medications if last_dose else calculate_regimen(patient.weight)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_days":
            extra_days_str = request.form.get("extra_days", "15").strip()
            try:
                extra_days = int(extra_days_str)
            except ValueError:
                flash("จำนวนวันไม่ถูกต้อง", "danger")
                return redirect(url_for("extend_schedule", id=id))

            # Use custom meds if provided, else same as last dose
            use_custom = request.form.get("use_custom_meds") == "on"
            if use_custom:
                regimen = {}
                drug_names = request.form.getlist("drug_name")
                drug_counts = request.form.getlist("drug_count")
                for dname, dcount in zip(drug_names, drug_counts):
                    dname = dname.strip()
                    if dname and dcount.strip():
                        try:
                            regimen[dname] = _parse_count(dcount)
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
            flash(f"เพิ่ม {extra_days} วัน (ตั้งแต่ {start.strftime('%Y-%m-%d')})", "success")

        elif action == "update_future":
            # Update all future untaken doses with new medications
            regimen = {}
            drug_names = request.form.getlist("drug_name")
            drug_counts = request.form.getlist("drug_count")
            for dname, dcount in zip(drug_names, drug_counts):
                dname = dname.strip()
                if dname and dcount.strip():
                    try:
                        regimen[dname] = _parse_count(dcount)
                    except ValueError:
                        pass
            if regimen:
                today = date.today()
                updated = db.session.execute(
                    MedicationDose.__table__.update()
                    .where(MedicationDose.__table__.c.patient_id == patient.id)
                    .where(MedicationDose.__table__.c.date >= today)
                    .where(MedicationDose.__table__.c.taken == False)
                    .values(medications_json=json.dumps(regimen))
                )
                db.session.commit()
                flash(f"อัปเดตยาสำหรับ {updated.rowcount} วันที่เหลือ", "success")
            else:
                flash("กรุณาระบุยาอย่างน้อย 1 รายการ", "danger")
                
        return redirect(url_for("view_patient", id=id))

    return render_template(
        "extend_schedule.html",
        patient=patient,
        last_date=last_date,
        current_meds=current_meds,
    )


# ---------------------------------------------------------------------------
# Unmark dose (staff only)
# ---------------------------------------------------------------------------

@app.route("/patient/<int:id>/unmark/<int:dose_id>", methods=["POST"])
@staff_required
def unmark_dose(id: int, dose_id: int) -> str:
    db.get_or_404(Patient, id)
    dose = MedicationDose.query.filter_by(id=dose_id, patient_id=id).first_or_404()
    dose.taken = False
    dose.taken_time = None
    db.session.commit()
    flash(f"ยกเลิกการกินยาวันที่ {dose.date.strftime('%Y-%m-%d')} เรียบร้อย", "success")
    return redirect(url_for("view_patient", id=id))


# ---------------------------------------------------------------------------
# Update weight + recalculate regimen (staff only)
# ---------------------------------------------------------------------------

@app.route("/patient/<int:id>/update_weight", methods=["POST"])
@staff_required
def update_weight(id: int) -> str:
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
        today = date.today()
        new_regimen = calculate_regimen(new_weight)
        db.session.execute(
            MedicationDose.__table__.update()
            .where(MedicationDose.__table__.c.patient_id == patient.id)
            .where(MedicationDose.__table__.c.date >= today)
            .where(MedicationDose.__table__.c.taken == False)
            .values(medications_json=json.dumps(new_regimen))
        )
        db.session.commit()
        flash(f"อัปเดตน้ำหนัก {new_weight} kg และคำนวณยาใหม่เรียบร้อย", "success")
    else:
        flash(f"อัปเดตน้ำหนัก {new_weight} kg (สูตรยาเฉพาะไม่เปลี่ยนแปลง)", "info")

    return redirect(url_for("view_patient", id=id))


# ---------------------------------------------------------------------------
# Export CSV (staff only)
# ---------------------------------------------------------------------------

@app.route("/patient/<int:id>/export_csv")
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
    filename = f"patient_{patient.hn}_{date.today()}.csv"
    return send_file(
        BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


# ---------------------------------------------------------------------------
# QR & Scan — 1 QR per patient
# ---------------------------------------------------------------------------

@app.route("/qr/patient/<int:patient_id>.png")
@staff_required
def qr_code_patient(patient_id: int):
    """Serve a single QR code image for a patient."""
    patient = db.get_or_404(Patient, patient_id)
    scan_url = url_for("scan_patient", token=patient.scan_token, _external=True)
    img_bytes = create_qr_code(scan_url)
    return send_file(
        BytesIO(img_bytes),
        mimetype="image/png",
        as_attachment=False,
        download_name=f"qr_patient_{patient.id}.png",
    )


@app.route("/qr_page/<int:patient_id>")
@staff_required
def qr_code_page(patient_id: int) -> str:
    """Show QR code page for a patient (single QR for all doses)."""
    patient = db.get_or_404(Patient, patient_id)
    return render_template("qr.html", patient=patient)


@app.route("/scan/<token>", methods=["GET", "POST"])
def scan_patient(token: str) -> str:
    """Mobile page opened when patient scans their QR code.

    Shows today's dose. Patient can confirm taking medication.
    Also shows recent dose history.
    """
    patient = Patient.query.filter_by(scan_token=token).first_or_404()
    today = date.today()

    today_dose = MedicationDose.query.filter_by(
        patient_id=patient.id, date=today
    ).first()

    if request.method == "POST" and today_dose and not today_dose.taken:
        today_dose.taken = True
        today_dose.taken_time = datetime.now(timezone.utc)
        db.session.commit()

    # Recent 7 days history
    week_ago = today - timedelta(days=6)
    recent_doses = MedicationDose.query.filter(
        MedicationDose.patient_id == patient.id,
        MedicationDose.date >= week_ago,
        MedicationDose.date <= today,
    ).order_by(MedicationDose.date.desc()).all()

    stats = get_adherence_stats(patient)

    return render_template(
        "scan.html",
        patient=patient,
        today_dose=today_dose,
        today=today,
        recent_doses=recent_doses,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def staff_login() -> str:
    if session.get("staff_logged_in"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        _hash = STAFF_ACCOUNTS.get(username)
        if _hash and check_password_hash(_hash, password):
            session.permanent = True
            session["staff_logged_in"] = True
            session["staff_user"] = username
            flash("เข้าสู่ระบบสำเร็จ", "success")
            next_url = request.args.get("next") or ""
            if not next_url or not next_url.startswith("/"):
                next_url = url_for("dashboard")
            return redirect(next_url)
        else:
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "danger")
    return render_template("login.html")


@app.route("/logout")
def staff_logout() -> str:
    session.pop("staff_logged_in", None)
    session.pop("staff_user", None)
    flash("ออกจากระบบเรียบร้อย", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@staff_required
def dashboard() -> str:
    patients = Patient.query.order_by(Patient.id).all()
    today = date.today()
    rows = []
    total_overdue_all = 0
    for p in patients:
        stats = get_adherence_stats(p)
        today_dose = MedicationDose.query.filter_by(
            patient_id=p.id, date=today
        ).first()
        rows.append({
            "patient": p,
            "stats": stats,
            "today_dose": today_dose,
        })
        total_overdue_all += stats["overdue"]

    return render_template(
        "dashboard.html", rows=rows, today=today,
        total_patients=len(patients), total_overdue=total_overdue_all,
    )


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

@app.context_processor
def inject_helpers():
    def format_date(dt: date) -> str:
        return dt.strftime("%Y-%m-%d") if dt else ""
    def format_datetime(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""
    return dict(format_date=format_date, format_datetime=format_datetime, date=date,
                drug_images=DRUG_IMAGES)


DRUG_IMAGES = {
    "INH 100mg": "drugs/inh_100mg.jpg",
    "Rifampicin 300mg": "drugs/rifampicin_300mg.jpg",
    "Rifampicin 450mg": "drugs/rifampicin_450mg.jpg",
    "PZA 500mg": "drugs/pza_500mg.jpg",
    "EMB 400mg": "drugs/emb_400mg.jpg",
    "EMB 500mg": "drugs/emb_500mg.jpg",
}

THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

@app.template_filter("thai_month")
def thai_month_filter(month_num):
    return THAI_MONTHS[month_num] if 1 <= month_num <= 12 else str(month_num)


@app.route("/ping")
def ping():
    return "ok", 200


if __name__ == "__main__":
    app.run(debug=True)
