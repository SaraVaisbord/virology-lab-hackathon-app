from __future__ import annotations

from pydantic import BaseModel, Field


class UploadItemResponse(BaseModel):
    filename: str = Field(..., description="Original uploaded filename, sanitized")
    status: str = Field(..., description="created, duplicate, rejected")
    form_ids: list[int] = Field(default_factory=list)
    error: str | None = None
