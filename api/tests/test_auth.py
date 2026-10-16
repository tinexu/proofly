"""Day 3: email magic-link sign-in."""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.models import AuditEvent, LoginToken, User
from app.security import hash_token


def request_link(client, email="renter@example.edu"):
    return client.post("/auth/magic-link", json={"email": email})


def token_from(outbox) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", outbox.sent[-1].body)
    assert match, "no sign-in link in the email"
    return match.group(1)


def test_request_sends_a_link(client, outbox):
    res = request_link(client)
    assert res.status_code == 202
    assert len(outbox.sent) == 1
    email = outbox.sent[0]
    assert email.to == "renter@example.edu"
    assert f"{get_settings().web_base_url}/auth/verify?token=" in email.body


def test_email_is_normalized(client, outbox):
    request_link(client, "  Renter@Example.EDU ")
    assert outbox.sent[0].to == "renter@example.edu"


def test_invalid_email_rejected(client, outbox):
    res = request_link(client, "not-an-email")
    assert res.status_code == 422
    assert outbox.sent == []


def test_request_does_not_create_an_account(client, db):
    request_link(client)
    assert db.scalar(select(User).where(User.email == "renter@example.edu")) is None


def test_only_the_hash_is_stored(client, db, outbox):
    request_link(client)
    token = token_from(outbox)
    row = db.scalar(select(LoginToken))
    assert row.token_hash == hash_token(token)
    assert token not in row.token_hash


def test_same_response_for_any_email(client):
    """No account enumeration: new and existing addresses look the same."""
    first = request_link(client, "someone@example.edu").json()
    request_link(client, "existing@example.edu")
    client.post("/auth/verify", json={"token": "x" * 43})
    again = request_link(client, "existing@example.edu").json()
    assert first == again


def test_verify_creates_account_on_first_sign_in(client, db, outbox):
    request_link(client)
    res = client.post("/auth/verify", json={"token": token_from(outbox)})
    assert res.status_code == 200
    body = res.json()
    assert body["new_account"] is True
    assert body["user"]["email"] == "renter@example.edu"
    user = db.scalar(select(User).where(User.email == "renter@example.edu"))
    assert user.last_login_at is not None


def test_verify_reuses_existing_account(client, outbox):
    request_link(client)
    first = client.post("/auth/verify", json={"token": token_from(outbox)}).json()
    request_link(client)
    second = client.post("/auth/verify", json={"token": token_from(outbox)}).json()
    assert second["new_account"] is False
    assert second["user"]["id"] == first["user"]["id"]


def test_link_works_only_once(client, outbox):
    request_link(client)
    token = token_from(outbox)
    assert client.post("/auth/verify", json={"token": token}).status_code == 200
    again = client.post("/auth/verify", json={"token": token})
    assert again.status_code == 400
    assert "already used" in again.json()["detail"]


def test_expired_link_rejected(client, db, outbox):
    request_link(client)
    token = token_from(outbox)
    row = db.scalar(select(LoginToken))
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.post("/auth/verify", json={"token": token}).status_code == 400


def test_made_up_token_rejected(client):
    assert client.post("/auth/verify", json={"token": "x" * 43}).status_code == 400


def test_too_many_requests_are_silently_dropped(client, outbox):
    limit = get_settings().magic_link_hourly_limit
    for _ in range(limit + 3):
        assert request_link(client).status_code == 202
    assert len(outbox.sent) == limit


def test_sign_in_is_audited_without_the_email(client, db, outbox):
    request_link(client)
    client.post("/auth/verify", json={"token": token_from(outbox)})
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "auth.signed_up"))
    assert event is not None
    assert "renter@example.edu" not in str(event.detail)