from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FieldResponse(BaseModel):
    id: int
    form_id: int
    field_name: str
    value: str | None = None  # normalized value shown to the user
    llm_value: str | None = None  # what Gemini read, unmodified
    barcode_value: str | None = None  # barcode that reads exactly the same value
    ocr_value: str | None = None  # what OCR read (no OCR engine yet — always null)
    corrected_value: str | None = None
    status: str
    confidence: str | None = None
    reason: str | None = None
    # Per-source candidates, assignment evidence and agreement verdict (see domain/verification.build_fields).
    evidence: dict[str, Any] | None = None
    page: int | None = None
    # Normalized to the page image (0..1); box_source says which source the box came from.
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    box_source: str | None = None
    created_at: datetime | None = None


class CommitmentDuplicate(BaseModel):
    """A commitment number of this form that another form has too — with where it is on each page."""

    field_id: int
    value: str
    other_form_id: int
    other_field_id: int
    other_source_file: str
    other_page_number: int
    other_status: str
    other_value: str
    # The other form's field box (normalized, 0..1), for the side-by-side view.
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    box_source: str | None = None


class FormResponse(BaseModel):
    id: int
    source_file: str
    file_hash: str
    page_number: int
    image_path: str
    form_type: str | None = None
    status: str
    error: str | None = None
    uploaded_at: datetime | None = None
    fields: list[FieldResponse] = Field(default_factory=list)
    duplicates: list[CommitmentDuplicate] = Field(default_factory=list)
    # Values the lab worker deleted, per field — re-extraction never puts them back.
    rejected_values: dict[str, list[str]] = Field(default_factory=dict)


class FormSources(BaseModel):
    """Raw result of each source for the page, exactly as stored (JSON)."""

    llm_result: dict[str, Any] | None = None
    barcode_result: dict[str, Any] | None = None
    ocr_result: dict[str, Any] | None = None
    source_errors: dict[str, str] | None = None


class NumberBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class PageNumber(BaseModel):
    """A number (or date) found on the page by any source — see domain/page_numbers.py."""

    key: str  # comparison key: digits, or DDMMYYYY for a date
    value: str  # as first read
    sources: list[str]  # which sources read it (SOURCE_LABELS keys)
    boxes: dict[str, NumberBox] = Field(default_factory=dict)  # where each source saw it
    notes: list[str] = Field(default_factory=list)  # labels / barcode types next to it
    box: NumberBox | None = None  # the most precise location (barcode, then OCR, then LLM)
    box_source: str | None = None
    is_date: bool = False


class FormDetailResponse(FormResponse):
    sources: FormSources
    page_numbers: list[PageNumber] = Field(default_factory=list)


class FormsPage(BaseModel):
    items: list[FormResponse]
    total: int
    limit: int
    offset: int


class QueueState(BaseModel):
    running: bool
    paused_until: datetime | None = None
    pause_reason: str | None = None


class FormsSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    pending: int
    fields_to_review: int
    queue: QueueState


class ConfirmFieldRequest(BaseModel):
    corrected_value: str | None = None


class BoxPayload(BaseModel):
    x: float
    y: float
    width: float
    height: float


class AddFieldRequest(BaseModel):
    field_name: str
    value: str
    # Set when the value was picked from a number a source found on the page (keeps its location for the UI).
    replace: bool = False
    box: BoxPayload | None = None
    picked_from: str | None = None
