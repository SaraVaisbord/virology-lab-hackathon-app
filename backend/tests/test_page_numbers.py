"""Numbers found on the page, merged across sources (domain/page_numbers.py) and sent with the form. Synthetic data."""

from __future__ import annotations

from domain.page_numbers import page_numbers, value_key
from tests.conftest import make_form

SOURCES = {
    "barcode_result": {"status": "ok", "items": [
        {"data": "12043017", "type": "CODE128", "x": 0.1, "y": 0.2, "width": 0.05, "height": 0.03},
        {"data": "555123", "type": "QRCODE", "x": 0.3, "y": 0.2, "width": 0.001, "height": 0.03},  # a scan line, no area
        {"data": "12", "type": "CODE39", "x": 0.3, "y": 0.2, "width": 0.05, "height": 0.03},  # too short to offer
    ]},
    "ocr_result": {"status": "ok", "candidates": [
        {"raw": "12043017", "source": "ocr", "label": "מרכזי:", "box": {"x": 0.4, "y": 0.3, "width": 0.1, "height": 0.02}},
        {"raw": "1.2.26", "source": "ocr", "label": "נתקבל", "box": {"x": 0.5, "y": 0.4, "width": 0.1, "height": 0.02}},
    ], "unassigned_numbers": [{"raw": "777-777", "source": "ocr", "box": {"x": 0.6, "y": 0.5, "width": 0.1, "height": 0.02}}]},
    "llm_result": {
        "all_numbers": [{"value": "12043017", "kind": "sticker", "assigned_to": "central_number", "box_2d": [100, 200, 150, 400]}],
        "received_date": [{"value": "2026-02-01", "confidence": "low"}],
    },
}


def test_values_are_merged_across_sources_with_the_most_precise_box():
    numbers = {item["key"]: item for item in page_numbers(SOURCES)}
    central = numbers["12043017"]
    assert central["sources"] == ["barcode", "ocr", "llm"] and central["notes"] == ["CODE128", "מרכזי:"]
    assert central["box_source"] == "barcode" and central["box"] == {"x": 0.1, "y": 0.2, "width": 0.05, "height": 0.03}
    assert numbers["555123"]["box"] is None and "12" not in numbers  # no usable area / too short
    assert numbers["777777"]["value"] == "777-777" and not numbers["777777"]["is_date"]


def test_dates_compare_by_day_month_and_full_year():
    assert value_key("1.2.26") == value_key("01/02/2026") == "01022026"
    date = page_numbers(SOURCES)[2]
    assert date["is_date"] and date["key"] == "01022026" and date["sources"] == ["ocr"]
    assert page_numbers(None) == [] and page_numbers({}) == []


def test_the_form_detail_carries_its_page_numbers(client, queries):
    form_id = make_form(queries)
    queries.save_source_results(form_id, **SOURCES)
    detail = client.get(f"/forms/{form_id}").json()
    assert detail["page_numbers"] == page_numbers(SOURCES)
    assert detail["sources"]["llm_result"] == SOURCES["llm_result"]  # the raw results are still there, unchanged
