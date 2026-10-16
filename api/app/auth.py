"""Email magic-link sign-in (Week 4, Day 3).

1. POST /auth/magic-link  {email}  emails a one-time link (prints it in development).
2. POST /auth/verify      {token}  uses the link and signs the person in (sets a session cookie).
3. GET  /auth/me                   who is signed in.
4. POST /auth/logout               signs this browser out.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.email import EmailSender, get_email_sender, magic_link_email
from app.audit import record
from app.models import LoginToken, User, UserSession
from app.security import hash_token, new_token, normalize_email
from app.sessions import clear_session_cookie, current_session, current_user, start_session

router = APIRouter(prefix="/auth", tags=["auth"])


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkResponse(BaseModel):
    status: str = "sent"
    message: str = "If that address can receive email, a sign-in link is on its way."


class VerifyRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class UserOut(BaseModel):
    id: UUID
    email: str


class VerifyResponse(BaseModel):
    user: UserOut
    new_account: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/magic-link", status_code=status.HTTP_202_ACCEPTED, response_model=MagicLinkResponse)
def request_magic_link(
    body: MagicLinkRequest,
    db: Session = Depends(get_session),
    sender: EmailSender = Depends(get_email_sender),
    settings: Settings = Depends(get_settings),
) -> MagicLinkResponse:
    """Always answers the same way, so nobody can use this to learn who has an account."""
    email = normalize_email(body.email)
    now = _now()

    recent = db.scalar(
        select(func.count()).select_from(LoginToken).where(
            LoginToken.email == email, LoginToken.created_at > now - timedelta(hours=1)
        )
    )
    if recent >= settings.magic_link_hourly_limit:
        return MagicLinkResponse()

    token = new_token()
    db.add(LoginToken(
        email=email,
        token_hash=hash_token(token),
        created_at=now,
        expires_at=now + timedelta(minutes=settings.magic_link_ttl_minutes),
    ))
    db.commit()

    link = f"{settings.web_base_url.rstrip('/')}/auth/verify?token={token}"
    sender.send(magic_link_email(email, link, settings.magic_link_ttl_minutes))
    return MagicLinkResponse()


@router.post("/verify", response_model=VerifyResponse)
def verify_magic_link(
    body: VerifyRequest,
    response: Response,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> VerifyResponse:
    now = _now()
    # Mark the token used in the same statement that checks it, so a link
    # can't be used twice even if two requests arrive at the same moment.
    email = db.scalar(
        update(LoginToken)
        .where(
            LoginToken.token_hash == hash_token(body.token),
            LoginToken.used_at.is_(None),
            LoginToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(LoginToken.email)
    )
    if email is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This sign-in link is invalid, expired, or already used. Request a new one.",
        )

    user = db.scalar(select(User).where(User.email == email))
    new_account = user is None
    if user is None:
        user = User(email=email)
        db.add(user)
    user.last_login_at = now
    db.flush()

    record(db, "auth.signed_up" if new_account else "auth.signed_in", actor_user_id=user.id, method="magic_link")
    start_session(db, user, response, settings)
    db.commit()
    return VerifyResponse(user=UserOut(id=user.id, email=user.email), new_account=new_account)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session: UserSession = Depends(current_session),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    session.revoked_at = _now()
    record(db, "auth.signed_out", actor_user_id=session.user_id)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    clear_session_cookie(response, settings)
    return response