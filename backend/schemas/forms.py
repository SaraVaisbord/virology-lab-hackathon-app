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
    # Per-source candidates, assignment evidence and agreement verdict (see extraction_service.build_fields).
    evidence: dict[str, Any] | None = None
    page: int | None = None
    # Normalized to the page image (0..1); box_source says which source the box came from.
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    box_source: str | None = None
    created_at: datetime | None = None


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


class FormSources(BaseModel):
    """Raw result of each source for the page, exactly as stored (JSON)."""

    llm_result: dict[str, Any] | None = None
    barcode_result: dict[str, Any] | None = None
    ocr_result: dict[str, Any] | None = None
    source_errors: dict[str, str] | None = None


class FormDetailResponse(FormResponse):
    sources: FormSources


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
