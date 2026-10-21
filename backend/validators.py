from __future__ import annotations

from datetime import datetime
import re

from db.constants import FIELD_KINDS


def digits_only(value) -> str:
    """The digits of a value — how two readings of the same number are compared (spaces, dashes ignored)."""
    return re.sub(r"\D", "", str(value or ""))


def text_key(value: str) -> str:
    """A text value without spaces, quotes, brackets and dashes — for comparing names and senders."""
    return re.sub(r"[\s\"'״׳()\-]", "", value)


def match_key(field_name: str, value) -> str:
    """The form in which two readings of the same value compare equal: numbers by their digits, dates by
    DD/MM/YYYY, text without punctuation. Original values are always kept; this is for comparison only."""
    text = str(value or "").strip()
    kind = FIELD_KINDS.get(field_name, "text")
    if kind in ("number", "id"):
        return digits_only(text)
    if kind == "date":
        parsed = parse_iso_like_date(text)
        return parsed.strftime("%d/%m/%Y") if parsed else text
    return text_key(text)


def israeli_id_is_valid(id_number: str) -> bool:
    """Validate Israeli ID checksum (returns True if valid).

    Accepts strings with or without leading zeros. Must be 5-9 digits; algorithm
    multiplies alternating digits by 1 or 2 and sums digits of products.
    """
    if not id_number:
        return False
    s = re.sub(r"\D", "", str(id_number))
    if len(s) < 5 or len(s) > 9:
        return False
    s = s.zfill(9)
    total = 0
    for i, ch in enumerate(s):
        val = int(ch)
        mul = val * (1 if (i % 2 == 0) else 2)
        total += mul if mul < 10 else (mul // 10 + mul % 10)
    return total % 10 == 0


def parse_iso_like_date(value: str) -> datetime | None:
    """Attempt to parse common Hebrew/ISO date formats into datetime.

    Returns None if parsing fails. Does not guess month/day order beyond
    common patterns.
    """
    if not value:
        return None
    v = value.strip()
    # Normalize separators
    v = re.sub(r"[\\./-]+", "/", v)
    # Try several patterns
    patterns = ["%Y/%m/%d", "%d/%m/%Y", "%d/%m/%y", "%Y/%d/%m", "%d %b %Y"]
    for p in patterns:
        try:
            return datetime.strptime(v, p)
        except Exception:
            continue
    # Last resort: try dateutil if available
    try:
        from dateutil.parser import parse

        return parse(v, dayfirst=True, yearfirst=False)
    except Exception:
        return None
