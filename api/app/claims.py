"""Claim reviews (Week 4, Day 6): record your own assessment of a claim.

PATCH  /cases/{case_id}/claims/{claim_type}         record a review (state + reason)
DELETE /cases/{case_id}/claims/{claim_type}/review  undo it; the rules take over again

Every review keeps its provenance: who made it, when, and why. The audit log
records the change of state, but not the reason text, which may be personal.

"Supported" always has to name the evidence behind it (spec section 08).
Evidence arrives in Week 6, so until then a review can only mark a claim
"needs review" or "conflicting".
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.access import owned_case
from app.cases import CaseOut, to_case_out
from app.db import get_session
from app.domain import CLAIM_TYPES
from app.models import AuditEvent, Case, Claim, User
from app.sessions import current_user

router = APIRouter(prefix="/cases/{case_id}/claims", tags=["claims"])

ClaimType = Literal[CLAIM_TYPES]  # type: ignore[valid-type]

# States a person may set by hand. UNCHECKED and EVIDENCE_SUBMITTED are only ever
# set by the system.
ReviewState = Literal["REVIEW_NEEDED", "SUPPORTED", "CONFLICTING"]

SUPPORTED_NEEDS_EVIDENCE = (
    "A claim can only be marked supported by naming the evidence behind it. "
    "Evidence uploads aren't available yet."
)


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    state: ReviewState
    rationale: str = Field(min_length=1, max_length=1000, description="Why. Kept with the claim.")


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
    if body.state == "SUPPORTED":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=SUPPORTED_NEEDS_EVIDENCE)

    claim = _claim(kase, claim_type)
    previous = claim.state
    claim.state = body.state
    claim.rationale = body.rationale
    claim.reviewer = "user"
    claim.reviewed_by_id = user.id
    claim.updated_at = datetime.now(timezone.utc)

    db.add(AuditEvent(
        case_id=kase.id,
        actor_type="user",
        actor_user_id=user.id,
        action="claim.reviewed",
        detail={"claim_type": claim_type, "from": previous, "to": body.state},
    ))
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
        # Until the rules engine (Week 7) re-evaluates, a cleared claim goes back to unchecked.
        claim.state = "UNCHECKED"
        claim.rationale = None
        claim.reviewer = "rules"
        claim.reviewed_by_id = None
        claim.updated_at = datetime.now(timezone.utc)
        db.add(AuditEvent(
            case_id=kase.id,
            actor_type="user",
            actor_user_id=user.id,
            action="claim.review_cleared",
            detail={"claim_type": claim_type, "from": previous, "to": "UNCHECKED"},
        ))
        db.commit()
        db.refresh(kase)
    return to_case_out(kase)