from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from db import queries

import barcode_reader as barcode_reader
import ai_extractor as ai_extractor

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"


def _find_uploaded_file(file_hash: str) -> Path | None:
    """Find the original uploaded file for a given file_hash by scanning uploads dir."""
    if not UPLOADS_DIR.exists():
        return None
    prefix = f"{file_hash}_"
    for p in UPLOADS_DIR.iterdir():
        if p.name.startswith(prefix) and p.is_file():
            return p.resolve()
    return None


def extract_for_form(form: dict[str, Any]) -> dict[str, Any]:
    """Run barcode scan, optional OCR and LLM extraction for a form, persist results.

    Returns a summary dict with status and any errors (no secrets).
    """
    form_id = form.get("id")
    file_hash = form.get("file_hash")
    if form_id is None or not file_hash:
        raise ValueError("form must include id and file_hash")

    upload_path = _find_uploaded_file(file_hash)
    if upload_path is None:
        # Nothing to do
        queries.set_form_status(form_id, "failed", error="uploaded file missing")
        return {"status": "failed", "error": "uploaded file missing"}

    # 1) Barcode scan (local, deterministic)
    try:
        lib_result = barcode_reader.scan_file(str(upload_path))
    except Exception as e:
        queries.set_form_status(form_id, "failed", error="barcode scan failed")
        return {"status": "failed", "error": "barcode scan failed"}

    # 2) LLM extraction (may raise if key missing)
    ai_result = None
    raw_llm_json = None
    try:
        ai_result = ai_extractor.extract_from_pdf(str(upload_path))
        raw_llm_json = json.dumps(ai_result, ensure_ascii=False)
    except EnvironmentError as ee:
        # Missing key or env — mark and continue without LLM
        ai_result = {}
    except Exception:
        ai_result = {}

    # 3) Build fields list from AI result (do not invent values)
    fields: list[dict[str, Any]] = []
    def _add_candidates(field_name: str, items: list[dict[str, Any]]):
        for it in items or []:
            entry = {
                "field_name": field_name,
                "value": None,
                "raw_value": it.get("value") if isinstance(it, dict) else it,
                "ocr_value": None,
                "llm_value": it.get("value") if isinstance(it, dict) else it,
                "status": "unverified",
                "page": it.get("page") if isinstance(it, dict) else None,
                "bbox": None,
            }
            fields.append(entry)

    _add_candidates("commitment_number", ai_result.get("commitment_numbers", []) if isinstance(ai_result, dict) else [])
    _add_candidates("central_number", ai_result.get("central_numbers", []) if isinstance(ai_result, dict) else [])
    # patient_names: do not split — store as first_name with a reason to verify
    for pn in (ai_result.get("patient_names", []) if isinstance(ai_result, dict) else []):
        fields.append({
            "field_name": "first_name",
            "value": None,
            "raw_value": pn.get("value") if isinstance(pn, dict) else pn,
            "ocr_value": None,
            "llm_value": pn.get("value") if isinstance(pn, dict) else pn,
            "status": "uncertain",
            "reason": "שם מלא זוהה אך נדרש פיצול/אימות אנושי",
        })
    _add_candidates("id_number", ai_result.get("id_numbers", []) if isinstance(ai_result, dict) else [])
    _add_candidates("sender", ai_result.get("sender_organizations", []) if isinstance(ai_result, dict) else [])
    _add_candidates("received_date", ai_result.get("received_dates", []) if isinstance(ai_result, dict) else [])

    # 4) Persist extraction results via queries.save_extraction
    try:
        queries.save_extraction(form_id=form_id, raw_llm_json=raw_llm_json, form_type=None, fields=fields)
    except Exception as e:
        queries.set_form_status(form_id, "failed", error="save_extraction failed")
        return {"status": "failed", "error": "save_extraction failed"}

    # 5) Prepare comparison summary using existing compare module
    try:
        from compare import compare_documents

        comparison = compare_documents(lib_result, ai_result or {})
    except Exception:
        comparison = {"file": str(upload_path), "error": "comparison failed"}

    queries.set_form_status(form_id, "extracted", error=None)

    return {"status": "extracted", "comparison": comparison}
