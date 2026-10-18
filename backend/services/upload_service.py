from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageOps

from db.queries import add_form, delete_forms_by_hash, find_forms_by_hash

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"
PAGES_IMG_DIR = DATA_DIR / "pages_img"
MAX_FILE_SIZE = 50 * 1024 * 1024
SUPPORTED_MIME_SNIPPETS = {
    "%PDF": "pdf",
    "\x89PNG": "png",
    "\xff\xd8\xff": "jpeg",
}


def _sanitize_filename(value: str) -> str:
    value = (value or '').strip()
    value = value.replace('\\', '/')
    value = value.rsplit('/', 1)[-1]

    # Remove control chars and filesystem-illegal characters while preserving Unicode text.
    cleaned_chars: list[str] = []
    for ch in value:
        code = ord(ch)
        if code < 32 or code == 127:
            continue
        if ch in {'/', '\\', ':', '*', '?', '"', '<', '>', '|'}:
            continue
        cleaned_chars.append(ch)

    value = ''.join(cleaned_chars).strip().strip('.')
    value = value[:255] or 'upload'
    return value


def _detect_file_type(file_bytes: bytes) -> str | None:
    if len(file_bytes) >= 4 and file_bytes[:4] == b"%PDF":
        return "pdf"
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


def _hash_file(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _save_upload(file_bytes: bytes, file_hash: str, original_name: str) -> str:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(original_name)
    target = UPLOADS_DIR / f"{file_hash}_{safe_name}"
    with open(target, "wb") as fh:
        fh.write(file_bytes)
    return str(target.relative_to(DATA_DIR))


def _page_png_path(file_hash: str, page_no: int) -> Path:
    PAGES_IMG_DIR.mkdir(parents=True, exist_ok=True)
    return PAGES_IMG_DIR / f"{file_hash}_p{page_no}.png"


def _render_pdf_pages(file_bytes: bytes, file_hash: str) -> list[str]:
    created: list[str] = []
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for page_index in range(len(doc)):
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), alpha=False)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                if max(image.size) > 2000:
                    scale = 2000 / max(image.size)
                    image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
                path = _page_png_path(file_hash, page_index + 1)
                image = ImageOps.exif_transpose(image)
                image.save(path, format="PNG")
                created.append(str(path.relative_to(DATA_DIR)))
        return created
    except Exception:
        for path in PAGES_IMG_DIR.glob(f"{file_hash}_p*.png"):
            if path.exists():
                path.unlink(missing_ok=True)
        raise


def _render_image(file_bytes: bytes, file_hash: str) -> str:
    path = _page_png_path(file_hash, 1)
    image = Image.open(__import__('io').BytesIO(file_bytes))
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    if max(image.size) > 2000:
        scale = 2000 / max(image.size)
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
    image.save(path, format="PNG")
    return str(path.relative_to(DATA_DIR))


def _cleanup_generated_for_hash(file_hash: str, created_paths: list[str], original_name: str) -> None:
    for relative in created_paths:
        full = (DATA_DIR / relative).resolve()
        if full.exists():
            full.unlink(missing_ok=True)
    for pattern in (f"{file_hash}_*",):
        for path in PAGES_IMG_DIR.glob(pattern):
            if path.exists():
                path.unlink(missing_ok=True)
    upload_candidate = UPLOADS_DIR / f"{file_hash}_{_sanitize_filename(original_name)}"
    if upload_candidate.exists():
        upload_candidate.unlink(missing_ok=True)
    delete_forms_by_hash(file_hash)


def process_upload(file: Any, *, allow_duplicate: bool = True) -> dict[str, Any]:
    if file is None:
        return {"filename": "", "status": "rejected", "form_ids": [], "error": "No file provided."}

    original_name = getattr(file, "filename", "") or ""
    original_name = _sanitize_filename(original_name)
    file_obj = getattr(file, "file", None)
    if file_obj is not None:
        try:
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
        except Exception:
            pass
        file_bytes = file_obj.read() if hasattr(file_obj, "read") else b""
    else:
        file_bytes = b""
    if len(file_bytes) > MAX_FILE_SIZE:
        return {"filename": original_name, "status": "rejected", "form_ids": [], "error": "File exceeds 50MB limit."}
    file_type = _detect_file_type(file_bytes)
    if file_type is None:
        return {"filename": original_name, "status": "rejected", "form_ids": [], "error": "Unsupported file type."}

    file_hash = _hash_file(file_bytes)
    existing = find_forms_by_hash(file_hash)
    if existing:
        return {"filename": original_name, "status": "duplicate", "form_ids": [item["id"] for item in existing], "error": None}

    source_path = _save_upload(file_bytes, file_hash, original_name)
    created_paths: list[str] = []
    form_ids: list[int] = []
    try:
        if file_type == "pdf":
            rendered_paths = _render_pdf_pages(file_bytes, file_hash)
            created_paths.extend(rendered_paths)
            for index, relative in enumerate(rendered_paths, start=1):
                page_name = os.path.basename(relative)
                form_id = add_form(
                    source_file=original_name,
                    file_hash=file_hash,
                    page_number=index,
                    image_path=relative,
                )
                form_ids.append(form_id)
        else:
            relative = _render_image(file_bytes, file_hash)
            created_paths.append(relative)
            form_id = add_form(
                source_file=original_name,
                file_hash=file_hash,
                page_number=1,
                image_path=relative,
            )
            form_ids.append(form_id)

        return {"filename": original_name, "status": "created", "form_ids": form_ids, "error": None}
    except Exception as exc:
        _cleanup_generated_for_hash(file_hash, created_paths, original_name)
        return {"filename": original_name, "status": "rejected", "form_ids": [], "error": str(exc)}
