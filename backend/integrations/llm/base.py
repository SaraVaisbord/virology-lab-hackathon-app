from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class LlmProvider(Protocol):
    """Reads one page image into the extraction JSON (see schema.response_schema).

    Raises MissingApiKeyError (not configured), ModelsUnavailableError (resting: quota / overload) or
    ExtractionError (no usable answer for this page) — see errors.py."""

    name: str

    def extract_from_image(self, image_path: str | Path, known_senders: list[str] | None = None) -> dict[str, Any]: ...
