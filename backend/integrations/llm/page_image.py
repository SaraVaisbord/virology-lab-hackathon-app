from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class PageImageSettings:
    """How the page is sent to a model: longest side and JPEG quality (smaller = fewer tokens)."""

    max_side_px: int
    jpeg_quality: int


def page_as_jpeg(image_path: Path, settings: PageImageSettings) -> bytes:
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((settings.max_side_px, settings.max_side_px))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=settings.jpeg_quality)
        return buffer.getvalue()
