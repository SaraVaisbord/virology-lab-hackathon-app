"""Extraction pipeline for one form page.

Three independent sources read the page; each one's raw result is stored separately on the form
(llm_result / barcode_result / ocr_result) as soon as it finishes, so a failure of one source never
discards another's evidence. `build_fields` then turns the evidence into reviewable field rows.

Verification rules (see also db/constants.py):
- A barcode match confirms the value READING, never which field it belongs to (barcodes have no label).
- central_number / commitment_number look alike, so a value is only `verified` for them when there is
  independent evidence for the assignment (a label read by OCR). Without OCR they stay `unverified`.
- Contradicting evidence (same number claimed by both fields, a label pointing to the other field,
  a barcode differing by one character) is a `conflict` — the number is kept, never force-assigned.
- A high model confidence alone never makes a value verified.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

import ai_extractor
import barcode_reader
import config
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


# ── Normalization (for comparison only — original values are always kept) ────


def _code_key(value: Any) -> str:
    return re.sub(r"[\s\-]", "", str(value or "")).upper()


def _text_key(value: str) -> str:
    return re.sub(r"[\s\"'״׳()\-]", "", value)


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


# ── Field evaluation ─────────────────────────────────────────────────────────


def _barcode_candidates(value_key: str, barcodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for barcode in barcodes:
        key = _code_key(barcode.get("data"))
        match = "exact" if key == value_key else "near" if _one_edit_apart(key, value_key) else None
        if match:
            candidates.append({"data": barcode["data"], "type": barcode.get("type"), "match": match, "box": _box_from_barcode(barcode)})
    return candidates


def _evaluate(field_name: str, candidate: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    raw = str(candidate.get("value") or "").strip()
    confidence = candidate.get("confidence") if candidate.get("confidence") in CONFIDENCE_LEVELS else None
    label = str(candidate.get("label") or "").strip()
    llm_box = _box_from_gemini(candidate)
    value = raw
    conflicts: list[str] = []
    doubts: list[str] = []

    # Value reading: compare with barcodes (exact = same reading, near = one character off).
    barcodes = _barcode_candidates(_code_key(raw), ctx["barcodes"]) if field_name in BARCODE_FIELDS else []
    exact = next((b for b in barcodes if b["match"] == "exact"), None)
    for near in (b for b in barcodes if b["match"] == "near"):
        conflicts.append(REASONS["barcode_near_match"].format(barcode=near["data"]))
    agreement = "conflict" if conflicts else "agree" if exact else "insufficient"

    # Field assignment: label next to the value and whether another field claims the same number.
    label_supports, label_other = _label_verdict(field_name, label)
    if label_other:
        conflicts.append(REASONS["label_points_elsewhere"].format(label=label, other=FIELD_LABELS[label_other]))
    also_claimed_by = sorted(ctx["claims"].get(_code_key(raw), set()) - {field_name}) if field_name in AMBIGUOUS_NUMBER_FIELDS else []
    for other in also_claimed_by:
        conflicts.append(REASONS["claimed_by_other_field"].format(other=FIELD_LABELS[other]))

    # Format checks on the normalized value (they can only lower the status, never raise it).
    if field_name == "id_number":
        value = re.sub(r"\D", "", raw)
        if not israeli_id_is_valid(value):
            doubts.append(REASONS["invalid_id_checksum"])
    elif field_name == "received_date":
        parsed = parse_iso_like_date(raw)
        if parsed is None:
            doubts.append(REASONS["invalid_date"])
        else:
            value = parsed.strftime("%d/%m/%Y")
            if not 0 <= (date.today() - parsed.date()).days <= config.RECEIVED_DATE_MAX_AGE_DAYS:
                doubts.append(REASONS["implausible_date"])
    elif field_name == "sender":
        known = match_sender(raw, ctx["known_senders"])
        if known:
            value = known
        else:
            doubts.append(REASONS["unknown_sender"])
    if confidence != "high":
        doubts.append(str(candidate.get("reason") or "").strip() or REASONS["low_confidence"])

    # OCR label evidence is the only independent proof of assignment for look-alike number fields.
    assignment_proven = field_name not in AMBIGUOUS_NUMBER_FIELDS or ctx["ocr_label_supports"](field_name, raw)
    if conflicts:
        status, reasons = "conflict", conflicts + doubts
    elif doubts:
        status, reasons = "uncertain", doubts
    elif agreement == "agree" and assignment_proven:
        status, reasons = "verified", []
    else:
        status, reasons = "unverified", [REASONS["assignment_llm_only"] if agreement == "agree" else REASONS["single_source"]]

    box, box_source = (exact["box"], "barcode") if exact and exact["box"] else (llm_box, "llm") if llm_box else (None, None)
    return {
        "field_name": field_name,
        "value": value,
        "llm_value": raw,
        "barcode_value": exact["data"] if exact else None,
        "ocr_value": None,
        "confidence": confidence,
        "status": status,
        "reason": " · ".join(dict.fromkeys(reasons)) or None,
        "box_source": box_source,
        **(box or {}),
        "evidence": {
            "llm": {"value": raw, "confidence": confidence, "label": label or None, "reason": candidate.get("reason") or None, "box": llm_box},
            "barcode_candidates": barcodes,
            "ocr_candidates": [],
            "assignment": {"label": label or None, "label_supports": label_supports, "also_claimed_by": also_claimed_by},
            "agreement": agreement,
        },
    }


def _candidates(llm_result: dict[str, Any], field_name: str) -> list[dict[str, Any]]:
    raw = llm_result.get(field_name)
    items = [item if isinstance(item, dict) else {"value": item} for item in raw] if isinstance(raw, list) else []
    items = [item for item in items if str(item.get("value") or "").strip()]
    items.sort(key=lambda item: _CONFIDENCE_RANK.get(item.get("confidence"), len(_CONFIDENCE_RANK)))

    unique, seen = [], set()
    for item in items:
        key = _code_key(item["value"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _not_found(field_name: str, page: int | None) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "status": "not_found",
        "reason": REASONS["not_found"],
        "page": page,
        "evidence": {"llm": None, "barcode_candidates": [], "ocr_candidates": [], "assignment": None, "agreement": "insufficient"},
    }


def build_fields(
    llm_result: dict[str, Any],
    barcodes: list[dict[str, Any]],
    known_senders: list[str],
    page: int | None = None,
    ocr_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Turn the per-source evidence into field rows (one row per value) with status, reason and evidence."""
    candidates = {name: _candidates(llm_result or {}, name) for name in FIELDS}
    claims: dict[str, set[str]] = {}
    for name in AMBIGUOUS_NUMBER_FIELDS:
        for item in candidates[name]:
            claims.setdefault(_code_key(item["value"]), set()).add(name)

    ctx = {
        "barcodes": [b for b in barcodes if b.get("data")],
        "known_senders": known_senders,
        "claims": claims,
        # No OCR engine yet (ocr_items is always empty), so no label can be confirmed independently.
        "ocr_label_supports": lambda field_name, value: False,
    }

    fields: list[dict[str, Any]] = []
    for field_name in FIELDS:
        items = candidates[field_name]
        if not items:
            fields.append(_not_found(field_name, page))
            continue
        if field_name in MULTI_VALUE_FIELDS:
            fields.extend({**_evaluate(field_name, item, ctx), "page": page} for item in items)
            continue

        entry = _evaluate(field_name, items[0], ctx)
        alternatives = [str(item["value"]) for item in items[1:]]
        if alternatives:
            entry["evidence"]["llm_alternatives"] = alternatives
            if entry["status"] in ("verified", "unverified"):
                entry["status"] = "uncertain"
            entry["reason"] = " · ".join(filter(None, [entry.get("reason"), f"נמצאו ערכים נוספים: {', '.join(alternatives)}"]))
        fields.append({**entry, "page": page})
    return fields


