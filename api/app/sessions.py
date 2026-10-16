"""Staying signed in (Week 4, Day 4).

After a sign-in link is used, the browser gets an HttpOnly cookie holding a
random session token. JavaScript can't read it, and only its hash is stored.
`current_user` is the dependency every protected endpoint uses.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import User, UserSession
from app.security import hash_token, new_token

# Avoid a database write on every request; refresh "last seen" at most this often.
LAST_SEEN_RESOLUTION = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_session(db: Session, user: User, response: Response, settings: Settings) -> None:
    """Create a session row and set the cookie. Caller commits."""
    token = new_token()
    now = _now()
    expires = now + timedelta(days=settings.session_ttl_days)
    db.add(UserSession(user_id=user.id, token_hash=hash_token(token), created_at=now, expires_at=expires, last_seen_at=now))
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=int(timedelta(days=settings.session_ttl_days).total_seconds()),
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name, path="/", httponly=True, secure=settings.is_production, samesite="lax"
    )


def _active_session(db: Session, token: str | None) -> UserSession | None:
    if not token:
        return None
    return db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > _now(),
        )
    )


def current_session(
    request: Request,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UserSession:
    session = _active_session(db, request.cookies.get(settings.session_cookie_name))
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in.")
    now = _now()
    if session.last_seen_at is None or now - session.last_seen_at > LAST_SEEN_RESOLUTION:
        session.last_seen_at = now
        db.commit()
    return session


def current_user(session: UserSession = Depends(current_session)) -> User:
    return session.user