"""Every number (and date) the sources found on a page, merged into one list — one entry per value — each with the
sources that read it and where it is, so the lab worker can see it on the document and pick it for a field.

Computed from the stored source results (the LLM's answer, the OCR result, the barcodes); sent to the UI with the
form as `page_numbers`.
"""

from __future__ import annotations

import re
from typing import Any

from domain.validators import digits_only
from domain.verification import MIN_BOX_SIDE, box_from_llm
from domain.vocabulary import DATE_PATTERN, FIELDS

MIN_DIGITS = 4
# Which source's location to show when several sources read the same number (most precise first).
BOX_PRIORITY = ("barcode", "ocr", "llm")
_DATE = re.compile(DATE_PATTERN)


def value_key(value: Any) -> str:
    """How two readings of one value compare: a date by day/month/full year ("20.08.26" = "20/08/2026"), else its
    digits. (The UI matches field values to these keys the same way: frontend/src/lib/pageNumbers.js valueKey.)"""
    match = _DATE.search(str(value if value is not None else ""))
    if not match:
        return digits_only(value)
    day, month, year = match.groups()
    return f"{day.zfill(2)}{month.zfill(2)}{'20' + year if len(year) == 2 else year}"


def _usable_box(box: dict[str, Any] | None) -> dict[str, Any] | None:
    if not box or (box.get("width") or 0) < MIN_BOX_SIDE or (box.get("height") or 0) < MIN_BOX_SIDE:
        return None
    return box


def page_numbers(sources: dict[str, Any] | None) -> list[dict[str, Any]]:
    """[{key, value, sources, boxes, notes, box, box_source, is_date}] in the order the values were first found:
    barcodes, OCR (labelled, then unassigned), the LLM's inventory, then the LLM's per-field candidates."""
    sources = sources or {}
    by_key: dict[str, dict[str, Any]] = {}

    def add(raw: Any, source: str, box: dict[str, Any] | None, note: str | None = None) -> None:
        if len(digits_only(raw)) < MIN_DIGITS:
            return
        key = value_key(raw)
        item = by_key.setdefault(key, {"key": key, "value": str(raw).strip(), "sources": [], "boxes": {}, "notes": []})
        if source not in item["sources"]:
            item["sources"].append(source)
        if box and source not in item["boxes"]:
            item["boxes"][source] = box
        if note and note not in item["notes"]:
            item["notes"].append(note)

    for barcode in (sources.get("barcode_result") or {}).get("items") or []:
        box = {"x": barcode.get("x"), "y": barcode.get("y"), "width": barcode.get("width"), "height": barcode.get("height")}
        add(barcode.get("data"), "barcode", _usable_box(box), barcode.get("type"))
    ocr = sources.get("ocr_result") or {}
    for candidate in ocr.get("candidates") or []:
        add(candidate.get("raw"), "barcode" if candidate.get("source") == "barcode" else "ocr", _usable_box(candidate.get("box")),
            candidate.get("label"))
    for number in ocr.get("unassigned_numbers") or []:
        add(number.get("raw"), "barcode" if number.get("source") == "barcode" else "ocr", _usable_box(number.get("box")))
    llm = sources.get("llm_result") or {}
    for number in llm.get("all_numbers") or []:
        if isinstance(number, dict):
            add(number.get("value"), "llm", box_from_llm(number), number.get("label") or None)
    for field_name in FIELDS:
        candidates = llm.get(field_name)
        for candidate in candidates if isinstance(candidates, list) else []:
            if isinstance(candidate, dict):
                add(candidate.get("value"), "llm", box_from_llm(candidate), candidate.get("label") or None)

    result = []
    for item in by_key.values():
        box_source = next((source for source in BOX_PRIORITY if item["boxes"].get(source)), None)
        result.append({**item, "box": item["boxes"][box_source] if box_source else None, "box_source": box_source,
                       "is_date": bool(_DATE.search(item["value"]))})
    return result
