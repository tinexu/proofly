"""Cases (Week 4, Day 5): create, list and view your own cases.
Day 7 adds each case's activity log.

A case is one sublet offer being checked (S2). Creating a case also creates
its five claims, all starting at UNCHECKED. The rules engine arrives in Week 7.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import owned_case
from app.db import get_session
from app.domain import CLAIM_TYPES, CLAIMED_ROLES, DECISIONS, PERMISSION_CLAIMS, PLATFORMS
from app.audit import describe, record
from app.models import AuditEvent, Case, Claim, User
from app.sessions import current_user

router = APIRouter(prefix="/cases", tags=["cases"])

Money = Decimal

# ---------------------------------------------------------------------------
# Request and response shapes


class CaseCreate(BaseModel):
    """What the renter enters on S2. Mirrors the prototype's offer form."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    address: str = Field(min_length=1, max_length=300)
    start_date: date | None = None
    end_date: date | None = None
    monthly_rent: Money | None = Field(default=None, ge=0, le=100_000, decimal_places=2)
    deposit: Money | None = Field(default=None, ge=0, le=100_000, decimal_places=2)
    platform: Literal[PLATFORMS] = "other"  # type: ignore[valid-type]
    source_url: str | None = Field(default=None, max_length=2000)
    claimed_role: Literal[CLAIMED_ROLES] = "not_stated"  # type: ignore[valid-type]
    contact_handle: str | None = Field(default=None, max_length=200)
    permission_claim: Literal[PERMISSION_CLAIMS] = "not_mentioned"  # type: ignore[valid-type]
    payment_method: str | None = Field(default=None, max_length=300)

    @field_validator("source_url")
    @classmethod
    def _http_link_only(cls, v: str | None) -> str | None:
        # We store the link but never fetch it. Only plain web links are allowed.
        if not v:
            return None
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Must be a web link starting with http:// or https://")
        return v

    @model_validator(mode="after")
    def _enough_to_check(self) -> "CaseCreate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("The move-out date is before the move-in date.")
        if self.monthly_rent is None and not (self.start_date and self.end_date):
            raise ValueError("Add the monthly rent or the move-in and move-out dates.")
        return self


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    state: str
    rationale: str | None
    reviewer: str
    reviewed_by_id: UUID | None
    updated_at: datetime


class CaseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address: str
    created_at: datetime


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    address: str
    start_date: date | None
    end_date: date | None
    monthly_rent: Money | None
    deposit: Money | None
    platform: str
    source_url: str | None
    claimed_role: str
    contact_handle: str | None
    permission_claim: str
    payment_method: str | None
    decision: Literal[DECISIONS] | None  # type: ignore[valid-type]
    decision_note: str | None
    claims: list[ClaimOut]


class ActivityItem(BaseModel):
    at: datetime
    actor: Literal["you", "subletter", "rules", "system"]
    action: str
    description: str


ACTOR = {"user": "you", "subletter": "subletter", "rules": "rules", "system": "system"}


def to_case_out(kase: Case) -> CaseOut:
    order = {t: i for i, t in enumerate(CLAIM_TYPES)}
    out = CaseOut.model_validate(kase)
    out.claims = sorted(out.claims, key=lambda c: order[c.type])
    return out


# ---------------------------------------------------------------------------
# Endpoints


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CaseOut)
def create_case(
    body: CaseCreate,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> CaseOut:
    kase = Case(owner_id=user.id, **body.model_dump())
    kase.claims = [Claim(type=t) for t in CLAIM_TYPES]
    db.add(kase)
    db.flush()
    # Audit details hold IDs and categories only, never the address or contact.
    record(db, "case.created", actor_user_id=user.id, case_id=kase.id, platform=kase.platform)
    db.commit()
    db.refresh(kase)
    return to_case_out(kase)


@router.get("", response_model=list[CaseSummary])
def list_cases(db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[Case]:
    return list(db.scalars(
        select(Case)
        .where(Case.owner_id == user.id, Case.status == "active")
        .order_by(Case.created_at.desc())
    ))


@router.get("/{case_id}", response_model=CaseOut)
def get_case(kase: Case = Depends(owned_case)) -> CaseOut:
    return to_case_out(kase)


@router.get("/{case_id}/activity", response_model=list[ActivityItem])
def case_activity(kase: Case = Depends(owned_case), db: Session = Depends(get_session)) -> list[ActivityItem]:
    """The case's history, newest first, in plain words (the activity log on S3)."""
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.case_id == kase.id).order_by(AuditEvent.created_at.desc())
    )
    return [
        ActivityItem(at=e.created_at, actor=ACTOR[e.actor_type], action=e.action, description=describe(e))
        for e in events
    ]