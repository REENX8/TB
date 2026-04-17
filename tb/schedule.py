"""Schedule generation and calendar view building."""
from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, timedelta

from tb.extensions import db
from tb.models import MedicationDose, Patient
from tb.regimen import calculate_regimen
from tb.time_utils import today_th


def generate_schedule(patient: Patient, days: int = 180, regimen: dict | None = None) -> None:
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


def build_calendar(patient: Patient, year: int, month: int) -> list:
    first_of_month = date(year, month, 1)
    _, last_day = monthrange(year, month)

    doses_in_month = MedicationDose.query.filter(
        MedicationDose.patient_id == patient.id,
        MedicationDose.date >= first_of_month,
        MedicationDose.date <= date(year, month, last_day),
    ).all()
    doses_by_date = {dose.date: dose for dose in doses_in_month}

    today = today_th()
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
