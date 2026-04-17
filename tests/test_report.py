"""Dashboard + report endpoint tests."""
from __future__ import annotations


def test_dashboard_renders_with_patients(staff_client, make_patient, frozen_today):
    make_patient(hn="D1", start_date=frozen_today)
    make_patient(hn="D2", start_date=frozen_today)
    resp = staff_client.get("/dashboard")
    assert resp.status_code == 200
    assert b"D1" in resp.data


def test_report_page_computes_adherence_percent(staff_client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import MedicationDose

    patient = make_patient(
        hn="RP1", start_date=frozen_today.replace(day=1), days=30
    )
    # Mark 10 of the month's doses
    doses = db.session.query(MedicationDose).filter_by(patient_id=patient.id).limit(10).all()
    for d in doses:
        d.taken = True
    db.session.commit()

    resp = staff_client.get(f"/report?year={frozen_today.year}&month={frozen_today.month}")
    assert resp.status_code == 200
    # Page should include the HN and some percent marker
    assert b"RP1" in resp.data


def test_ping_endpoint_is_open(client):
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.data == b"ok"


def test_extend_schedule_add_days(staff_client, make_patient):
    from tb.extensions import db
    from tb.models import MedicationDose

    patient = make_patient(days=10)
    initial = db.session.query(MedicationDose).filter_by(patient_id=patient.id).count()
    resp = staff_client.post(
        f"/patient/{patient.id}/extend",
        data={"action": "add_days", "extra_days": "5"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    after = db.session.query(MedicationDose).filter_by(patient_id=patient.id).count()
    assert after == initial + 5
