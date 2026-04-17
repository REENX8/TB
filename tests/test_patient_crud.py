"""Patient CRUD and schedule generation tests."""
from __future__ import annotations

from datetime import date


def test_create_patient_generates_scan_token_and_doses(staff_client):
    from tb.extensions import db
    from tb.models import MedicationDose, Patient

    resp = staff_client.post(
        "/patient/new",
        data={
            "name": "สมหญิง ทดสอบ",
            "hn": "HN100",
            "age": "35",
            "tb_no": "TB100",
            "weight": "52",
            "tb_type": "PTB",
            "start_date": "2026-04-01",
            "days_of_medication": "180",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    patient = db.session.query(Patient).filter_by(hn="HN100").first()
    assert patient is not None
    assert patient.scan_token is not None
    assert len(patient.scan_token) > 30
    dose_count = db.session.query(MedicationDose).filter_by(patient_id=patient.id).count()
    assert dose_count == 180


def test_edit_patient_updates_and_writes_audit(staff_client, make_patient):
    from tb.extensions import db
    from tb.models import AuditLog, Patient

    patient = make_patient()
    resp = staff_client.post(
        f"/patient/{patient.id}/edit",
        data={
            "name": "Updated Name",
            "hn": patient.hn,
            "tb_no": patient.tb_no,
            "tb_type": patient.tb_type,
            "age": "50",
            "phone": "0812345678",
            "notes": "allergic",
            "outcome": "cured",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    updated = db.session.get(Patient, patient.id)
    assert updated.name == "Updated Name"
    assert updated.age == 50
    assert updated.outcome == "cured"
    log = db.session.query(AuditLog).filter_by(action="EDIT_PATIENT").first()
    assert log is not None
    assert log.patient_id == patient.id


def test_archive_then_restore_patient(staff_client, make_patient):
    from tb.extensions import db
    from tb.models import Patient

    patient = make_patient()
    staff_client.post(f"/patient/{patient.id}/archive", follow_redirects=False)
    assert db.session.get(Patient, patient.id).archived is True

    staff_client.post(f"/patient/{patient.id}/restore", follow_redirects=False)
    assert db.session.get(Patient, patient.id).archived is False


def test_delete_patient_removes_doses(staff_client, make_patient):
    from tb.extensions import db
    from tb.models import MedicationDose, Patient

    patient = make_patient()
    pid = patient.id
    staff_client.post(f"/patient/{pid}/delete", follow_redirects=False)
    assert db.session.get(Patient, pid) is None
    assert db.session.query(MedicationDose).filter_by(patient_id=pid).count() == 0


def test_update_weight_recomputes_future_meds(staff_client, make_patient):
    import json

    from tb.extensions import db
    from tb.models import MedicationDose

    patient = make_patient(weight=45.0, start_date=date(2026, 4, 1))
    staff_client.post(
        f"/patient/{patient.id}/update_weight",
        data={"weight": "72"},
        follow_redirects=False,
    )
    future_dose = db.session.query(MedicationDose).filter_by(patient_id=patient.id).order_by(
        MedicationDose.date.desc()
    ).first()
    meds = json.loads(future_dose.medications_json)
    assert meds.get("PZA 500mg") == 4
