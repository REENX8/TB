"""Database models."""
from __future__ import annotations

import json
from datetime import datetime

from tb.extensions import db
from tb.time_utils import TZ_THAI


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
    archived = db.Column(db.Boolean, default=False, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    outcome = db.Column(db.String(30), nullable=True, default="")
    doses = db.relationship(
        "MedicationDose", backref="patient", cascade="all, delete-orphan"
    )
    symptom_reports = db.relationship(
        "SymptomReport", backref="patient", cascade="all, delete-orphan"
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

    __table_args__ = (
        db.Index("ix_dose_patient_date", "patient_id", "date"),
        db.Index("ix_dose_patient_taken", "patient_id", "taken"),
    )

    def __repr__(self) -> str:
        return f"<Dose {self.id} {self.date} taken={self.taken}>"


class SymptomReport(db.Model):
    __tablename__ = "symptom_reports"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer, db.ForeignKey("patients.id"), nullable=False
    )
    reported_at = db.Column(
        db.DateTime, nullable=False,
        default=lambda: datetime.now(TZ_THAI).replace(tzinfo=None),
    )
    category = db.Column(db.String(40), nullable=False)
    detail = db.Column(db.Text, nullable=True)
    auto_response = db.Column(db.Text, nullable=True)
    # Short human-typeable code (e.g. A01) used to route LINE replies back
    # to this report. Held until the report is resolved, then recyclable.
    ticket_code = db.Column(db.String(8), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="new")
    pharmacist_reply = db.Column(db.Text, nullable=True)
    replied_by = db.Column(db.String(60), nullable=True)
    replied_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index("ix_symptom_patient_reported", "patient_id", "reported_at"),
        db.Index("ix_symptom_status", "status"),
        db.Index("ix_symptom_ticket", "ticket_code"),
    )

    def __repr__(self) -> str:
        return f"<SymptomReport {self.id} {self.category} ({self.status})>"


class LineRecipient(db.Model):
    """A pharmacist's LINE account registered to receive symptom alerts."""
    __tablename__ = "line_recipients"
    id = db.Column(db.Integer, primary_key=True)
    line_user_id = db.Column(db.String(64), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    registered_at = db.Column(
        db.DateTime, nullable=False,
        default=lambda: datetime.now(TZ_THAI).replace(tzinfo=None),
    )

    def __repr__(self) -> str:
        return f"<LineRecipient {self.id} {self.display_name or self.line_user_id}>"


class StaffAccount(db.Model):
    __tablename__ = "staff_accounts"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="nurse")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, nullable=False,
        default=lambda: datetime.now(TZ_THAI).replace(tzinfo=None),
    )
    last_login = db.Column(db.DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<StaffAccount {self.id} {self.username} ({self.role})>"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(
        db.DateTime, nullable=False,
        default=lambda: datetime.now(TZ_THAI).replace(tzinfo=None), index=True,
    )
    staff_user = db.Column(db.String(60), nullable=False)
    action = db.Column(db.String(60), nullable=False)
    patient_id = db.Column(
        db.Integer, db.ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
    )
    patient_name = db.Column(db.String(120), nullable=True)
    detail = db.Column(db.Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog {self.id} {self.action}>"
