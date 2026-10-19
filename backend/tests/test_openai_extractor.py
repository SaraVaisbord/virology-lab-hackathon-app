"""OpenAI provider: schema conversion and response normalization (no API calls)."""

from __future__ import annotations

from db.constants import FIELDS
from openai_extractor import _drop_nulls, strict_schema


def test_strict_schema_is_generated_from_the_same_field_list():
    schema = strict_schema()
    assert set(FIELDS) <= set(schema["properties"])
    assert schema["additionalProperties"] is False and set(schema["required"]) == set(schema["properties"])
    candidate = schema["properties"]["commitment_number"]["items"]
    assert candidate["properties"]["value"]["type"] == "string"  # required in the source schema → not nullable
    assert candidate["properties"]["label"]["type"] == ["string", "null"]  # optional → nullable in strict mode


def test_nulls_from_strict_mode_are_dropped_like_gemini_omits_them():
    answer = {"central_number": [{"value": "1", "confidence": "high", "label": None, "box_2d": None}], "notes": None}
    assert _drop_nulls(answer) == {"central_number": [{"value": "1", "confidence": "high"}]}
