"""Extraction pipeline for one form page.

    preprocess (upright, deskewed, clean)  →  barcodes  →  local OCR extraction  →  [LLM, if enabled]  →  merge

Each source's raw result is stored separately on the form (barcode_result / ocr_result / llm_result) as soon as
it finishes, so a failure of one source never discards another's evidence. `build_fields` merges the evidence
into reviewable field rows — one row per value.

Verification rules (labels/thresholds in db/constants.py and config.py):
- `verified` needs BOTH: the field assignment proven by an OCR-read label next to the value (look-alike number
  fields — central / commitment — always need it), AND the same value read by at least two independent sources
  (LLM, OCR, barcode).
- A barcode match confirms the value READING, never which field it belongs to (barcodes have no label).
- Contradicting evidence — the same number claimed by both look-alike fields, a label pointing to the other
  field, a barcode one character off — is a `conflict`: the number is kept, never force-assigned.
- A single source (LLM alone, OCR alone) leaves the value `unverified`; failed format checks make it `uncertain`.
  A high model confidence alone never makes a value verified. Every undecided value goes to the lab worker.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

import ai_extractor
import barcode_reader
import config
import local_extractor
import ocr_reader
from db import queries
from db.constants import (
    AMBIGUOUS_NUMBER_FIELDS,
    BARCODE_FIELDS,
    CONFIDENCE_LEVELS,
    EXTRACTION_ERRORS,
    FIELD_LABEL_KEYWORDS,
    FIELD_LABELS,
    FIELDS,
    MULTI_VALUE_FIELDS,
    OCR_UNAVAILABLE_REASON,
    REASONS,
)
from preprocessing import preprocess
from services.forms_service import resolve_image_path
from validators import israeli_id_is_valid, parse_iso_like_date

logger = logging.getLogger(__name__)

_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}
_BOX_SCALE = 1000  # Gemini box_2d coordinates are normalized to 0..1000
# zbar sometimes reports a 1-pixel scan line instead of the barcode area; such boxes are useless for highlighting.
_MIN_BARCODE_BOX_SIDE = 0.005
# Near-match (one character off) is only meaningful for reasonably long codes.
_NEAR_MATCH_MIN_LENGTH = 4
_BOX_KEYS = ("x", "y", "width", "height")
_NUMBER_FIELDS = BARCODE_FIELDS  # central / commitment / id — compared as digit strings
# Tesseract confidence (0..100) mapped onto the confidence levels used for LLM values.
_OCR_CONFIDENCE_LEVELS = ((85, "high"), (60, "medium"))


# ── Normalization (for comparison only — original values are always kept) ────


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _text_key(value: str) -> str:
    return re.sub(r"[\s\"'״׳()\-]", "", value)


def _match_key(field_name: str, value: Any) -> str:
    """The form in which two readings of the same value compare equal."""
    text = str(value or "").strip()
    if field_name in _NUMBER_FIELDS:
        return _digits(text)
    if field_name == "received_date":
        parsed = parse_iso_like_date(text)
        return parsed.strftime("%d/%m/%Y") if parsed else text
    return _text_key(text)


def _one_edit_apart(a: str, b: str) -> bool:
    """True when two different codes differ by exactly one substitution, insertion or deletion."""
    if a == b or min(len(a), len(b)) < _NEAR_MATCH_MIN_LENGTH or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    shorter, longer = sorted((a, b), key=len)
    return any(longer[:i] + longer[i + 1:] == shorter for i in range(len(longer)))


def _box_from_gemini(candidate: dict[str, Any]) -> dict[str, float] | None:
    box = candidate.get("box_2d")
    if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
        return None
    ymin, xmin, ymax, xmax = (min(max(v / _BOX_SCALE, 0.0), 1.0) for v in box)
    if xmax <= xmin or ymax <= ymin:
        return None
    return {"x": xmin, "y": ymin, "width": xmax - xmin, "height": ymax - ymin}


def _box_from_barcode(barcode: dict[str, Any]) -> dict[str, float] | None:
    if min(barcode.get("width") or 0, barcode.get("height") or 0) < _MIN_BARCODE_BOX_SIDE:
        return None
    return {key: barcode[key] for key in _BOX_KEYS}


def match_sender(value: str, known_senders: list[str]) -> str | None:
    """Exact match, otherwise the longest known sender name contained in the value."""
    key = _text_key(value)
    if not key:
        return None
    matches = [name for name in known_senders if _text_key(name) and _text_key(name) in key]
    return max(matches, key=len) if matches else None


def _label_verdict(field_name: str, label: str) -> tuple[bool | None, str | None]:
    """Does the label next to the value support this field? Returns (supports, other_field_it_points_to)."""
    if not label:
        return None, None
    if any(word in label for word in FIELD_LABEL_KEYWORDS.get(field_name, ())):
        return True, None
    for other, words in FIELD_LABEL_KEYWORDS.items():
        if other != field_name and any(word in label for word in words):
            return False, other
    return None, None


def _ocr_confidence_level(confidence: float) -> str:
    return next((level for threshold, level in _OCR_CONFIDENCE_LEVELS if confidence >= threshold), "low")


# ── Field evaluation ─────────────────────────────────────────────────────────


def _barcode_candidates(value_key: str, barcodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for barcode in barcodes:
        key = _digits(barcode.get("data"))
        match = "exact" if key == value_key else "near" if _one_edit_apart(key, value_key) else None
        if match:
            candidates.append({"data": barcode["data"], "type": barcode.get("type"), "match": match, "box": _box_from_barcode(barcode)})
    return candidates


def _format_doubts(field_name: str, value: str, ctx: dict[str, Any]) -> tuple[str, list[str]]:
    """Normalize the value for display and return the format problems found."""
    doubts: list[str] = []
    if field_name == "id_number":
        value = _digits(value)
        if not israeli_id_is_valid(value):
            doubts.append(REASONS["invalid_id_checksum"])
    elif field_name == "received_date":
        parsed = parse_iso_like_date(value)
        if parsed is None:
            doubts.append(REASONS["invalid_date"])
        else:
            value = parsed.strftime("%d/%m/%Y")
            if not 0 <= (date.today() - parsed.date()).days <= config.RECEIVED_DATE_MAX_AGE_DAYS:
                doubts.append(REASONS["implausible_date"])
    elif field_name == "sender":
        known = match_sender(value, ctx["known_senders"])
        if known:
            value = known
        else:
            doubts.append(REASONS["unknown_sender"])
    return value, doubts


def _evaluate(field_name: str, key: str, llm: dict[str, Any] | None, local: dict[str, Any] | None, ctx: dict[str, Any]) -> dict[str, Any]:
    """Merge one value's evidence from the LLM candidate and/or the local (OCR/barcode) candidate."""
    llm_raw = str(llm.get("value") or "").strip() if llm else None
    llm_confidence = llm.get("confidence") if llm and llm.get("confidence") in CONFIDENCE_LEVELS else None
    llm_label = str(llm.get("label") or "").strip() if llm else ""
    llm_box = _box_from_gemini(llm) if llm else None
    local_source = local["source"] if local else None
    ocr_raw = local["raw"] if local and local_source.startswith("ocr") else None
    # The OCR may have read the same number somewhere on the page without a label: that confirms the READING
    # (an independent second source) but not the assignment.
    ocr_seen_unlabeled = None if ocr_raw or field_name not in _NUMBER_FIELDS else ctx["ocr_numbers"].get(key)
    conflicts: list[str] = []

    # Value readings by independent sources.
    barcodes = _barcode_candidates(key, ctx["barcodes"]) if field_name in BARCODE_FIELDS else []
    exact = next((b for b in barcodes if b["match"] == "exact"), None)
    barcode_reading = exact["data"] if exact else (local["raw"] if local_source == "barcode" else None)
    readings = [r for r in (llm_raw, ocr_raw or ocr_seen_unlabeled, barcode_reading) if r]
    if not exact:
        conflicts += [REASONS["barcode_near_match"].format(barcode=b["data"]) for b in barcodes if b["match"] == "near"]
    agreement = "conflict" if conflicts else "agree" if len(readings) >= 2 else "insufficient"

    # Field assignment evidence: the LLM's label, the OCR label next to the value, other fields claiming it.
    label_supports, label_other = _label_verdict(field_name, llm_label)
    if label_other:
        conflicts.append(REASONS["label_points_elsewhere"].format(label=llm_label, other=FIELD_LABELS[label_other]))
    also_claimed_by: list[str] = []
    if field_name in AMBIGUOUS_NUMBER_FIELDS:
        also_claimed_by = sorted(ctx["llm_claims"].get(key, set()) - {field_name})
        conflicts += [REASONS["claimed_by_other_field"].format(other=FIELD_LABELS[o]) for o in also_claimed_by]
        ocr_elsewhere = sorted(ctx["local_claims"].get(key, set()) - {field_name})
        conflicts += [REASONS["ocr_label_elsewhere"].format(other=FIELD_LABELS[o]) for o in ocr_elsewhere]
    else:
        ocr_elsewhere = []
    assignment_proven = local is not None or field_name not in AMBIGUOUS_NUMBER_FIELDS

    value, doubts = _format_doubts(field_name, llm_raw if llm_raw else local["value"], ctx)
    if llm and llm_confidence != "high":
        doubts.append(str(llm.get("reason") or "").strip() or REASONS["low_confidence"])
    if not llm and local_source and local_source.startswith("ocr") and local["confidence"] < config.LOCAL_OCR_MIN_CONFIDENCE:
        doubts.append(REASONS["low_confidence"])

    if conflicts:
        status, reasons = "conflict", conflicts + doubts
    elif doubts:
        status, reasons = "uncertain", doubts
    elif len(readings) >= 2 and assignment_proven:
        status, reasons = "verified", []
    elif len(readings) >= 2:
        status, reasons = "unverified", [REASONS["assignment_llm_only"]]
    else:
        status, reasons = "unverified", [REASONS["single_source"] if llm else REASONS["local_only"]]

    if exact and exact["box"]:
        box, box_source = exact["box"], "barcode"
    elif local:
        box, box_source = local["box"], ("barcode" if local_source == "barcode" else "ocr")
    else:
        box, box_source = llm_box, ("llm" if llm_box else None)

    confidence = llm_confidence or (_ocr_confidence_level(local["confidence"]) if local else None)
    return {
        "field_name": field_name,
        "value": value,
        "llm_value": llm_raw,
        "ocr_value": ocr_raw or ocr_seen_unlabeled,
        "barcode_value": barcode_reading,
        "confidence": confidence,
        "status": status,
        "reason": " · ".join(dict.fromkeys(reasons)) or None,
        "box_source": box_source,
        **(box or {}),
        "evidence": {
            "llm": {"value": llm_raw, "confidence": llm_confidence, "label": llm_label or None, "reason": llm.get("reason") or None, "box": llm_box} if llm else None,
            "ocr": ({key_: local[key_] for key_ in ("raw", "source", "confidence", "label", "distance")} if local
                    else {"raw": ocr_seen_unlabeled, "source": "ocr", "confidence": None, "label": None, "distance": None} if ocr_seen_unlabeled
                    else None),
            "barcode_candidates": barcodes,
            "ocr_candidates": [r for r in (ocr_raw, ocr_seen_unlabeled) if r],
            "assignment": {
                "label": llm_label or None,
                "label_supports": label_supports,
                "ocr_label": local["label"] if local else None,
                "also_claimed_by": also_claimed_by,
                "ocr_assigned_elsewhere": ocr_elsewhere,
            },
            "agreement": agreement,
            "sources": sorted(s for s, present in (("llm", llm_raw), ("ocr", ocr_raw or ocr_seen_unlabeled), ("barcode", barcode_reading)) if present),
        },
    }


