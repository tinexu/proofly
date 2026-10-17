"""Case export (Week 7, Day 4; spec F06 and S6).

  GET /cases/{case_id}/export                      Markdown summary, as a download
  GET /cases/{case_id}/export?include_notes=false  a version to share: leaves out your
                                                   notes, the subletter's contact and
                                                   the listing link

Built from the database, so it says exactly what Proofly has recorded: the
offer as listed, each claim with who set it and why, listing vs. files, files
received (with SHA-256 fingerprints), what has NOT been verified, the decision
and the activity log. It never says a sublet is safe; it always ends with the
reminder to verify independently.

Everything a person typed is escaped, so a note can't add links, images or
headings to the file.
"""

import re
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import owned_case
from app.audit import CLAIM_LABEL, DECISION_LABEL, describe, record
from app.db import get_session
from app.domain import CLAIM_TYPES, FACT_FIELDS
from app.fact_routes import to_fact_out
from app.facts import DATE_FIELDS, FACT_LABEL, MONEY_FIELDS
from app.models import AuditEvent, Case, CaseFact, Evidence, User
from app.rules import payment_concern
from app.sessions import current_user

router = APIRouter(prefix="/cases/{case_id}/export", tags=["export"])

DISCLAIMER = (
    "This summary is not a safety guarantee and not legal advice. It lists what was "
    "checked and what was not. Verify using contact details you found yourself before paying."
)

STATE = {
    "UNCHECKED": "Not checked yet",
    "EVIDENCE_SUBMITTED": "Evidence received, not reviewed",
    "REVIEW_NEEDED": "Needs review",
    "SUPPORTED": "Supported",
    "CONFLICTING": "Conflicting",
}

# Kept in step with web/lib/content.ts.
NOT_CONFIRMED = {
    "property_existence": "We have not confirmed this address or unit exists.",
    "person_unit_relationship": "We have not confirmed this person is on the lease or lives in the unit.",
    "sublet_authorization": "We have not confirmed the landlord or property manager allows this sublet.",
    "price_and_term": "We have not confirmed the rent, deposit and dates are consistent.",
    "payment_destination": "We have not confirmed who would receive your payment.",
}
CHECK_INDEPENDENTLY = {
    "property_existence": "Look up the address on a map and in your county's public property records.",
    "person_unit_relationship": "Ask for a live video walkthrough where they show the unit door and number.",
    "sublet_authorization": "Find the landlord or property manager's phone or email yourself and ask whether this unit can be sublet for your dates.",
    "price_and_term": "Get rent, deposit, dates and utilities in writing, in one place, and compare them with the listing.",
    "payment_destination": "Pay only after you've confirmed the unit and the sublet with the landlord or property manager.",
}
ROLE = {
    "leaseholder": "Says they're the leaseholder",
    "roommate": "Says they're a roommate on the lease",
    "manager": "Says they manage the property",
    "not_stated": "Didn't say",
}
PERMISSION = {
    "says_approved": "Says the landlord approved it",
    "says_not_needed": "Says approval isn't needed",
    "not_mentioned": "Didn't mention it",
}
PLATFORM = {
    "facebook": "Facebook", "instagram": "Instagram", "reddit": "Reddit",
    "discord": "Discord", "group_chat": "Group chat", "other": "Other",
}
SCAN = {
    "pending_scan": "still being checked for viruses",
    "clean": "passed the virus check",
    "infected": "blocked by the virus check and deleted",
    "scan_error": "couldn't be checked for viruses",
}
RESULT = {"matches": "Matches", "differs": "**Differs**", "listing_silent": "Listing didn't say"}


# ---------------------------------------------------------------------------
# Formatting

# Enough to stop links, images, HTML, code and emphasis. Typed text never starts a line,
# so "#", "-" and "1." can't become headings or lists.
_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>|~])")


def esc(text: object) -> str:
    """Make typed text inert in Markdown: one line, every special character escaped."""
    one_line = re.sub(r"\s+", " ", str(text)).strip()
    return _MD_SPECIAL.sub(r"\\\1", one_line)


def money(v: object) -> str:
    if v is None or v == "":
        return "not stated"
    amount = Decimal(str(v))
    return f"${amount:,.0f}" if amount == amount.to_integral() else f"${amount:,.2f}"


def day(v: date | datetime | str | None) -> str:
    if v is None or v == "":
        return "not stated"
    if isinstance(v, str):
        v = date.fromisoformat(v)
    return f"{v:%b} {v.day}, {v.year}"


def when(v: datetime) -> str:
    v = v.astimezone(timezone.utc)
    return f"{day(v)}, {v:%H:%M} UTC"


def fact_value(field: str, v: object) -> str:
    if v is None or v == "":
        return "not stated"
    if field in MONEY_FIELDS:
        return money(v)
    if field in DATE_FIELDS:
        return day(v if isinstance(v, (date, str)) else str(v))
    return esc(v)


# ---------------------------------------------------------------------------
# Building the summary


