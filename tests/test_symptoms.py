"""Patient symptom reporting tests."""
from __future__ import annotations


def _report(client, patient, category="nausea", detail=""):
    return client.post(
        f"/scan/{patient.scan_token}/report",
        data={"category": category, "detail": detail},
        follow_redirects=False,
    )


def test_report_creates_record_with_auto_response(client, make_patient, frozen_today):
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    resp = _report(client, patient, category="nausea", detail="อาเจียนตอนเช้า")
    assert resp.status_code == 302

    report = SymptomReport.query.filter_by(patient_id=patient.id).first()
    assert report is not None
    assert report.category == "nausea"
    assert report.detail == "อาเจียนตอนเช้า"
    assert report.status == "new"
    assert report.auto_response
    assert "อาหาร" in report.auto_response


def test_severe_category_includes_urgent_warning(client, make_patient, frozen_today):
    from tb.constants import SYMPTOM_SEVERE_WARNING
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    _report(client, patient, category="jaundice")
    report = SymptomReport.query.filter_by(patient_id=patient.id).first()
    assert report.auto_response.startswith(SYMPTOM_SEVERE_WARNING)


def test_invalid_category_creates_nothing(client, make_patient, frozen_today):
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    resp = _report(client, patient, category="not_a_category")
    assert resp.status_code == 302
    assert SymptomReport.query.filter_by(patient_id=patient.id).count() == 0


def test_invalid_token_returns_404(client):
    resp = client.post(
        "/scan/nonexistenttoken/report", data={"category": "nausea"}
    )
    assert resp.status_code == 404


def test_detail_truncated_to_500_chars(client, make_patient, frozen_today):
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    _report(client, patient, category="other", detail="x" * 600)
    report = SymptomReport.query.filter_by(patient_id=patient.id).first()
    assert len(report.detail) == 500


def test_daily_report_cap(client, make_patient, frozen_today):
    from tb.models import SymptomReport
    from tb.scan.routes import MAX_SYMPTOM_REPORTS_PER_DAY

    patient = make_patient(start_date=frozen_today, days=10)
    for _ in range(MAX_SYMPTOM_REPORTS_PER_DAY + 2):
        _report(client, patient)
    assert (
        SymptomReport.query.filter_by(patient_id=patient.id).count()
        == MAX_SYMPTOM_REPORTS_PER_DAY
    )


def test_scan_page_shows_auto_response_and_reply(client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    _report(client, patient, category="numbness")
    report = SymptomReport.query.filter_by(patient_id=patient.id).first()
    report.pharmacist_reply = "เพิ่มวิตามิน B6 ให้ในนัดหน้า"
    report.replied_by = "pharm1"
    report.status = "replied"
    db.session.commit()

    resp = client.get(f"/scan/{patient.scan_token}")
    body = resp.data.decode()
    assert "ชาปลายมือปลายเท้า" in body
    assert "เพิ่มวิตามิน B6 ให้ในนัดหน้า" in body


def test_staff_list_requires_login(client):
    resp = client.get("/symptoms/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_staff_list_shows_reports(staff_client, client, make_patient, frozen_today):
    patient = make_patient(start_date=frozen_today, days=10)
    _report(client, patient, category="rash")
    resp = staff_client.get("/symptoms/")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "ผื่นคัน" in body
    assert patient.name in body


def test_nurse_cannot_reply(nurse_client, client, make_patient, frozen_today):
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    _report(client, patient)
    report = SymptomReport.query.filter_by(patient_id=patient.id).first()
    resp = nurse_client.post(
        f"/symptoms/{report.id}/reply", data={"reply": "no"}
    )
    assert resp.status_code == 403


def test_pharmacist_reply_sets_fields(pharmacist_client, client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    _report(client, patient)
    report = SymptomReport.query.filter_by(patient_id=patient.id).first()
    resp = pharmacist_client.post(
        f"/symptoms/{report.id}/reply",
        data={"reply": "กินยาพร้อมอาหารนะคะ"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.session.expire_all()
    refreshed = db.session.get(SymptomReport, report.id)
    assert refreshed.status == "replied"
    assert refreshed.pharmacist_reply == "กินยาพร้อมอาหารนะคะ"
    assert refreshed.replied_by == "pharm_user"
    assert refreshed.replied_at is not None


def test_resolve_sets_status(staff_client, client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    _report(client, patient)
    report = SymptomReport.query.filter_by(patient_id=patient.id).first()
    staff_client.post(f"/symptoms/{report.id}/resolve")
    db.session.expire_all()
    refreshed = db.session.get(SymptomReport, report.id)
    assert refreshed.status == "resolved"


def test_nav_badge_counts_new_reports(staff_client, client, make_patient, frozen_today):
    patient = make_patient(start_date=frozen_today, days=10)
    _report(client, patient)
    _report(client, patient, category="rash")
    resp = staff_client.get("/")
    assert b'<span class="badge bg-danger">2</span>' in resp.data


def test_symptom_report_is_audit_logged(client, make_patient, frozen_today):
    from tb.models import AuditLog

    patient = make_patient(start_date=frozen_today, days=10)
    _report(client, patient, category="jaundice")
    log = AuditLog.query.filter_by(action="SYMPTOM_REPORT").first()
    assert log is not None
    assert log.patient_id == patient.id
