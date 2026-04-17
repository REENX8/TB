"""QR scan endpoint tests."""
from __future__ import annotations


def test_scan_invalid_token_returns_404(client):
    resp = client.get("/scan/nonexistenttoken")
    assert resp.status_code == 404


def test_scan_token_valid_renders_page(client, make_patient, frozen_today):
    patient = make_patient(start_date=frozen_today, days=10)
    resp = client.get(f"/scan/{patient.scan_token}")
    assert resp.status_code == 200


def test_scan_post_marks_today_dose(client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import MedicationDose

    patient = make_patient(start_date=frozen_today, days=10)
    today_dose = db.session.query(MedicationDose).filter_by(
        patient_id=patient.id, date=frozen_today
    ).first()
    assert today_dose is not None
    assert today_dose.taken is False

    resp = client.post(f"/scan/{patient.scan_token}", follow_redirects=False)
    assert resp.status_code == 302
    db.session.expire_all()
    refreshed = db.session.get(MedicationDose, today_dose.id)
    assert refreshed.taken is True


def test_scan_rate_limit_30s_cooldown(client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import MedicationDose

    patient = make_patient(start_date=frozen_today, days=10)

    # First scan
    client.post(f"/scan/{patient.scan_token}")
    dose = db.session.query(MedicationDose).filter_by(
        patient_id=patient.id, date=frozen_today
    ).first()
    assert dose.taken is True
    first_time = dose.taken_time

    # Unmark manually and try again within cooldown → should NOT mark due to cooldown
    dose.taken = False
    dose.taken_time = None
    db.session.commit()
    client.post(f"/scan/{patient.scan_token}")
    db.session.expire_all()
    refreshed = db.session.get(MedicationDose, dose.id)
    assert refreshed.taken is False
    # Make sure 'first_time' referenced something real and cooldown guarded subsequent POST
    assert first_time is not None


def test_regenerate_token_invalidates_old_scan_url(staff_client, client, make_patient):
    from tb.extensions import db
    from tb.models import Patient

    patient = make_patient()
    old_token = patient.scan_token

    staff_client.post(f"/patient/{patient.id}/regenerate_token", follow_redirects=False)
    db.session.expire_all()
    refreshed = db.session.get(Patient, patient.id)
    assert refreshed.scan_token != old_token

    resp = client.get(f"/scan/{old_token}")
    assert resp.status_code == 404
