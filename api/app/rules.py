"""The rules engine (Week 7, Day 1; spec section 09: rules first, AI never decides).

Every rule is explicit and explainable. Rules only set claims that the renter
hasn't reviewed by hand (reviewer == "rules"); a manual review always wins.
Rules never mark a claim "SUPPORTED" on their own: that needs a person to
name the evidence behind it (Week 7, Day 2).

Current rules, in priority order for each claim:
1. a file says something different from the listing     -> CONFLICTING  (Week 7, Day 3)
2. payment_destination + a hard-to-reverse payment method -> REVIEW_NEEDED
3. any evidence that isn't blocked as unsafe            -> EVIDENCE_SUBMITTED
4. otherwise                                            -> UNCHECKED

`evaluate` is a pure function (easy to test). `apply_rules` writes the
results and logs each change as done by "rules".
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record
from app.domain import CLAIM_TYPES, FACT_CLAIM, FACT_FIELDS
from app.facts import FACT_LABEL, compare
from app.models import Case, CaseFact, Claim, Evidence

# Payment methods that are usually hard to reverse. Kept in step with web/lib/rules.ts.
HARD_TO_REVERSE = [
    (re.compile(r"wire|western union|moneygram", re.I), "a wire transfer"),
    (re.compile(r"gift ?card", re.I), "gift cards"),
    (re.compile(r"crypto|bitcoin|btc|usdt|\beth\b", re.I), "cryptocurrency"),
    (re.compile(r"zelle|venmo|cash ?app|paypal friends", re.I), "a person-to-person payment app"),
]


@dataclass(frozen=True)
class Outcome:
    state: str
    rationale: str | None


def payment_concern(payment_method: str | None) -> str | None:
    """A neutral explanation if the payment method is hard to reverse, else None."""
    for pattern, name in HARD_TO_REVERSE:
        if payment_method and pattern.search(payment_method):
            return (
                f"Payment was requested through {name}. These payments are usually hard to reverse "
                "if something goes wrong. Confirm the unit and the sublet with the landlord or "
                "property manager, using contact details you found yourself, before paying."
            )
    return None


def _join(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def mismatch_note(fields: list[str]) -> str:
    labels = [FACT_LABEL[f] for f in FACT_FIELDS if f in fields]
    verb = "differs" if len(labels) == 1 else "differ"
    return (
        f"What a file says about the {_join(labels)} {verb} from the listing. Ask the subletter "
        "why, and check with the landlord or property manager yourself."
    )


def evaluate(
    payment_method: str | None,
    evidence_by_claim: dict[str, int],
    mismatched_fields: list[str] | tuple[str, ...] = (),
) -> dict[str, Outcome]:
    """What the rules say for each claim.

    `evidence_by_claim` counts usable evidence per claim; `mismatched_fields`
    lists the facts (app/facts.py) where a file and the listing disagree.
    """
    concern = payment_concern(payment_method)
    out: dict[str, Outcome] = {}
    for claim_type in CLAIM_TYPES:
        mismatches = [f for f in mismatched_fields if FACT_CLAIM[f] == claim_type]
        if mismatches:
            out[claim_type] = Outcome("CONFLICTING", mismatch_note(mismatches))
        elif claim_type == "payment_destination" and concern:
            out[claim_type] = Outcome("REVIEW_NEEDED", concern)
        elif evidence_by_claim.get(claim_type, 0) > 0:
            out[claim_type] = Outcome(
                "EVIDENCE_SUBMITTED",
                "The subletter sent a file for this. Open it and judge what it shows; a file alone doesn't confirm the claim.",
            )
        else:
            out[claim_type] = Outcome("UNCHECKED", None)
    return out


def listed_value(kase: Case, field: str) -> object:
    """What the listing (the case as entered) says for a fact field."""
    return getattr(kase, field)


def mismatched_fields(db: Session, kase: Case) -> list[str]:
    facts = db.scalars(select(CaseFact).where(CaseFact.case_id == kase.id))
    return [f.field for f in facts if compare(f.field, listed_value(kase, f.field), f.value) == "differs"]


def apply_rules(db: Session, kase: Case) -> list[str]:
    """Re-evaluate the case's rule-owned claims. Returns the claim types that changed. Caller commits."""
    usable: dict[str, int] = {}
    for claim_type in db.scalars(
        select(Evidence.claim_type).where(Evidence.case_id == kase.id, Evidence.status != "infected")
    ):
        usable[claim_type] = usable.get(claim_type, 0) + 1

    outcomes = evaluate(kase.payment_method, usable, mismatched_fields(db, kase))
    now = datetime.now(timezone.utc)
    changed: list[str] = []
    for claim in db.scalars(select(Claim).where(Claim.case_id == kase.id, Claim.reviewer == "rules")):
        outcome = outcomes[claim.type]
        if (claim.state, claim.rationale) == (outcome.state, outcome.rationale):
            continue
        previous = claim.state
        claim.state, claim.rationale, claim.updated_at = outcome.state, outcome.rationale, now
        changed.append(claim.type)
        if previous != outcome.state:
            record(db, "claim.rules_updated", actor_type="rules", case_id=kase.id,
                   claim_type=claim.type, **{"from": previous, "to": outcome.state})
    return changed