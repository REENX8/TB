"""QR code generation and scan token helpers."""
from __future__ import annotations

import secrets
from io import BytesIO

import qrcode


def make_patient_token(patient_id: int | None = None) -> str:
    """Generate a cryptographically random scan token (URL-safe)."""
    return secrets.token_urlsafe(32)


def create_qr_code(data: str) -> bytes:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()
