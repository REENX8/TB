"""Adherence statistics."""
from __future__ import annotations

from calendar import monthrange as cal_monthrange
from collections import defaultdict
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
    ).filter(
        MedicationDose.patient_id == patient.id,
        MedicationDose.medications_json != '{}',
    ).one()
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
    ).filter(
        MedicationDose.patient_id.in_(patient_ids),
        MedicationDose.medications_json != '{}',
    ).group_by(MedicationDose.patient_id).all()

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


def get_at_risk_patients(patients: list, stats_map: dict, today: date) -> list[dict]:
    """Return patients at risk: adherence <70% (with past doses) OR 2+ consecutive missed doses."""
    candidate_ids = [p.id for p in patients if stats_map[p.id]["overdue"] >= 1]
    if not candidate_ids:
        return []

    dose_rows = (
        MedicationDose.query
        .filter(
            MedicationDose.patient_id.in_(candidate_ids),
            MedicationDose.date <= today,
            MedicationDose.medications_json != '{}',
        )
        .order_by(MedicationDose.patient_id, MedicationDose.date.desc())
        .with_entities(MedicationDose.patient_id, MedicationDose.date, MedicationDose.taken)
        .all()
    )

    doses_by_pid: dict = {}
    for row in dose_rows:
        doses_by_pid.setdefault(row.patient_id, []).append(row)

    patient_map = {p.id: p for p in patients}
    result = []
    for pid in candidate_ids:
        stats = stats_map[pid]
        if stats["total_past"] == 0:
            continue
        doses = doses_by_pid.get(pid, [])

        consecutive_missed = 0
        for dose in doses:
            if not dose.taken:
                consecutive_missed += 1
            else:
                break

        last_taken_date = next((d.date for d in doses if d.taken), None)

        if stats["adherence_pct"] < 70 or consecutive_missed >= 2:
            result.append({
                "patient": patient_map[pid],
                "adherence_pct": stats["adherence_pct"],
                "consecutive_missed": consecutive_missed,
                "last_taken_date": last_taken_date,
            })

    result.sort(key=lambda x: (-x["consecutive_missed"], x["adherence_pct"]))
    return result


def get_tb_type_stats(patients: list, stats_map: dict) -> list[dict]:
    """Group patients by TB type with counts and average adherence."""
    groups: dict = defaultdict(list)
    for p in patients:
        groups[p.tb_type].append(stats_map[p.id]["adherence_pct"])
    result = []
    for tb_type, pcts in groups.items():
        avg_pct = round(sum(pcts) / len(pcts), 1) if pcts else 0
        result.append({"tb_type": tb_type, "count": len(pcts), "avg_pct": avg_pct})
    result.sort(key=lambda x: -x["count"])
    return result


def get_monthly_adherence_trend(patient_ids: list, num_months: int = 6) -> list[dict]:
    """Return average adherence % per month for the last num_months months."""
    if not patient_ids:
        return []

    today = today_th()
    months = []
    for delta in range(num_months - 1, -1, -1):
        total = today.year * 12 + (today.month - 1) - delta
        months.append((total // 12, total % 12 + 1))

    first_date = date(months[0][0], months[0][1], 1)
    last_y, last_m = months[-1]
    _, last_day = cal_monthrange(last_y, last_m)
    last_date = date(last_y, last_m, last_day)

    rows = (
        MedicationDose.query
        .filter(
            MedicationDose.patient_id.in_(patient_ids),
            MedicationDose.date >= first_date,
            MedicationDose.date <= last_date,
        )
        .with_entities(MedicationDose.date, MedicationDose.taken)
        .all()
    )

    month_data: dict = defaultdict(lambda: {"total": 0, "taken": 0})
    for row in rows:
        key = (row.date.year, row.date.month)
        month_data[key]["total"] += 1
        if row.taken:
            month_data[key]["taken"] += 1

    from tb.constants import THAI_MONTHS
    result = []
    for y, m in months:
        d = month_data.get((y, m))
        avg_pct = round(d["taken"] / d["total"] * 100, 1) if d and d["total"] else None
        result.append({"year": y, "month": m, "label": f"{THAI_MONTHS[m]} {y}", "avg_pct": avg_pct})
    return result
