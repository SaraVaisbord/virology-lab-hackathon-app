"""
compare.py - Compare barcode-reader results with AI extraction results.
"""

from __future__ import annotations
import re
from typing import Any

# ── Comparison status labels ─────────────────────────────────────────────────
AGREE = "agreement"
DISAGREE = "disagreement"
LIBRARY_ONLY = "library_only"
AI_ONLY = "ai_only"
AMBIGUOUS = "ambiguous"


def normalize(value: Any) -> str:
    """
    Normalize a barcode/field value for comparison.
    - Strip surrounding whitespace only (preserve leading zeros and internal spaces).
    - Uppercase for case-insensitive comparison.
    """
    if value is None:
        return ""
    return str(value).strip().upper()


def _match_key(bc: dict) -> tuple:
    """Primary match key: (page, normalized_value)."""
    return (bc.get("page"), normalize(bc.get("data") or bc.get("value", "")))


def compare_barcodes(library_result: dict, ai_result: dict) -> list[dict]:
    """
    Match library barcodes to AI barcodes.

    Matching strategy:
    1. Exact match on (page, normalized_value).
    2. If page is missing on one side, fall back to value-only match.
    3. Unmatched entries are labelled library_only or ai_only.
    4. If multiple AI entries share the same value on the same page → ambiguous.
    """
    lib_barcodes = library_result.get("barcodes", [])
    ai_barcodes = ai_result.get("barcodes", [])

    comparisons = []
    used_ai_indices: set[int] = set()

    for lib_bc in lib_barcodes:
        lib_val = normalize(lib_bc.get("data", ""))
        lib_page = lib_bc.get("page")

        # Try exact (page + value) match first
        candidates = [
            i for i, a in enumerate(ai_barcodes)
            if i not in used_ai_indices
            and normalize(a.get("value", "")) == lib_val
            and a.get("page") == lib_page
        ]

        # Fall back to value-only match if page is missing on AI side
        if not candidates:
            candidates = [
                i for i, a in enumerate(ai_barcodes)
                if i not in used_ai_indices
                and normalize(a.get("value", "")) == lib_val
                and a.get("page") is None
            ]

        if len(candidates) == 1:
            ai_idx = candidates[0]
            used_ai_indices.add(ai_idx)
            ai_bc = ai_barcodes[ai_idx]
            comparisons.append({
                "page": lib_page,
                "library_value": lib_bc.get("data", ""),
                "library_type": lib_bc.get("type", ""),
                "ai_value": ai_bc.get("value", ""),
                "ai_type_guess": ai_bc.get("type_guess", ""),
                "ai_confidence": ai_bc.get("confidence", ""),
                "status": AGREE,
                "note": "",
            })
        elif len(candidates) > 1:
            # Multiple AI matches → ambiguous
            used_ai_indices.update(candidates)
            comparisons.append({
                "page": lib_page,
                "library_value": lib_bc.get("data", ""),
                "library_type": lib_bc.get("type", ""),
                "ai_value": "; ".join(ai_barcodes[i].get("value", "") for i in candidates),
                "ai_type_guess": "",
                "ai_confidence": "",
                "status": AMBIGUOUS,
                "note": f"Multiple AI matches for value '{lib_val}' on page {lib_page}",
            })
        else:
            # No AI match
            comparisons.append({
                "page": lib_page,
                "library_value": lib_bc.get("data", ""),
                "library_type": lib_bc.get("type", ""),
                "ai_value": "",
                "ai_type_guess": "",
                "ai_confidence": "",
                "status": LIBRARY_ONLY,
                "note": "Not found by AI",
            })

    # Remaining AI barcodes not matched to any library result
    for i, ai_bc in enumerate(ai_barcodes):
        if i not in used_ai_indices:
            comparisons.append({
                "page": ai_bc.get("page"),
                "library_value": "",
                "library_type": "",
                "ai_value": ai_bc.get("value", ""),
                "ai_type_guess": ai_bc.get("type_guess", ""),
                "ai_confidence": ai_bc.get("confidence", ""),
                "status": AI_ONLY,
                "note": "Not found by barcode library",
            })

    return comparisons


def summarize(comparisons: list[dict]) -> dict:
    counts = {AGREE: 0, DISAGREE: 0, LIBRARY_ONLY: 0, AI_ONLY: 0, AMBIGUOUS: 0}
    for c in comparisons:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    total = len(comparisons)
    return {"total": total, "counts": counts}


def compare_documents(library_result: dict, ai_result: dict) -> dict:
    """Top-level comparison for a single document."""
    comparisons = compare_barcodes(library_result, ai_result)
    return {
        "file": library_result.get("file", ""),
        "library_pages": library_result.get("pages", 0),
        "library_found": library_result.get("found", 0),
        "ai_pages_analyzed": ai_result.get("pages_analyzed", 0),
        "ai_barcodes_found": len(ai_result.get("barcodes", [])),
        "ai_model": ai_result.get("_model", ""),
        "barcode_comparisons": comparisons,
        "summary": summarize(comparisons),
        "ai_extra_fields": {
            # Preserve original snake_case detailed arrays returned by the extractor
            "commitment_numbers": ai_result.get("commitment_numbers", []),
            "central_numbers": ai_result.get("central_numbers", []),
            "sender_organizations": ai_result.get("sender_organizations", []),
            "received_dates": ai_result.get("received_dates", []),
            "uncertain_fields": ai_result.get("uncertain_fields", []),
            "notes": ai_result.get("notes", ""),
            # Also provide camelCase convenience arrays of plain values for frontend
            # consumers that expect simple lists (e.g., centralNumbers: ["123", ...]).
            "centralNumbers": [item.get("value") for item in ai_result.get("central_numbers", []) if item.get("value")],
            "commitmentNumbers": [item.get("value") for item in ai_result.get("commitment_numbers", []) if item.get("value")],
            "senderOrgs": [item.get("value") for item in ai_result.get("sender_organizations", []) if item.get("value")],
            "receivedDates": [item.get("value") for item in ai_result.get("received_dates", []) if item.get("value")],
        },
    }
