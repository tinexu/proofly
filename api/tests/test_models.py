"""Day 2: the database itself refuses data that breaks the trust model."""

from datetime import date, datetime, timezone

import pytest
from alembic import command
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.domain import CLAIM_TYPES
from app.models import AuditEvent, Case, Claim, User
from tests.conftest import _test_url, alembic_config


def make_user(db, email="renter@example.edu") -> User:
    user = User(email=email)
    db.add(user)
    db.flush()
    return user


def make_case(db, owner: User, **overrides) -> Case:
    fields = {"owner_id": owner.id, "address": "214 Elm Street, Unit 3B"} | overrides
    kase = Case(**fields)
    db.add(kase)
    db.flush()
    return kase


def expect_rejected(db, obj) -> None:
    db.add(obj)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_migration_creates_all_tables(db_engine):
    tables = set(inspect(db_engine).get_table_names())
    assert {"users", "cases", "claims", "audit_events", "alembic_version"} <= tables


def test_migration_downgrades_and_upgrades_cleanly(db_engine):
    cfg = alembic_config(_test_url())
    command.downgrade(cfg, "base")
    assert "cases" not in inspect(db_engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "cases" in inspect(db_engine).get_table_names()


def test_case_ids_are_random_uuids(db):
    owner = make_user(db)
    a, b = make_case(db, owner), make_case(db, owner)
    assert a.id != b.id and a.id.version == 4


def test_case_defaults(db):
    kase = make_case(db, make_user(db))
    db.refresh(kase)
    assert kase.status == "active"
    assert kase.platform == "other"
    assert kase.claimed_role == "not_stated"
    assert kase.deleted_at is None


def test_one_claim_of_each_type_per_case(db):
    kase = make_case(db, make_user(db))
    db.add_all(Claim(case_id=kase.id, type=t) for t in CLAIM_TYPES)
    db.flush()
    expect_rejected(db, Claim(case_id=kase.id, type="price_and_term"))


def test_unknown_claim_state_rejected(db):
    kase = make_case(db, make_user(db))
    expect_rejected(db, Claim(case_id=kase.id, type="price_and_term", state="SAFE"))


def test_unknown_claim_type_rejected(db):
    kase = make_case(db, make_user(db))
    expect_rejected(db, Claim(case_id=kase.id, type="landlord_vibes"))


def test_manual_review_requires_rationale(db):
    owner = make_user(db)
    kase = make_case(db, owner)
    expect_rejected(db, Claim(case_id=kase.id, type="sublet_authorization", state="CONFLICTING", reviewer="user", reviewed_by_id=owner.id))

    owner = make_user(db)
    kase = make_case(db, owner)
    ok = Claim(
        case_id=kase.id, type="sublet_authorization", state="CONFLICTING",
        reviewer="user", reviewed_by_id=owner.id, rationale="Called the property office myself.",
    )
    db.add(ok)
    db.flush()


def test_email_must_be_lowercase(db):
    expect_rejected(db, User(email="Renter@Example.edu"))


def test_email_unique(db):
    make_user(db, "same@example.edu")
    expect_rejected(db, User(email="same@example.edu"))


def test_move_out_before_move_in_rejected(db):
    owner = make_user(db)
    expect_rejected(db, Case(owner_id=owner.id, address="x", start_date=date(2027, 5, 1), end_date=date(2027, 1, 1)))


def test_negative_rent_rejected(db):
    owner = make_user(db)
    expect_rejected(db, Case(owner_id=owner.id, address="x", monthly_rent=-1))


def test_deleted_status_requires_deleted_at(db):
    owner = make_user(db)
    expect_rejected(db, Case(owner_id=owner.id, address="x", status="deleted"))


def test_purging_case_removes_claims_but_keeps_audit_trail(db):
    owner = make_user(db)
    kase = make_case(db, owner)
    db.add(Claim(case_id=kase.id, type="price_and_term"))
    db.add(AuditEvent(case_id=kase.id, actor_type="user", actor_user_id=owner.id, action="case.deleted"))
    db.flush()
    case_id = kase.id

    kase.status, kase.deleted_at = "deleted", datetime.now(timezone.utc)
    db.flush()
    db.delete(kase)
    db.flush()

    assert db.scalars(select(Claim).where(Claim.case_id == case_id)).all() == []
    events = db.scalars(select(AuditEvent).where(AuditEvent.case_id == case_id)).all()
    assert [e.action for e in events] == ["case.deleted"]


def test_unknown_audit_actor_rejected(db):
    expect_rejected(db, AuditEvent(actor_type="hacker", action="x"))