"""Exposes the domain vocabulary and UI-relevant settings, so the frontend has no copies of them."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_settings
from config import Settings
from domain.vocabulary import (
    AGREEMENT_LABELS,
    BARCODE_MATCH_LABELS,
    CONFIDENCE_LABELS,
    DATE_PATTERN,
    EXPORT_MODE_LABELS,
    FIELD_KINDS,
    FIELD_LABELS,
    FIELD_STATUS_LABELS,
    FORM_COLUMN_LABELS,
    FORM_STATUS_LABELS,
    FORM_TYPE_LABELS,
    INSIGHT_PATTERN_LABELS,
    INSIGHT_SUPPORT_LABELS,
    INVENTORY_KIND_LABELS,
    MULTI_VALUE_FIELDS,
    ROW_KEY_FIELD,
    PENDING_FORM_STATUSES,
    QUEUE_PAUSE_REASON_LABELS,
    REVIEW_FIELD_STATUSES,
    SOURCE_LABELS,
    SOURCE_STATUS_LABELS,
    UPLOAD_TYPES,
)

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("")
def get_meta(settings: Settings = Depends(get_settings)):
    return {
        "fields": [
            # kind (text / number / id / date): which numbers found on the page are offered as options for the field
            {"key": key, "label": label, "multi_value": key in MULTI_VALUE_FIELDS, "kind": FIELD_KINDS[key]}
            for key, label in FIELD_LABELS.items()
        ],
        "row_key_field": ROW_KEY_FIELD,
        "date_pattern": DATE_PATTERN,  # Python regex syntax that JavaScript also accepts
        "form_columns": FORM_COLUMN_LABELS,
        "form_statuses": FORM_STATUS_LABELS,
        "field_statuses": FIELD_STATUS_LABELS,
        "pending_form_statuses": sorted(PENDING_FORM_STATUSES),
        "review_field_statuses": sorted(REVIEW_FIELD_STATUSES),
        "export_modes": EXPORT_MODE_LABELS,
        "agreement_labels": AGREEMENT_LABELS,
        "confidence_labels": CONFIDENCE_LABELS,
        "barcode_match_labels": BARCODE_MATCH_LABELS,
        "source_labels": SOURCE_LABELS,
        "source_status_labels": SOURCE_STATUS_LABELS,
        "queue_pause_reasons": QUEUE_PAUSE_REASON_LABELS,
        "insight_patterns": INSIGHT_PATTERN_LABELS,
        "insight_support_levels": INSIGHT_SUPPORT_LABELS,
        "form_types": FORM_TYPE_LABELS,
        "written_as_labels": INVENTORY_KIND_LABELS,  # how a value is written on the page
        "upload": {
            "max_file_size_mb": settings.max_file_size_mb,
            "accepted_mime_types": [spec["mime"] for spec in UPLOAD_TYPES.values()],
            "accepted_extensions": [ext for spec in UPLOAD_TYPES.values() for ext in spec["extensions"]],
        },
        "page_size": settings.default_page_size,
        "poll_interval_ms": settings.processing_poll_interval_ms,
    }
