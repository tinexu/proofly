"""Day 4: sessions, /auth/me, sign-out, owner-only access, origin check."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.access import get_owned_case
from app.config import get_settings
from app.models import Case, User, UserSession
from app.security import hash_token
from tests.test_auth import request_link, token_from

COOKIE = get_settings().session_cookie_name


def sign_in(client, outbox, email="renter@example.edu"):
    request_link(client, email)
    res = client.post("/auth/verify", json={"token": token_from(outbox)})
    assert res.status_code == 200
    return res


def test_verify_sets_a_secure_session_cookie(client, outbox):
    res = sign_in(client, outbox)
    header = res.headers["set-cookie"].lower()
    assert f"{COOKIE}=" in header
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "max-age=" in header


def test_me_requires_sign_in(client):
    res = client.get("/auth/me")
    assert res.status_code == 401
    assert res.json()["detail"] == "Please sign in."


def test_me_after_sign_in(client, outbox):
    user = sign_in(client, outbox).json()["user"]
    res = client.get("/auth/me")
    assert res.status_code == 200
    assert res.json() == user


def test_session_token_is_stored_hashed(client, db, outbox):
    sign_in(client, outbox)
    token = client.cookies.get(COOKIE)
    row = db.scalar(select(UserSession))
    assert row.token_hash == hash_token(token)


def test_logout_ends_the_session(client, db, outbox):
    sign_in(client, outbox)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert db.scalar(select(UserSession)).revoked_at is not None


def test_old_cookie_is_useless_after_logout(client, outbox):
    sign_in(client, outbox)
    token = client.cookies.get(COOKIE)
    client.post("/auth/logout")
    client.cookies.set(COOKIE, token)
    assert client.get("/auth/me").status_code == 401


def test_logout_without_session_is_401(client):
    assert client.post("/auth/logout").status_code == 401


def test_expired_session_rejected(client, db, outbox):
    sign_in(client, outbox)
    row = db.scalar(select(UserSession))
    row.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.get("/auth/me").status_code == 401


def test_made_up_cookie_rejected(client):
    client.cookies.set(COOKIE, "not-a-real-session")
    assert client.get("/auth/me").status_code == 401


def test_two_browsers_have_separate_sessions(client, db, outbox):
    sign_in(client, outbox)
    first = client.cookies.get(COOKIE)
    client.cookies.clear()
    sign_in(client, outbox)
    second = client.cookies.get(COOKIE)
    assert first != second
    client.post("/auth/logout")  # signs out the second browser only
    client.cookies.set(COOKIE, first)
    assert client.get("/auth/me").status_code == 200


# --- Owner-only access -------------------------------------------------------

def _user(db, email):
    u = User(email=email)
    db.add(u)
    db.flush()
    return u


def test_owner_can_load_their_case(db):
    owner = _user(db, "owner@example.edu")
    kase = Case(owner_id=owner.id, address="214 Elm St")
    db.add(kase)
    db.flush()
    assert get_owned_case(db, owner, kase.id).id == kase.id


def test_other_users_get_404_not_403(db):
    owner, stranger = _user(db, "owner@example.edu"), _user(db, "stranger@example.edu")
    kase = Case(owner_id=owner.id, address="214 Elm St")
    db.add(kase)
    db.flush()
    with pytest.raises(HTTPException) as exc:
        get_owned_case(db, stranger, kase.id)
    assert exc.value.status_code == 404


def test_deleted_case_is_404_even_for_owner(db):
    owner = _user(db, "owner@example.edu")
    kase = Case(owner_id=owner.id, address="214 Elm St", status="deleted", deleted_at=datetime.now(timezone.utc))
    db.add(kase)
    db.flush()
    with pytest.raises(HTTPException) as exc:
        get_owned_case(db, owner, kase.id)
    assert exc.value.status_code == 404


def test_missing_case_looks_the_same_as_someone_elses(db):
    owner, stranger = _user(db, "owner@example.edu"), _user(db, "stranger@example.edu")
    kase = Case(owner_id=owner.id, address="214 Elm St")
    db.add(kase)
    db.flush()
    errors = []
    for case_id in (kase.id, uuid.uuid4()):
        with pytest.raises(HTTPException) as exc:
            get_owned_case(db, stranger, case_id)
        errors.append((exc.value.status_code, exc.value.detail))
    assert errors[0] == errors[1]


# --- Origin check --------------------------------------------------------------

def test_post_from_another_site_is_blocked(client):
    res = client.post("/auth/magic-link", json={"email": "a@example.edu"}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_post_from_the_web_app_is_allowed(client):
    origin = get_settings().cors_origin_list[0]
    res = client.post("/auth/magic-link", json={"email": "a@example.edu"}, headers={"Origin": origin})
    assert res.status_code == 202


def test_get_from_another_site_is_not_blocked_by_origin_check(client):
    res = client.get("/health", headers={"Origin": "https://evil.example"})
    assert res.status_code == 200