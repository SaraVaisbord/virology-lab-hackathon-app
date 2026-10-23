from __future__ import annotations

from functools import lru_cache
from typing import Any

from db.constants import CONFIDENCE_LEVELS, FIELDS, FORM_TYPES, INVENTORY_KINDS, UNASSIGNED


@lru_cache(maxsize=1)
def response_schema() -> dict[str, Any]:
    """Structured-output schema, generated from the field list so the model can only return valid JSON with our keys.
    Written in Gemini's dialect (uppercase types); the other providers convert it to standard JSON Schema."""
    candidate = {
        "type": "OBJECT",
        "properties": {
            "value": {"type": "STRING"},
            "confidence": {"type": "STRING", "enum": sorted(CONFIDENCE_LEVELS)},
            "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
            "label": {"type": "STRING"},
            "reason": {"type": "STRING"},
        },
        "required": ["value", "confidence"],
    }
    # Inventory of every number on the page — forces an exhaustive scan before fields are filled (without it the
    # model returned only 14 of 31 barcode values on the samples) and keeps numbers it can't assign.
    inventory_item = {
        "type": "OBJECT",
        "properties": {
            "value": {"type": "STRING"},
            "kind": {"type": "STRING", "enum": list(INVENTORY_KINDS)},
            "label": {"type": "STRING"},
            "assigned_to": {"type": "STRING", "enum": [*FIELDS, UNASSIGNED]},
            "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        },
        "required": ["value", "kind", "assigned_to"],
    }
    properties = {
        "all_numbers": {"type": "ARRAY", "items": inventory_item},
        # Whose form it is — some labels exist only on one fund's forms (Leumit "דגימה" = commitment number).
        "form_type": {"type": "STRING", "enum": sorted(FORM_TYPES)},
    }
    properties.update({name: {"type": "ARRAY", "items": candidate} for name in FIELDS})
    properties["notes"] = {"type": "STRING"}
    return {"type": "OBJECT", "properties": properties, "required": ["all_numbers", *FIELDS]}
