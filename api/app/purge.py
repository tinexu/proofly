"""The purge job (Week 4, Day 8): permanently removes deleted data.

Run it on a schedule (for example hourly) in production, or by hand:

    python -m app.purge            # purge now
    python -m app.purge --dry-run  # only report what would be purged

It removes:
- cases deleted more than `case_purge_delay_hours` ago, with their claims
- sign-in links and sessions that ended more than `auth_record_retention_days` ago

Audit events are kept (they hold no personal details); each purged case gets a
"case.purged" event so the history shows when the data actually went away.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.audit import record
from app.config import Settings, get_settings
from app.models import Case, LoginToken, UserSession


@dataclass
class PurgeResult:
    cases: int = 0
    login_tokens: int = 0
    sessions: int = 0


def purge(db: Session, settings: Settings | None = None, now: datetime | None = None, dry_run: bool = False) -> PurgeResult:
    settings = settings or get_settings()
    now = now or datetime.now(timezone.utc)
    case_cutoff = now - timedelta(hours=settings.case_purge_delay_hours)
    auth_cutoff = now - timedelta(days=settings.auth_record_retention_days)
    result = PurgeResult()

    case_ids = list(db.scalars(
        select(Case.id).where(Case.status == "deleted", Case.deleted_at <= case_cutoff)
    ))
    result.cases = len(case_ids)

    token_filter = or_(LoginToken.used_at <= auth_cutoff, LoginToken.expires_at <= auth_cutoff)
    session_filter = or_(UserSession.revoked_at <= auth_cutoff, UserSession.expires_at <= auth_cutoff)
    result.login_tokens = len(list(db.scalars(select(LoginToken.id).where(token_filter))))
    result.sessions = len(list(db.scalars(select(UserSession.id).where(session_filter))))

    if dry_run:
        return result

    for case_id in case_ids:
        # Claims go with the case (ON DELETE CASCADE). Audit events stay.
        db.execute(delete(Case).where(Case.id == case_id))
        record(db, "case.purged", actor_type="system", case_id=case_id)
    db.execute(delete(LoginToken).where(token_filter))
    db.execute(delete(UserSession).where(session_filter))
    db.commit()
    return result


def main() -> None:
    from app.db import get_session

    parser = argparse.ArgumentParser(description="Permanently remove deleted Proofly data.")
    parser.add_argument("--dry-run", action="store_true", help="report what would be purged, change nothing")
    args = parser.parse_args()

    db = next(get_session())
    try:
        result = purge(db, dry_run=args.dry_run)
    finally:
        db.close()
    verb = "Would purge" if args.dry_run else "Purged"
    print(f"{verb}: {result.cases} case(s), {result.login_tokens} sign-in link(s), {result.sessions} session(s).")


if __name__ == "__main__":
    main()