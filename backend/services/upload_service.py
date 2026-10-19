from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any, Iterator

import pymupdf
from PIL import Image, ImageOps

import config
from db.constants import UPLOAD_TYPES
from db.queries import add_form, delete_forms_by_hash, find_forms_by_hash

_ILLEGAL_FILENAME_CHARS = set('/\\:*?"<>|')


def _sanitize_filename(value: str) -> str:
    name = (value or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    # Drop control and filesystem-illegal characters while preserving Unicode (Hebrew) text.
    name = "".join(ch for ch in name if ord(ch) >= 32 and ord(ch) != 127 and ch not in _ILLEGAL_FILENAME_CHARS)
    return name.strip().strip(".")[:255] or "upload"


def _detect_file_type(file_bytes: bytes) -> str | None:
    return next((kind for kind, spec in UPLOAD_TYPES.items() if file_bytes.startswith(spec["magic"])), None)


def _page_image_path(file_hash: str, page_number: int) -> Path:
    config.PAGES_IMG_DIR.mkdir(parents=True, exist_ok=True)
    return config.PAGES_IMG_DIR / f"{file_hash}_p{page_number}.png"


def _normalize_page(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((config.PAGE_MAX_SIDE_PX, config.PAGE_MAX_SIDE_PX), Image.Resampling.LANCZOS)
    return image


def _iter_pages(file_bytes: bytes, file_type: str) -> Iterator[Image.Image]:
    if file_type == "pdf":
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=config.PAGE_RENDER_DPI, alpha=False)
                yield Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        yield Image.open(io.BytesIO(file_bytes))


def _relative(path: Path) -> str:
    return path.relative_to(config.DATA_DIR).as_posix()


def _cleanup(file_hash: str) -> None:
    for directory in (config.PAGES_IMG_DIR, config.UPLOADS_DIR):
        for path in directory.glob(f"{file_hash}_*"):
            path.unlink(missing_ok=True)
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
        config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        (config.UPLOADS_DIR / f"{file_hash}_{original_name}").write_bytes(file_bytes)

        form_ids = []
        for page_number, page in enumerate(_iter_pages(file_bytes, file_type), start=1):
            path = _page_image_path(file_hash, page_number)
            _normalize_page(page).save(path, format="PNG")
            form_ids.append(add_form(source_file=original_name, file_hash=file_hash, page_number=page_number, image_path=_relative(path)))
        return _result(original_name, "created", form_ids)
    except Exception as exc:
        _cleanup(file_hash)
        return _result(original_name, "rejected", error=str(exc))
