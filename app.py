"""
app.py
------

Flask web application for tracking tuberculosis (TB) medication adherence.

Features:
- Register patients and auto-generate medication schedules based on weight
- Record when doses are taken (button or QR scan)
- Calendar view with weekday alignment and month navigation
- Staff dashboard with adherence statistics across all patients
- Today's dose quick-confirm view
- Overdue dose indicators
- QR codes for individual doses

Dependencies:
    pip install flask flask_sqlalchemy qrcode pillow

Run:
    python app.py
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
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///tb.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret")
db = SQLAlchemy(app)

# Staff credentials — password stored as hash (never plaintext)
STAFF_USERNAME = os.environ.get("STAFF_USER", "REEN")
STAFF_PASSWORD_HASH = os.environ.get(
    "STAFF_PASS_HASH",
    "scrypt:32768:8:1$lYS9DAFUtGkNDbY5$10b7a5f05d5244417e8bb34c6848b6a016b9ae0cad769814db43d87d310b57b5910fabbb719c43d15e4b615791284c01d165bb0d74b38abd5db0468165a7c91d",
)


def staff_required(f):
    """Decorator to require staff login."""
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
    scan_token = db.Column(db.String(64), unique=True, nullable=True)

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
# Medication calculation and schedule generation
# ---------------------------------------------------------------------------

def calculate_regimen(weight: float) -> dict:
    """Return a medication regimen based on the patient's weight."""
    if weight < 35:
        return {"INH": 2, "Rifampicin": 2, "PZA": 1, "EMB": 1}
    elif weight < 50:
        return {"INH": 3, "Rifampicin": 2, "PZA": 2, "EMB": 1}
    elif weight < 70:
        return {"INH": 3, "Rifampicin": 3, "PZA": 2, "EMB": 2}
    else:
        return {"INH": 4, "Rifampicin": 3, "PZA": 3, "EMB": 2}


def make_scan_token(patient_id: int, dose_date: date) -> str:
    """Generate a unique token for a dose based on patient ID and date."""
    raw = f"{patient_id}-{dose_date.isoformat()}-{app.secret_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_schedule(patient: Patient, days: int = 180) -> None:
    """Generate a medication schedule for a patient."""
    MedicationDose.query.filter_by(patient_id=patient.id).delete()
    regimen = calculate_regimen(patient.weight)
    for i in range(days):
        scheduled_date = patient.start_date + timedelta(days=i)
        dose = MedicationDose(
            patient_id=patient.id,
            date=scheduled_date,
            taken=False,
            scan_token=make_scan_token(patient.id, scheduled_date),
        )
        dose.medications = regimen
        db.session.add(dose)
    db.session.commit()


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def build_calendar(patient: Patient, year: int, month: int) -> list:
    """Build a calendar grid aligned to weekdays (Mon=0).

    Returns a list of dicts: {date, status, day_of_month}.
    Leading None entries pad the grid so day 1 falls on the correct weekday.
    """
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

    # Pad leading empty cells (Monday=0 ... Sunday=6)
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
    """Generate a QR code PNG image."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


def get_adherence_stats(patient: Patient) -> dict:
    """Calculate adherence statistics for a patient."""
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
    """Home page: list all patients with basic adherence info."""
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
    """Create a new patient via form submission."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        hn = request.form.get("hn", "").strip()
        age = request.form.get("age", "0").strip()
        tb_no = request.form.get("tb_no", "").strip()
        weight = request.form.get("weight", "0").strip()
        tb_type = request.form.get("tb_type", "").strip()
        start_date_str = request.form.get("start_date", "").strip()
        days_str = request.form.get("days_of_medication", "180").strip()

        if not all([name, hn, age, tb_no, weight, tb_type, start_date_str]):
            flash("กรุณากรอกข้อมูลให้ครบทุกช่อง", "danger")
            return render_template("create_patient.html")
        try:
            start_date_obj = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("รูปแบบวันที่ไม่ถูกต้อง ใช้ YYYY-MM-DD", "danger")
            return render_template("create_patient.html")
        try:
            age_val = int(age)
            weight_val = float(weight)
            days_of_medication = int(days_str)
        except ValueError:
            flash("ค่าตัวเลขไม่ถูกต้อง (อายุ, น้ำหนัก, หรือจำนวนวัน)", "danger")
            return render_template("create_patient.html")

        patient = Patient(
            name=name,
            hn=hn,
            age=age_val,
            tb_no=tb_no,
            weight=weight_val,
            tb_type=tb_type,
            start_date=start_date_obj,
        )
        db.session.add(patient)
        db.session.commit()
        generate_schedule(patient, days_of_medication)
        flash("เพิ่มผู้ป่วยสำเร็จ", "success")
        return redirect(url_for("view_patient", id=patient.id))
    return render_template("create_patient.html")


