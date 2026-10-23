"""Login with a one-time code mailed to one mailbox. No mail is sent: the sender is replaced."""

from __future__ import annotations

import pytest


class _SentCodes(list):
    """A fake mailer: keeps the code of every mail (the last word of the subject)."""

    def send(self, to, subject, body):
        self.append(subject.rsplit(" ", 1)[-1])


@pytest.fixture
def auth_app(make_container):
    """auth_app(**setting_overrides) → (client, sent codes): the app with login on and mail configured."""
    from fastapi.testclient import TestClient

    from api.app import create_app

    def make(**overrides):
        sent = _SentCodes()
        settings = {"auth_enabled": True, "auth_email": "lab@example.org", "smtp_host": "smtp.example.org",
                    "smtp_username": "lab@example.org", "smtp_password": "x", "auth_code_resend_seconds": 0, **overrides}
        container = make_container(mailer=sent, **settings)
        return TestClient(create_app(container=container)), sent
    return make


@pytest.fixture
def auth_client(auth_app):
    return auth_app()


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


def test_wrong_codes_void_the_code(auth_app):
    client, sent = auth_app(auth_code_max_attempts=3)
    client.post("/auth/request-code")
    wrong = "000000" if sent[0] != "000000" else "111111"
    for _ in range(3):
        assert client.post("/auth/verify", json={"code": wrong}).status_code == 400
    # Even the right code no longer works: a new one must be requested.
    assert client.post("/auth/verify", json={"code": sent[0]}).status_code == 400


def test_expired_code_and_forged_session(auth_app):
    client, sent = auth_app(auth_code_ttl_minutes=0)
    auth_service = client.app.state.container.auth
    client.post("/auth/request-code")
    assert client.post("/auth/verify", json={"code": sent[0]}).json()["detail"] == "אין קוד בתוקף – יש לבקש קוד חדש"

    client.cookies.set(client.app.state.container.settings.auth_cookie_name, "9999999999.forged")
    assert client.get("/forms").status_code == 401
    assert auth_service.session_is_valid(auth_service.create_session())


def test_resend_is_rate_limited_and_unconfigured_mail_is_reported(auth_app):
    client, _ = auth_app(auth_code_resend_seconds=60)
    assert client.post("/auth/request-code").status_code == 200
    assert "בעוד" in client.post("/auth/request-code").json()["detail"]

    unconfigured, _ = auth_app(smtp_host="")
    assert unconfigured.post("/auth/request-code").status_code == 503


def test_demo_mode_any_address_and_the_fixed_code(auth_app):
    """AUTH_DEMO_CODE: nothing is mailed, any typed address is accepted, the fixed code logs in."""
    client, sent = auth_app(auth_demo_code="424242")
    assert client.get("/auth/status").json()["ask_email"] is True
    assert client.post("/auth/request-code", json={"email": "not-an-address"}).status_code == 400
    assert client.post("/auth/request-code", json={"email": "dana@lab.org"}).json() == {"email": "da***@lab.org"}
    assert sent == []  # no mail in demo mode
    assert client.post("/auth/verify", json={"code": "123456"}).status_code == 400
    assert client.post("/auth/verify", json={"code": "424242"}).status_code == 200
    assert client.get("/forms").status_code == 200
