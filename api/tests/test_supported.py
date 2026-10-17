"""Week 7, Day 2: "Supported" names a clean file from the same case."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models import AuditEvent, Claim, Evidence
from app.purge import purge
from tests.test_cases import as_other_user, create
from tests.test_deletion import NOW
from tests.test_scanning import EVIL_PDF
from tests.test_uploads import PDF, setup_link, submit

from datetime import timedelta


def case_with_file(client, outbox, content=PDF, name="lease.pdf"):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", name, content)])
    files = client.get(f"/cases/{case_id}/evidence").json()
    return case_id, files[0]["id"]


def support(client, case_id, evidence_id, claim="sublet_authorization", rationale="Lease clause 12 allows subletting."):
    body = {"state": "SUPPORTED", "rationale": rationale}
    if evidence_id is not None:
        body["evidence_id"] = evidence_id
    return client.patch(f"/cases/{case_id}/claims/{claim}", json=body)


def claim_of(client, case_id, claim="sublet_authorization"):
    return next(c for c in client.get(f"/cases/{case_id}").json()["claims"] if c["type"] == claim)


def test_mark_supported_with_a_clean_file(client, outbox):
    case_id, evidence_id = case_with_file(client, outbox)
    res = support(client, case_id, evidence_id)
    assert res.status_code == 200
    claim = claim_of(client, case_id)
    assert claim["state"] == "SUPPORTED"
    assert claim["supporting_evidence_id"] == evidence_id
    assert claim["reviewer"] == "user" and claim["reviewed_by_id"] is not None
    assert claim["rationale"] == "Lease clause 12 allows subletting."


def test_other_claims_name_no_file(client, outbox):
    case_id, evidence_id = case_with_file(client, outbox)
    support(client, case_id, evidence_id)
    others = [c for c in client.get(f"/cases/{case_id}").json()["claims"] if c["type"] != "sublet_authorization"]
    assert all(c["supporting_evidence_id"] is None for c in others)


def test_a_file_can_support_a_different_claim(client, outbox):
    # A lease page sent for "permission" may also show the rent; the renter decides.
    case_id, evidence_id = case_with_file(client, outbox)
    assert support(client, case_id, evidence_id, claim="price_and_term").status_code == 200
    assert claim_of(client, case_id, "price_and_term")["supporting_evidence_id"] == evidence_id


def test_supported_without_a_file_is_refused(client, outbox):
    case_id, _ = case_with_file(client, outbox)
    res = support(client, case_id, None)
    assert res.status_code == 422
    assert "always names the evidence" in res.json()["detail"]
    assert claim_of(client, case_id)["state"] == "EVIDENCE_SUBMITTED"


def test_supported_still_needs_a_reason(client, outbox):
    case_id, evidence_id = case_with_file(client, outbox)
    assert support(client, case_id, evidence_id, rationale="  ").status_code == 422


def test_other_states_cannot_name_a_file(client, outbox):
    case_id, evidence_id = case_with_file(client, outbox)
    res = client.patch(f"/cases/{case_id}/claims/sublet_authorization",
                       json={"state": "CONFLICTING", "rationale": "x", "evidence_id": evidence_id})
    assert res.status_code == 422
    assert "Only a \"supported\" review" in res.json()["detail"]


def test_unknown_file_is_refused(client, outbox):
    case_id, _ = case_with_file(client, outbox)
    res = support(client, case_id, str(uuid.uuid4()))
    assert res.status_code == 422 and res.json()["detail"] == "That file isn't part of this case."


def test_file_from_another_case_is_refused(client, outbox):
    case_a, evidence_a = case_with_file(client, outbox)
    case_b = create(client).json()["id"]
    res = support(client, case_b, evidence_a)
    assert res.status_code == 422 and res.json()["detail"] == "That file isn't part of this case."


def test_file_from_another_users_case_gets_the_same_answer(client, outbox):
    _, evidence_a = case_with_file(client, outbox)
    as_other_user(client, outbox)
    my_case = create(client).json()["id"]
    res = support(client, my_case, evidence_a)
    assert res.status_code == 422 and res.json()["detail"] == "That file isn't part of this case."


@pytest.mark.parametrize("setup", ["down", "fail", "evil"])
def test_locked_or_blocked_files_cannot_support(client, outbox, scanner, setup):
    scanner.up = setup != "down"
    scanner.fail = setup == "fail"
    case_id, evidence_id = case_with_file(client, outbox, EVIL_PDF if setup == "evil" else PDF)
    res = support(client, case_id, evidence_id)
    assert res.status_code == 422
    assert res.json()["detail"] == "Only files that passed the virus check can support a claim."


def test_changing_to_another_state_drops_the_file(client, outbox):
    case_id, evidence_id = case_with_file(client, outbox)
    support(client, case_id, evidence_id)
    client.patch(f"/cases/{case_id}/claims/sublet_authorization", json={"state": "CONFLICTING", "rationale": "Landlord said no"})
    claim = claim_of(client, case_id)
    assert (claim["state"], claim["supporting_evidence_id"]) == ("CONFLICTING", None)


def test_undo_drops_the_file_and_hands_back_to_the_rules(client, outbox):
    case_id, evidence_id = case_with_file(client, outbox)
    support(client, case_id, evidence_id)
    client.delete(f"/cases/{case_id}/claims/sublet_authorization/review")
    claim = claim_of(client, case_id)
    assert (claim["state"], claim["reviewer"], claim["supporting_evidence_id"]) == ("EVIDENCE_SUBMITTED", "rules", None)


def test_supported_is_audited_without_the_reason_or_file_name(client, db, outbox):
    case_id, evidence_id = case_with_file(client, outbox, name="my lease.pdf")
    support(client, case_id, evidence_id)
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "claim.reviewed"))
    assert event.detail == {"claim_type": "sublet_authorization", "from": "EVIDENCE_SUBMITTED", "to": "SUPPORTED"}
    descriptions = [a["description"] for a in client.get(f"/cases/{case_id}/activity").json()]
    assert 'Marked "Subletting is allowed" as supported' in descriptions


def test_new_evidence_does_not_override_a_supported_review(client, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    evidence_id = client.get(f"/cases/{case_id}/evidence").json()[0]["id"]
    support(client, case_id, evidence_id)
    token2 = client.post(f"/cases/{case_id}/evidence-requests", json={"scopes": ["sublet_authorization"]}).json()["link"].rsplit("/r/", 1)[1]
    submit(client, token2, [("sublet_authorization", "b.pdf", PDF)])
    assert claim_of(client, case_id)["state"] == "SUPPORTED"


# --- Database guarantees -------------------------------------------------------------

def _a_claim(db, client, outbox):
    case_id, evidence_id = case_with_file(client, outbox)
    claim = db.scalar(select(Claim).where(Claim.case_id == uuid.UUID(case_id), Claim.type == "price_and_term"))
    return claim, uuid.UUID(evidence_id)


def test_database_refuses_supported_without_a_file(client, db, outbox):
    claim, _ = _a_claim(db, client, outbox)
    claim.state, claim.reviewer, claim.rationale = "SUPPORTED", "user", "x"
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_database_refuses_supported_set_by_the_rules(client, db, outbox):
    claim, evidence_id = _a_claim(db, client, outbox)
    claim.state, claim.supporting_evidence_id = "SUPPORTED", evidence_id
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_database_refuses_a_file_on_other_states(client, db, outbox):
    claim, evidence_id = _a_claim(db, client, outbox)
    claim.supporting_evidence_id = evidence_id
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# --- Deleting -------------------------------------------------------------------------

def test_deleting_a_case_clears_supported_reviews(client, db, outbox):
    case_id, evidence_id = case_with_file(client, outbox)
    support(client, case_id, evidence_id)
    client.delete(f"/cases/{case_id}")
    db.expire_all()
    claims = db.scalars(select(Claim).where(Claim.case_id == uuid.UUID(case_id))).all()
    assert all((c.state, c.supporting_evidence_id) == ("UNCHECKED", None) for c in claims)


def test_purging_a_case_with_a_supported_review(client, db, outbox, storage):
    case_id, evidence_id = case_with_file(client, outbox)
    support(client, case_id, evidence_id)
    client.delete(f"/cases/{case_id}")
    later = NOW + timedelta(hours=get_settings().case_purge_delay_hours + 1)
    result = purge(db, now=later, storage=storage)
    assert (result.cases, result.files) == (1, 1)
    assert db.get(Evidence, uuid.UUID(evidence_id)) is None