from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class InsightConcentration(BaseModel):
    """Where most of a pattern's events are (null: spread out, or unknown)."""

    form_type: str | None = None
    sender: str | None = None  # a name from the known senders list — never free text read from a form
    written_as: str | None = None  # how the shown value is written on the page (handwritten / printed / ...)


class CorrectionInsight(BaseModel):
    pattern_type: str  # INSIGHT_PATTERN_LABELS key (labels in GET /meta)
    field_name: str
    # The detail that refines the pattern, when it has one:
    matched_field: str | None = None  # wrong_field: the field the value belonged to
    digit_swap: str | None = None  # digit_confusion: "read>correct", e.g. "1>7"
    source: str | None = None  # better_source: the source that read the right value
    event_count: int
    reviewed_count: int  # machine values of this field the lab worker decided on in the range
    share: float  # event_count / reviewed_count — a share of reviewed values, not an accuracy figure
    first_seen: datetime  # UTC
    last_seen: datetime
    concentrated_in: InsightConcentration
    support: str  # INSIGHT_SUPPORT_LABELS key: how many events back the pattern
    recommendation: str


class FieldCoverage(BaseModel):
    field_name: str
    reviewed: int
    corrected: int


class InsightsCoverage(BaseModel):
    reviewed_fields: int  # machine values the lab worker decided on (approved, corrected, filled or deleted)
    corrected_fields: int  # of those, the ones whose value was wrong
    required_reviewed_fields: int  # below this, no patterns are reported
    auto_accepted_fields: int  # verified fields nobody reviewed — not in the history, so not in any figure above
    by_field: list[FieldCoverage]  # the same counts per field, most corrected first


class CorrectionInsightsResponse(BaseModel):
    status: str  # "ok" | "insufficient_data"
    message: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    field_name: str | None = None
    coverage: InsightsCoverage
    insights: list[CorrectionInsight]
