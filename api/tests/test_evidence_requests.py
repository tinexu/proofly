"""Week 6, Day 1: evidence-request rules (no endpoints yet)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import AuditEvent, Case, EvidenceRequest, User
from app.evidence_requests import (
    EvidenceRequestError,
    clean_scopes,
    create_request,
    find_by_token,
    find_open_by_token,
    list_for_case,
    revoke,
    status_of,
)
from app.security import hash_token

NOW = datetime.now(timezone.utc)


@pytest.fixture
def owner(db) -> User:
    user = User(email="renter@example.edu")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def kase(db, owner) -> Case:
    c = Case(owner_id=owner.id, address="214 Elm St", monthly_rent=850)
    db.add(c)
    db.flush()
    return c


def make(db, kase, owner, scopes=("sublet_authorization",), hours=72, now=NOW):
    return create_request(db, kase, owner, list(scopes), hours, now=now)


# --- Scopes ---------------------------------------------------------------------------

def test_scopes_are_deduplicated_and_ordered():
    assert clean_scopes(["price_and_term", "property_existence", "price_and_term"]) == [
        "property_existence", "price_and_term",
    ]


@pytest.mark.parametrize("scopes", [[], ["landlord_vibes"], ["price_and_term", "ssn"]])
def test_bad_scopes_rejected(scopes):
    with pytest.raises(EvidenceRequestError):
        clean_scopes(scopes)


# --- Creating -----------------------------------------------------------------------

def test_create_request(db, kase, owner):
    created = make(db, kase, owner, ["person_unit_relationship", "sublet_authorization"])
    req = created.request
    assert req.case_id == kase.id and req.created_by_id == owner.id
    assert req.scopes == ["person_unit_relationship", "sublet_authorization"]
    assert req.expires_at - req.created_at == timedelta(hours=72)
    assert status_of(req, NOW) == "open"


def test_only_the_token_hash_is_stored(db, kase, owner):
    created = make(db, kase, owner)
    assert created.request.token_hash == hash_token(created.token)
    assert created.token not in created.request.token_hash
    assert len(created.token) >= 40  # 256 random bits


def test_each_link_is_different(db, kase, owner):
    assert make(db, kase, owner).token != make(db, kase, owner).token


@pytest.mark.parametrize("hours", [24, 72, 168])
def test_allowed_expiry_options(db, kase, owner, hours):
    req = make(db, kase, owner, hours=hours).request
    assert req.expires_at - req.created_at == timedelta(hours=hours)


@pytest.mark.parametrize("hours", [0, 1, 48, 169, 24 * 30])
def test_other_expiry_options_rejected(db, kase, owner, hours):
    with pytest.raises(EvidenceRequestError):
        make(db, kase, owner, hours=hours)


def test_creation_is_audited_without_the_token(db, kase, owner):
    created = make(db, kase, owner, ["price_and_term", "payment_destination"], hours=24)
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "evidence_request.created"))
    assert event.case_id == kase.id
    assert event.detail == {"scope_count": 2, "hours": 24}
    assert created.token not in str(event.detail)


# --- The database also enforces the rules -------------------------------------------

def _raw_insert(db, kase, scopes_sql, created, expires):
    db.execute(text(
        f"INSERT INTO evidence_requests (id, case_id, token_hash, scopes, created_at, expires_at) "
        f"VALUES (gen_random_uuid(), :case_id, :hash, {scopes_sql}, :created, :expires)"
    ), {"case_id": kase.id, "hash": "f" * 64, "created": created, "expires": expires})


@pytest.mark.parametrize("scopes_sql", ["ARRAY[]::varchar[]", "ARRAY['ssn']::varchar[]"])
def test_database_rejects_bad_scopes(db, kase, scopes_sql):
    with pytest.raises(IntegrityError):
        _raw_insert(db, kase, scopes_sql, NOW, NOW + timedelta(hours=1))
    db.rollback()


def test_database_rejects_links_longer_than_7_days(db, kase):
    with pytest.raises(IntegrityError):
        _raw_insert(db, kase, "ARRAY['price_and_term']::varchar[]", NOW, NOW + timedelta(days=8))
    db.rollback()


# --- Finding by link ----------------------------------------------------------------

def test_find_by_token(db, kase, owner):
    created = make(db, kase, owner)
    assert find_open_by_token(db, created.token, NOW).id == created.request.id


@pytest.mark.parametrize("token", ["", "made-up", "x" * 500])
def test_unknown_tokens_find_nothing(db, kase, owner, token):
    make(db, kase, owner)
    assert find_by_token(db, token) is None


def test_expired_link_is_not_open(db, kase, owner):
    created = make(db, kase, owner, hours=24)
    later = NOW + timedelta(hours=25)
    assert status_of(created.request, later) == "expired"
    assert find_open_by_token(db, created.token, later) is None
    assert find_by_token(db, created.token) is not None  # still known, just closed


def test_responded_link_is_not_open(db, kase, owner):
    created = make(db, kase, owner)
    created.request.responded_at = NOW
    assert status_of(created.request, NOW) == "responded"
    assert find_open_by_token(db, created.token, NOW) is None


def test_link_to_deleted_case_finds_nothing(db, kase, owner):
    created = make(db, kase, owner)
    kase.status, kase.deleted_at = "deleted", NOW
    db.flush()
    assert find_by_token(db, created.token) is None


# --- Revoking -------------------------------------------------------------------------

def test_revoke_closes_the_link(db, kase, owner):
    created = make(db, kase, owner)
    assert revoke(db, created.request, owner, NOW) is True
    assert status_of(created.request, NOW) == "revoked"
    assert find_open_by_token(db, created.token, NOW) is None
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "evidence_request.revoked")) is not None


def test_revoking_a_closed_link_changes_nothing(db, kase, owner):
    created = make(db, kase, owner, hours=24)
    assert revoke(db, created.request, owner, NOW + timedelta(days=2)) is False
    assert created.request.revoked_at is None


# --- Listing and deletion -------------------------------------------------------------

def test_list_newest_first(db, kase, owner):
    first = make(db, kase, owner, now=NOW - timedelta(hours=2)).request
    second = make(db, kase, owner, now=NOW - timedelta(hours=1)).request
    assert [r.id for r in list_for_case(db, kase.id)] == [second.id, first.id]


def test_purging_a_case_removes_its_requests(db, kase, owner):
    make(db, kase, owner)
    case_id = kase.id
    kase.status, kase.deleted_at = "deleted", NOW
    db.flush()
    db.delete(kase)
    db.flush()
    assert db.scalars(select(EvidenceRequest).where(EvidenceRequest.case_id == case_id)).all() == []