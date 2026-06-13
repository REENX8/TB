"""Configuration hardening tests."""
from __future__ import annotations

import pytest


def test_prod_config_requires_secret_key(_staff_env, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    # Reload config so the class attribute reflects the missing env var.
    import importlib

    import tb.config

    importlib.reload(tb.config)
    from tb import create_app

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("tb.config.ProdConfig")

    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    importlib.reload(tb.config)


def test_session_cookie_flags(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_prod_config_secure_cookie(_staff_env):
    from tb.config import DevConfig, ProdConfig

    assert ProdConfig.SESSION_COOKIE_SECURE is True
    assert DevConfig.SECRET_KEY  # dev fallback keeps local runs working
