"""Adherence calculation tests — verifies single and bulk versions agree."""
from __future__ import annotations

from datetime import date


def test_regimen_calculation_weight_bands():
    from tb.regimen import calculate_regimen

    assert calculate_regimen(32)["PZA 500mg"] == 1.5
    assert calculate_regimen(45)["Rifampicin 450mg"] == 1
    assert calculate_regimen(60)["PZA 500mg"] == 3
    assert calculate_regimen(75)["PZA 500mg"] == 4
    low = calculate_regimen(25)
    assert low["INH 100mg"] >= 1


def test_get_adherence_stats_matches_bulk_version(app, make_patient, frozen_today):
    from tb.adherence import get_adherence_stats, get_adherence_stats_bulk
    from tb.extensions import db
    from tb.models import MedicationDose

    p1 = make_patient(hn="P1", start_date=date(2026, 4, 1), days=20)
    p2 = make_patient(hn="P2", start_date=date(2026, 4, 1), days=20)

    doses = db.session.query(MedicationDose).filter_by(patient_id=p1.id).order_by(
        MedicationDose.date
    ).limit(3).all()
    for d in doses:
        d.taken = True
    db.session.commit()

    single_p1 = get_adherence_stats(p1)
    single_p2 = get_adherence_stats(p2)
    bulk = get_adherence_stats_bulk([p1.id, p2.id], frozen_today)

    assert single_p1 == bulk[p1.id]
    assert single_p2 == bulk[p2.id]
    assert bulk[p1.id]["taken"] == 3
    assert bulk[p2.id]["taken"] == 0


def test_bulk_stats_empty_input_returns_empty():
    from tb.adherence import get_adherence_stats_bulk

    assert get_adherence_stats_bulk([], date(2026, 4, 17)) == {}


def test_bulk_stats_missing_patient_returns_empty_row(app, make_patient, frozen_today):
    from tb.adherence import get_adherence_stats_bulk

    p = make_patient(hn="X", days=5)
    bulk = get_adherence_stats_bulk([p.id, 99999], frozen_today)
    assert bulk[99999] == {
        "total_past": 0,
        "taken": 0,
        "overdue": 0,
        "total_all": 0,
        "adherence_pct": 0,
    }
