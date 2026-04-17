"""Shared pytest fixtures."""
from __future__ import annotations

import os
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpass"


@pytest.fixture(scope="session", autouse=True)
def _staff_env():
    """Seed staff credentials before the app is imported."""
    os.environ["STAFF_USER"] = TEST_USERNAME
    os.environ["STAFF_PASS_HASH"] = generate_password_hash(TEST_PASSWORD)
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["TB_CONFIG"] = "tb.config.TestConfig"
    yield


@pytest.fixture()
def app(_staff_env):
    from tb import create_app
    from tb.extensions import db
    from tb.security import reset_login_state

    app = create_app("tb.config.TestConfig")
    with app.app_context():
        db.create_all()
        reset_login_state()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def staff_client(app, client):
    """Client pre-authenticated as staff via direct session write."""
    with client.session_transaction() as sess:
        sess["staff_logged_in"] = True
        sess["staff_user"] = TEST_USERNAME
    return client


@pytest.fixture()
def frozen_today(monkeypatch):
    """Freeze today_th() to 2026-04-17 for deterministic adherence tests."""
    fixed = date(2026, 4, 17)

    def _today():
        return fixed

    # Patch every module that imported today_th at import time.
    for mod in (
        "tb.time_utils",
        "tb.adherence",
        "tb.schedule",
        "tb.patient.routes",
        "tb.scan.routes",
        "tb.report.routes",
    ):
        monkeypatch.setattr(f"{mod}.today_th", _today, raising=False)
    return fixed


@pytest.fixture()
def make_patient(app):
    """Factory that creates a patient with a generated schedule."""
    from tb.extensions import db
    from tb.models import Patient
    from tb.qr_utils import make_patient_token
    from tb.schedule import generate_schedule

    created = []

    def _make(
        name="Somchai Test",
        hn="HN001",
        age=40,
        tb_no="TB001",
        weight=55.0,
        tb_type="PTB",
        start_date=date(2026, 4, 1),
        days=180,
        custom_regimen=False,
        phone=None,
        notes=None,
        outcome="",
    ):
        patient = Patient(
            name=name, hn=hn, age=age, tb_no=tb_no, weight=weight,
            tb_type=tb_type, start_date=start_date,
            custom_regimen=custom_regimen, phone=phone, notes=notes,
            outcome=outcome,
        )
        db.session.add(patient)
        db.session.commit()
        patient.scan_token = make_patient_token(patient.id)
        db.session.commit()
        generate_schedule(patient, days=days)
        created.append(patient)
        return patient

    return _make
