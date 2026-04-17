"""Adherence statistics."""
from __future__ import annotations

from datetime import date

from sqlalchemy import case as sa_case
from sqlalchemy import func

from tb.extensions import db
from tb.models import MedicationDose, Patient
from tb.time_utils import today_th


def get_adherence_stats(patient: Patient) -> dict:
    today = today_th()
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


def get_adherence_stats_bulk(patient_ids: list, today: date) -> dict:
    """Return adherence stats keyed by patient_id in a single query."""
    if not patient_ids:
        return {}
    rows = db.session.query(
        MedicationDose.patient_id,
        func.count(MedicationDose.id).label("total_all"),
        func.sum(sa_case((MedicationDose.date <= today, 1), else_=0)).label("total_past"),
        func.sum(sa_case(
            (db.and_(MedicationDose.date <= today, MedicationDose.taken == True), 1),
            else_=0,
        )).label("taken"),
    ).filter(MedicationDose.patient_id.in_(patient_ids)).group_by(MedicationDose.patient_id).all()

    result = {}
    for row in rows:
        total_past = row.total_past or 0
        taken = row.taken or 0
        pct = round(taken / total_past * 100, 1) if total_past > 0 else 0
        result[row.patient_id] = {
            "total_past": total_past,
            "taken": taken,
            "overdue": total_past - taken,
            "total_all": row.total_all or 0,
            "adherence_pct": pct,
        }
    empty = {"total_past": 0, "taken": 0, "overdue": 0, "total_all": 0, "adherence_pct": 0}
    for pid in patient_ids:
        result.setdefault(pid, dict(empty))
    return result
