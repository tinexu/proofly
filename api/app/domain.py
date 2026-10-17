"""Allowed values for the trust model (spec section 08).

Keep these in sync with web/lib/types.ts. The database enforces them with
CHECK constraints, so a typo can't slip a bad state into a claim.
"""

CLAIM_TYPES = (
    "property_existence",
    "person_unit_relationship",
    "sublet_authorization",
    "price_and_term",
    "payment_destination",
)

CLAIM_STATES = (
    "UNCHECKED",
    "EVIDENCE_SUBMITTED",
    "REVIEW_NEEDED",
    "SUPPORTED",
    "CONFLICTING",
)

# Who last set a claim's state: the rules engine, or the renter with a reason.
CLAIM_REVIEWERS = ("rules", "user")

PLATFORMS = ("facebook", "instagram", "reddit", "discord", "group_chat", "other")
CLAIMED_ROLES = ("leaseholder", "roommate", "manager", "not_stated")
PERMISSION_CLAIMS = ("says_approved", "says_not_needed", "not_mentioned")
DECISIONS = ("proceed_independent", "pause", "stop")

CASE_STATUSES = ("active", "deleted")

AUDIT_ACTORS = ("user", "subletter", "rules", "system")

# Uploaded evidence files start locked until a virus scan passes them (Week 6, Day 4).
EVIDENCE_STATUSES = ("pending_scan", "clean", "infected", "scan_error")
EVIDENCE_CONTENT_TYPES = ("application/pdf", "image/png", "image/jpeg", "image/webp", "image/heic")


def check_in(column: str, values: tuple[str, ...]) -> str:
    """SQL for a CHECK constraint limiting a column to the given values."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"