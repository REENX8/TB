"""Audit log tests."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "action_name,trigger_url,method,data,needs_dose",
    [
        ("NEW_PATIENT", "/patient/new", "POST",
         {"name": "X", "hn": "H", "age": "30", "tb_no": "T", "weight": "55",
          "tb_type": "PTB", "start_date": "2026-04-01", "days_of_medication": "10"},
         False),
        ("ARCHIVE", "/patient/{pid}/archive", "POST", {}, False),
        ("RESTORE", "/patient/{pid}/restore", "POST", {}, False),
        ("REGEN_TOKEN", "/patient/{pid}/regenerate_token", "POST", {}, False),
        ("MARK_DOSE", "/patient/{pid}/mark/{did}", "POST", {}, True),
    ],
)
def test_audit_log_created_on_key_actions(
    staff_client, make_patient, action_name, trigger_url, method, data, needs_dose
):
    from tb.extensions import db
    from tb.models import AuditLog, MedicationDose

    patient = make_patient() if action_name != "NEW_PATIENT" else None
    url = trigger_url
    if patient:
        url = url.replace("{pid}", str(patient.id))
    if needs_dose:
        dose = db.session.query(MedicationDose).filter_by(patient_id=patient.id).first()
        url = url.replace("{did}", str(dose.id))

    if method == "POST":
        staff_client.post(url, data=data)
    else:
        staff_client.get(url)

    log = db.session.query(AuditLog).filter_by(action=action_name).first()
    assert log is not None, f"Expected audit log for {action_name}"


def test_audit_log_view_filters_by_action(staff_client, make_patient):
    patient = make_patient()
    staff_client.post(f"/patient/{patient.id}/archive")
    staff_client.post(f"/patient/{patient.id}/restore")

    resp = staff_client.get("/audit?action=ARCHIVE")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "ARCHIVE" in body
