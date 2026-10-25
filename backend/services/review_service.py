"""The lab worker's actions on forms: decide on field values, delete a form, send it back to extraction."""

from __future__ import annotations

from typing import Any

from db.repositories import FormRepository, ReviewRepository
from integrations.storage import UPLOADS_PREFIX, Storage
from services.extraction_queue import ExtractionQueue


class ReviewService:
    def __init__(self, forms: FormRepository, review: ReviewRepository, files: Storage, queue: ExtractionQueue) -> None:
        self._forms = forms
        self._review = review
        self._files = files
        self._queue = queue

    def confirm_field(self, form_id: int, field_id: int, corrected_value: str | None) -> dict[str, Any]:
        """Approve one value, optionally corrected (LookupError when the field doesn't exist)."""
        corrected = corrected_value.strip() if corrected_value else None
        return self._review.confirm_field(form_id=form_id, field_id=field_id, corrected_value=corrected)

    def add_field(self, form_id: int, field_name: str, value: str, *, replace: bool = False,
                  box: dict[str, float] | None = None, picked_from: str | None = None) -> dict[str, Any]:
        """A value typed by the lab worker — works whether or not the form was (or could be) extracted."""
        return self._review.add_manual_field(form_id, field_name, value, replace=replace, box=box, picked_from=picked_from)

    def delete_field(self, form_id: int, field_id: int) -> dict[str, Any]:
        return self._review.delete_field(form_id, field_id)

    def delete_form(self, form_id: int) -> None:
        """Delete a form (one page) with its fields and its page image; the uploaded file goes with its last page.
        LookupError: no such form; ValueError: it is being processed."""
        removed = self._forms.delete_form(form_id)
        self._files.delete(removed["image_path"])
        if removed["last_page_of_upload"]:
            self._files.delete_prefix(f"{UPLOADS_PREFIX}/{removed['file_hash']}_")

    def retry(self, form_id: int) -> dict[str, Any] | None:
        """Send the form back to the extraction queue (ValueError when it doesn't exist); returns it as it is now."""
        self._forms.requeue_form(form_id)
        self._queue.notify()
        return self._forms.get_form(form_id, with_sources=True)
