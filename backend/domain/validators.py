from __future__ import annotations

from datetime import datetime
import re

from domain.vocabulary import FIELD_KINDS, TYPO_MAX_CHANGED_CHARS


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


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance: how many single characters must be inserted, deleted or replaced to turn a into b."""
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


def _digit_swaps(old: str, new: str) -> str | None:
    """Which digit was read as which ("1>7,0>8") where two same-length values differ: the reading confusion, without
    the value it happened in."""
    if len(old) != len(new):
        return None
    return ",".join(f"{a}>{b}" for a, b in zip(old, new) if a != b and a.isdigit() and b.isdigit()) or None


def _is_day_month_swap(field_name: str, old: str, new: str) -> bool:
    """Two dates (in match_key form, DD/MM/YYYY) that differ only by day and month trading places."""
    if FIELD_KINDS.get(field_name) != "date":
        return False
    old_parts, new_parts = old.split("/"), new.split("/")
    return len(old_parts) == len(new_parts) == 3 and old_parts == [new_parts[1], new_parts[0], new_parts[2]]


def _field_holding(field_name: str, key: str, other_fields: dict[str, list]) -> str | None:
    """The first of the form's other fields that holds this value (compared as values of `field_name`)."""
    return next((name for name, values in other_fields.items()
                 if any(value and match_key(field_name, value) == key for value in values)), None)


def classify_change(field_name: str, before, after, *, other_fields: dict[str, list] | None = None,
                    machine_values=()) -> dict:
    """What kind of change the lab worker made to a field, as the FieldEvent columns that describe it:
    change_kind (a CHANGE_KINDS key), chars_changed (typo: how many characters changed), matched_field (the other
    field the new value — or a removed value — was found under) and digit_swaps (typo in a number or date: which digit
    was read as which). Compared in match_key form; none of it reveals the values themselves.

    other_fields: {field_name: [values the page holds under it]} for the form's other fields.
    machine_values: what the sources read for this field — set only when `before` was already decided by the worker,
    so going back to one of them is "restored"."""
    other_fields = other_fields or {}

    def change(kind: str, **details) -> dict:
        return {"change_kind": kind, "chars_changed": None, "matched_field": None, "digit_swaps": None, **details}

    before, after = str(before or "").strip(), str(after or "").strip()
    if not after:
        if not before:
            return change("none")
        return change("removed", matched_field=_field_holding(field_name, match_key(field_name, before), other_fields))
    if not before:
        return change("filled_missing")
    if before == after:
        return change("none")
    old, new = match_key(field_name, before), match_key(field_name, after)
    if old == new:
        return change("format_only")
    if new in {match_key(field_name, value) for value in machine_values if value}:
        return change("restored")
    matched = _field_holding(field_name, new, other_fields)
    if matched:
        return change("wrong_field", matched_field=matched)
    if _is_day_month_swap(field_name, old, new):
        return change("day_month_swap")
    if len(old) == len(new) and sorted(old) == sorted(new):
        return change("transposition")
    changed = edit_distance(old, new)
    if changed > TYPO_MAX_CHANGED_CHARS:
        return change("different_value")
    swaps = _digit_swaps(old, new) if FIELD_KINDS.get(field_name) in ("number", "id", "date") else None
    return change("typo", chars_changed=changed, digit_swaps=swaps)


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
