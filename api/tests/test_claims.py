"""Day 6: reviewing claims, with provenance."""

import pytest
from sqlalchemy import select

from app.models import AuditEvent
from tests.test_cases import as_other_user, create
from tests.test_sessions import sign_in

REASON = "Rent on the lease ($950) doesn't match the listing ($850)."


def new_case(client, outbox):
    me = sign_in(client, outbox).json()["user"]
    return me, create(client).json()["id"]


def review(client, case_id, claim_type="price_and_term", state="CONFLICTING", rationale=REASON):
    return client.patch(f"/cases/{case_id}/claims/{claim_type}", json={"state": state, "rationale": rationale})


def claim_of(case_json, claim_type):
    return next(c for c in case_json["claims"] if c["type"] == claim_type)


def test_review_requires_sign_in(client):
    import uuid
    res = client.patch(f"/cases/{uuid.uuid4()}/claims/price_and_term", json={"state": "CONFLICTING", "rationale": "x"})
    assert res.status_code == 401


def test_mark_claim_conflicting_with_provenance(client, outbox):
    me, case_id = new_case(client, outbox)
    res = review(client, case_id)
    assert res.status_code == 200
    claim = claim_of(res.json(), "price_and_term")
    assert claim["state"] == "CONFLICTING"
    assert claim["rationale"] == REASON
    assert claim["reviewer"] == "user"
    assert claim["reviewed_by_id"] == me["id"]


def test_other_claims_are_untouched(client, outbox):
    _, case_id = new_case(client, outbox)
    claims = review(client, case_id).json()["claims"]
    others = [c for c in claims if c["type"] not in ("price_and_term", "payment_destination")]
    assert all(c["state"] == "UNCHECKED" and c["reviewer"] == "rules" for c in others)


def test_review_persists(client, outbox):
    _, case_id = new_case(client, outbox)
    review(client, case_id, "sublet_authorization", "REVIEW_NEEDED", "Landlord hasn't replied yet.")
    claim = claim_of(client.get(f"/cases/{case_id}").json(), "sublet_authorization")
    assert claim["state"] == "REVIEW_NEEDED"


@pytest.mark.parametrize("rationale", ["", "   "])
def test_review_requires_a_reason(client, outbox, rationale):
    _, case_id = new_case(client, outbox)
    assert review(client, case_id, rationale=rationale).status_code == 422


def test_reason_has_a_length_limit(client, outbox):
    _, case_id = new_case(client, outbox)
    assert review(client, case_id, rationale="x" * 1001).status_code == 422


def test_supported_needs_evidence(client, outbox):
    _, case_id = new_case(client, outbox)
    res = review(client, case_id, state="SUPPORTED", rationale="Looks fine to me.")
    assert res.status_code == 422
    assert "naming the evidence" in res.json()["detail"]
    assert claim_of(client.get(f"/cases/{case_id}").json(), "price_and_term")["state"] == "UNCHECKED"


@pytest.mark.parametrize("state", ["UNCHECKED", "EVIDENCE_SUBMITTED", "SAFE", "supported"])
def test_system_only_or_unknown_states_rejected(client, outbox, state):
    _, case_id = new_case(client, outbox)
    assert review(client, case_id, state=state).status_code == 422


def test_unknown_claim_type_rejected(client, outbox):
    _, case_id = new_case(client, outbox)
    assert review(client, case_id, claim_type="landlord_vibes").status_code == 422


def test_extra_fields_rejected(client, outbox):
    _, case_id = new_case(client, outbox)
    res = client.patch(
        f"/cases/{case_id}/claims/price_and_term",
        json={"state": "CONFLICTING", "rationale": REASON, "reviewer": "rules"},
    )
    assert res.status_code == 422


def test_other_user_cannot_review(client, outbox):
    _, case_id = new_case(client, outbox)
    as_other_user(client, outbox)
    assert review(client, case_id).status_code == 404
    assert client.delete(f"/cases/{case_id}/claims/price_and_term/review").status_code == 404


def test_review_is_audited_without_the_reason(client, db, outbox):
    _, case_id = new_case(client, outbox)
    review(client, case_id)
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "claim.reviewed"))
    assert str(event.case_id) == case_id
    assert event.detail == {"claim_type": "price_and_term", "from": "UNCHECKED", "to": "CONFLICTING"}
    assert "950" not in str(event.detail)


def test_changing_a_review_records_both_steps(client, db, outbox):
    _, case_id = new_case(client, outbox)
    review(client, case_id, state="REVIEW_NEEDED", rationale="Asked them to confirm.")
    review(client, case_id, state="CONFLICTING", rationale=REASON)
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "claim.reviewed").order_by(AuditEvent.created_at)
    ).all()
    assert [(e.detail["from"], e.detail["to"]) for e in events] == [
        ("UNCHECKED", "REVIEW_NEEDED"), ("REVIEW_NEEDED", "CONFLICTING"),
    ]


# --- Undo ----------------------------------------------------------------------

def test_undo_returns_claim_to_the_rules(client, db, outbox):
    _, case_id = new_case(client, outbox)
    review(client, case_id)
    res = client.delete(f"/cases/{case_id}/claims/price_and_term/review")
    assert res.status_code == 200
    claim = claim_of(res.json(), "price_and_term")
    assert claim == claim | {"state": "UNCHECKED", "rationale": None, "reviewer": "rules", "reviewed_by_id": None}
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "claim.review_cleared")) is not None


def test_undo_without_a_review_changes_nothing(client, db, outbox):
    _, case_id = new_case(client, outbox)
    res = client.delete(f"/cases/{case_id}/claims/price_and_term/review")
    assert res.status_code == 200
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "claim.review_cleared")) is None