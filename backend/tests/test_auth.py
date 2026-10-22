"""Login with a one-time code mailed to one mailbox. No mail is sent: the sender is replaced."""

from __future__ import annotations

import pytest


@pytest.fixture
def auth_client(client, monkeypatch):
    """The app with login on and mail configured; returns (client, sent codes)."""
    import config
    from services import auth_service

    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    for name, value in (("AUTH_EMAIL", "lab@example.org"), ("SMTP_HOST", "smtp.example.org"),
                        ("SMTP_USERNAME", "lab@example.org"), ("SMTP_PASSWORD", "x")):
        monkeypatch.setattr(config, name, value)
    monkeypatch.setattr(config, "AUTH_CODE_RESEND_SECONDS", 0)
    auth_service._pending.clear()
    sent = []
    monkeypatch.setattr(auth_service, "_send_mail", sent.append)
    return client, sent


def test_everything_but_login_needs_a_session(auth_client):
    client, _ = auth_client
    assert client.get("/forms").status_code == 401
    assert client.get("/meta").status_code == 401
    assert client.get("/health").status_code == 200
    status = client.get("/auth/status").json()
    assert status == {"enabled": True, "authenticated": False, "email": "la***@example.org", "ask_email": False}


def test_code_login_and_logout(auth_client):
    client, sent = auth_client
    assert client.post("/auth/request-code").json() == {"email": "la***@example.org"}
    [code] = sent
    assert len(code) == 6 and code.isdigit()

    response = client.post("/auth/verify", json={"code": code})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/forms").status_code == 200
    assert client.get("/auth/status").json()["authenticated"] is True

    # The code is used up.
    assert client.post("/auth/verify", json={"code": code}).status_code == 400
    client.post("/auth/logout")
    assert client.get("/forms").status_code == 401


def test_wrong_codes_void_the_code(auth_client, monkeypatch):
    import config

    client, sent = auth_client
    monkeypatch.setattr(config, "AUTH_CODE_MAX_ATTEMPTS", 3)
    client.post("/auth/request-code")
    wrong = "000000" if sent[0] != "000000" else "111111"
    for _ in range(3):
        assert client.post("/auth/verify", json={"code": wrong}).status_code == 400
    # Even the right code no longer works: a new one must be requested.
    assert client.post("/auth/verify", json={"code": sent[0]}).status_code == 400


def test_expired_code_and_forged_session(auth_client, monkeypatch):
    import config
    from services import auth_service

    client, sent = auth_client
    monkeypatch.setattr(config, "AUTH_CODE_TTL_MINUTES", 0)
    client.post("/auth/request-code")
    assert client.post("/auth/verify", json={"code": sent[0]}).json()["detail"] == "אין קוד בתוקף – יש לבקש קוד חדש"

    client.cookies.set(config.AUTH_COOKIE_NAME, "9999999999.forged")
    assert client.get("/forms").status_code == 401
    assert auth_service.session_is_valid(auth_service.create_session())


def test_resend_is_rate_limited_and_unconfigured_mail_is_reported(auth_client, monkeypatch):
    import config

    client, _ = auth_client
    monkeypatch.setattr(config, "AUTH_CODE_RESEND_SECONDS", 60)
    assert client.post("/auth/request-code").status_code == 200
    assert "בעוד" in client.post("/auth/request-code").json()["detail"]

    monkeypatch.setattr(config, "SMTP_HOST", "")
    assert client.post("/auth/request-code").status_code == 503


def test_demo_mode_any_address_and_the_fixed_code(auth_client, monkeypatch):
    """AUTH_DEMO_CODE: nothing is mailed, any typed address is accepted, the fixed code logs in."""
    import config

    client, sent = auth_client
    monkeypatch.setattr(config, "AUTH_DEMO_CODE", "424242")
    assert client.get("/auth/status").json()["ask_email"] is True
    assert client.post("/auth/request-code", json={"email": "not-an-address"}).status_code == 400
    assert client.post("/auth/request-code", json={"email": "dana@lab.org"}).json() == {"email": "da***@lab.org"}
    assert sent == []  # no mail in demo mode
    assert client.post("/auth/verify", json={"code": "123456"}).status_code == 400
    assert client.post("/auth/verify", json={"code": "424242"}).status_code == 200
    assert client.get("/forms").status_code == 200
