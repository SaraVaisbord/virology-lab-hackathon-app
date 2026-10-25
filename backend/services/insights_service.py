"""Correction insights — recurring patterns in the lab worker's corrections (the field_events history).

Computed on request: one query for the history, aggregated here. Nothing is stored or cached.
An insight points at something worth checking; it is not an accuracy figure — fields the lab worker never opened
are not in the history (coverage.auto_accepted_fields counts them), and an approval only means she did not change
the value. Only field names, form types, known sender names, digits of a confusion and counts leave this module.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Iterator

from db.repositories import CorrectionHistory, SenderRepository
from domain.verification import match_sender
from domain.vocabulary import (
    FIELD_LABELS,
    INSIGHT_RECOMMENDATIONS,
    INSIGHT_STATUS_MESSAGES,
    SOURCE_LABELS,
    WRONG_VALUE_CHANGE_KINDS,
)

@dataclass(frozen=True)
class InsightThresholds:
    min_reviewed_fields: int  # below this many reviewed machine values there is not enough history for any pattern
    min_events: int  # a pattern is reported from this many events
    medium_support_events: int  # from this many events its support is medium,
    high_support_events: int  # and from this many high
    min_correction_percent: int  # a field is "often corrected" from this share (%) of its reviewed values
    concentration_percent: int  # a pattern is "concentrated" where at least this share (%) of it is


_SUPPORT_ORDER = {"high": 0, "medium": 1, "low": 2}
# Insight detail columns: the one that refines a pattern (e.g. which digit swap), set per pattern below.
_DETAILS = ("matched_field", "digit_swap", "source")
# Where a pattern may be concentrated: insight key → event key.
_CONCENTRATION_KEYS = {"form_type": "form_type", "sender": "sender", "written_as": "before_written_as"}


def _naive_utc(value: datetime | None) -> datetime | None:
    """Event times are stored as naive UTC; a time with a zone is converted to that."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _split(value: str | None) -> list[str]:
    return sorted(set(value.split(","))) if value else []


def _pattern_keys(event: dict[str, Any]) -> Iterator[tuple[str, str, str | None, str | None]]:
    """The patterns one event is part of: (pattern, field, detail column, detail value)."""
    field, kind = event["field_name"], event["change_kind"]
    if kind in WRONG_VALUE_CHANGE_KINDS:
        yield "frequent_correction", field, None, None
        if event["before_status"] == "verified":
            yield "silent_error", field, None, None
        shown_by = set(_split(event["before_sources"]))
        for source in _split(event["correct_seen_by"]):
            if source not in shown_by:
                yield "better_source", field, "source", source
    if kind == "wrong_field" and event["matched_field"]:
        yield "wrong_field", field, "matched_field", event["matched_field"]
    if kind == "day_month_swap":
        yield "day_month_swap", field, None, None
    for swap in _split(event["digit_swaps"]):
        yield "digit_confusion", field, "digit_swap", swap
    if kind == "filled_missing":
        yield "missed_value", field, None, None
    if kind == "removed":
        yield "extra_value", field, None, None


def _support(event_count: int, thresholds: InsightThresholds) -> str:
    if event_count >= thresholds.high_support_events:
        return "high"
    return "medium" if event_count >= thresholds.medium_support_events else "low"


def _concentrated_in(events: list[dict[str, Any]], key: str, thresholds: InsightThresholds) -> str | None:
    """The value of `key` that most of these events share (thresholds.concentration_percent), if any."""
    counts = Counter(event[key] for event in events if event[key])
    if not counts:
        return None
    value, count = counts.most_common(1)[0]
    return value if count * 100 >= thresholds.concentration_percent * len(events) else None


def _recommendation(pattern: str, field: str, detail: str | None, value: str | None, share: float) -> str:
    read, _, correct = (value or "").partition(">") if detail == "digit_swap" else ("", "", "")
    return INSIGHT_RECOMMENDATIONS[pattern].format(
        field=FIELD_LABELS[field],
        matched_field=FIELD_LABELS.get(value, "") if detail == "matched_field" else "",
        source=SOURCE_LABELS.get(value, "") if detail == "source" else "",
        read=read,
        correct=correct,
        percent=round(share * 100),
    )


