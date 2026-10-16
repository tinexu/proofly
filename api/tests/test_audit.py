"""Day 7: every change is logged, the log can't be edited, and owners can read it."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.audit import AuditDetailError, record
from app.models import AuditEvent, User
from tests.test_cases import as_other_user, create
from tests.test_sessions import sign_in


def actions(db) -> list[str]:
    return [e.action for e in db.scalars(select(AuditEvent).order_by(AuditEvent.created_at))]


# --- record() refuses personal details --------------------------------------------

def test_record_accepts_short_codes(db):
    record(db, "case.created", platform="facebook")
    db.flush()


@pytest.mark.parametrize("detail", [
    {"address": "214 Elm St"},
    {"email": "renter@example.edu"},
    {"rationale": "Called the landlord"},
    {"claim_type": "x" * 41},
    {"platform": {"nested": "dict"}},
])
def test_record_rejects_unknown_keys_and_free_text(db, detail):
    with pytest.raises(AuditDetailError):
        record(db, "case.created", **detail)


# --- Every change is logged once -----------------------------------------------------

def test_each_change_adds_exactly_one_event(client, db, outbox):
    sign_in(client, outbox)
    assert actions(db) == ["auth.signed_up"]

    case_id = create(client).json()["id"]
    assert actions(db)[-1] == "case.created"

    client.patch(f"/cases/{case_id}/claims/price_and_term", json={"state": "CONFLICTING", "rationale": "Rent differs"})
    assert actions(db)[-1] == "claim.reviewed"

    client.delete(f"/cases/{case_id}/claims/price_and_term/review")
    assert actions(db)[-1] == "claim.review_cleared"

    client.post("/auth/logout")
    assert actions(db) == ["auth.signed_up", "case.created", "claim.reviewed", "claim.review_cleared", "auth.signed_out"]


def test_reads_are_not_logged(client, db, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    before = len(actions(db))
    client.get("/cases")
    client.get(f"/cases/{case_id}")
    client.get(f"/cases/{case_id}/activity")
    client.get("/auth/me")
    assert len(actions(db)) == before


def test_rejected_changes_are_not_logged(client, db, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    before = len(actions(db))
    client.patch(f"/cases/{case_id}/claims/price_and_term", json={"state": "SUPPORTED", "rationale": "ok"})
    client.post("/cases", json={"address": ""})
    assert len(actions(db)) == before


# --- The database refuses to change the log ----------------------------------------

def _one_event(db) -> AuditEvent:
    record(db, "case.created", platform="facebook")
    db.flush()
    return db.scalar(select(AuditEvent))


def test_audit_rows_cannot_be_edited(db):
    event = _one_event(db)
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_events SET action = 'nothing.happened' WHERE id = :id"), {"id": event.id})
    db.rollback()


def test_audit_rows_cannot_be_deleted(db):
    event = _one_event(db)
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": event.id})
    db.rollback()


def test_deleting_a_user_keeps_their_history_without_them(db):
    user = User(email="leaving@example.edu")
    db.add(user)
    db.flush()
    record(db, "auth.signed_in", actor_user_id=user.id, method="magic_link")
    db.flush()
    db.delete(user)
    db.flush()
    db.expire_all()
    event = db.scalar(select(AuditEvent))
    assert event.action == "auth.signed_in"
    assert event.actor_user_id is None


# --- Reading a case's activity ------------------------------------------------------

def test_activity_newest_first_in_plain_words(client, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    client.patch(f"/cases/{case_id}/claims/price_and_term", json={"state": "CONFLICTING", "rationale": "Rent differs"})
    res = client.get(f"/cases/{case_id}/activity")
    assert res.status_code == 200
    items = res.json()
    assert [i["description"] for i in items] == [
        'Marked "Price and dates match" as conflicting',
        "Created the case",
    ]
    assert all(i["actor"] == "you" for i in items)


def test_activity_shows_only_this_case(client, outbox):
    sign_in(client, outbox)
    first = create(client).json()["id"]
    create(client)
    assert len(client.get(f"/cases/{first}/activity").json()) == 1


def test_activity_has_no_reason_text_or_sign_in_events(client, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    client.patch(f"/cases/{case_id}/claims/price_and_term", json={"state": "CONFLICTING", "rationale": "Secret note 950"})
    body = client.get(f"/cases/{case_id}/activity").text
    assert "Secret note" not in body
    assert "signed" not in body


def test_activity_is_owner_only(client, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    as_other_user(client, outbox)
    assert client.get(f"/cases/{case_id}/activity").status_code == 404


def test_activity_requires_sign_in(client):
    import uuid
    assert client.get(f"/cases/{uuid.uuid4()}/activity").status_code == 401