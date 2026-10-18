from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UploadItemResponse(BaseModel):
    filename: str = Field(..., description="Original uploaded filename, sanitized")
    status: str = Field(..., description="created, duplicate, rejected")
    form_ids: list[int] = Field(default_factory=list)
    error: str | None = None


class FormFieldResponse(BaseModel):
    id: int
    form_id: int
    field_name: str
    value: Any | None = None
    raw_value: Any | None = None
    status: str | None = None
    corrected_value: Any | None = None
    bbox: str | None = None
    created_at: Any | None = None


class FormRecordResponse(BaseModel):
    id: int
    source_file: str
    file_hash: str
    page_number: int
    image_path: str
    form_type: str | None = None
    status: str
    raw_llm_json: str | None = None
    error: str | None = None
    uploaded_at: Any | None = None
    fields: list[FormFieldResponse] = Field(default_factory=list)
