"""Compatibility shim during the refactor — data access is db/repositories/ (one class per aggregate).
Each name below is the method of a repository over the current session factory. Removed in its last step."""

from __future__ import annotations

from db import session as _session
from db.repositories import CorrectionHistory, FormFilters, FormListing, FormRepository, ReviewRepository, SenderRepository  # noqa: F401
from db.repositories.listing import FORM_SORT_COLUMNS  # noqa: F401
from db.serialization import SOURCE_COLUMNS, field_to_dict, form_to_dict  # noqa: F401

_METHODS = {
    FormRepository: ("add_form", "find_forms_by_hash", "get_form", "delete_forms_by_hash", "delete_form", "set_form_status",
                     "claim_next_form", "requeue_stale_processing", "return_to_queue", "requeue_form",
                     "save_source_results", "save_extraction"),
    ReviewRepository: ("add_manual_field", "delete_field", "confirm_field", "list_field_events"),
    FormListing: ("list_forms", "forms_summary"),
    CorrectionHistory: ("correction_events", "count_unreviewed_verified_fields"),
    SenderRepository: ("list_senders", "add_sender"),
}


def __getattr__(name: str):
    for repository, methods in _METHODS.items():
        if name in methods:
            return getattr(repository(_session.SessionLocal), name)
    raise AttributeError(name)