# ── Sources ──────────────────────────────────────────────────────────────────


def user_facing_error(exc: Exception) -> str:
    """Short Hebrew message for the UI; technical details are logged, never shown or stored."""
    if isinstance(exc, ai_extractor.MissingApiKeyError):
        return EXTRACTION_ERRORS["config"]
    if isinstance(exc, ai_extractor.QuotaExceededError):
        return EXTRACTION_ERRORS["quota"]
    if isinstance(exc, ai_extractor.ExtractionError):
        return EXTRACTION_ERRORS["timeout" if "timed out" in str(exc).lower() else "model"]
    if isinstance(exc, FileNotFoundError):
        return EXTRACTION_ERRORS["image_missing"]
    return EXTRACTION_ERRORS["unexpected"]


def run_barcode_scan(image_path, page: int | None) -> dict[str, Any]:
    """Local barcode scan. Returns {"status": "ok", "items": [...]} or {"status": "error", "error": ...}."""
    try:
        items = barcode_reader.scan_image(image_path)
    except Exception as exc:
        logger.warning("Barcode scan failed: %s", type(exc).__name__)
        return {"status": "error", "error": EXTRACTION_ERRORS["barcode"], "items": []}
    return {"status": "ok", "items": [{**item, "page": page} for item in items]}


def run_ocr(image_path, page: int | None) -> dict[str, Any]:
    """OCR source. No OCR engine is installed in this project, so the result says so explicitly
    (instead of silently returning nothing). Plug an engine in here; build_fields already accepts ocr_items."""
    return {"status": "unavailable", "reason": OCR_UNAVAILABLE_REASON, "items": []}


