"""Comparing what files say with the listing (Week 7, Day 3; spec F05).

Pure functions, no database: `parse` checks and canonicalises a value the
renter typed, and `compare` says whether it matches what the listing claimed.

- money (rent, deposit): compared as amounts, so "$1,200" matches "1200.00"
- dates: compared as dates
- address and payment method: compared as text after tidying (case, punctuation,
  "Street" = "St", "Apt" = "Unit" = "#"). If one contains the other they match:
  "214 Elm St" vs "214 Elm Street, Unit 3B" isn't a contradiction, but
  "Unit 3B" vs "Unit 3C" is.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

MONEY_FIELDS = {"monthly_rent", "deposit"}
DATE_FIELDS = {"start_date", "end_date"}
TEXT_FIELDS = {"address", "payment_method"}

# How the activity log and rationales name each field.
FACT_LABEL = {
    "address": "address",
    "start_date": "move-in date",
    "end_date": "move-out date",
    "monthly_rent": "monthly rent",
    "deposit": "deposit",
    "payment_method": "payment details",
}

Result = Literal["matches", "differs", "listing_silent"]


class FactValueError(ValueError):
    pass


def _money(raw: str) -> Decimal:
    cleaned = re.sub(r"[\s$,]", "", raw)
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        raise FactValueError("Enter an amount, like 1200 or 1,200.00.") from None
    if not amount.is_finite() or amount < 0 or amount >= Decimal("100000000"):
        raise FactValueError("Enter an amount, like 1200 or 1,200.00.")
    return amount.quantize(Decimal("0.01"))


def _date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise FactValueError("Enter a date as YYYY-MM-DD.") from None


_WORDS = {
    "street": "st", "avenue": "ave", "road": "rd", "boulevard": "blvd", "drive": "dr",
    "lane": "ln", "court": "ct", "place": "pl", "north": "n", "south": "s", "east": "e", "west": "w",
    "apartment": "unit", "apt": "unit", "suite": "unit", "ste": "unit", "no": "unit",
}


def _tidy(text: str) -> str:
    text = text.lower().replace("#", " unit ")
    words = re.sub(r"[^a-z0-9]+", " ", text).split()
    words = [_WORDS.get(w, w) for w in words]
    # "unit unit 3b" (from "Apt #3B") -> "unit 3b"
    out: list[str] = []
    for w in words:
        if not (w == "unit" and out and out[-1] == "unit"):
            out.append(w)
    return " ".join(out)


def parse(field: str, raw: str) -> str:
    """Check a typed value and return its canonical form for storing."""
    raw = raw.strip()
    if not raw:
        raise FactValueError("Enter what the file says.")
    if field in MONEY_FIELDS:
        return str(_money(raw))
    if field in DATE_FIELDS:
        return _date(raw).isoformat()
    if len(raw) > 200:
        raise FactValueError("Keep it under 200 characters.")
    return raw


def compare(field: str, listed: object, provided: str) -> Result:
    """Does what the file says (`provided`, canonical) match the listing's value?"""
    if listed is None or (isinstance(listed, str) and not listed.strip()):
        return "listing_silent"
    if field in MONEY_FIELDS:
        return "matches" if Decimal(str(listed)).quantize(Decimal("0.01")) == _money(provided) else "differs"
    if field in DATE_FIELDS:
        listed_date = listed if isinstance(listed, date) else _date(str(listed))
        return "matches" if listed_date == _date(provided) else "differs"
    a, b = _tidy(str(listed)), _tidy(provided)
    if not a or not b:
        return "listing_silent" if not a else "differs"
    return "matches" if a == b or f" {a} " in f" {b} " or f" {b} " in f" {a} " else "differs"