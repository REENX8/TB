"""LINE webhook + symptom-alert integration tests."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

TEST_SECRET = "line-test-secret"
TEST_REGISTER_CODE = "JOIN-TB"


def _enable_line(app, *, token="", secret=TEST_SECRET, code=TEST_REGISTER_CODE):
    """Configure LINE on the app. Empty token keeps outbound calls no-op."""
    app.config["LINE_CHANNEL_SECRET"] = secret
    app.config["LINE_CHANNEL_ACCESS_TOKEN"] = token
    app.config["LINE_REGISTER_CODE"] = code


def _signed_post(client, payload, secret=TEST_SECRET):
    body = json.dumps(payload).encode("utf-8")
    sig = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    return client.post(
        "/line/webhook", data=body,
        headers={"X-Line-Signature": sig},
        content_type="application/json",
    )


def _text_event(text, user_id="U123", reply_token="rt"):
    return {
        "events": [{
            "type": "message",
            "replyToken": reply_token,
            "source": {"type": "user", "userId": user_id},
            "message": {"type": "text", "text": text},
        }]
    }


def test_verify_signature_roundtrip():
    from tb.line_service import verify_signature

    body = b'{"hello":"world"}'
    sig = base64.b64encode(
        hmac.new(TEST_SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()
    assert verify_signature(TEST_SECRET, body, sig) is True
    assert verify_signature(TEST_SECRET, body, "bad") is False
    assert verify_signature("", body, sig) is False


def test_webhook_404_when_not_configured(client):
    # TestConfig leaves LINE secret empty.
    resp = client.post("/line/webhook", data=b"{}")
    assert resp.status_code == 404


def test_webhook_rejects_bad_signature(app, client):
    _enable_line(app)
    resp = client.post(
        "/line/webhook", data=b"{}",
        headers={"X-Line-Signature": "wrong"},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_registration_creates_recipient(app, client):
    from tb.models import LineRecipient

    _enable_line(app)
    resp = _signed_post(client, _text_event(TEST_REGISTER_CODE))
    assert resp.status_code == 200
    rec = LineRecipient.query.filter_by(line_user_id="U123").first()
    assert rec is not None
    assert rec.is_active is True


def test_unregister_deactivates_recipient(app, client):
    from tb.extensions import db
    from tb.models import LineRecipient

    _enable_line(app)
    db.session.add(LineRecipient(line_user_id="U9", is_active=True))
    db.session.commit()
    _signed_post(client, _text_event("ยกเลิก", user_id="U9"))
    rec = LineRecipient.query.filter_by(line_user_id="U9").first()
    assert rec.is_active is False


def test_ticket_code_assigned_on_report(app, client, make_patient, frozen_today):
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    client.post(
        f"/scan/{patient.scan_token}/report", data={"category": "nausea"}
    )
    report = SymptomReport.query.filter_by(patient_id=patient.id).first()
    assert report.ticket_code == "A01"


def test_ticket_codes_are_unique_among_open(app, client, make_patient, frozen_today):
    from tb.models import SymptomReport

    p1 = make_patient(hn="L1", start_date=frozen_today, days=10)
    p2 = make_patient(hn="L2", start_date=frozen_today, days=10)
    client.post(f"/scan/{p1.scan_token}/report", data={"category": "nausea"})
    client.post(f"/scan/{p2.scan_token}/report", data={"category": "rash"})
    codes = {r.ticket_code for r in SymptomReport.query.all()}
    assert codes == {"A01", "A02"}


def test_line_reply_routes_to_report_and_shows_on_web(app, client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import LineRecipient, SymptomReport

    _enable_line(app)
    db.session.add(
        LineRecipient(line_user_id="Uph", display_name="ภก.สมหญิง", is_active=True)
    )
    db.session.commit()

    patient = make_patient(start_date=frozen_today, days=10)
    client.post(
        f"/scan/{patient.scan_token}/report", data={"category": "nausea"}
    )
    report = SymptomReport.query.filter_by(patient_id=patient.id).first()
    code = report.ticket_code

    resp = _signed_post(
        client,
        _text_event(f"{code}+กินยาพร้อมอาหารนะคะ", user_id="Uph"),
    )
    assert resp.status_code == 200

    db.session.expire_all()
    refreshed = db.session.get(SymptomReport, report.id)
    assert refreshed.status == "replied"
    assert refreshed.pharmacist_reply == "กินยาพร้อมอาหารนะคะ"
    assert "LINE" in refreshed.replied_by

    # Patient sees the reply on the scan page (without the ticket code).
    page = client.get(f"/scan/{patient.scan_token}").data.decode()
    assert "กินยาพร้อมอาหารนะคะ" in page
    assert code not in page


def test_line_reply_requires_registration(app, client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import SymptomReport

    _enable_line(app)
    patient = make_patient(start_date=frozen_today, days=10)
    client.post(
        f"/scan/{patient.scan_token}/report", data={"category": "nausea"}
    )
    report = SymptomReport.query.filter_by(patient_id=patient.id).first()

    # Unregistered LINE user cannot answer.
    _signed_post(client, _text_event(f"{report.ticket_code}+hi", user_id="stranger"))
    db.session.expire_all()
    assert db.session.get(SymptomReport, report.id).status == "new"


def test_line_reply_unknown_code_does_nothing(app, client):
    from tb.extensions import db
    from tb.models import LineRecipient

    _enable_line(app)
    db.session.add(LineRecipient(line_user_id="Uph", is_active=True))
    db.session.commit()
    resp = _signed_post(client, _text_event("Z99+ตอบ", user_id="Uph"))
    assert resp.status_code == 200  # handled gracefully


def test_ticket_code_recycled_after_resolve(app, client, make_patient, frozen_today):
    from tb.extensions import db
    from tb.models import SymptomReport

    patient = make_patient(start_date=frozen_today, days=10)
    client.post(f"/scan/{patient.scan_token}/report", data={"category": "nausea"})
    first = SymptomReport.query.filter_by(patient_id=patient.id).first()
    assert first.ticket_code == "A01"
    first.status = "resolved"
    db.session.commit()

    client.post(f"/scan/{patient.scan_token}/report", data={"category": "rash"})
    second = (
        SymptomReport.query.filter_by(patient_id=patient.id)
        .order_by(SymptomReport.id.desc()).first()
    )
    # A01 is free again now that the first report is resolved.
    assert second.ticket_code == "A01"
