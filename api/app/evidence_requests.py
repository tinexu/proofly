"""Evidence requests (Week 6, Day 1; spec F03): the rules, without endpoints.

A request is a private link the renter sends to the subletter. It:
- asks only for the claims the renter picked (its scopes),
- expires after 24 hours, 3 days or 7 days,
- can be revoked at any time,
- accepts one reply, then closes.

The link's token is shown once, when the request is created. Only its hash is
stored, so the database can't be used to open links. Endpoints arrive on Day 2.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record
from app.domain import CLAIM_TYPES
from app.models import Case, EvidenceRequest, User
from app.security import hash_token, new_token

EXPIRY_HOURS = (24, 72, 168)
DEFAULT_EXPIRY_HOURS = 72

RequestStatus = Literal["open", "responded", "expired", "revoked"]


class EvidenceRequestError(ValueError):
    """A request that breaks the rules (bad scopes or expiry)."""


@dataclass
class CreatedRequest:
    request: EvidenceRequest
    token: str  # the only time the plain token exists; put it in the link and forget it


def _now() -> datetime:
    return datetime.now(timezone.utc)


def clean_scopes(scopes: list[str]) -> list[str]:
    """Known claim types only, no repeats, at least one, kept in the standard order."""
    unknown = [s for s in scopes if s not in CLAIM_TYPES]
    if unknown:
        raise EvidenceRequestError(f"Unknown claim type(s): {', '.join(unknown)}")
    picked = [t for t in CLAIM_TYPES if t in set(scopes)]
    if not picked:
        raise EvidenceRequestError("Pick at least one thing to ask for.")
    return picked


def create_request(
    db: Session,
    kase: Case,
    user: User,
    scopes: list[str],
    expires_in_hours: int = DEFAULT_EXPIRY_HOURS,
    now: datetime | None = None,
) -> CreatedRequest:
    """Add a new request to the session and log it. The caller commits."""
    if expires_in_hours not in EXPIRY_HOURS:
        raise EvidenceRequestError(f"Links can last {', '.join(str(h) for h in EXPIRY_HOURS)} hours.")
    now = now or _now()
    token = new_token()
    req = EvidenceRequest(
        case_id=kase.id,
        created_by_id=user.id,
        token_hash=hash_token(token),
        scopes=clean_scopes(scopes),
        created_at=now,
        expires_at=now + timedelta(hours=expires_in_hours),
    )
    db.add(req)
    db.flush()
    record(db, "evidence_request.created", actor_user_id=user.id, case_id=kase.id,
           scope_count=len(req.scopes), hours=expires_in_hours)
    return CreatedRequest(request=req, token=token)


def status_of(req: EvidenceRequest, now: datetime | None = None) -> RequestStatus:
    now = now or _now()
    if req.revoked_at is not None:
        return "revoked"
    if req.responded_at is not None:
        return "responded"
    if req.expires_at <= now:
        return "expired"
    return "open"


def find_by_token(db: Session, token: str) -> EvidenceRequest | None:
    """The request behind a link, if its case still exists. Any status; check `status_of`.

    A link to a deleted case looks exactly like a link that never existed.
    """
    if not token or len(token) > 200:
        return None
    return db.scalar(
        select(EvidenceRequest)
        .join(Case, Case.id == EvidenceRequest.case_id)
        .where(EvidenceRequest.token_hash == hash_token(token), Case.status == "active")
    )


def find_open_by_token(db: Session, token: str, now: datetime | None = None) -> EvidenceRequest | None:
    """The request behind a link only if it can still accept a reply."""
    req = find_by_token(db, token)
    return req if req is not None and status_of(req, now) == "open" else None


def list_for_case(db: Session, case_id: UUID) -> list[EvidenceRequest]:
    return list(db.scalars(
        select(EvidenceRequest).where(EvidenceRequest.case_id == case_id).order_by(EvidenceRequest.created_at.desc())
    ))


def revoke(db: Session, req: EvidenceRequest, user: User, now: datetime | None = None) -> bool:
    """Close a link early. Returns False (and changes nothing) if it was already closed."""
    if status_of(req, now) != "open":
        return False
    req.revoked_at = now or _now()
    record(db, "evidence_request.revoked", actor_user_id=user.id, case_id=req.case_id)
    return True