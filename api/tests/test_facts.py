"""Week 7, Day 3: what files say, compared with the listing."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.facts import FactValueError, compare, parse
from app.models import AuditEvent, CaseFact
from app.rules import evaluate
from tests.test_cases import OFFER, as_other_user, create
from tests.test_scanning import EVIL_PDF
from tests.test_sessions import sign_in
from tests.test_uploads import PDF, setup_link, submit


# --- Pure comparison -------------------------------------------------------------------

@pytest.mark.parametrize("field,raw,stored", [
    ("monthly_rent", "$1,200", "1200.00"),
    ("monthly_rent", " 950.5 ", "950.50"),
    ("deposit", "0", "0.00"),
    ("start_date", "2026-06-01", "2026-06-01"),
    ("address", "  214 Elm St  ", "214 Elm St"),
    ("payment_method", "Check to Oakwood Management", "Check to Oakwood Management"),
])
def test_parse_canonicalises(field, raw, stored):
    assert parse(field, raw) == stored


@pytest.mark.parametrize("field,raw", [
    ("monthly_rent", "about 900"), ("monthly_rent", "-5"), ("deposit", "NaN"), ("deposit", "1e12"),
    ("start_date", "June 1"), ("end_date", "2026-13-01"), ("address", "   "), ("address", "x" * 201),
])
def test_parse_rejects(field, raw):
    with pytest.raises(FactValueError):
        parse(field, raw)


@pytest.mark.parametrize("field,listed,provided,result", [
    ("monthly_rent", Decimal("1200.00"), "1200.00", "matches"),
    ("monthly_rent", Decimal("1200.00"), "1250.00", "differs"),
    ("deposit", None, "500.00", "listing_silent"),
    ("start_date", date(2026, 6, 1), "2026-06-01", "matches"),
    ("end_date", date(2026, 8, 15), "2026-08-31", "differs"),
    ("address", "214 Elm Street, Apt #3B", "214 elm st unit 3b", "matches"),
    ("address", "214 Elm Street", "214 Elm St, Unit 3B", "matches"),      # less detail isn't a contradiction
    ("address", "214 Elm St, Unit 3B", "214 Elm St, Unit 3C", "differs"),
    ("address", "214 Elm St", "41 Elm St", "differs"),
    ("payment_method", "Zelle", "Zelle to Jordan K.", "matches"),
    ("payment_method", "Zelle deposit before tour", "Check to the property office", "differs"),
    ("payment_method", "", "Check", "listing_silent"),
])
def test_compare(field, listed, provided, result):
    assert compare(field, listed, provided) == result


def test_mismatch_rule_outranks_payment_flag_and_evidence():
    out = evaluate("Zelle", {"price_and_term": 1, "payment_destination": 1}, ["monthly_rent", "payment_method"])
    assert out["price_and_term"].state == "CONFLICTING"
    assert "monthly rent differs from the listing" in out["price_and_term"].rationale
    assert out["payment_destination"].state == "CONFLICTING"
    assert out["property_existence"].state == "UNCHECKED"


def test_mismatch_note_names_every_field():
    out = evaluate(None, {}, ["deposit", "monthly_rent", "end_date"])
    assert "move-out date, monthly rent and deposit differ" in out["price_and_term"].rationale


def test_mismatch_wording_is_neutral():
    note = evaluate(None, {}, ["address"])["property_existence"].rationale.lower()
    for word in ("scam", "fraud", "fake", "lie", "safe"):
        assert word not in note


# --- Endpoints ---------------------------------------------------------------------------

def case_with_file(client, outbox, content=PDF):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("person_unit_relationship", "lease.pdf", content)])
    return case_id, client.get(f"/cases/{case_id}/evidence").json()[0]["id"]


def put(client, case_id, field, value, evidence_id):
    return client.put(f"/cases/{case_id}/facts/{field}", json={"value": value, "evidence_id": evidence_id})


def claims_of(client, case_id):
    return {c["type"]: c for c in client.get(f"/cases/{case_id}").json()["claims"]}


def test_matching_fact(client, outbox):
    case_id, ev = case_with_file(client, outbox)
    res = put(client, case_id, "monthly_rent", f"${OFFER['monthly_rent']}", ev)
    assert res.status_code == 200
    body = res.json()
    assert (body["field"], body["claim_type"], body["result"]) == ("monthly_rent", "price_and_term", "matches")
    assert body["listed"] == "850.00" and body["value"] == "850.00" and body["evidence_id"] == ev
    assert claims_of(client, case_id)["price_and_term"]["state"] == "UNCHECKED"


def test_different_fact_marks_the_claim_conflicting(client, outbox):
    case_id, ev = case_with_file(client, outbox)
    body = put(client, case_id, "monthly_rent", "1100", ev).json()
    assert (body["result"], body["listed"], body["value"]) == ("differs", "850.00", "1100.00")
    claim = claims_of(client, case_id)["price_and_term"]
    assert claim["state"] == "CONFLICTING" and claim["reviewer"] == "rules"
    assert "monthly rent differs" in claim["rationale"]


def test_fixing_the_fact_clears_the_conflict(client, outbox):
    case_id, ev = case_with_file(client, outbox)
    put(client, case_id, "monthly_rent", "1100", ev)
    put(client, case_id, "monthly_rent", "850", ev)  # misread the first time
    assert claims_of(client, case_id)["price_and_term"]["state"] == "UNCHECKED"
    assert len(client.get(f"/cases/{case_id}/facts").json()) == 1  # replaced, not added


def test_removing_the_fact_clears_the_conflict(client, outbox):
    case_id, ev = case_with_file(client, outbox)
    put(client, case_id, "monthly_rent", "1100", ev)
    assert client.delete(f"/cases/{case_id}/facts/monthly_rent").status_code == 204
    assert client.get(f"/cases/{case_id}/facts").json() == []
    assert claims_of(client, case_id)["price_and_term"]["state"] == "UNCHECKED"
    assert client.delete(f"/cases/{case_id}/facts/monthly_rent").status_code == 204  # safe to repeat


def test_payment_mismatch_replaces_the_payment_flag(client, outbox):
    case_id, ev = case_with_file(client, outbox)  # OFFER asks for Zelle
    assert claims_of(client, case_id)["payment_destination"]["state"] == "REVIEW_NEEDED"
    put(client, case_id, "payment_method", "Check to Oakwood Property Management", ev)
    assert claims_of(client, case_id)["payment_destination"]["state"] == "CONFLICTING"
    client.delete(f"/cases/{case_id}/facts/payment_method")
    assert claims_of(client, case_id)["payment_destination"]["state"] == "REVIEW_NEEDED"


def test_listing_silent_is_not_a_conflict(client, outbox):
    sign_in(client, outbox)
    case_id = create(client, deposit=None).json()["id"]
    link = client.post(f"/cases/{case_id}/evidence-requests", json={"scopes": ["price_and_term"]}).json()["link"]
    submit(client, link.rsplit("/r/", 1)[1], [("price_and_term", "terms.pdf", PDF)])
    ev = client.get(f"/cases/{case_id}/evidence").json()[0]["id"]
    body = put(client, case_id, "deposit", "500", ev).json()
    assert (body["result"], body["listed"]) == ("listing_silent", None)
    assert claims_of(client, case_id)["price_and_term"]["state"] == "EVIDENCE_SUBMITTED"


def test_manual_review_beats_a_mismatch(client, outbox):
    case_id, ev = case_with_file(client, outbox)
    client.patch(f"/cases/{case_id}/claims/price_and_term", json={"state": "REVIEW_NEEDED", "rationale": "Asked about the rent"})
    put(client, case_id, "monthly_rent", "1100", ev)
    claim = claims_of(client, case_id)["price_and_term"]
    assert (claim["state"], claim["reviewer"]) == ("REVIEW_NEEDED", "user")
    client.delete(f"/cases/{case_id}/claims/price_and_term/review")
    assert claims_of(client, case_id)["price_and_term"]["state"] == "CONFLICTING"


def test_list_is_in_field_order(client, outbox):
    case_id, ev = case_with_file(client, outbox)
    for field, value in [("payment_method", "Zelle"), ("address", OFFER["address"]), ("monthly_rent", "850")]:
        put(client, case_id, field, value, ev)
    assert [f["field"] for f in client.get(f"/cases/{case_id}/facts").json()] == ["address", "monthly_rent", "payment_method"]


@pytest.mark.parametrize("value,detail", [("about 900", "Enter an amount"), ("", "Enter what the file says")])
def test_bad_values_are_refused(client, outbox, value, detail):
    case_id, ev = case_with_file(client, outbox)
    res = put(client, case_id, "monthly_rent", value, ev)
    assert res.status_code == 422 and detail in res.json()["detail"]


def test_unknown_field_is_refused(client, outbox):
    case_id, ev = case_with_file(client, outbox)
    assert put(client, case_id, "landlord_name", "x", ev).status_code == 422


def test_file_must_be_from_this_case(client, outbox):
    case_id, _ = case_with_file(client, outbox)
    res = put(client, case_id, "monthly_rent", "900", str(uuid.uuid4()))
    assert res.status_code == 422 and res.json()["detail"] == "That file isn't part of this case."


def test_someone_elses_file_gets_the_same_answer(client, outbox):
    _, theirs = case_with_file(client, outbox)
    as_other_user(client, outbox)
    mine = create(client).json()["id"]
    res = put(client, mine, "monthly_rent", "900", theirs)
    assert res.status_code == 422 and res.json()["detail"] == "That file isn't part of this case."


def test_blocked_file_cannot_be_used(client, outbox):
    case_id, ev = case_with_file(client, outbox, EVIL_PDF)
    res = put(client, case_id, "monthly_rent", "900", ev)
    assert res.status_code == 422 and "passed the virus check" in res.json()["detail"]


def test_audited_without_the_value(client, db, outbox):
    case_id, ev = case_with_file(client, outbox)
    put(client, case_id, "address", "999 Secret Lane", ev)
    client.delete(f"/cases/{case_id}/facts/address")
    events = db.scalars(select(AuditEvent).where(AuditEvent.action.in_(["fact.recorded", "fact.removed"]))).all()
    assert [e.detail for e in events] == [{"field": "address"}, {"field": "address"}]
    assert all("Secret" not in str(e.detail) for e in events)
    descriptions = [a["description"] for a in client.get(f"/cases/{case_id}/activity").json()]
    assert "Noted what a file says about the address" in descriptions
    assert "Removed your note about the address" in descriptions
    assert 'Proofly marked "The unit exists" as conflicting' in descriptions


def test_deleting_the_case_removes_facts_at_once(client, db, outbox):
    case_id, ev = case_with_file(client, outbox)
    put(client, case_id, "address", "999 Secret Lane", ev)
    client.delete(f"/cases/{case_id}")
    assert db.scalars(select(CaseFact).where(CaseFact.case_id == uuid.UUID(case_id))).all() == []