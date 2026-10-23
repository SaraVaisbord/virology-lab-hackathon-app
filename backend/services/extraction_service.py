"""Extraction pipeline for one form page.

    preprocess (upright, deskewed, clean)  →  barcodes  →  local OCR extraction  →  [LLM, if enabled]  →  merge

Each source's raw result is stored separately on the form (barcode_result / ocr_result / llm_result) as soon as
it finishes, so a failure of one source never discards another's evidence. The merge and the verification rules
are domain/verification.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

import barcode_reader
import config
import local_extractor
import ocr_reader
from db import queries
from domain.verification import VerificationRules, build_fields, form_type_of, sample_is_commitment_on
from domain.vocabulary import EXTRACTION_ERRORS, OCR_UNAVAILABLE_REASON
from integrations.llm.errors import ExtractionError, MissingApiKeyError, ModelsUnavailableError
from preprocessing import preprocess
from services import llm_router
from storage import get_storage

logger = logging.getLogger(__name__)


def verification_rules() -> VerificationRules:
    return VerificationRules(received_date_max_age_days=config.RECEIVED_DATE_MAX_AGE_DAYS,
                             local_ocr_min_confidence=config.LOCAL_OCR_MIN_CONFIDENCE)

# ── Sources ──────────────────────────────────────────────────────────────────


def user_facing_error(exc: Exception) -> str:
    """Short Hebrew message for the UI; technical details are logged, never shown or stored."""
    if isinstance(exc, MissingApiKeyError):
        return EXTRACTION_ERRORS["config"]
    if isinstance(exc, ModelsUnavailableError):
        return EXTRACTION_ERRORS["quota"]
    if isinstance(exc, ExtractionError):
        return EXTRACTION_ERRORS["timeout" if "timed out" in str(exc).lower() else "model"]
    if isinstance(exc, FileNotFoundError):
        return EXTRACTION_ERRORS["image_missing"]
    return EXTRACTION_ERRORS["unexpected"]


def read_image(path: Path) -> np.ndarray:
    """cv2.imread can't open non-ASCII paths on Windows (the project folder is Hebrew) — decode from bytes."""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot decode image {path.name}")
    return image


def png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Cannot encode image")
    return encoded.tobytes()


def run_barcode_scan(views, page: int | None) -> dict[str, Any]:
    """zbar on every barcode view of the page (no single rendition decodes every barcode); one item per value.
    Returns {"status": "ok", "items": [...]} or {"status": "error", "error": ...}. Coordinates are normalized."""
    found: dict[str, dict] = {}
    try:
        for view in views.barcode_views:
            for item in barcode_reader.scan_pil_image(Image.fromarray(view).convert("RGB")):
                found.setdefault(item["data"], {**item, "page": page})
    except Exception as exc:
        logger.warning("Barcode scan failed: %s", type(exc).__name__)
        return {"status": "error", "error": EXTRACTION_ERRORS["barcode"], "items": list(found.values())}
    return {"status": "ok", "items": list(found.values())}


def run_ocr(views, barcodes: list[dict[str, Any]], page: int | None) -> dict[str, Any]:
    """Local OCR extraction (labels → values). Returns {"status", "candidates", "labels", "unassigned_numbers"}."""
    if not ocr_reader.is_available():
        return {"status": "unavailable", "reason": OCR_UNAVAILABLE_REASON, "candidates": [], "labels": [], "unassigned_numbers": [], "items": []}
    try:
        result = local_extractor.extract(views, barcodes).as_dict()
    except Exception as exc:
        logger.warning("Local OCR extraction failed: %s", type(exc).__name__)
        return {"status": "error", "error": EXTRACTION_ERRORS["ocr"], "candidates": [], "labels": [], "unassigned_numbers": [], "items": []}
    return {"status": "ok", "page": page, **result, "items": result["candidates"]}


def extract_for_form(form: dict[str, Any], provider: str | None = None, use_llm: bool | None = None) -> None:
    """Run all sources for one page, persist each result separately, then build the field rows.

    The page image is replaced by its preprocessed (upright, deskewed, highlighter-free) version first, so every
    source and the UI share one geometry. The LLM is the first of config.LLM_PROVIDERS that answers (llm_router);
    `provider` forces one. use_llm defaults to config.LLM_ENABLED; without it no LLM is called (no tokens) and only
    an LLM answer already stored for the page is merged. Raises on LLM failure — local results are already saved
    by then."""
    form_id, page = form["id"], form.get("page_number")
    use_llm = config.LLM_ENABLED if use_llm is None else use_llm
    files, key = get_storage(), form.get("image_path")
    # A local copy of the page (S3: a temporary download) — OpenCV and the LLM clients read files.
    with files.local_path(key) as image_path:  # FileNotFoundError when the page image is missing
        views = preprocess(read_image(image_path), source_dpi=config.PAGE_RENDER_DPI)
        normalized = png_bytes(views.normalized)
        image_path.write_bytes(normalized)  # what the LLM reads below
        files.put(key, normalized, "image/png")  # what the lab worker sees
        _extract_sources(form_id, page, views, image_path, provider, use_llm)


