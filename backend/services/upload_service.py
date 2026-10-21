from __future__ import annotations

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from typing import Any, Iterator

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageOps

import config
from db.constants import UPLOAD_TYPES
from preprocessing import straighten
from db.queries import add_form, delete_forms_by_hash, find_forms_by_hash
from storage import PAGES_PREFIX, UPLOADS_PREFIX, get_storage, page_key, upload_key

_ILLEGAL_FILENAME_CHARS = set('/\\:*?"<>|')


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


def _normalize_page(image: Image.Image) -> Image.Image:
    """Phone-photo rotation (EXIF), size cap, then upright + deskewed — so the page the lab worker sees is
    always straight, from the moment it is uploaded (not only after extraction)."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((config.PAGE_MAX_SIDE_PX, config.PAGE_MAX_SIDE_PX), Image.Resampling.LANCZOS)
    upright, _rotation, _skew = straighten(cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR))
    return Image.fromarray(cv2.cvtColor(upright, cv2.COLOR_BGR2RGB))


# A page whose only image covers at least this share of it is a scan — use that image instead of re-rendering.
_SCAN_COVERAGE = 0.9


def _pdf_page_image(doc, page) -> Image.Image:
    """The scan embedded in the page at its own resolution (re-rendering loses detail), scaled to PAGE_RENDER_DPI;
    pages that aren't a single scan (vector PDFs, several images) are rendered at PAGE_RENDER_DPI."""
    images = page.get_images(full=True)
    if len(images) == 1:
        rects = page.get_image_rects(images[0][0])
        covered = sum(r.width * r.height for r in rects) / (page.rect.width * page.rect.height)
        if covered >= _SCAN_COVERAGE:
            info = doc.extract_image(images[0][0])
            image = Image.open(io.BytesIO(info["image"])).convert("RGB")
            dpi = image.width / (page.rect.width / 72)
            if abs(dpi - config.PAGE_RENDER_DPI) > 5:
                scale = config.PAGE_RENDER_DPI / dpi
                image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
            return image
    pix = page.get_pixmap(dpi=config.PAGE_RENDER_DPI, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _iter_pages(file_bytes: bytes, file_type: str) -> Iterator[Image.Image]:
    if file_type == "pdf":
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            for page in doc:
                yield _pdf_page_image(doc, page)
    else:
        yield Image.open(io.BytesIO(file_bytes))


def _cleanup(file_hash: str) -> None:
    files = get_storage()
    for prefix in (PAGES_PREFIX, UPLOADS_PREFIX):
        files.delete_prefix(f"{prefix}/{file_hash}_")
    delete_forms_by_hash(file_hash)


def _result(filename: str, status: str, form_ids: list[int] | None = None, error: str | None = None) -> dict[str, Any]:
    return {"filename": filename, "status": status, "form_ids": form_ids or [], "error": error}


def process_upload(file: Any) -> dict[str, Any]:
    """Store an uploaded file, split it into page images and queue one form per page."""
    if file is None:
        return _result("", "rejected", error="No file provided.")

    original_name = _sanitize_filename(getattr(file, "filename", "") or "")
    file_obj = getattr(file, "file", None)
    if file_obj is None:
        return _result(original_name, "rejected", error="No file provided.")
    file_obj.seek(0)
    file_bytes = file_obj.read()

    if len(file_bytes) > config.MAX_FILE_SIZE:
        return _result(original_name, "rejected", error=f"File exceeds {config.MAX_FILE_SIZE_MB}MB limit.")
    file_type = _detect_file_type(file_bytes)
    if file_type is None:
        return _result(original_name, "rejected", error="Unsupported file type.")

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing = find_forms_by_hash(file_hash)
    if existing:
        return _result(original_name, "duplicate", [item["id"] for item in existing])

    try:
        files = get_storage()
        files.put(upload_key(file_hash, original_name), file_bytes, UPLOAD_TYPES[file_type]["mime"])

        form_ids = []
        pages = enumerate(_iter_pages(file_bytes, file_type), start=1)
        # Straightening (OCR orientation check) dominates the time per page and runs in a separate Tesseract
        # process, so pages are done in parallel — in small batches, to keep only a few full scans in memory.
        with ThreadPoolExecutor(max_workers=config.UPLOAD_PAGE_WORKERS) as pool:
            while batch := list(islice(pages, config.UPLOAD_PAGE_WORKERS)):
                for (page_number, _), page in zip(batch, pool.map(_normalize_page, (page for _, page in batch))):
                    key = page_key(file_hash, page_number)
                    files.put(key, _png_bytes(page), "image/png")
                    form_ids.append(add_form(source_file=original_name, file_hash=file_hash, page_number=page_number, image_path=key))
        return _result(original_name, "created", form_ids)
    except Exception as exc:
        _cleanup(file_hash)
        return _result(original_name, "rejected", error=str(exc))
