"""Characterization tests: the API contract and the verification rules' full output must not change by accident.

The snapshots in tests/snapshots/ were recorded from the code as it was; a refactor must leave them identical.
After an intended change, re-record with UPDATE_SNAPSHOTS=1 pytest tests/test_contract_snapshots.py and review the diff.
All data is synthetic (no real patient data); no date depends on today.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
VALID_ID = "000000018"
SENDERS = ["המרכז הרפואי שמיר", "כללית"]


def _matches_snapshot(name: str, value) -> None:
    path = SNAPSHOTS / name
    text = json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
    if os.getenv("UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert path.is_file(), f"Missing snapshot {name} — record it with UPDATE_SNAPSHOTS=1"
    assert json.loads(text) == json.loads(path.read_text(encoding="utf-8"))


def test_openapi_contract_is_unchanged(client):
    _matches_snapshot("openapi.json", client.app.openapi())


def _barcode(data, x=0.1, y=0.2):
    return {"data": data, "type": "CODE128", "x": x, "y": y, "width": 0.05, "height": 0.03, "page": 1}


def _local(field, value, label, source="ocr", confidence=90.0, distance=0.05, anchor=None, rank=0):
    return {"field": field, "value": value, "raw": value, "source": source, "confidence": confidence, "label": label,
            "distance": distance, "anchor": anchor, "rank": rank,
            "box": {"x": 0.4, "y": 0.3, "width": 0.1, "height": 0.02}}


CASES = {
    "empty_page": {"llm": {}, "barcodes": []},
    "all_sources_agree": {
        "llm": {"commitment_number": [{"value": "555123", "confidence": "high", "label": "מספר התחייבות", "box_2d": [100, 100, 200, 300]}],
                "id_number": [{"value": "000-000-018", "confidence": "high", "label": 'ת"ז'}]},
        "barcodes": [_barcode("555123"), _barcode(VALID_ID, y=0.5)],
        "local": [_local("commitment_number", "555123", "מספר התחייבות"), _local("id_number", VALID_ID, 'ת"ז')],
    },
    "look_alike_fields_claim_same_number": {
        "llm": {"central_number": [{"value": "947768", "confidence": "high"}],
                "commitment_number": [{"value": "947768", "confidence": "high", "label": "מרכזי"}]},
        "barcodes": [_barcode("947768")],
        "local": [_local("central_number", "947768", "מרכזי")],
    },
    "barcode_one_char_off": {"llm": {"commitment_number": [{"value": "555124", "confidence": "high"}]}, "barcodes": [_barcode("555123")]},
    "multi_value_and_alternatives": {
        "llm": {"commitment_number": [{"value": "111111", "confidence": "high"}, {"value": "222222", "confidence": "low", "reason": "מטושטש"}],
                "first_name": [{"value": "דנה", "confidence": "high"}, {"value": "דינה", "confidence": "medium"}]},
        "barcodes": [_barcode("222222")],
    },
    "format_doubts": {
        "llm": {"id_number": [{"value": "123456789", "confidence": "high"}],
                "received_date": [{"value": "01/02/2001", "confidence": "high"}],
                "sender": [{"value": "מוסד לא מוכר", "confidence": "high"}, ]},
        "barcodes": [],
    },
    "unparseable_date_and_known_sender": {
        "llm": {"received_date": [{"value": "31/31/31", "confidence": "medium"}],
                "sender": [{"value": "המרכז הרפואי שמיר (אסף הרופא)", "confidence": "high"}]},
        "barcodes": [],
    },
    "ocr_only_low_confidence": {
        "llm": None, "barcodes": [],
        "local": [_local("central_number", "123456", "מרכזי", confidence=40.0), _local("commitment_number", "654321", "דרישה", source="barcode")],
        "ocr_numbers": [{"value": "777777", "raw": "777777", "source": "ocr"}],
    },
    "unlabeled_ocr_number_confirms_reading": {
        "llm": {"central_number": [{"value": "777777", "confidence": "high", "label": "מרכזי"}]},
        "barcodes": [],
        "ocr_numbers": [{"value": "777777", "raw": "777777", "source": "ocr"}],
    },
    "different_dates_under_central_numbers": {
        "llm": {}, "barcodes": [],
        "local": [_local("received_date", "01/02/2001", "נתקבל", anchor="מתחת למספר המרכזי 1"),
                  _local("received_date", "03/04/2001", "נתקבל", anchor="מתחת למספר המרכזי 2", distance=0.1)],
    },
    "sample_label_on_leumit_page": {
        "llm": {"commitment_number": [{"value": "888888", "confidence": "high", "label": "מספר דגימה"}]},
        "barcodes": [], "sample_is_commitment": True,
    },
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_build_fields_output_is_unchanged(name):
    from services.extraction_service import build_fields

    case = CASES[name]
    fields = build_fields(case["llm"], case["barcodes"], SENDERS, page=1, local_candidates=case.get("local"),
                          ocr_numbers=case.get("ocr_numbers"), sample_is_commitment=case.get("sample_is_commitment", False))
    _matches_snapshot(f"build_fields/{name}.json", fields)