def extract_for_form(form: dict[str, Any]) -> None:
    """Run all sources for one page, persist each result separately, then build the field rows.
    Raises on LLM failure (the queue marks the form failed / re-queues it) — barcode/OCR results are already saved."""
    form_id, page = form["id"], form.get("page_number")
    image_path = resolve_image_path(form.get("image_path"))
    if image_path is None:
        raise FileNotFoundError("page image not found")

    barcode_result = run_barcode_scan(image_path, page)
    ocr_result = run_ocr(image_path, page)
    errors = {"barcode": barcode_result["error"]} if barcode_result["status"] == "error" else {}
    queries.save_source_results(form_id, barcode_result=barcode_result, ocr_result=ocr_result, source_errors=errors or None)

    known_senders = [name for name, _kind in queries.list_senders()]
    try:
        llm_result = ai_extractor.extract_from_image(image_path, known_senders)
    except Exception as exc:
        queries.save_source_results(form_id, source_errors={**errors, "llm": user_facing_error(exc)})
        raise
    queries.save_source_results(form_id, llm_result=llm_result)

    fields = build_fields(llm_result, barcode_result["items"], known_senders, page=page, ocr_items=ocr_result["items"])
    queries.save_extraction(form_id, fields)


def reverify_form(form_id: int) -> bool:
    """Re-run the verification rules on the stored source results (no new Gemini call). Returns False if the
    form has no stored LLM result."""
    form = queries.get_form(form_id, with_sources=True)
    sources = (form or {}).get("sources") or {}
    if not sources.get("llm_result"):
        return False
    barcodes = (sources.get("barcode_result") or {}).get("items", [])
    ocr_items = (sources.get("ocr_result") or {}).get("items", [])
    known_senders = [name for name, _kind in queries.list_senders()]
    queries.save_extraction(form_id, build_fields(sources["llm_result"], barcodes, known_senders, page=form["page_number"], ocr_items=ocr_items))
    return True


if __name__ == "__main__":
    # python -m services.extraction_service  → re-verify every form that already has an LLM result
    import sys

    from db.queries import FormFilters, list_forms

    rows, _ = list_forms(FormFilters(), limit=config.EXPORT_MAX_ROWS)
    done = sum(reverify_form(row["id"]) for row in rows)
    print(f"Re-verified {done} of {len(rows)} forms.", file=sys.stderr)