@app.route("/patient/<int:id>")
def view_patient(id: int) -> str:
    """Display details, schedule, and calendar for a patient."""
    patient = Patient.query.get_or_404(id)
    today = date.today()

    # Calendar month
    try:
        cal_year = int(request.args.get("year", today.year))
        cal_month = int(request.args.get("month", today.month))
    except ValueError:
        cal_year, cal_month = today.year, today.month

    calendar = build_calendar(patient, cal_year, cal_month)

    # Previous / next month for navigation
    if cal_month == 1:
        prev_year, prev_month = cal_year - 1, 12
    else:
        prev_year, prev_month = cal_year, cal_month - 1
    if cal_month == 12:
        next_year, next_month = cal_year + 1, 1
    else:
        next_year, next_month = cal_year, cal_month + 1

    # Date range filter for doses
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

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = 30
    pagination = query.order_by(MedicationDose.date).paginate(
        page=page, per_page=per_page, error_out=False
    )
    doses = pagination.items

    # Today's dose
    today_dose = MedicationDose.query.filter_by(
        patient_id=patient.id, date=today
    ).first()

    stats = get_adherence_stats(patient)

    return render_template(
        "patient.html",
        patient=patient,
        doses=doses,
        pagination=pagination,
        calendar=calendar,
        calendar_year=cal_year,
        calendar_month=cal_month,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        today_dose=today_dose,
        today=today,
        stats=stats,
        filter_start=filter_start or "",
        filter_end=filter_end or "",
    )


@app.route("/patient/<int:id>/mark/<int:dose_id>", methods=["POST"])
def mark_dose(id: int, dose_id: int) -> str:
    """Mark a scheduled dose as taken (POST only)."""
    patient = Patient.query.get_or_404(id)
    dose = MedicationDose.query.filter_by(
        id=dose_id, patient_id=id
    ).first_or_404()
    if not dose.taken:
        dose.taken = True
        dose.taken_time = datetime.utcnow()
        db.session.commit()
        flash(
            f"บันทึกการกินยาวันที่ {dose.date.strftime('%Y-%m-%d')} เรียบร้อย",
            "success",
        )
    else:
        flash("บันทึกการกินยาไปแล้ว", "info")
    return redirect(url_for("view_patient", id=id))


@app.route("/patient/<int:id>/delete", methods=["POST"])
def delete_patient(id: int) -> str:
    """Delete a patient and all their doses."""
    patient = Patient.query.get_or_404(id)
    db.session.delete(patient)
    db.session.commit()
    flash(f"ลบผู้ป่วย {patient.name} เรียบร้อย", "success")
    return redirect(url_for("index"))


@app.route("/login", methods=["GET", "POST"])
def staff_login() -> str:
    """Staff login page."""
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
    """Staff logout."""
    session.pop("staff_logged_in", None)
    session.pop("staff_user", None)
    flash("ออกจากระบบเรียบร้อย", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@staff_required
def dashboard() -> str:
    """Staff dashboard showing adherence across all patients."""
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
        "dashboard.html",
        rows=rows,
        today=today,
        total_patients=len(patients),
        total_overdue=total_overdue_all,
    )


@app.route("/qr/<int:dose_id>.png")
def qr_code(dose_id: int):
    """Serve a QR code image encoding the scan URL for this dose."""
    dose = MedicationDose.query.get_or_404(dose_id)
    scan_url = url_for("scan_dose", token=dose.scan_token, _external=True)
    img_bytes = create_qr_code(scan_url)
    return send_file(
        BytesIO(img_bytes),
        mimetype="image/png",
        as_attachment=False,
        download_name=f"qr_{dose.id}.png",
    )


@app.route("/qr_page/<int:dose_id>")
def qr_code_page(dose_id: int) -> str:
    """Render a page showing the QR code for a dose."""
    dose = MedicationDose.query.get_or_404(dose_id)
    return render_template("qr.html", dose=dose)


@app.route("/scan/<token>", methods=["GET", "POST"])
def scan_dose(token: str) -> str:
    """Mobile-friendly page opened when patient scans QR code.

    GET  — show dose details and a confirm button.
    POST — mark the dose as taken and show success.
    """
    dose = MedicationDose.query.filter_by(scan_token=token).first_or_404()
    patient = Patient.query.get_or_404(dose.patient_id)

    if request.method == "POST" and not dose.taken:
        dose.taken = True
        dose.taken_time = datetime.utcnow()
        db.session.commit()

    return render_template("scan.html", dose=dose, patient=patient)


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

@app.context_processor
def inject_helpers():
    def format_date(dt: date) -> str:
        return dt.strftime("%Y-%m-%d") if dt else ""

    def format_datetime(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""

    return dict(
        format_date=format_date,
        format_datetime=format_datetime,
        date=date,
    )


THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

@app.template_filter("thai_month")
def thai_month_filter(month_num):
    return THAI_MONTHS[month_num] if 1 <= month_num <= 12 else str(month_num)


if __name__ == "__main__":
    app.run(debug=True)
