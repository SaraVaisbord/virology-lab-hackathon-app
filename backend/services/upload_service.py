"""Uploads: store the file, split it into page images (upright and deskewed) and queue one form per page."""

from __future__ import annotations

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import islice
from typing import Any, Iterator

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageOps

from db.repositories import FormRepository
from domain.vocabulary import UPLOAD_TYPES
from integrations.imaging.preprocessing import straighten
from integrations.ocr.base import OcrEngine
from integrations.storage import PAGES_PREFIX, UPLOADS_PREFIX, Storage, page_key, upload_key

_ILLEGAL_FILENAME_CHARS = set('/\\:*?"<>|')
# A page whose only image covers at least this share of it is a scan — use that image instead of re-rendering.
_SCAN_COVERAGE = 0.9


@dataclass(frozen=True)
class UploadSettings:
    max_file_size_mb: int
    page_render_dpi: int  # pages are stored at this resolution
    page_max_side_px: int
    page_workers: int  # pages of one upload straightened in parallel


def _sanitize_filename(value: str) -> str:
    name = (value or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    # Drop control and filesystem-illegal characters while preserving Unicode (Hebrew) text.
    name = "".join(ch for ch in name if ord(ch) >= 32 and ord(ch) != 127 and ch not in _ILLEGAL_FILENAME_CHARS)
    return name.strip().strip(".")[:255] or "upload"


def _detect_file_type(file_bytes: bytes) -> str | None:
    return next((kind for kind, spec in UPLOAD_TYPES.items() if file_bytes.startswith(spec["magic"])), None)


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _result(filename: str, status: str, form_ids: list[int] | None = None, error: str | None = None) -> dict[str, Any]:
    return {"filename": filename, "status": status, "form_ids": form_ids or [], "error": error}


class UploadService:
    def __init__(self, forms: FormRepository, files: Storage, ocr: OcrEngine, settings: UploadSettings) -> None:
        self._forms = forms
        self._files = files
        self._ocr = ocr
        self._settings = settings

    def _normalize_page(self, image: Image.Image) -> Image.Image:
        """Phone-photo rotation (EXIF), size cap, then upright + deskewed — so the page the lab worker sees is
        always straight, from the moment it is uploaded (not only after extraction)."""
        image = ImageOps.exif_transpose(image).convert("RGB")
        side = self._settings.page_max_side_px
        image.thumbnail((side, side), Image.Resampling.LANCZOS)
        upright, _rotation, _skew = straighten(cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR), ocr=self._ocr)
        return Image.fromarray(cv2.cvtColor(upright, cv2.COLOR_BGR2RGB))

    def _pdf_page_image(self, doc, page) -> Image.Image:
        """The scan embedded in the page at its own resolution (re-rendering loses detail), scaled to page_render_dpi;
        pages that aren't a single scan (vector PDFs, several images) are rendered at page_render_dpi."""
        target_dpi = self._settings.page_render_dpi
        images = page.get_images(full=True)
        if len(images) == 1:
            rects = page.get_image_rects(images[0][0])
            covered = sum(r.width * r.height for r in rects) / (page.rect.width * page.rect.height)
            if covered >= _SCAN_COVERAGE:
                info = doc.extract_image(images[0][0])
                image = Image.open(io.BytesIO(info["image"])).convert("RGB")
                dpi = image.width / (page.rect.width / 72)
                if abs(dpi - target_dpi) > 5:
                    scale = target_dpi / dpi
                    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
                return image
        pix = page.get_pixmap(dpi=target_dpi, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    def _iter_pages(self, file_bytes: bytes, file_type: str) -> Iterator[Image.Image]:
        if file_type == "pdf":
            with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    yield self._pdf_page_image(doc, page)
        else:
            yield Image.open(io.BytesIO(file_bytes))

    def _cleanup(self, file_hash: str) -> None:
        for prefix in (PAGES_PREFIX, UPLOADS_PREFIX):
            self._files.delete_prefix(f"{prefix}/{file_hash}_")
        self._forms.delete_forms_by_hash(file_hash)

    def process_upload(self, filename: str, file_bytes: bytes) -> dict[str, Any]:
        """Store an uploaded file, split it into page images and queue one form per page."""
        original_name = _sanitize_filename(filename)
        if len(file_bytes) > self._settings.max_file_size_mb * 1024 * 1024:
            return _result(original_name, "rejected", error=f"File exceeds {self._settings.max_file_size_mb}MB limit.")
        file_type = _detect_file_type(file_bytes)
        if file_type is None:
            return _result(original_name, "rejected", error="Unsupported file type.")

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        existing = self._forms.find_forms_by_hash(file_hash)
        if existing:
            return _result(original_name, "duplicate", [item["id"] for item in existing])

        workers = self._settings.page_workers
        try:
            self._files.put(upload_key(file_hash, original_name), file_bytes, UPLOAD_TYPES[file_type]["mime"])

            form_ids = []
            pages = enumerate(self._iter_pages(file_bytes, file_type), start=1)
            # Straightening (OCR orientation check) dominates the time per page and runs in a separate Tesseract
            # process, so pages are done in parallel — in small batches, to keep only a few full scans in memory.
            with ThreadPoolExecutor(max_workers=workers) as pool:
                while batch := list(islice(pages, workers)):
                    for (page_number, _), page in zip(batch, pool.map(self._normalize_page, (page for _, page in batch))):
                        key = page_key(file_hash, page_number)
                        self._files.put(key, _png_bytes(page), "image/png")
                        form_ids.append(self._forms.add_form(source_file=original_name, file_hash=file_hash,
                                                             page_number=page_number, image_path=key))
            return _result(original_name, "created", form_ids)
        except Exception as exc:
            self._cleanup(file_hash)
            return _result(original_name, "rejected", error=str(exc))
