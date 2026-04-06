"""
app.py — TB Medication Tracker

Features:
- 1 QR code per patient (scans to patient's dose page)
- Medication with mg dosages (INH 100mg, Rifampicin 300/450mg, PZA 500mg, EMB 400/500mg)
- Custom medication for allergic patients (pharmacist manual entry)
- Pharmacist can extend/add/edit doses and medications per patient
- Staff dashboard with login protection
"""

import hashlib
import json
import os
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO
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
from werkzeug.security import check_password_hash
import qrcode


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///tb.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret")
db = SQLAlchemy(app)

STAFF_USERNAME = os.environ.get("STAFF_USER", "REEN")
STAFF_PASSWORD_HASH = os.environ.get(
    "STAFF_PASS_HASH",
    "scrypt:32768:8:1$lYS9DAFUtGkNDbY5$10b7a5f05d5244417e8bb34c6848b6a016b9ae0cad769814db43d87d310b57b5910fabbb719c43d15e4b615791284c01d165bb0d74b38abd5db0468165a7c91d",
)


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

# Drug info: name -> mg per tablet
DRUG_INFO = {
    "INH": {"mg": 100},
    "Rifampicin 300mg": {"mg": 300},
    "Rifampicin 450mg": {"mg": 450},
    "PZA": {"mg": 500},
    "EMB 400mg": {"mg": 400},
    "EMB 500mg": {"mg": 500},
}


def calculate_regimen(weight: float) -> dict:
    """Return medication regimen with tablet counts.

    Format: {"drug_name (mg)": count, ...}
    """
    if weight < 35:
        return {
            "INH 100mg": 2,
            "Rifampicin 300mg": 2,
            "PZA 500mg": 1,
            "EMB 400mg": 1,
        }
    elif weight < 50:
        return {
            "INH 100mg": 3,
            "Rifampicin 300mg": 2,
            "PZA 500mg": 2,
            "EMB 400mg": 1,
        }
    elif weight < 70:
        return {
            "INH 100mg": 3,
            "Rifampicin 450mg": 3,
            "PZA 500mg": 2,
            "EMB 500mg": 2,
        }
    else:
        return {
            "INH 100mg": 4,
            "Rifampicin 450mg": 3,
            "PZA 500mg": 3,
            "EMB 500mg": 2,
        }


def make_patient_token(patient_id: int) -> str:
    """Generate a unique scan token for a patient."""
    raw = f"patient-{patient_id}-{app.secret_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_schedule(patient: Patient, days: int = 180,
                      regimen: dict = None) -> None:
    """Generate medication schedule. Uses custom regimen if provided."""
    MedicationDose.query.filter_by(patient_id=patient.id).delete()
    if regimen is None:
        regimen = calculate_regimen(patient.weight)
    for i in range(days):
        scheduled_date = patient.start_date + timedelta(days=i)
        dose = MedicationDose(
            patient_id=patient.id,
            date=scheduled_date,
            taken=False,
        )
        dose.medications = regimen
        db.session.add(dose)
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
    total_past = MedicationDose.query.filter(
        MedicationDose.patient_id == patient.id,
        MedicationDose.date <= today,
    ).count()
    taken = MedicationDose.query.filter(
        MedicationDose.patient_id == patient.id,
        MedicationDose.date <= today,
        MedicationDose.taken == True,
    ).count()
    overdue = MedicationDose.query.filter(
        MedicationDose.patient_id == patient.id,
        MedicationDose.date <= today,
        MedicationDose.taken == False,
    ).count()
    total_all = MedicationDose.query.filter_by(patient_id=patient.id).count()
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
                        custom[dname] = int(dcount)
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
def view_patient(id: int) -> str:
    patient = Patient.query.get_or_404(id)
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
def mark_dose(id: int, dose_id: int) -> str:
    Patient.query.get_or_404(id)
    dose = MedicationDose.query.filter_by(
        id=dose_id, patient_id=id
    ).first_or_404()
    if not dose.taken:
        dose.taken = True
        dose.taken_time = datetime.utcnow()
        db.session.commit()
        flash(f"บันทึกการกินยาวันที่ {dose.date.strftime('%Y-%m-%d')} เรียบร้อย", "success")
    else:
        flash("บันทึกการกินยาไปแล้ว", "info")
    return redirect(url_for("view_patient", id=id))


@app.route("/patient/<int:id>/delete", methods=["POST"])
def delete_patient(id: int) -> str:
    patient = Patient.query.get_or_404(id)
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
    patient = Patient.query.get_or_404(id)
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
                    new_meds[dname] = int(dcount)
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
    patient = Patient.query.get_or_404(id)

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
                            regimen[dname] = int(dcount)
                        except ValueError:
                            pass
                if not regimen:
                    regimen = current_meds
            else:
                regimen = current_meds

            start = last_date + timedelta(days=1)
            for i in range(extra_days):
                d = start + timedelta(days=i)
                dose = MedicationDose(
                    patient_id=patient.id, date=d, taken=False,
                )
                dose.medications = regimen
                db.session.add(dose)
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
                        regimen[dname] = int(dcount)
                    except ValueError:
                        pass
            if regimen:
                today = date.today()
                future_doses = MedicationDose.query.filter(
                    MedicationDose.patient_id == patient.id,
                    MedicationDose.date >= today,
                    MedicationDose.taken == False,
                ).all()
                for d in future_doses:
                    d.medications = regimen
                db.session.commit()
                flash(f"อัปเดตยาสำหรับ {len(future_doses)} วันที่เหลือ", "success")
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
# QR & Scan — 1 QR per patient
# ---------------------------------------------------------------------------

@app.route("/qr/patient/<int:patient_id>.png")
def qr_code_patient(patient_id: int):
    """Serve a single QR code image for a patient."""
    patient = Patient.query.get_or_404(patient_id)
    scan_url = url_for("scan_patient", token=patient.scan_token, _external=True)
    img_bytes = create_qr_code(scan_url)
    return send_file(
        BytesIO(img_bytes),
        mimetype="image/png",
        as_attachment=False,
        download_name=f"qr_patient_{patient.id}.png",
    )


@app.route("/qr_page/<int:patient_id>")
def qr_code_page(patient_id: int) -> str:
    """Show QR code page for a patient (single QR for all doses)."""
    patient = Patient.query.get_or_404(patient_id)
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
        today_dose.taken_time = datetime.utcnow()
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
        if username == STAFF_USERNAME and check_password_hash(STAFF_PASSWORD_HASH, password):
            session["staff_logged_in"] = True
            session["staff_user"] = username
            flash("เข้าสู่ระบบสำเร็จ", "success")
            next_url = request.args.get("next") or url_for("dashboard")
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
    return dict(format_date=format_date, format_datetime=format_datetime, date=date)


THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

@app.template_filter("thai_month")
def thai_month_filter(month_num):
    return THAI_MONTHS[month_num] if 1 <= month_num <= 12 else str(month_num)


if __name__ == "__main__":
    app.run(debug=True)