def _extract_sources(form_id: int, page: int | None, views, image_path: Path, provider: str | None, use_llm: bool) -> None:
    barcode_result = run_barcode_scan(views, page)
    ocr_result = run_ocr(views, barcode_result["items"], page)
    errors = {source: result["error"] for source, result in (("barcode", barcode_result), ("ocr", ocr_result)) if result["status"] == "error"}
    queries.save_source_results(form_id, barcode_result=barcode_result, ocr_result=ocr_result, source_errors=errors or None)

    known_senders = [name for name, _kind in queries.list_senders()]
    # Without a new LLM call, an answer already stored for this page (from an earlier run) is still merged.
    llm_result = (queries.get_form(form_id, with_sources=True) or {}).get("sources", {}).get("llm_result")
    if use_llm:
        try:
            answer = llm_router.extract_from_image(image_path, known_senders, providers=[provider] if provider else None)
            llm_result = local_extractor.drop_irrelevant_numbers(answer)
        except Exception as exc:
            queries.save_source_results(form_id, source_errors={**errors, "llm": user_facing_error(exc)})
            raise
        queries.save_source_results(form_id, llm_result=llm_result)

    form_type = form_type_of(ocr_result, llm_result)
    fields = build_fields(llm_result, barcode_result["items"], known_senders, verification_rules(), page=page, local_candidates=ocr_result["candidates"],
                          ocr_numbers=ocr_result.get("unassigned_numbers"),
                          sample_is_commitment=sample_is_commitment_on(ocr_result, form_type))
    queries.save_extraction(form_id, fields, form_type=form_type)


def reverify_form(form_id: int) -> bool:
    """Re-run the verification rules on the stored source results (no new LLM call). False if nothing is stored."""
    form = queries.get_form(form_id, with_sources=True)
    sources = (form or {}).get("sources") or {}
    if not (sources.get("llm_result") or sources.get("ocr_result")):
        return False
    barcodes = (sources.get("barcode_result") or {}).get("items", [])
    local = (sources.get("ocr_result") or {}).get("candidates", [])
    known_senders = [name for name, _kind in queries.list_senders()]
    ocr_numbers = (sources.get("ocr_result") or {}).get("unassigned_numbers", [])
    form_type = form_type_of(sources.get("ocr_result"), sources.get("llm_result"))
    queries.save_extraction(form_id, build_fields(sources.get("llm_result"), barcodes, known_senders, verification_rules(), page=form["page_number"],
                                                  local_candidates=local, ocr_numbers=ocr_numbers,
                                                  sample_is_commitment=sample_is_commitment_on(sources.get("ocr_result"), form_type)),
                            form_type=form_type)
    return True


def extract_one(form_id: int, provider: str | None = None, use_llm: bool | None = None) -> str:
    """One-off extraction of a single form outside the queue (optionally with one provider). Returns its status."""
    form = queries.get_form(form_id)
    if form is None:
        raise ValueError(f"Form {form_id} not found")
    queries.set_form_status(form_id, "processing")
    try:
        extract_for_form(form, provider=provider, use_llm=use_llm)
    except Exception as exc:
        logger.exception("One-off extraction failed for form %s", form_id)
        queries.set_form_status(form_id, "failed", error=user_facing_error(exc))
    return queries.get_form(form_id)["status"]


if __name__ == "__main__":
    # python -m services.extraction_service                                → re-verify every form (no LLM calls)
    # python -m services.extraction_service --form 2 [--provider claude]   → extract one form now
    # python -m services.extraction_service --form 2 --local-only          → local OCR/barcodes only (no tokens)
    import argparse
    import sys

    from db.queries import FormFilters, list_forms

    parser = argparse.ArgumentParser()
    parser.add_argument("--form", type=int)
    parser.add_argument("--provider", choices=sorted(llm_router.PROVIDER_MODULES), default=None,
                        help="one provider only (default: config.LLM_PROVIDERS, with failover)")
    parser.add_argument("--local-only", action="store_true")
    cli = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

    if cli.form is not None:
        status = extract_one(cli.form, cli.provider, use_llm=False if cli.local_only else None)
        source = "local only" if cli.local_only else cli.provider or ", ".join(config.LLM_PROVIDERS)
        print(f"Form {cli.form} ({source}): {status}", file=sys.stderr)
    else:
        rows, _ = list_forms(FormFilters(), limit=config.EXPORT_MAX_ROWS)
        done = sum(reverify_form(row["id"]) for row in rows)
        print(f"Re-verified {done} of {len(rows)} forms.", file=sys.stderr)
