"""Day 5: create, list and view cases."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.domain import CLAIM_TYPES
from app.models import AuditEvent, Case
from tests.test_sessions import sign_in

OFFER = {
    "address": "214 Elm Street, Unit 3B",
    "start_date": "2027-01-05",
    "end_date": "2027-04-30",
    "monthly_rent": "850",
    "deposit": "500",
    "platform": "facebook",
    "source_url": "https://www.facebook.com/groups/example/posts/1",
    "claimed_role": "leaseholder",
    "contact_handle": "Jordan (Messenger)",
    "permission_claim": "says_approved",
    "payment_method": "Zelle deposit before tour",
}


def create(client, **overrides):
    return client.post("/cases", json=OFFER | overrides)


def as_other_user(client, outbox):
    client.cookies.clear()
    sign_in(client, outbox, "stranger@example.edu")


# --- Sign-in required ----------------------------------------------------------

@pytest.mark.parametrize("method,path", [("post", "/cases"), ("get", "/cases"), ("get", f"/cases/{uuid.uuid4()}")])
def test_cases_require_sign_in(client, method, path):
    res = getattr(client, method)(path, json=OFFER) if method == "post" else client.get(path)
    assert res.status_code == 401


# --- Create --------------------------------------------------------------------

def test_create_case(client, outbox):
    sign_in(client, outbox)
    res = create(client)
    assert res.status_code == 201
    body = res.json()
    assert body["address"] == OFFER["address"]
    assert body["monthly_rent"] == "850.00"
    assert body["platform"] == "facebook"
    assert body["decision"] is None


def test_new_case_has_five_unchecked_claims_in_order(client, outbox):
    sign_in(client, outbox)
    claims = create(client, payment_method=None).json()["claims"]
    assert [c["type"] for c in claims] == list(CLAIM_TYPES)
    assert all(c["state"] == "UNCHECKED" and c["reviewer"] == "rules" for c in claims)


def test_hard_to_reverse_payment_flagged_on_create(client, outbox):
    """Rules engine (Week 7): OFFER asks for a Zelle deposit."""
    sign_in(client, outbox)
    claims = {c["type"]: c for c in create(client).json()["claims"]}
    assert claims["payment_destination"]["state"] == "REVIEW_NEEDED"
    assert "hard to reverse" in claims["payment_destination"]["rationale"]
    assert all(claims[t]["state"] == "UNCHECKED" for t in CLAIM_TYPES if t != "payment_destination")


def test_minimal_case(client, outbox):
    sign_in(client, outbox)
    res = client.post("/cases", json={"address": "Somewhere", "monthly_rent": "700"})
    assert res.status_code == 201
    body = res.json()
    assert body["platform"] == "other"
    assert body["claimed_role"] == "not_stated"
    assert body["permission_claim"] == "not_mentioned"


def test_whitespace_is_trimmed(client, outbox):
    sign_in(client, outbox)
    assert create(client, address="  214 Elm St  ").json()["address"] == "214 Elm St"


@pytest.mark.parametrize("overrides,message", [
    ({"address": ""}, None),
    ({"address": "   "}, None),
    ({"end_date": "2026-12-01"}, "move-out date is before"),
    ({"monthly_rent": "-5"}, None),
    ({"deposit": "-1"}, None),
    ({"platform": "myspace"}, None),
    ({"claimed_role": "landlord_ceo"}, None),
    ({"source_url": "javascript:alert(1)"}, "web link"),
    ({"source_url": "ftp://example.com/x"}, "web link"),
    ({"surprise_field": "x"}, None),
])
def test_invalid_offers_rejected(client, outbox, overrides, message):
    sign_in(client, outbox)
    res = create(client, **overrides)
    assert res.status_code == 422
    if message:
        assert message in res.text


def test_needs_rent_or_both_dates(client, outbox):
    sign_in(client, outbox)
    res = client.post("/cases", json={"address": "Somewhere", "start_date": "2027-01-01"})
    assert res.status_code == 422
    assert "monthly rent or the move-in and move-out dates" in res.text


def test_create_is_audited_without_personal_details(client, db, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "case.created"))
    assert str(event.case_id) == case_id
    text = str(event.detail)
    assert "Elm" not in text and "Jordan" not in text


# --- View ----------------------------------------------------------------------

def test_owner_can_view_case(client, outbox):
    sign_in(client, outbox)
    created = create(client).json()
    res = client.get(f"/cases/{created['id']}")
    assert res.status_code == 200
    assert res.json() == created


def test_other_user_gets_404(client, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    as_other_user(client, outbox)
    res = client.get(f"/cases/{case_id}")
    assert res.status_code == 404
    assert res.json()["detail"] == "Case not found."


def test_unknown_case_gets_same_404(client, outbox):
    sign_in(client, outbox)
    res = client.get(f"/cases/{uuid.uuid4()}")
    assert res.status_code == 404
    assert res.json()["detail"] == "Case not found."


def test_malformed_case_id_is_422(client, outbox):
    sign_in(client, outbox)
    assert client.get("/cases/1").status_code == 422


def test_deleted_case_is_hidden(client, db, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    kase = db.get(Case, uuid.UUID(case_id))
    kase.status, kase.deleted_at = "deleted", datetime.now(timezone.utc)
    db.commit()
    assert client.get(f"/cases/{case_id}").status_code == 404
    assert client.get("/cases").json() == []


# --- List ----------------------------------------------------------------------

def test_list_shows_only_my_cases_newest_first(client, outbox):
    sign_in(client, outbox)
    first = create(client, address="First place").json()["id"]
    second = create(client, address="Second place").json()["id"]
    as_other_user(client, outbox)
    create(client, address="Stranger's place")

    client.cookies.clear()
    sign_in(client, outbox)
    listed = client.get("/cases").json()
    assert [c["id"] for c in listed] == [second, first]
    assert set(listed[0]) == {"id", "address", "created_at"}


def test_list_is_empty_for_new_user(client, outbox):
    sign_in(client, outbox)
    assert client.get("/cases").json() == []