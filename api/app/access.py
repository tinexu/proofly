"""Owner-only access to cases (Week 4, Day 4).

Every case endpoint loads its case through `get_owned_case`. Someone else's
case, a deleted case and a case that never existed all give the same 404, so
a stranger can't even learn that a case ID exists.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Case, User
from app.sessions import current_user

NOT_FOUND = "Case not found."


def get_owned_case(db: Session, user: User, case_id: UUID) -> Case:
    kase = db.scalar(
        select(Case).where(Case.id == case_id, Case.owner_id == user.id, Case.status == "active")
    )
    if kase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return kase


def owned_case(
    case_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Case:
    """Dependency for routes like /cases/{case_id}. Used from Day 5 on."""
    return get_owned_case(db, user, case_id)