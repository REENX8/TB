"""Staff account management tests."""
from __future__ import annotations

from tests.conftest import TEST_PASSWORD, TEST_USERNAME


def test_staff_list_requires_admin(nurse_client):
    resp = nurse_client.get("/staff/")
    assert resp.status_code == 403


def test_staff_list_requires_login(client):
    resp = client.get("/staff/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_legacy_session_without_role_is_admin(staff_client):
    # Sessions created before roles existed must keep full access.
    resp = staff_client.get("/staff/")
    assert resp.status_code == 200


def test_admin_creates_staff_account(admin_client):
    from tb.models import StaffAccount

    resp = admin_client.post(
        "/staff/new",
        data={"username": "newnurse", "password": "longpassword", "role": "nurse"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    account = StaffAccount.query.filter_by(username="newnurse").first()
    assert account is not None
    assert account.role == "nurse"
    assert account.is_active is True


def test_create_rejects_duplicate_username(admin_client, make_staff):
    from tb.models import StaffAccount

    make_staff(username="dup_user")
    admin_client.post(
        "/staff/new",
        data={"username": "dup_user", "password": "longpassword", "role": "nurse"},
    )
    assert StaffAccount.query.filter_by(username="dup_user").count() == 1


def test_create_rejects_short_password(admin_client):
    from tb.models import StaffAccount

    admin_client.post(
        "/staff/new",
        data={"username": "shortpw", "password": "short", "role": "nurse"},
    )
    assert StaffAccount.query.filter_by(username="shortpw").first() is None


def test_create_rejects_invalid_role(admin_client):
    from tb.models import StaffAccount

    admin_client.post(
        "/staff/new",
        data={"username": "badrole", "password": "longpassword", "role": "superuser"},
    )
    assert StaffAccount.query.filter_by(username="badrole").first() is None


def test_admin_edits_role_and_active(admin_client, make_staff):
    from tb.extensions import db
    from tb.models import StaffAccount

    account = make_staff(username="editme", role="nurse")
    admin_client.post(
        f"/staff/{account.id}/edit",
        data={"role": "pharmacist"},  # is_active unchecked -> deactivate
    )
    db.session.expire_all()
    refreshed = db.session.get(StaffAccount, account.id)
    assert refreshed.role == "pharmacist"
    assert refreshed.is_active is False


def test_admin_cannot_deactivate_self(admin_client, make_staff):
    from tb.extensions import db
    from tb.models import StaffAccount

    account = make_staff(username="admin_user", role="admin")
    admin_client.post(f"/staff/{account.id}/edit", data={"role": "admin"})
    db.session.expire_all()
    refreshed = db.session.get(StaffAccount, account.id)
    assert refreshed.is_active is True


def test_db_account_login_sets_role_and_last_login(client, make_staff):
    from tb.extensions import db
    from tb.models import StaffAccount

    account = make_staff(username="pharm1", password="password123", role="pharmacist")
    resp = client.post(
        "/login",
        data={"username": "pharm1", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["staff_logged_in"] is True
        assert sess["staff_role"] == "pharmacist"
    db.session.expire_all()
    refreshed = db.session.get(StaffAccount, account.id)
    assert refreshed.last_login is not None


def test_deactivated_account_cannot_login(client, make_staff):
    make_staff(username="gone", password="password123", is_active=False)
    client.post("/login", data={"username": "gone", "password": "password123"})
    with client.session_transaction() as sess:
        assert not sess.get("staff_logged_in")


def test_env_account_fallback_logs_in_as_admin(client, app):
    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["staff_logged_in"] is True
        assert sess["staff_role"] == "admin"


def test_reset_password(admin_client, client, make_staff):
    account = make_staff(username="resetme", password="oldpassword1")
    admin_client.post(
        f"/staff/{account.id}/reset_password",
        data={"password": "brandnewpass"},
    )
    admin_client.get("/logout")
    client.post("/login", data={"username": "resetme", "password": "brandnewpass"})
    with client.session_transaction() as sess:
        assert sess.get("staff_logged_in") is True


def test_change_own_password_round_trip(client, make_staff):
    make_staff(username="selfserve", password="password123", role="nurse")
    client.post("/login", data={"username": "selfserve", "password": "password123"})
    resp = client.post(
        "/staff/password",
        data={"current_password": "password123", "new_password": "newpassword9"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    client.get("/logout")
    client.post("/login", data={"username": "selfserve", "password": "newpassword9"})
    with client.session_transaction() as sess:
        assert sess.get("staff_logged_in") is True


def test_change_own_password_wrong_current(client, make_staff):
    make_staff(username="wrongpw", password="password123")
    client.post("/login", data={"username": "wrongpw", "password": "password123"})
    client.post(
        "/staff/password",
        data={"current_password": "incorrect", "new_password": "newpassword9"},
    )
    client.get("/logout")
    client.post("/login", data={"username": "wrongpw", "password": "password123"})
    with client.session_transaction() as sess:
        assert sess.get("staff_logged_in") is True  # old password still valid


def test_env_account_change_password_shows_warning(staff_client):
    resp = staff_client.get("/staff/password")
    assert resp.status_code == 200
    assert b"environment variables" in resp.data
