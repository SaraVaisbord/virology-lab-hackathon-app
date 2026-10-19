"""Exposes the domain vocabulary and UI-relevant settings, so the frontend has no copies of them."""

from __future__ import annotations

from fastapi import APIRouter

import config
from db.constants import (
    AGREEMENT_LABELS,
    BARCODE_MATCH_LABELS,
    CONFIDENCE_LABELS,
    EXPORT_MODE_LABELS,
    FIELD_LABELS,
    FIELD_STATUS_LABELS,
    FORM_COLUMN_LABELS,
    FORM_STATUS_LABELS,
    MULTI_VALUE_FIELDS,
    PENDING_FORM_STATUSES,
    QUEUE_PAUSE_REASON_LABELS,
    REVIEW_FIELD_STATUSES,
    SOURCE_LABELS,
    SOURCE_STATUS_LABELS,
    UPLOAD_TYPES,
)

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("")
def get_meta():
    return {
        "fields": [
            {"key": key, "label": label, "multi_value": key in MULTI_VALUE_FIELDS}
            for key, label in FIELD_LABELS.items()
        ],
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
        "upload": {
            "max_file_size_mb": config.MAX_FILE_SIZE_MB,
            "accepted_mime_types": [spec["mime"] for spec in UPLOAD_TYPES.values()],
            "accepted_extensions": [ext for spec in UPLOAD_TYPES.values() for ext in spec["extensions"]],
        },
        "page_size": config.DEFAULT_PAGE_SIZE,
        "poll_interval_ms": config.PROCESSING_POLL_INTERVAL_MS,
    }
