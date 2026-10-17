"""Week 7, Day 1: the rules engine."""

import uuid

import pytest
from sqlalchemy import select

from app.domain import CLAIM_TYPES
from app.models import AuditEvent, Claim
from app.rules import evaluate, payment_concern
from tests.test_cases import create
from tests.test_scanning import EVIL_PDF
from tests.test_sessions import sign_in
from tests.test_uploads import PDF, setup_link, submit


# --- Pure rules ----------------------------------------------------------------------

@pytest.mark.parametrize("method,flagged", [
    ("Zelle deposit before the tour", "person-to-person payment app"),
    ("venmo", "person-to-person payment app"),
    ("Cash App", "person-to-person payment app"),
    ("PayPal friends and family", "person-to-person payment app"),
    ("Wire transfer to my bank", "wire transfer"),
    ("Western Union", "wire transfer"),
    ("Amazon gift cards", "gift cards"),
    ("USDT or bitcoin", "cryptocurrency"),
    ("ETH", "cryptocurrency"),
])
def test_hard_to_reverse_methods_are_flagged(method, flagged):
    concern = payment_concern(method)
    assert concern and flagged in concern
    assert "hard to reverse" in concern


@pytest.mark.parametrize("method", [None, "", "Check to the property office", "Through the landlord's portal", "Ethernet cable deposit"])
def test_other_methods_are_not_flagged(method):
    assert payment_concern(method) is None


def test_flag_wording_is_neutral():
    concern = payment_concern("Zelle").lower()
    for word in ("scam", "fraud", "fake", "safe", "guarantee", "legit"):
        assert word not in concern


def test_evaluate_defaults_to_unchecked():
    out = evaluate(None, {})
    assert {t: o.state for t, o in out.items()} == {t: "UNCHECKED" for t in CLAIM_TYPES}
    assert all(o.rationale is None for o in out.values())


def test_evaluate_evidence_and_payment():
    out = evaluate("Venmo", {"person_unit_relationship": 1, "payment_destination": 2})
    assert out["person_unit_relationship"].state == "EVIDENCE_SUBMITTED"
    assert out["payment_destination"].state == "REVIEW_NEEDED"  # payment concern outranks evidence
    assert out["property_existence"].state == "UNCHECKED"


def test_rules_never_mark_supported():
    for method in (None, "Zelle", "Check"):
        out = evaluate(method, {t: 5 for t in CLAIM_TYPES})
        assert all(o.state != "SUPPORTED" for o in out.values())


# --- Applied to real cases ------------------------------------------------------------

def claims_of(client, case_id):
    return {c["type"]: c for c in client.get(f"/cases/{case_id}").json()["claims"]}


def test_payment_flag_logged_as_rules(client, db, outbox):
    sign_in(client, outbox)
    case_id = create(client, payment_method="Wire transfer").json()["id"]
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "claim.rules_updated"))
    assert event.actor_type == "rules" and event.actor_user_id is None
    assert event.detail == {"claim_type": "payment_destination", "from": "UNCHECKED", "to": "REVIEW_NEEDED"}
    descriptions = [a["description"] for a in client.get(f"/cases/{case_id}/activity").json()]
    assert 'Proofly marked "Where the money goes" as needs review' in descriptions


def test_evidence_moves_claim_with_explanation(client, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    claim = claims_of(client, case_id)["sublet_authorization"]
    assert claim["state"] == "EVIDENCE_SUBMITTED"
    assert "doesn't confirm the claim" in claim["rationale"]


def test_blocked_file_does_not_count_as_evidence(client, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "evil.pdf", EVIL_PDF)])
    assert claims_of(client, case_id)["sublet_authorization"]["state"] == "UNCHECKED"


def test_manual_review_beats_the_rules(client, outbox):
    case_id, token = setup_link(client, outbox)
    client.patch(f"/cases/{case_id}/claims/sublet_authorization", json={"state": "CONFLICTING", "rationale": "Landlord said no"})
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    claim = claims_of(client, case_id)["sublet_authorization"]
    assert (claim["state"], claim["reviewer"], claim["rationale"]) == ("CONFLICTING", "user", "Landlord said no")


def test_undo_hands_back_to_the_rules(client, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    client.patch(f"/cases/{case_id}/claims/sublet_authorization", json={"state": "CONFLICTING", "rationale": "x"})
    res = client.delete(f"/cases/{case_id}/claims/sublet_authorization/review").json()
    claim = next(c for c in res["claims"] if c["type"] == "sublet_authorization")
    assert (claim["state"], claim["reviewer"]) == ("EVIDENCE_SUBMITTED", "rules")  # not back to "unchecked"


def test_undo_on_payment_restores_the_flag(client, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]  # Zelle
    client.patch(f"/cases/{case_id}/claims/payment_destination", json={"state": "CONFLICTING", "rationale": "x"})
    client.delete(f"/cases/{case_id}/claims/payment_destination/review")
    assert claims_of(client, case_id)["payment_destination"]["state"] == "REVIEW_NEEDED"


def test_rules_only_touch_rule_owned_claims(client, db, outbox):
    sign_in(client, outbox)
    case_id = create(client, payment_method=None).json()["id"]
    claims = db.scalars(select(Claim).where(Claim.case_id == uuid.UUID(case_id))).all()
    assert all(c.reviewer == "rules" for c in claims)