def build_summary(db: Session, kase: Case, include_notes: bool = True, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    files = list(db.scalars(select(Evidence).where(Evidence.case_id == kase.id).order_by(Evidence.uploaded_at)))
    by_id = {f.id: f for f in files}
    order = {f: i for i, f in enumerate(FACT_FIELDS)}
    facts = sorted(db.scalars(select(CaseFact).where(CaseFact.case_id == kase.id)), key=lambda f: order[f.field])
    compared = [(f, to_fact_out(kase, f)) for f in facts]
    claims = {c.type: c for c in kase.claims}
    events = db.scalars(select(AuditEvent).where(AuditEvent.case_id == kase.id).order_by(AuditEvent.created_at))

    out: list[str] = []
    add = out.append
    add("# Proofly case summary")
    add("")
    add(f"Generated {when(now)}. Case created {when(kase.created_at)}.")
    if not include_notes:
        add("")
        add("This copy leaves out the renter's private notes, the subletter's contact details and the listing link.")
    add("")
    add(f"> {DISCLAIMER}")
    add("")

    add("## The offer as listed")
    add("")
    add(f"- Address: {esc(kase.address)}")
    dates = "not stated" if not (kase.start_date or kase.end_date) else f"{day(kase.start_date)} to {day(kase.end_date)}"
    add(f"- Dates: {dates}")
    add(f"- Monthly rent: {money(kase.monthly_rent)}")
    add(f"- Deposit: {money(kase.deposit)}")
    add(f"- Payment requested: {esc(kase.payment_method) if kase.payment_method else 'not stated'}")
    add(f"- Found on: {PLATFORM.get(kase.platform, 'Other')}")
    if include_notes and kase.source_url:
        add(f"- Listing link: {esc(kase.source_url)}")
    add(f"- The subletter: {ROLE.get(kase.claimed_role, ROLE['not_stated'])}")
    if include_notes and kase.contact_handle:
        add(f"- Contact: {esc(kase.contact_handle)}")
    add(f"- Permission to sublet: {PERMISSION.get(kase.permission_claim, PERMISSION['not_mentioned'])}")
    add("")

    add("## Claims")
    for claim_type in CLAIM_TYPES:
        claim = claims[claim_type]
        add("")
        add(f"### {CLAIM_LABEL[claim_type]}: {STATE[claim.state]}")
        add("")
        if claim.reviewer == "user":
            add(f"- Set by: the renter, {when(claim.updated_at)}")
        else:
            add("- Set by: Proofly's rules (no one has reviewed this claim by hand)")
        if claim.state == "SUPPORTED":
            f = by_id.get(claim.supporting_evidence_id)
            add(f"- Based on the renter's review of: {esc(f.original_name) if f else 'a file'}")
        if claim.rationale and (claim.reviewer == "rules" or include_notes):
            label = "Renter's note" if claim.reviewer == "user" else "Why"
            add(f"- {label}: {esc(claim.rationale)}")
        if claim.state == "SUPPORTED":
            add("- Not confirmed: whether that file is genuine, current, or about this unit. Proofly doesn't read files.")
        else:
            add(f"- {NOT_CONFIRMED[claim_type]}")
    add("")

    add("## Listing vs. files")
    add("")
    if compared:
        add("| Detail | Listing says | A file says | File | Result |")
        add("|---|---|---|---|---|")
        for fact, cmp in compared:
            f = by_id.get(fact.evidence_id)
            add(
                f"| {FACT_LABEL[fact.field].capitalize()} | {fact_value(fact.field, cmp.listed)} | "
                f"{fact_value(fact.field, fact.value)} | {esc(f.original_name) if f else ''} | {RESULT[cmp.result]} |"
            )
        add("")
        add("The renter noted what each file says; Proofly compared it with the listing.")
    else:
        add("Nothing noted from files yet, so nothing has been compared. That doesn't mean everything matches.")
    add("")

    concern = payment_concern(kase.payment_method)
    if concern:
        add("## Payment")
        add("")
        add(concern)
        add("")

    add("## What has NOT been verified")
    add("")
    for claim_type in CLAIM_TYPES:
        claim = claims[claim_type]
        if claim.state == "SUPPORTED":
            add(f"- {CLAIM_LABEL[claim_type]}: supported by the renter's review of one file. Not confirmed: whether that file is genuine, current, or about this unit.")
        else:
            add(f"- {NOT_CONFIRMED[claim_type]}")
    add("")

    unconfirmed = [t for t in CLAIM_TYPES if claims[t].state != "SUPPORTED"]
    if unconfirmed:
        add("## How to check independently")
        add("")
        for claim_type in unconfirmed:
            add(f"- {CLAIM_LABEL[claim_type]}: {CHECK_INDEPENDENTLY[claim_type]}")
        add("")

    add("## Files received")
    add("")
    if files:
        for f in files:
            line = f"- {esc(f.original_name)} (for \"{CLAIM_LABEL[f.claim_type]}\"), {SCAN[f.status]}, received {when(f.uploaded_at)}"
            if f.status == "clean":
                line += f". SHA-256: `{f.sha256}`"
            add(line)
        add("")
        add("A SHA-256 fingerprint lets you check later that a downloaded file is the same one.")
    else:
        add("No files received.")
    add("")

    add("## Decision")
    add("")
    add(f"- {DECISION_LABEL[kase.decision].capitalize()}" if kase.decision else "- No decision recorded")
    if include_notes and kase.decision_note:
        add(f"- Note: {esc(kase.decision_note)}")
    add("")

    add("## Activity")
    add("")
    for e in events:
        add(f"- {when(e.created_at)}: {esc(describe(e))}")
    add("")
    add("---")
    add("")
    add(DISCLAIMER)
    add("")
    return "\n".join(out)


@router.get("", response_class=Response, responses={200: {"content": {"text/markdown": {}}}})
def export_case(
    include_notes: bool = Query(True, description="False leaves out your notes, the contact and the listing link."),
    kase: Case = Depends(owned_case),
    user: User = Depends(current_user),
    db: Session = Depends(get_session),
) -> Response:
    now = datetime.now(timezone.utc)
    text = build_summary(db, kase, include_notes=include_notes, now=now)
    record(db, "case.exported", actor_user_id=user.id, case_id=kase.id, notes="included" if include_notes else "left_out")
    db.commit()
    name = f"proofly-case-summary-{now:%Y-%m-%d}{'' if include_notes else '-to-share'}.md"
    return Response(
        content=text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )