"""LINE webhook: pharmacist registration and ticketed replies."""
from __future__ import annotations

import json
import re
from datetime import datetime

from flask import Blueprint, abort, current_app, request

from tb.audit import log_audit
from tb.extensions import csrf, db
from tb.line_service import (
    channel_secret,
    register_code,
    register_recipient,
    reply_text,
    verify_signature,
)
from tb.models import LineRecipient, SymptomReport
from tb.time_utils import TZ_THAI

bp = Blueprint("line_bp", __name__, url_prefix="/line")

# Ticket code (A01) optionally followed by '+' / space, then the reply text.
_REPLY_RE = re.compile(r"^([A-Za-z]\d{2})\s*\+?\s*(.*)$", re.DOTALL)
_UNREGISTER_WORDS = {"ยกเลิกการลงทะเบียน", "ยกเลิก", "unregister", "stop"}


@bp.route("/webhook", methods=["POST"])
@csrf.exempt
def webhook():
    secret = channel_secret()
    if not secret:
        # LINE integration not configured for this deployment.
        abort(404)
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_signature(secret, body, signature):
        abort(400)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        abort(400)
    for event in payload.get("events", []):
        try:
            _handle_event(event)
        except Exception:
            current_app.logger.exception("LINE event handling failed")
    return "OK", 200


def _handle_event(event: dict) -> None:
    if event.get("type") != "message":
        return
    message = event.get("message", {})
    if message.get("type") != "text":
        return
    text = (message.get("text") or "").strip()
    user_id = (event.get("source") or {}).get("userId")
    reply_token = event.get("replyToken")
    if not user_id:
        return

    code = register_code()
    if code and text == code:
        _register(user_id, reply_token)
        return
    if text in _UNREGISTER_WORDS:
        _unregister(user_id, reply_token)
        return

    match = _REPLY_RE.match(text)
    if match:
        _handle_reply(user_id, reply_token, match.group(1).upper(), match.group(2).strip())
        return

    reply_text(
        reply_token,
        "พิมพ์ \"เลขรับคำตอบ+ข้อความ\" เพื่อตอบผู้ป่วย เช่น A01+กินยาพร้อมอาหารนะคะ",
    )


def _register(user_id: str, reply_token: str) -> None:
    rec = register_recipient(user_id)
    log_audit("LINE_REGISTER", detail=rec.display_name or user_id)
    reply_text(
        reply_token,
        "ลงทะเบียนรับแจ้งอาการสำเร็จ ✅\n"
        "ระบบจะส่งการแจ้งอาการของผู้ป่วยมาที่นี่ "
        "ตอบกลับด้วย \"เลขรับคำตอบ+ข้อความ\"",
    )


def _unregister(user_id: str, reply_token: str) -> None:
    rec = LineRecipient.query.filter_by(line_user_id=user_id).first()
    if rec and rec.is_active:
        rec.is_active = False
        db.session.commit()
        log_audit("LINE_UNREGISTER", detail=rec.display_name or user_id)
    reply_text(reply_token, "ยกเลิกการลงทะเบียนแล้ว จะไม่ได้รับการแจ้งอาการอีก")


def _handle_reply(user_id: str, reply_token: str, code: str, answer: str) -> None:
    rec = LineRecipient.query.filter_by(line_user_id=user_id, is_active=True).first()
    if rec is None:
        reply_text(
            reply_token,
            "คุณยังไม่ได้ลงทะเบียน กรุณาพิมพ์รหัสลงทะเบียนก่อนจึงจะตอบได้",
        )
        return
    if not answer:
        reply_text(reply_token, f"กรุณาพิมพ์ข้อความหลังรหัส เช่น {code}+ข้อความถึงผู้ป่วย")
        return
    report = (
        SymptomReport.query
        .filter(
            SymptomReport.ticket_code == code,
            SymptomReport.status != "resolved",
        )
        .order_by(SymptomReport.reported_at.desc())
        .first()
    )
    if report is None:
        reply_text(reply_token, f"ไม่พบเลขรับคำตอบ {code} ที่กำลังรอตอบอยู่")
        return
    report.pharmacist_reply = answer
    report.replied_by = f"{rec.display_name or 'เภสัชกร'} (LINE)"
    report.replied_at = datetime.now(TZ_THAI).replace(tzinfo=None)
    report.status = "replied"
    db.session.commit()
    log_audit("REPLY_SYMPTOM", patient=report.patient, detail=f"LINE {code}")
    reply_text(
        reply_token,
        f"บันทึกคำตอบเลข {code} เรียบร้อย ✅ ระบบส่งให้ผู้ป่วยในเว็บแล้ว",
    )
