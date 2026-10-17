"""Claim reviews (Week 4, Day 6): record your own assessment of a claim.

PATCH  /cases/{case_id}/claims/{claim_type}         record a review (state + reason)
DELETE /cases/{case_id}/claims/{claim_type}/review  undo it; the rules take over again

Undoing a review hands the claim back to the rules engine (app/rules.py).

Every review keeps its provenance: who made it, when, and why. The audit log
records the change of state, but not the reason text, which may be personal.

"Supported" always has to name the evidence behind it (spec section 08), since
Week 7, Day 2: a clean file from the same case, plus your reason. Only a person can
mark a claim supported; the rules never do. It's your judgement of that one file,
never a safety rating of the sublet as a whole.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.access import owned_case
from app.audit import record
from app.cases import CaseOut, to_case_out
from app.db import get_session
from app.domain import CLAIM_TYPES
from app.models import Case, Claim, Evidence, User
from app.rules import apply_rules
from app.sessions import current_user

router = APIRouter(prefix="/cases/{case_id}/claims", tags=["claims"])

ClaimType = Literal[CLAIM_TYPES]  # type: ignore[valid-type]

# States a person may set by hand. UNCHECKED and EVIDENCE_SUBMITTED are only ever
# set by the system.
ReviewState = Literal["REVIEW_NEEDED", "SUPPORTED", "CONFLICTING"]

SUPPORTED_NEEDS_EVIDENCE = "Choose the file this is based on. \"Supported\" always names the evidence behind it."
ONLY_SUPPORTED_NAMES_EVIDENCE = "Only a \"supported\" review names a file."
NOT_IN_CASE = "That file isn't part of this case."
NOT_CLEAN = "Only files that passed the virus check can support a claim."


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    state: ReviewState
    rationale: str = Field(min_length=1, max_length=1000, description="Why. Kept with the claim.")
    evidence_id: UUID | None = Field(
        default=None, description='Required for "SUPPORTED": the clean file from this case the review is based on.'
    )


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _supporting_file(db: Session, kase: Case, body: ClaimReview) -> Evidence | None:
    """Check the named file. Returns it for SUPPORTED reviews, None otherwise."""
    if body.state != "SUPPORTED":
        if body.evidence_id is not None:
            raise _unprocessable(ONLY_SUPPORTED_NAMES_EVIDENCE)
        return None
    if body.evidence_id is None:
        raise _unprocessable(SUPPORTED_NEEDS_EVIDENCE)
    evidence = db.get(Evidence, body.evidence_id)
    if evidence is None or evidence.case_id != kase.id:
        raise _unprocessable(NOT_IN_CASE)  # same answer for "doesn't exist" and "someone else's"
    if evidence.status != "clean":
        raise _unprocessable(NOT_CLEAN)
    return evidence


def _claim(kase: Case, claim_type: str) -> Claim:
    claim = next((c for c in kase.claims if c.type == claim_type), None)
    if claim is None:  # every case has all five; this would mean corrupted data
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found.")
    return claim


@router.patch("/{claim_type}", response_model=CaseOut)
def review_claim(
    claim_type: ClaimType,
    body: ClaimReview,
    kase: Case = Depends(owned_case),
    user: User = Depends(current_user),
    db: Session = Depends(get_session),
) -> CaseOut:
    evidence = _supporting_file(db, kase, body)
    claim = _claim(kase, claim_type)
    previous = claim.state
    claim.state = body.state
    claim.rationale = body.rationale
    claim.supporting_evidence_id = evidence.id if evidence else None
    claim.reviewer = "user"
    claim.reviewed_by_id = user.id
    claim.updated_at = datetime.now(timezone.utc)

    record(db, "claim.reviewed", actor_user_id=user.id, case_id=kase.id,
           claim_type=claim_type, **{"from": previous, "to": body.state})
    db.commit()
    db.refresh(kase)
    return to_case_out(kase)


@router.delete("/{claim_type}/review", response_model=CaseOut)
def clear_review(
    claim_type: ClaimType,
    kase: Case = Depends(owned_case),
    user: User = Depends(current_user),
    db: Session = Depends(get_session),
) -> CaseOut:
    """Undo your review. Safe to repeat: clearing a claim with no review changes nothing."""
    claim = _claim(kase, claim_type)
    if claim.reviewer == "user":
        previous = claim.state
        claim.state = "UNCHECKED"  # placeholder; the rules decide below
        claim.rationale = None
        claim.reviewer = "rules"
        claim.reviewed_by_id = None
        claim.supporting_evidence_id = None
        claim.updated_at = datetime.now(timezone.utc)
        db.flush()
        apply_rules(db, kase)
        record(db, "claim.review_cleared", actor_user_id=user.id, case_id=kase.id,
               claim_type=claim_type, **{"from": previous, "to": claim.state})
        db.commit()
        db.refresh(kase)
    return to_case_out(kase)