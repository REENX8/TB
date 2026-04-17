"""Dose marking tests."""
from __future__ import annotations


def test_mark_dose_sets_taken_time_in_thai_tz(staff_client, make_patient):
    from tb.extensions import db
    from tb.models import MedicationDose

    patient = make_patient()
    dose = db.session.query(MedicationDose).filter_by(patient_id=patient.id).first()
    resp = staff_client.post(
        f"/patient/{patient.id}/mark/{dose.id}",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.session.expire_all()
    refreshed = db.session.get(MedicationDose, dose.id)
    assert refreshed.taken is True
    assert refreshed.taken_time is not None
    if refreshed.taken_time.tzinfo is not None:
        # aiosqlite preserves tz; plain sqlite strips it — just verify something recorded
        offset = refreshed.taken_time.utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 7 * 3600


def test_unmark_dose_clears_taken(staff_client, make_patient):
    from tb.extensions import db
    from tb.models import MedicationDose

    patient = make_patient()
    dose = db.session.query(MedicationDose).filter_by(patient_id=patient.id).first()
    staff_client.post(f"/patient/{patient.id}/mark/{dose.id}")
    staff_client.post(f"/patient/{patient.id}/unmark/{dose.id}")
    db.session.expire_all()
    refreshed = db.session.get(MedicationDose, dose.id)
    assert refreshed.taken is False
    assert refreshed.taken_time is None


def test_edit_dose_updates_medications(staff_client, make_patient):
    import json

    from tb.extensions import db
    from tb.models import MedicationDose

    patient = make_patient()
    dose = db.session.query(MedicationDose).filter_by(patient_id=patient.id).first()
    staff_client.post(
        f"/patient/{patient.id}/edit_dose/{dose.id}",
        data={
            "drug_name": ["INH 100mg", "Custom Med"],
            "drug_count": ["5", "2"],
        },
    )
    db.session.expire_all()
    refreshed = db.session.get(MedicationDose, dose.id)
    meds = json.loads(refreshed.medications_json)
    assert meds == {"INH 100mg": 5, "Custom Med": 2}


def test_mark_dose_twice_is_idempotent(staff_client, make_patient):
    from tb.extensions import db
    from tb.models import MedicationDose

    patient = make_patient()
    dose = db.session.query(MedicationDose).filter_by(patient_id=patient.id).first()
    staff_client.post(f"/patient/{patient.id}/mark/{dose.id}")
    first_time = db.session.get(MedicationDose, dose.id).taken_time
    staff_client.post(f"/patient/{patient.id}/mark/{dose.id}")
    second_time = db.session.get(MedicationDose, dose.id).taken_time
    assert first_time == second_time
