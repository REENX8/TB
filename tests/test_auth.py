"""Auth + brute-force protection tests."""
from __future__ import annotations

from tests.conftest import TEST_PASSWORD, TEST_USERNAME


def test_login_success(client):
    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("staff_logged_in") is True
        assert sess.get("staff_user") == TEST_USERNAME


def test_login_wrong_password_records_failure(client):
    from tb.security import login_attempt_count

    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": "wrong"},
    )
    assert resp.status_code == 200
    assert login_attempt_count("127.0.0.1") == 1


def test_login_brute_force_lockout_after_5_failures(client):
    from tb.security import is_login_locked

    for _ in range(5):
        client.post(
            "/login",
            data={"username": TEST_USERNAME, "password": "wrong"},
        )
    assert is_login_locked("127.0.0.1")

    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("staff_logged_in") is None


def test_logout_clears_session(staff_client):
    resp = staff_client.get("/logout", follow_redirects=False)
    assert resp.status_code == 302
    with staff_client.session_transaction() as sess:
        assert sess.get("staff_logged_in") is None
        assert sess.get("staff_user") is None


def test_view_patient_unauthed_redirects_to_login(client, make_patient):
    patient = make_patient()
    resp = client.get(f"/patient/{patient.id}", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
