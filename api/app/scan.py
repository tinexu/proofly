"""Scanning evidence files (Week 6, Day 4).

New uploads are scanned right after they're saved. If the scanner was down,
they stay locked (`pending_scan`) and this job retries them:

    python -m app.scan              # scan everything still pending
    python -m app.scan --selftest   # check the scanner is up and catches the EICAR test file

In production, run `python -m app.scan` on a schedule (for example every few minutes).

Outcomes per file:
- clean      -> unlocked; the renter can download it
- infected   -> the file is deleted from storage at once; the row stays, marked blocked
- scan_error -> stays locked; retried by the next run
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record
from app.models import Case, Evidence
from app.scanner import EICAR, Scanner, get_scanner
from app.storage import Storage, StorageError, get_storage


@dataclass
class ScanSummary:
    clean: int = 0
    infected: int = 0
    errors: int = 0
    skipped: bool = False  # scanner unreachable, nothing attempted


def scan_pending(
    db: Session,
    storage: Storage,
    scanner: Scanner,
    evidence_ids: list[UUID] | None = None,
) -> ScanSummary:
    """Scan files that are pending (or failed before). Commits as it goes."""
    summary = ScanSummary()
    query = (
        select(Evidence)
        .join(Case, Case.id == Evidence.case_id)
        .where(Evidence.status.in_(("pending_scan", "scan_error")), Case.status == "active")
        .order_by(Evidence.uploaded_at)
    )
    if evidence_ids is not None:
        query = query.where(Evidence.id.in_(evidence_ids))
    pending = list(db.scalars(query))
    if not pending:
        return summary
    if not scanner.ping():
        summary.skipped = True
        return summary

    by_case: dict[UUID, ScanSummary] = {}
    for ev in pending:
        case_summary = by_case.setdefault(ev.case_id, ScanSummary())
        now = datetime.now(timezone.utc)
        try:
            data = storage.get(ev.storage_key)
        except StorageError:
            ev.status, ev.scanned_at = "scan_error", now
            summary.errors += 1
            continue
        result = scanner.scan(data)
        ev.scanned_at = now
        if result.verdict == "clean":
            ev.status = "clean"
            summary.clean += 1
            case_summary.clean += 1
        elif result.verdict == "infected":
            ev.status = "infected"
            try:
                storage.delete(ev.storage_key)  # never keep a known-bad file
            except StorageError:
                pass  # it's marked infected either way, so it can never be downloaded
            summary.infected += 1
            case_summary.infected += 1
        else:
            ev.status = "scan_error"
            summary.errors += 1
        db.commit()

    for case_id, s in by_case.items():
        if s.clean or s.infected:
            record(db, "evidence.scanned", actor_type="system", case_id=case_id,
                   clean_count=s.clean, infected_count=s.infected)
    db.commit()
    return summary


def selftest(scanner: Scanner) -> bool:
    if not scanner.ping():
        print("Scanner not reachable. Is the clamav container running? (docker compose up -d)")
        return False
    clean = scanner.scan(b"%PDF-1.7 harmless test")
    bad = scanner.scan(EICAR)
    print(f"Harmless file: {clean.verdict}")
    print(f"EICAR test file: {bad.verdict} {bad.detail}".rstrip())
    ok = clean.verdict == "clean" and bad.verdict == "infected"
    print("Scanner works." if ok else "Scanner is reachable but didn't give the expected answers.")
    return ok


def main() -> None:
    from app.db import get_session

    parser = argparse.ArgumentParser(description="Scan pending evidence files for viruses.")
    parser.add_argument("--selftest", action="store_true", help="check the scanner with the EICAR test file")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(0 if selftest(get_scanner()) else 1)

    db = next(get_session())
    try:
        s = scan_pending(db, get_storage(), get_scanner())
    finally:
        db.close()
    if s.skipped:
        print("Scanner not reachable; files stay locked. Try again once it's running.")
        sys.exit(1)
    print(f"Scanned: {s.clean} clean, {s.infected} infected (deleted), {s.errors} error(s) to retry.")


if __name__ == "__main__":
    main()