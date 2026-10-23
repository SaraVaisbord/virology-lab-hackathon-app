"""Verification rules: merge the evidence of every source (LLM, OCR, barcode) into reviewable field rows — one row
per value — and decide for each how far the machine can vouch for it.

Rules (labels in vocabulary.py; thresholds in VerificationRules, set from the configuration):
- `verified` needs BOTH: the field assignment proven by an OCR-read label next to the value (look-alike number
  fields — central / commitment — always need it), AND the same value read by at least two independent sources
  (LLM, OCR, barcode).
- A barcode match confirms the value READING, never which field it belongs to (barcodes have no label).
- Contradicting evidence — the same number claimed by both look-alike fields, a label pointing to the other
  field, a barcode one character off — is a `conflict`: the number is kept, never force-assigned.
- A single source (LLM alone, OCR alone) leaves the value `unverified`; failed format checks make it `uncertain`.
  A high model confidence alone never makes a value verified. Every undecided value goes to the lab worker.
- The received date is the one under the central number; different dates under different central numbers are
  never decided by the machine — the lab worker picks one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from domain.validators import digits_only, israeli_id_is_valid, match_key, parse_iso_like_date, text_key
from domain.vocabulary import (
    AMBIGUOUS_NUMBER_FIELDS,
    BARCODE_FIELDS,
    CONFIDENCE_LEVELS,
    FIELD_LABELS,
    FIELDS,
    FORM_TYPES,
    MULTI_VALUE_FIELDS,
    REASONS,
    SAMPLE_IS_COMMITMENT_FORM_TYPES,
    label_keywords,
)


@dataclass(frozen=True)
class VerificationRules:
    """The tunable thresholds of the rules."""

    received_date_max_age_days: int  # a received date further than this from today is suspicious
    local_ocr_min_confidence: float  # OCR-only values below this Tesseract confidence (0..100) are uncertain


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


# Value comparison (digits / dates / text keys) lives in validators.py — shared with the DB layer.


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
    key = text_key(value)
    if not key:
        return None
    matches = [name for name in known_senders if text_key(name) and text_key(name) in key]
    return max(matches, key=len) if matches else None


def _label_verdict(field_name: str, label: str, keywords: dict[str, tuple[str, ...]]) -> tuple[bool | None, str | None]:
    """Does the label next to the value support this field? Returns (supports, other_field_it_points_to).
    keywords: label words per field for this page (see label_keywords)."""
    if not label:
        return None, None
    if any(word in label for word in keywords.get(field_name, ())):
        return True, None
    for other, words in keywords.items():
        if other != field_name and any(word in label for word in words):
            return False, other
    return None, None


def _ocr_confidence_level(confidence: float) -> str:
    return next((level for threshold, level in _OCR_CONFIDENCE_LEVELS if confidence >= threshold), "low")


# ── Field evaluation ─────────────────────────────────────────────────────────


def _barcode_candidates(value_key: str, barcodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for barcode in barcodes:
        key = digits_only(barcode.get("data"))
        match = "exact" if key == value_key else "near" if _one_edit_apart(key, value_key) else None
        if match:
            candidates.append({"data": barcode["data"], "type": barcode.get("type"), "match": match, "box": _box_from_barcode(barcode)})
    return candidates


def _format_doubts(field_name: str, value: str, ctx: dict[str, Any]) -> tuple[str, list[str]]:
    """Normalize the value for display and return the format problems found."""
    doubts: list[str] = []
    if field_name == "id_number":
        value = digits_only(value)
        if not israeli_id_is_valid(value):
            doubts.append(REASONS["invalid_id_checksum"])
    elif field_name == "received_date":
        parsed = parse_iso_like_date(value)
        if parsed is None:
            doubts.append(REASONS["invalid_date"])
        else:
            value = parsed.strftime("%d/%m/%Y")
            if not 0 <= (date.today() - parsed.date()).days <= ctx["rules"].received_date_max_age_days:
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
    label_supports, label_other = _label_verdict(field_name, llm_label, ctx["label_keywords"])
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
    if not llm and local_source and local_source.startswith("ocr") and local["confidence"] < ctx["rules"].local_ocr_min_confidence:
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
            "ocr": ({key_: local.get(key_) for key_ in ("raw", "source", "confidence", "label", "distance", "anchor")} if local
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


def form_type_of(ocr_result: dict[str, Any] | None, llm_result: dict[str, Any] | None) -> str | None:
    """The health-fund form type: recognised on the page by the OCR, otherwise as reported by the LLM."""
    for result in (ocr_result, llm_result):
        form_type = (result or {}).get("form_type")
        if form_type in FORM_TYPES:
            return form_type
    return None


def sample_is_commitment_on(ocr_result: dict[str, Any] | None, form_type: str | None) -> bool:
    """Does "דגימה" label the commitment number on this page? Leumit forms, or the page says so itself (seen by OCR)."""
    return form_type in SAMPLE_IS_COMMITMENT_FORM_TYPES or bool((ocr_result or {}).get("sample_is_commitment"))


def build_fields(
    llm_result: dict[str, Any] | None,
    barcodes: list[dict[str, Any]],
    known_senders: list[str],
    rules: VerificationRules,
    page: int | None = None,
    local_candidates: list[dict[str, Any]] | None = None,
    ocr_numbers: list[dict[str, Any]] | None = None,
    sample_is_commitment: bool = False,
) -> list[dict[str, Any]]:
    """Merge LLM candidates, local (OCR/barcode) candidates and barcodes into field rows (one row per value).
    ocr_numbers: numbers the OCR read without a label (they confirm readings, not assignments).
    sample_is_commitment: "דגימה" labels the commitment number on this page (see sample_is_commitment_on)."""
    llm_result = llm_result or {}
    local_candidates = local_candidates or []
    ocr_unlabeled = {digits_only(n["value"]): n["raw"] for n in ocr_numbers or [] if n.get("source", "ocr").startswith("ocr")}
    llm_by_field = {name: _llm_candidates(llm_result, name) for name in FIELDS}

    llm_claims: dict[str, set[str]] = {}
    local_claims: dict[str, set[str]] = {}
    for name in AMBIGUOUS_NUMBER_FIELDS:
        for item in llm_by_field[name]:
            llm_claims.setdefault(match_key(name, item["value"]), set()).add(name)
    for item in local_candidates:
        if item["field"] in AMBIGUOUS_NUMBER_FIELDS:
            local_claims.setdefault(match_key(item["field"], item["value"]), set()).add(item["field"])

    ctx = {
        "rules": rules,
        "barcodes": [b for b in barcodes if b.get("data")],
        "known_senders": known_senders,
        "llm_claims": llm_claims,
        "local_claims": local_claims,
        "ocr_numbers": ocr_unlabeled,
        "label_keywords": label_keywords(sample_is_commitment),
    }

    fields: list[dict[str, Any]] = []
    for field_name in FIELDS:
        # Group every reading of this field by its comparable key (LLM first, best local candidate per key).
        llm_items: dict[str, dict] = {}
        for item in llm_by_field[field_name]:
            llm_items.setdefault(match_key(field_name, item["value"]), item)
        local_items: dict[str, dict] = {}
        for item in sorted((c for c in local_candidates if c["field"] == field_name), key=lambda c: (c.get("rank", 0), c["distance"])):
            local_items.setdefault(match_key(field_name, item["value"]), item)
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
        # Several central numbers with different dates under them: not the machine's call, even if one is verified.
        anchored = [e["value"] for e in entries if ((e["evidence"].get("ocr") or {}).get("anchor"))]
        if len(set(anchored)) > 1:
            if best["status"] != "conflict":
                best["status"] = "uncertain"
            best["reason"] = " · ".join(filter(None, [best.get("reason"), REASONS["received_dates_differ"].format(dates=", ".join(anchored))]))
        fields.append({**best, "page": page})
    return fields
