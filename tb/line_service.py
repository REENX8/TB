"""LINE Messaging API integration for symptom-report alerts.

Outbound: push a notification to every registered pharmacist when a
patient reports an adverse symptom. Inbound replies are handled by the
webhook blueprint (tb/line_bp). Uses only the standard library so no
extra dependency is required.

All network calls are best-effort: failures are logged, never raised,
so they can never break a patient's report submission.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import string
import urllib.request

from flask import current_app

from tb.constants import SYMPTOM_CATEGORIES
from tb.extensions import db
from tb.models import LineRecipient, SymptomReport

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/multicast"
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PROFILE_URL = "https://api.line.me/v2/bot/profile/"
_MAX_TEXT = 4900  # LINE hard limit is 5000 chars per text message


def access_token() -> str:
    return current_app.config.get("LINE_CHANNEL_ACCESS_TOKEN", "") or ""


def channel_secret() -> str:
    return current_app.config.get("LINE_CHANNEL_SECRET", "") or ""


def register_code() -> str:
    return current_app.config.get("LINE_REGISTER_CODE", "") or ""


def line_enabled() -> bool:
    """True when both the push token and the webhook secret are configured."""
    return bool(access_token() and channel_secret())


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Validate the X-Line-Signature header (HMAC-SHA256, base64)."""
    if not secret or not signature:
        return False
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("ascii")
    return hmac.compare_digest(expected, signature)


def _post(url: str, payload: dict) -> int | None:
    token = access_token()
    if not token:
        return None
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except Exception:
        logger.exception("LINE API call failed: %s", url)
        return None


def push_text(user_ids, text: str) -> None:
    """Multicast a text message to the given LINE user ids."""
    user_ids = list(user_ids)
    if not user_ids:
        return
    _post(LINE_PUSH_URL, {
        "to": user_ids,
        "messages": [{"type": "text", "text": text[:_MAX_TEXT]}],
    })


def reply_text(reply_token: str, text: str) -> None:
    """Reply to a webhook event using its reply token."""
    if not reply_token:
        return
    _post(LINE_REPLY_URL, {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:_MAX_TEXT]}],
    })


def fetch_display_name(user_id: str) -> str | None:
    token = access_token()
    if not token or not user_id:
        return None
    req = urllib.request.Request(
        LINE_PROFILE_URL + user_id,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8")).get("displayName")
    except Exception:
        logger.exception("LINE profile fetch failed")
        return None


def _all_codes():
    for letter in string.ascii_uppercase:
        for n in range(1, 100):
            yield f"{letter}{n:02d}"


def allocate_ticket_code() -> str:
    """Pick the first short code not held by an unresolved report.

    A code is reserved until its report is resolved, guaranteeing it
    routes a reply to exactly one open report at a time.
    """
    used = {
        r.ticket_code
        for r in SymptomReport.query.filter(
            SymptomReport.status != "resolved",
            SymptomReport.ticket_code.isnot(None),
        ).all()
    }
    for code in _all_codes():
        if code not in used:
            return code
    # Pathological fallback (>2600 simultaneous open reports).
    return f"Z{SymptomReport.query.count() % 100:02d}"


def notify_new_symptom(report: SymptomReport) -> None:
    """Push a new-symptom alert to all active pharmacists (best effort)."""
    if not access_token():
        return
    recipients = [
        r.line_user_id
        for r in LineRecipient.query.filter_by(is_active=True).all()
    ]
    if not recipients:
        return
    info = SYMPTOM_CATEGORIES.get(report.category)
    label = info["label"] if info else report.category
    severe = " ⚠️(รุนแรง)" if info and info["severe"] else ""
    lines = [
        "🔔 มีการแจ้งอาการใหม่จากผู้ป่วย",
        f"ชื่อ: {report.patient.name}",
        f"เลขคนไข้ (HN): {report.patient.hn}",
        f"อาการที่พบ: {label}{severe}",
    ]
    if report.detail:
        lines.append(f"รายละเอียด: {report.detail}")
    lines.append("")
    lines.append(f"เลขรับคำตอบ: {report.ticket_code}")
    lines.append(f"ตอบกลับโดยพิมพ์: {report.ticket_code}+ข้อความถึงผู้ป่วย")
    try:
        push_text(recipients, "\n".join(lines))
    except Exception:
        logger.exception("notify_new_symptom push failed")


def register_recipient(user_id: str) -> LineRecipient:
    """Register (or reactivate) a pharmacist's LINE account."""
    name = fetch_display_name(user_id)
    rec = LineRecipient.query.filter_by(line_user_id=user_id).first()
    if rec:
        rec.is_active = True
        if name:
            rec.display_name = name
    else:
        rec = LineRecipient(
            line_user_id=user_id, display_name=name, is_active=True,
        )
        db.session.add(rec)
    db.session.commit()
    return rec