def _llm_candidates(llm_result: dict[str, Any], field_name: str) -> list[dict[str, Any]]:
    raw = llm_result.get(field_name)
    items = [item if isinstance(item, dict) else {"value": item} for item in raw] if isinstance(raw, list) else []
    items = [item for item in items if str(item.get("value") or "").strip()]
    items.sort(key=lambda item: _CONFIDENCE_RANK.get(item.get("confidence"), len(_CONFIDENCE_RANK)))
    return items


def _not_found(field_name: str, page: int | None) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "status": "not_found",
        "reason": REASONS["not_found"],
        "page": page,
        "evidence": {"llm": None, "ocr": None, "barcode_candidates": [], "ocr_candidates": [], "assignment": None, "agreement": "insufficient", "sources": []},
    }


_STATUS_PREFERENCE = {"verified": 0, "unverified": 1, "uncertain": 2, "conflict": 3}


def build_fields(
    llm_result: dict[str, Any] | None,
    barcodes: list[dict[str, Any]],
    known_senders: list[str],
    page: int | None = None,
    local_candidates: list[dict[str, Any]] | None = None,
    ocr_numbers: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge LLM candidates, local (OCR/barcode) candidates and barcodes into field rows (one row per value).
    ocr_numbers: numbers the OCR read without a label (they confirm readings, not assignments)."""
    llm_result = llm_result or {}
    local_candidates = local_candidates or []
    ocr_unlabeled = {_digits(n["value"]): n["raw"] for n in ocr_numbers or [] if n.get("source", "ocr").startswith("ocr")}
    llm_by_field = {name: _llm_candidates(llm_result, name) for name in FIELDS}

    llm_claims: dict[str, set[str]] = {}
    local_claims: dict[str, set[str]] = {}
    for name in AMBIGUOUS_NUMBER_FIELDS:
        for item in llm_by_field[name]:
            llm_claims.setdefault(_match_key(name, item["value"]), set()).add(name)
    for item in local_candidates:
        if item["field"] in AMBIGUOUS_NUMBER_FIELDS:
            local_claims.setdefault(_match_key(item["field"], item["value"]), set()).add(item["field"])

    ctx = {
        "barcodes": [b for b in barcodes if b.get("data")],
        "known_senders": known_senders,
        "llm_claims": llm_claims,
        "local_claims": local_claims,
        "ocr_numbers": ocr_unlabeled,
    }

    fields: list[dict[str, Any]] = []
    for field_name in FIELDS:
        # Group every reading of this field by its comparable key (LLM first, best local candidate per key).
        llm_items: dict[str, dict] = {}
        for item in llm_by_field[field_name]:
            llm_items.setdefault(_match_key(field_name, item["value"]), item)
        local_items: dict[str, dict] = {}
        for item in sorted((c for c in local_candidates if c["field"] == field_name), key=lambda c: (c.get("rank", 0), c["distance"])):
            local_items.setdefault(_match_key(field_name, item["value"]), item)
        keys = list(dict.fromkeys([*llm_items, *local_items]))
        if not keys:
            fields.append(_not_found(field_name, page))
            continue

        entries = [_evaluate(field_name, key, llm_items.get(key), local_items.get(key), ctx) for key in keys]
        if field_name in MULTI_VALUE_FIELDS:
            fields.extend({**entry, "page": page} for entry in entries)
            continue

        # Single-value field: keep the best-supported value; the others are alternatives for the lab worker.
        entries.sort(key=lambda e: (_STATUS_PREFERENCE.get(e["status"], 9), -len(e["evidence"]["sources"])))
        best, alternatives = entries[0], [e["value"] for e in entries[1:]]
        if alternatives:
            best["evidence"]["alternatives"] = alternatives
            if best["status"] != "verified":
                best["status"] = "uncertain" if best["status"] != "conflict" else "conflict"
                best["reason"] = " · ".join(filter(None, [best.get("reason"), f"נמצאו ערכים נוספים: {', '.join(alternatives)}"]))
        fields.append({**best, "page": page})
    return fields


# ── Sources ──────────────────────────────────────────────────────────────────


def user_facing_error(exc: Exception) -> str:
    """Short Hebrew message for the UI; technical details are logged, never shown or stored."""
    if isinstance(exc, ai_extractor.MissingApiKeyError):
        return EXTRACTION_ERRORS["config"]
    if isinstance(exc, ai_extractor.ModelsUnavailableError):
        return EXTRACTION_ERRORS["quota"]
    if isinstance(exc, ai_extractor.ExtractionError):
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


def write_image(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Cannot encode image")
    encoded.tofile(str(path))


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


def _llm_module(provider: str):
    """LLM providers share one interface: extract_from_image(image_path, known_senders) -> dict in the same shape.
    Looked up at call time (not cached) so tests can monkeypatch the providers."""
    if provider == "gemini":
        return ai_extractor
    if provider == "openai":
        import openai_extractor

        return openai_extractor
    raise ValueError(f"Unknown LLM provider: {provider!r}")


LLM_PROVIDERS = ("gemini", "openai")


def extract_for_form(form: dict[str, Any], provider: str = "gemini", use_llm: bool | None = None) -> None:
    """Run all sources for one page, persist each result separately, then build the field rows.

    The page image is replaced by its preprocessed (upright, deskewed, highlighter-free) version first, so every
    source and the UI share one geometry. use_llm defaults to config.LLM_ENABLED; without it no LLM is called
    (no tokens) and only an LLM answer already stored for the page is merged. Raises on LLM failure — local
    results are already saved by then."""
    form_id, page = form["id"], form.get("page_number")
    image_path = resolve_image_path(form.get("image_path"))
    if image_path is None:
        raise FileNotFoundError("page image not found")
    use_llm = config.LLM_ENABLED if use_llm is None else use_llm

    views = preprocess(read_image(image_path), source_dpi=config.PAGE_RENDER_DPI)
    write_image(image_path, views.normalized)

    barcode_result = run_barcode_scan(views, page)
    ocr_result = run_ocr(views, barcode_result["items"], page)
    errors = {source: result["error"] for source, result in (("barcode", barcode_result), ("ocr", ocr_result)) if result["status"] == "error"}
    queries.save_source_results(form_id, barcode_result=barcode_result, ocr_result=ocr_result, source_errors=errors or None)

    known_senders = [name for name, _kind in queries.list_senders()]
    # Without a new LLM call, an answer already stored for this page (from an earlier run) is still merged.
    llm_result = (queries.get_form(form_id, with_sources=True) or {}).get("sources", {}).get("llm_result")
    if use_llm:
        try:
            llm_result = _llm_module(provider).extract_from_image(image_path, known_senders)
        except Exception as exc:
            queries.save_source_results(form_id, source_errors={**errors, "llm": user_facing_error(exc)})
            raise
        queries.save_source_results(form_id, llm_result=llm_result)

    fields = build_fields(llm_result, barcode_result["items"], known_senders, page=page, local_candidates=ocr_result["candidates"],
                          ocr_numbers=ocr_result.get("unassigned_numbers"))
    queries.save_extraction(form_id, fields)


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
    queries.save_extraction(form_id, build_fields(sources.get("llm_result"), barcodes, known_senders, page=form["page_number"],
                                                  local_candidates=local, ocr_numbers=ocr_numbers))
    return True


def extract_one(form_id: int, provider: str, use_llm: bool | None = None) -> str:
    """One-off extraction of a single form outside the queue (e.g. with OpenAI). Returns the final form status."""
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
    # python -m services.extraction_service --form 2 [--provider openai]   → extract one form now
    # python -m services.extraction_service --form 2 --local-only          → local OCR/barcodes only (no tokens)
    import argparse
    import sys

    from db.queries import FormFilters, list_forms

    parser = argparse.ArgumentParser()
    parser.add_argument("--form", type=int)
    parser.add_argument("--provider", choices=LLM_PROVIDERS, default="gemini")
    parser.add_argument("--local-only", action="store_true")
    cli = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

    if cli.form is not None:
        status = extract_one(cli.form, cli.provider, use_llm=False if cli.local_only else None)
        print(f"Form {cli.form} ({'local only' if cli.local_only else cli.provider}): {status}", file=sys.stderr)
    else:
        rows, _ = list_forms(FormFilters(), limit=config.EXPORT_MAX_ROWS)
        done = sum(reverify_form(row["id"]) for row in rows)
        print(f"Re-verified {done} of {len(rows)} forms.", file=sys.stderr)
