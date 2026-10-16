"""Database tables (spec section 10). Day 2: users, cases, claims, audit events.

Evidence, evidence requests and uploads arrive in Week 6.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain import (
    AUDIT_ACTORS,
    CASE_STATUSES,
    CLAIM_REVIEWERS,
    CLAIM_STATES,
    CLAIM_TYPES,
    CLAIMED_ROLES,
    DECISIONS,
    PERMISSION_CLAIMS,
    PLATFORMS,
    check_in,
)

# Predictable constraint names make migrations reviewable and reversible.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _uuid_pk() -> Mapped[uuid.UUID]:
    # Random UUIDs: case IDs must not be guessable (spec section 11).
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Stored lower-cased by the app; unique so one email = one account.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cases: Mapped[list["Case"]] = relationship(back_populates="owner")

    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Deletion (F07): marked deleted right away, then purged by a job (Day 8).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The offer as the renter entered it (S2).
    address: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    monthly_rent: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    deposit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="other", server_default="other")
    source_url: Mapped[str | None] = mapped_column(Text)
    claimed_role: Mapped[str] = mapped_column(String(16), nullable=False, default="not_stated", server_default="not_stated")
    contact_handle: Mapped[str | None] = mapped_column(Text)
    permission_claim: Mapped[str] = mapped_column(String(20), nullable=False, default="not_mentioned", server_default="not_mentioned")
    payment_method: Mapped[str | None] = mapped_column(Text)

    # The renter's decision (S6).
    decision: Mapped[str | None] = mapped_column(String(24))
    decision_note: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[User] = relationship(back_populates="cases")
    claims: Mapped[list["Claim"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(check_in("status", CASE_STATUSES), name="status_valid"),
        CheckConstraint(check_in("platform", PLATFORMS), name="platform_valid"),
        CheckConstraint(check_in("claimed_role", CLAIMED_ROLES), name="claimed_role_valid"),
        CheckConstraint(check_in("permission_claim", PERMISSION_CLAIMS), name="permission_claim_valid"),
        CheckConstraint(f"decision IS NULL OR {check_in('decision', DECISIONS)}", name="decision_valid"),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="dates_ordered"),
        CheckConstraint("monthly_rent IS NULL OR monthly_rent >= 0", name="rent_non_negative"),
        CheckConstraint("deposit IS NULL OR deposit >= 0", name="deposit_non_negative"),
        CheckConstraint("(status = 'deleted') = (deleted_at IS NOT NULL)", name="deleted_at_matches_status"),
    )


class Claim(Base):
    """One of the five claims per case, with who set its state and why."""

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="UNCHECKED", server_default="UNCHECKED")
    rationale: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(8), nullable=False, default="rules", server_default="rules")
    # Set when reviewer = 'user', so every manual decision has provenance.
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="claims")

    __table_args__ = (
        UniqueConstraint("case_id", "type", name="uq_claims_case_id_type"),
        CheckConstraint(check_in("type", CLAIM_TYPES), name="type_valid"),
        CheckConstraint(check_in("state", CLAIM_STATES), name="state_valid"),
        CheckConstraint(check_in("reviewer", CLAIM_REVIEWERS), name="reviewer_valid"),
        # A manual review always records a reason (spec: explainable, auditable).
        CheckConstraint("reviewer = 'rules' OR rationale IS NOT NULL", name="user_review_has_rationale"),
    )


class AuditEvent(Base):
    """Append-only record of who did what, when.

    case_id deliberately has no foreign key: when a case is purged, its
    "case deleted" event must survive. Never put personal details in `detail`;
    store IDs and field names, not values.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = _created_at()
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_type: Mapped[str] = mapped_column(String(12), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    __table_args__ = (
        CheckConstraint(check_in("actor_type", AUDIT_ACTORS), name="actor_type_valid"),
        Index("ix_audit_events_case_id_created_at", "case_id", "created_at"),
    )