def build_insights(events: list[dict[str, Any]], thresholds: InsightThresholds) -> dict[str, Any]:
    """Patterns in these events (each with its form's `form_type` and known `sender`). Only first decisions on the
    machine's output count (before_origin "machine"): changing her own earlier value says nothing about extraction."""
    reviewed = [event for event in events if event["before_origin"] == "machine"]
    reviewed_per_field = Counter(event["field_name"] for event in reviewed)
    corrected_per_field = Counter(event["field_name"] for event in reviewed if event["change_kind"] in WRONG_VALUE_CHANGE_KINDS)
    coverage = {
        "reviewed_fields": len(reviewed),
        "corrected_fields": sum(corrected_per_field.values()),
        "required_reviewed_fields": thresholds.min_reviewed_fields,
        # Counts, not insights: which fields were corrected most (most first).
        "by_field": [
            {"field_name": name, "reviewed": count, "corrected": corrected_per_field[name]}
            for name, count in sorted(reviewed_per_field.items(), key=lambda item: (-corrected_per_field[item[0]], -item[1], item[0]))
        ],
    }
    if len(reviewed) < thresholds.min_reviewed_fields:
        message = INSIGHT_STATUS_MESSAGES["insufficient_data"].format(
            reviewed=len(reviewed), required=thresholds.min_reviewed_fields
        )
        return {"status": "insufficient_data", "message": message, "coverage": coverage, "insights": []}

    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for event in reviewed:
        for key in _pattern_keys(event):
            groups[key].append(event)

    insights = []
    for (pattern, field, detail, value), group in groups.items():
        share = len(group) / reviewed_per_field[field]
        if len(group) < thresholds.min_events:
            continue
        if pattern == "frequent_correction" and share * 100 < thresholds.min_correction_percent:
            continue
        times = [event["created_at"] for event in group]
        insights.append({
            "pattern_type": pattern,
            "field_name": field,
            **{name: (value if name == detail else None) for name in _DETAILS},
            "event_count": len(group),
            "reviewed_count": reviewed_per_field[field],
            "share": round(share, 3),
            "first_seen": min(times),
            "last_seen": max(times),
            "concentrated_in": {name: _concentrated_in(group, key, thresholds) for name, key in _CONCENTRATION_KEYS.items()},
            "support": _support(len(group), thresholds),
            "recommendation": _recommendation(pattern, field, detail, value, share),
        })
    insights.sort(key=lambda item: (_SUPPORT_ORDER[item["support"]], -item["event_count"], item["pattern_type"], item["field_name"]))
    return {"status": "ok", "message": INSIGHT_STATUS_MESSAGES["ok"], "coverage": coverage, "insights": insights}


class InsightsService:
    def __init__(self, history: CorrectionHistory, senders: SenderRepository, thresholds: InsightThresholds) -> None:
        self._history = history
        self._senders = senders
        self._thresholds = thresholds

    def correction_insights(self, since: datetime | None = None, until: datetime | None = None,
                            field_name: str | None = None) -> dict[str, Any]:
        """Insights for the history in [since, until] (event times), optionally for one field."""
        since, until = _naive_utc(since), _naive_utc(until)
        if since is not None and until is not None and since > until:
            raise ValueError("'since' must not be later than 'until'.")
        events = self._history.correction_events(since, until, field_name)
        known_senders = self._senders.names()
        for event in events:
            # Only the name of a known institution goes on — never the free text read from the form.
            event["sender"] = match_sender(event.pop("sender_text") or "", known_senders)
        result = build_insights(events, self._thresholds)
        result["coverage"]["auto_accepted_fields"] = self._history.count_unreviewed_verified_fields(since, until, field_name)
        return {"since": since, "until": until, "field_name": field_name, **result}
