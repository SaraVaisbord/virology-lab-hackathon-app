"""
tests/test_compare.py - Unit tests for comparison logic. No API calls.
Run: python -m pytest tests/ -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.compare import (
    normalize, compare_barcodes, compare_documents, summarize,
    AGREE, LIBRARY_ONLY, AI_ONLY, AMBIGUOUS,
)


# ── normalize ────────────────────────────────────────────────────────────────

def test_normalize_strips_whitespace():
    assert normalize("  123  ") == "123"

def test_normalize_uppercase():
    assert normalize("abc") == "ABC"

def test_normalize_preserves_leading_zeros():
    assert normalize("007") == "007"

def test_normalize_none():
    assert normalize(None) == ""

def test_normalize_internal_spaces_preserved():
    # Internal spaces are meaningful identifiers – must not be removed
    assert normalize("  36499923") == "36499923"


# ── compare_barcodes ─────────────────────────────────────────────────────────

def _lib(data, page=1, bc_type="CODE128"):
    return {"data": data, "page": page, "type": bc_type, "x": 0, "y": 0, "width": 10, "height": 10}

def _ai(value, page=1, confidence="high"):
    return {"value": value, "page": page, "type_guess": "CODE128", "confidence": confidence}


def test_exact_match():
    lib = {"barcodes": [_lib("123456", page=1)], "file": "f.pdf", "pages": 1, "found": 1}
    ai  = {"barcodes": [_ai("123456",  page=1)]}
    result = compare_barcodes(lib, ai)
    assert len(result) == 1
    assert result[0]["status"] == AGREE


def test_library_only():
    lib = {"barcodes": [_lib("999", page=2)], "file": "f.pdf", "pages": 1, "found": 1}
    ai  = {"barcodes": []}
    result = compare_barcodes(lib, ai)
    assert result[0]["status"] == LIBRARY_ONLY


def test_ai_only():
    lib = {"barcodes": [], "file": "f.pdf", "pages": 1, "found": 0}
    ai  = {"barcodes": [_ai("888", page=3)]}
    result = compare_barcodes(lib, ai)
    assert result[0]["status"] == AI_ONLY


def test_no_match_different_page():
    lib = {"barcodes": [_lib("555", page=1)], "file": "f.pdf", "pages": 2, "found": 1}
    ai  = {"barcodes": [_ai("555", page=2)]}
    # Different page → no exact match; falls back to value-only only if AI page is None
    result = compare_barcodes(lib, ai)
    statuses = {c["status"] for c in result}
    assert LIBRARY_ONLY in statuses or AI_ONLY in statuses


def test_ai_page_none_fallback():
    lib = {"barcodes": [_lib("777", page=5)], "file": "f.pdf", "pages": 5, "found": 1}
    ai_bc = {"value": "777", "page": None, "type_guess": "CODE128", "confidence": "medium"}
    ai  = {"barcodes": [ai_bc]}
    result = compare_barcodes(lib, ai)
    assert result[0]["status"] == AGREE


def test_ambiguous_multiple_ai_matches():
    lib = {"barcodes": [_lib("111", page=1)], "file": "f.pdf", "pages": 1, "found": 1}
    ai  = {"barcodes": [_ai("111", page=1), _ai("111", page=1)]}
    result = compare_barcodes(lib, ai)
    assert result[0]["status"] == AMBIGUOUS


def test_leading_zeros_not_stripped():
    lib = {"barcodes": [_lib("0046025783", page=1)], "file": "f.pdf", "pages": 1, "found": 1}
    ai  = {"barcodes": [_ai("0046025783", page=1)]}
    result = compare_barcodes(lib, ai)
    assert result[0]["status"] == AGREE
    # Ensure the original value is preserved, not stripped
    assert result[0]["library_value"] == "0046025783"


def test_whitespace_value_normalized():
    # AI returns value with surrounding spaces
    lib = {"barcodes": [_lib("36499923", page=3)], "file": "f.pdf", "pages": 3, "found": 1}
    ai_bc = {"value": "    36499923", "page": 3, "type_guess": "CODE128", "confidence": "high"}
    ai  = {"barcodes": [ai_bc]}
    result = compare_barcodes(lib, ai)
    assert result[0]["status"] == AGREE


def test_multiple_barcodes_correct_pairing():
    lib = {"barcodes": [_lib("AAA", page=1), _lib("BBB", page=2)],
           "file": "f.pdf", "pages": 2, "found": 2}
    ai  = {"barcodes": [_ai("BBB", page=2), _ai("AAA", page=1)]}
    result = compare_barcodes(lib, ai)
    assert all(c["status"] == AGREE for c in result)


# ── summarize ────────────────────────────────────────────────────────────────

def test_summarize_counts():
    comps = [
        {"status": AGREE},
        {"status": AGREE},
        {"status": LIBRARY_ONLY},
        {"status": AI_ONLY},
    ]
    s = summarize(comps)
    assert s["total"] == 4
    assert s["counts"][AGREE] == 2
    assert s["counts"][LIBRARY_ONLY] == 1
    assert s["counts"][AI_ONLY] == 1


def test_summarize_empty():
    s = summarize([])
    assert s["total"] == 0
