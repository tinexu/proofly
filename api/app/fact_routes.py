"""Facts from files, compared with the listing (Week 7, Day 3; spec S5 / F05).

  GET    /cases/{case_id}/facts           every fact noted so far, with the comparison
  PUT    /cases/{case_id}/facts/{field}   note what a file says (replaces any earlier note)
  DELETE /cases/{case_id}/facts/{field}   remove the note

Proofly doesn't read files: the renter opens one and notes what it says,
naming the file. Only clean files from the same case can be named. After each
change the rules engine runs, so a difference marks the related claim
"conflicting" unless the renter has reviewed that claim by hand.

The audit log records which field changed, never the value.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import owned_case
from app.audit import record
from app.db import get_session
from app.domain import FACT_CLAIM, FACT_FIELDS
from app.facts import FactValueError, Result, compare, parse
from app.models import Case, CaseFact, Evidence, User
from app.rules import apply_rules, listed_value
from app.sessions import current_user

router = APIRouter(prefix="/cases/{case_id}/facts", tags=["facts"])

FactField = Literal[FACT_FIELDS]  # type: ignore[valid-type]

NOT_IN_CASE = "That file isn't part of this case."
NOT_CLEAN = "Only files that passed the virus check can be used."


class FactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(max_length=200, description="What the file says. Money like 1200.00, dates as YYYY-MM-DD.")
    evidence_id: UUID = Field(description="The clean file from this case it comes from.")


class FactOut(BaseModel):
    field: str
    claim_type: str
    value: str
    listed: str | None
    result: Result
    evidence_id: UUID
    updated_at: datetime


def _listed_text(kase: Case, field: str) -> str | None:
    v = listed_value(kase, field)
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def to_fact_out(kase: Case, fact: CaseFact) -> FactOut:
    return FactOut(
        field=fact.field,
        claim_type=FACT_CLAIM[fact.field],
        value=fact.value,
        listed=_listed_text(kase, fact.field),
        result=compare(fact.field, listed_value(kase, fact.field), fact.value),
        evidence_id=fact.evidence_id,
        updated_at=fact.updated_at,
    )


def _find(db: Session, kase: Case, field: str) -> CaseFact | None:
    return db.scalar(select(CaseFact).where(CaseFact.case_id == kase.id, CaseFact.field == field))


@router.get("", response_model=list[FactOut])
def list_facts(kase: Case = Depends(owned_case), db: Session = Depends(get_session)) -> list[FactOut]:
    order = {f: i for i, f in enumerate(FACT_FIELDS)}
    facts = sorted(db.scalars(select(CaseFact).where(CaseFact.case_id == kase.id)), key=lambda f: order[f.field])
    return [to_fact_out(kase, f) for f in facts]


@router.put("/{field}", response_model=FactOut)
def record_fact(
    field: FactField,
    body: FactIn,
    kase: Case = Depends(owned_case),
    user: User = Depends(current_user),
    db: Session = Depends(get_session),
) -> FactOut:
    try:
        value = parse(field, body.value)
    except FactValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from None
    evidence = db.get(Evidence, body.evidence_id)
    if evidence is None or evidence.case_id != kase.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=NOT_IN_CASE)
    if evidence.status != "clean":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=NOT_CLEAN)

    fact = _find(db, kase, field)
    if fact is None:
        fact = CaseFact(case_id=kase.id, field=field, value=value, evidence_id=evidence.id)
        db.add(fact)
    fact.value, fact.evidence_id, fact.recorded_by_id = value, evidence.id, user.id
    fact.updated_at = datetime.now(timezone.utc)
    db.flush()
    record(db, "fact.recorded", actor_user_id=user.id, case_id=kase.id, field=field)
    apply_rules(db, kase)
    db.commit()
    return to_fact_out(kase, fact)


@router.delete("/{field}", status_code=status.HTTP_204_NO_CONTENT)
def remove_fact(
    field: FactField,
    kase: Case = Depends(owned_case),
    user: User = Depends(current_user),
    db: Session = Depends(get_session),
) -> Response:
    """Remove a note. Safe to repeat."""
    fact = _find(db, kase, field)
    if fact is not None:
        db.delete(fact)
        db.flush()
        record(db, "fact.removed", actor_user_id=user.id, case_id=kase.id, field=field)
        apply_rules(db, kase)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)