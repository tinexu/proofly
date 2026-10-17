"""Evidence-request endpoints (Week 6, Day 2).

For the renter (signed in, own case only):
  POST /cases/{case_id}/evidence-requests                        create a link (shown once)
  GET  /cases/{case_id}/evidence-requests                        list links and their status
  POST /cases/{case_id}/evidence-requests/{request_id}/revoke    close a link early

For the subletter (no account):
  POST /evidence-requests/lookup  {token}   what a link asks for, if it's still open

The lookup takes the token in the body, not the URL, so it never lands in
server access logs. Every closed or unknown link gets the same 404, so a link
can't be used to learn anything about the case.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.access import owned_case
from app.audit import CLAIM_LABEL
from app.config import Settings, get_settings
from app.db import get_session
from app.domain import CLAIM_TYPES
from app.evidence_requests import (
    DEFAULT_EXPIRY_HOURS,
    EXPIRY_HOURS,
    EvidenceRequestError,
    create_request,
    find_open_by_token,
    list_for_case,
    revoke,
    status_of,
)
from app.models import Case, EvidenceRequest, User
from app.sessions import current_user

owner_router = APIRouter(prefix="/cases/{case_id}/evidence-requests", tags=["evidence requests"])
public_router = APIRouter(prefix="/evidence-requests", tags=["evidence requests (subletter)"])

ClaimType = Literal[CLAIM_TYPES]  # type: ignore[valid-type]
ExpiryHours = Literal[EXPIRY_HOURS]  # type: ignore[valid-type]

# What the subletter is asked for, per claim (kept in step with web/lib/content.ts).
REQUEST_PROMPTS = {
    "property_existence": "A short live video or recent photo that shows the unit number or building entrance.",
    "person_unit_relationship": "A lease excerpt showing your name and the unit address. Cover rent amounts, signatures and ID numbers if you prefer.",
    "sublet_authorization": "Any written permission to sublet from the landlord or property manager, or the lease clause about subletting.",
    "price_and_term": "A message or document confirming the monthly rent, deposit, move-in and move-out dates.",
    "payment_destination": "How and to whom the deposit and rent would be paid.",
}

LINK_NOT_VALID = "This link isn't valid or has expired. Ask the person who sent it for a new one."


# ---------------------------------------------------------------------------
# Shapes


class RequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scopes: list[ClaimType] = Field(min_length=1, max_length=5)
    expires_in_hours: ExpiryHours = DEFAULT_EXPIRY_HOURS


class RequestOut(BaseModel):
    id: UUID
    scopes: list[str]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    responded_at: datetime | None
    status: Literal["open", "responded", "expired", "revoked"]


class RequestCreated(RequestOut):
    link: str = Field(description="Send this to the subletter. It's shown only now and can't be retrieved later.")


class TokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=200)


class AskedItem(BaseModel):
    type: str
    label: str
    prompt: str


class PublicRequestOut(BaseModel):
    """All a subletter sees: what's asked and until when. Nothing about the renter or case."""

    items: list[AskedItem]
    expires_at: datetime


def to_out(req: EvidenceRequest) -> RequestOut:
    return RequestOut(
        id=req.id, scopes=list(req.scopes), created_at=req.created_at, expires_at=req.expires_at,
        revoked_at=req.revoked_at, responded_at=req.responded_at, status=status_of(req),
    )


# ---------------------------------------------------------------------------
# Renter endpoints


@owner_router.post("", status_code=status.HTTP_201_CREATED, response_model=RequestCreated)
def create(
    body: RequestCreate,
    kase: Case = Depends(owned_case),
    user: User = Depends(current_user),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RequestCreated:
    try:
        created = create_request(db, kase, user, list(body.scopes), body.expires_in_hours)
    except EvidenceRequestError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from e
    db.commit()
    link = f"{settings.web_base_url.rstrip('/')}/r/{created.token}"
    return RequestCreated(**to_out(created.request).model_dump(), link=link)


@owner_router.get("", response_model=list[RequestOut])
def list_requests(kase: Case = Depends(owned_case), db: Session = Depends(get_session)) -> list[RequestOut]:
    return [to_out(r) for r in list_for_case(db, kase.id)]


@owner_router.post("/{request_id}/revoke", response_model=RequestOut)
def revoke_request(
    request_id: UUID,
    kase: Case = Depends(owned_case),
    user: User = Depends(current_user),
    db: Session = Depends(get_session),
) -> RequestOut:
    """Safe to repeat: revoking a link that's already closed changes nothing."""
    req = db.get(EvidenceRequest, request_id)
    if req is None or req.case_id != kase.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
    if revoke(db, req, user):
        db.commit()
    return to_out(req)


# ---------------------------------------------------------------------------
# Subletter endpoint (no sign-in)


@public_router.post("/lookup", response_model=PublicRequestOut)
def lookup(body: TokenBody, db: Session = Depends(get_session)) -> PublicRequestOut:
    req = find_open_by_token(db, body.token)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=LINK_NOT_VALID)
    return PublicRequestOut(
        items=[AskedItem(type=t, label=CLAIM_LABEL[t], prompt=REQUEST_PROMPTS[t]) for t in req.scopes],
        expires_at=req.expires_at,
    )