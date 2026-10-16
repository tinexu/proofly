"""Day 8: deleting a case and purging deleted data."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.models import AuditEvent, Case, Claim, LoginToken, User, UserSession
from app.purge import purge
from tests.test_cases import as_other_user, create
from tests.test_sessions import sign_in

NOW = datetime.now(timezone.utc)


def new_case(client, outbox) -> str:
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    client.patch(f"/cases/{case_id}/claims/price_and_term", json={"state": "CONFLICTING", "rationale": "Private note"})
    return case_id


def actions(db, case_id) -> list[str]:
    return [e.action for e in db.scalars(
        select(AuditEvent).where(AuditEvent.case_id == uuid.UUID(case_id)).order_by(AuditEvent.created_at)
    )]


# --- DELETE /cases/{id} ----------------------------------------------------------

def test_delete_requires_sign_in(client):
    assert client.delete(f"/cases/{uuid.uuid4()}").status_code == 401


def test_delete_case(client, outbox):
    case_id = new_case(client, outbox)
    res = client.delete(f"/cases/{case_id}")
    assert res.status_code == 204
    assert res.content == b""
    assert client.get(f"/cases/{case_id}").status_code == 404
    assert client.get(f"/cases/{case_id}/activity").status_code == 404
    assert client.get("/cases").json() == []


def test_deleting_twice_is_404(client, outbox):
    case_id = new_case(client, outbox)
    client.delete(f"/cases/{case_id}")
    assert client.delete(f"/cases/{case_id}").status_code == 404


def test_other_user_cannot_delete(client, db, outbox):
    case_id = new_case(client, outbox)
    as_other_user(client, outbox)
    assert client.delete(f"/cases/{case_id}").status_code == 404
    assert db.get(Case, uuid.UUID(case_id)).status == "active"


def test_deleted_case_cannot_be_changed(client, outbox):
    case_id = new_case(client, outbox)
    client.delete(f"/cases/{case_id}")
    res = client.patch(f"/cases/{case_id}/claims/sublet_authorization", json={"state": "CONFLICTING", "rationale": "x"})
    assert res.status_code == 404


def test_personal_details_wiped_immediately(client, db, outbox):
    case_id = new_case(client, outbox)
    client.delete(f"/cases/{case_id}")
    db.expire_all()
    kase = db.get(Case, uuid.UUID(case_id))
    assert kase.status == "deleted" and kase.deleted_at is not None
    assert kase.address == "(deleted)"
    assert kase.source_url is None and kase.contact_handle is None and kase.payment_method is None
    claims = db.scalars(select(Claim).where(Claim.case_id == kase.id)).all()
    assert all(c.rationale is None and c.reviewed_by_id is None for c in claims)


def test_delete_is_audited(client, db, outbox):
    case_id = new_case(client, outbox)
    client.delete(f"/cases/{case_id}")
    assert actions(db, case_id)[-1] == "case.deleted"


def test_other_cases_untouched(client, outbox):
    case_id = new_case(client, outbox)
    keep = create(client).json()["id"]
    client.delete(f"/cases/{case_id}")
    assert [c["id"] for c in client.get("/cases").json()] == [keep]


# --- Purge job ---------------------------------------------------------------------

def _deleted_case(db, hours_ago: float) -> Case:
    user = db.scalar(select(User).where(User.email == "purge@example.edu"))
    if user is None:
        user = User(email="purge@example.edu")
        db.add(user)
        db.flush()
    kase = Case(owner_id=user.id, address="(deleted)", status="deleted", deleted_at=NOW - timedelta(hours=hours_ago))
    kase.claims = [Claim(type="price_and_term")]
    db.add(kase)
    db.flush()
    return kase


def test_purge_removes_cases_past_the_delay(db):
    delay = get_settings().case_purge_delay_hours
    old = _deleted_case(db, delay + 1)
    old_id = old.id
    result = purge(db, now=NOW)
    assert result.cases == 1
    db.expire_all()
    assert db.get(Case, old_id) is None
    assert db.scalars(select(Claim).where(Claim.case_id == old_id)).all() == []


def test_purge_keeps_recently_deleted_and_active_cases(db):
    recent = _deleted_case(db, 1)
    active = Case(owner_id=recent.owner_id, address="Active place")
    db.add(active)
    db.flush()
    assert purge(db, now=NOW).cases == 0
    assert db.get(Case, recent.id) is not None
    assert db.get(Case, active.id) is not None


def test_purge_keeps_the_audit_trail_and_adds_a_purged_event(client, db, outbox):
    case_id = new_case(client, outbox)
    client.delete(f"/cases/{case_id}")
    later = NOW + timedelta(hours=get_settings().case_purge_delay_hours + 1)
    purge(db, now=later)
    assert actions(db, case_id) == ["case.created", "claim.reviewed", "case.deleted", "case.purged"]
    purged = db.scalar(select(AuditEvent).where(AuditEvent.action == "case.purged"))
    assert purged.actor_type == "system" and purged.actor_user_id is None


def test_dry_run_changes_nothing(db):
    kase = _deleted_case(db, get_settings().case_purge_delay_hours + 1)
    result = purge(db, now=NOW, dry_run=True)
    assert result.cases == 1
    assert db.get(Case, kase.id) is not None
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "case.purged")) is None


def test_purge_cleans_old_sign_in_links_and_sessions(db):
    keep_days = get_settings().auth_record_retention_days
    old, recent = NOW - timedelta(days=keep_days + 1), NOW - timedelta(hours=1)
    user = User(email="sessions@example.edu")
    db.add(user)
    db.flush()
    db.add_all([
        LoginToken(email="a@example.edu", token_hash="a" * 64, created_at=old - timedelta(minutes=15), expires_at=old),
        LoginToken(email="b@example.edu", token_hash="b" * 64, created_at=recent, expires_at=recent + timedelta(minutes=15)),
        UserSession(user_id=user.id, token_hash="c" * 64, created_at=old - timedelta(days=1), expires_at=NOW + timedelta(days=1), revoked_at=old),
        UserSession(user_id=user.id, token_hash="d" * 64, created_at=recent, expires_at=NOW + timedelta(days=13)),
    ])
    db.flush()
    result = purge(db, now=NOW)
    assert (result.login_tokens, result.sessions) == (1, 1)
    assert [t.email for t in db.scalars(select(LoginToken))] == ["b@example.edu"]
    assert [s.token_hash for s in db.scalars(select(UserSession))] == ["d" * 64]


def test_purge_with_nothing_to_do(db):
    result = purge(db, now=NOW)
    assert (result.cases, result.login_tokens, result.sessions) == (0, 0, 0)