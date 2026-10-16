"""The audit log (Week 4, Day 7).

Every change goes through `record`, which only accepts known detail keys with
short values. That makes it hard to log personal details (an address, an email,
a renter's note) by accident. The database also refuses to edit or delete
log rows (see migration 0004).

`describe` turns an event into the plain-language line shown in a case's
activity log.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent

# Keys allowed in `detail`, and nothing else. Values are short codes, never free text.
ALLOWED_DETAIL_KEYS = {"method", "platform", "claim_type", "from", "to", "decision", "scope_count", "hours"}
MAX_VALUE_LENGTH = 40


class AuditDetailError(ValueError):
    pass


def _check_detail(detail: dict) -> None:
    for key, value in detail.items():
        if key not in ALLOWED_DETAIL_KEYS:
            raise AuditDetailError(f"Audit detail key {key!r} isn't allowed. Add it to ALLOWED_DETAIL_KEYS if it's safe.")
        if not isinstance(value, (str, int, bool)) or (isinstance(value, str) and len(value) > MAX_VALUE_LENGTH):
            raise AuditDetailError(f"Audit detail {key!r} must be a short code, not free text.")


def record(
    db: Session,
    action: str,
    *,
    actor_type: str = "user",
    actor_user_id: UUID | None = None,
    case_id: UUID | None = None,
    **detail: str | int | bool,
) -> AuditEvent:
    """Add an audit event to the session. The caller commits with the change itself,
    so the change and its log entry are saved together or not at all."""
    _check_detail(detail)
    event = AuditEvent(
        action=action, actor_type=actor_type, actor_user_id=actor_user_id, case_id=case_id, detail=detail
    )
    db.add(event)
    return event


# ---------------------------------------------------------------------------
# Plain-language descriptions for the activity log

CLAIM_LABEL = {
    "property_existence": "The unit exists",
    "person_unit_relationship": "This person lives there or controls the lease",
    "sublet_authorization": "Subletting is allowed",
    "price_and_term": "Price and dates match",
    "payment_destination": "Where the money goes",
}

STATE_LABEL = {
    "UNCHECKED": "not checked yet",
    "EVIDENCE_SUBMITTED": "evidence received, not reviewed",
    "REVIEW_NEEDED": "needs review",
    "SUPPORTED": "supported",
    "CONFLICTING": "conflicting",
}


DECISION_LABEL = {
    "proceed_independent": "continue after confirming with the landlord",
    "pause": "pause until missing evidence arrives",
    "stop": "stop",
}


def describe(event: AuditEvent) -> str:
    d = event.detail or {}
    claim = CLAIM_LABEL.get(d.get("claim_type", ""), "a claim")
    to_state = STATE_LABEL.get(d.get("to", ""), d.get("to", ""))
    match event.action:
        case "case.created":
            return "Created the case"
        case "claim.reviewed":
            return f'Marked "{claim}" as {to_state}'
        case "claim.review_cleared":
            return f'Cleared your review of "{claim}"'
        case "case.decision_recorded":
            return f"Recorded a decision: {DECISION_LABEL.get(d.get('decision', ''), 'cleared')}"
        case "evidence_request.created":
            n = d.get("scope_count", 0)
            days = {24: "24 hours", 72: "3 days", 168: "7 days"}.get(d.get("hours", 0), "a few days")
            return f"Created an evidence link asking for {n} item{'s' if n != 1 else ''} (expires in {days})"
        case "evidence_request.revoked":
            return "Revoked an evidence link"
        case "case.deleted":
            return "Deleted the case"
        case "case.purged":
            return "Permanently removed the case's data"
        case _:
            return event.action.replace(".", " ").replace("_", " ").capitalize()