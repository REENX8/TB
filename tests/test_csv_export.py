"""CSV export tests."""
from __future__ import annotations


def test_export_csv_has_utf8_bom_and_expected_rows(staff_client, make_patient):
    patient = make_patient(days=10)
    resp = staff_client.get(f"/patient/{patient.id}/export_csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    body = resp.data
    assert body.startswith(b"\xef\xbb\xbf"), "CSV must include UTF-8 BOM for Excel"
    # Header row + 10 data rows
    lines = body.decode("utf-8-sig").strip().splitlines()
    assert len(lines) == 11
    assert "วันที่" in lines[0]


def test_report_export_lists_all_active_patients(staff_client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import MedicationDose

    p1 = make_patient(hn="R1", days=30, start_date=frozen_today.replace(day=1))
    make_patient(hn="R2", days=30, start_date=frozen_today.replace(day=1))
    # Mark 5 doses for p1
    for d in db.session.query(MedicationDose).filter_by(patient_id=p1.id).limit(5):
        d.taken = True
    db.session.commit()

    resp = staff_client.get(f"/report/export?year={frozen_today.year}&month={frozen_today.month}")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8-sig")
    assert "R1" in body and "R2" in body
