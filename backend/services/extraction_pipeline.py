"""Extraction pipeline for one form page.

    preprocess (upright, deskewed, clean)  →  barcodes  →  local OCR extraction  →  [LLM, if enabled]  →  merge

Each source's raw result is stored separately on the form (barcode_result / ocr_result / llm_result) as soon as
it finishes, so a failure of one source never discards another's evidence. The merge and the verification rules
are domain/verification.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from domain.verification import VerificationRules, build_fields, form_type_of, sample_is_commitment_on
from domain.vocabulary import EXTRACTION_ERRORS, OCR_UNAVAILABLE_REASON
from integrations.imaging.image_io import png_bytes, read_image
from integrations.imaging.preprocessing import PageViews, preprocess
from integrations.llm.errors import ExtractionError, MissingApiKeyError, ModelsUnavailableError
from integrations.llm.router import LlmRouter
from integrations.ocr.local_extractor import LocalExtractor, drop_irrelevant_numbers
from integrations.storage import Storage

logger = logging.getLogger(__name__)

BarcodeScanner = Callable[[Image.Image], list[dict]]


def user_facing_error(exc: Exception) -> str:
    """Short Hebrew message for the UI; technical details are logged, never shown or stored."""
    if isinstance(exc, MissingApiKeyError):
        return EXTRACTION_ERRORS["config"]
    if isinstance(exc, ModelsUnavailableError):
        return EXTRACTION_ERRORS["quota"]
    if isinstance(exc, ExtractionError):
        return EXTRACTION_ERRORS["timeout" if "timed out" in str(exc).lower() else "model"]
    if isinstance(exc, FileNotFoundError):
        return EXTRACTION_ERRORS["image_missing"]
    return EXTRACTION_ERRORS["unexpected"]


class ExtractionPipeline:
    """store: where forms and their results are kept (get_form, list_senders, save_source_results, save_extraction,
    set_form_status); files: the page images; llm: the providers, with failover; local: the OCR extraction;
    scan_barcodes: zbar on one image; llm_enabled: whether pages are sent to an LLM by default."""

    def __init__(self, store, files: Storage, llm: LlmRouter, local: LocalExtractor, scan_barcodes: BarcodeScanner,
                 rules: VerificationRules, page_render_dpi: int, llm_enabled: bool) -> None:
        self._store = store
        self._files = files
        self._llm = llm
        self._local = local
        self._scan_barcodes = scan_barcodes
        self._rules = rules
        self._page_render_dpi = page_render_dpi
        self._llm_enabled = llm_enabled

    @property
    def llm_providers(self) -> list[str]:
        return self._llm.known

    # ── Sources ──────────────────────────────────────────────────────────────

    def _barcode_scan(self, views: PageViews, page: int | None) -> dict[str, Any]:
        """zbar on every barcode view of the page (no single rendition decodes every barcode); one item per value.
        Returns {"status": "ok", "items": [...]} or {"status": "error", "error": ...}. Coordinates are normalized."""
        found: dict[str, dict] = {}
        try:
            for view in views.barcode_views:
                for item in self._scan_barcodes(Image.fromarray(view).convert("RGB")):
                    found.setdefault(item["data"], {**item, "page": page})
        except Exception as exc:
            logger.warning("Barcode scan failed: %s", type(exc).__name__)
            return {"status": "error", "error": EXTRACTION_ERRORS["barcode"], "items": list(found.values())}
        return {"status": "ok", "items": list(found.values())}

    def _ocr(self, views: PageViews, barcodes: list[dict[str, Any]], page: int | None) -> dict[str, Any]:
        """Local OCR extraction (labels → values). Returns {"status", "candidates", "labels", "unassigned_numbers"}."""
        empty = {"candidates": [], "labels": [], "unassigned_numbers": [], "items": []}
        if not self._local.ocr.is_available():
            return {"status": "unavailable", "reason": OCR_UNAVAILABLE_REASON, **empty}
        try:
            result = self._local.extract(views, barcodes).as_dict()
        except Exception as exc:
            logger.warning("Local OCR extraction failed: %s", type(exc).__name__)
            return {"status": "error", "error": EXTRACTION_ERRORS["ocr"], **empty}
        return {"status": "ok", "page": page, **result, "items": result["candidates"]}

    def _known_senders(self) -> list[str]:
        return [name for name, _kind in self._store.list_senders()]

    def _fields(self, page: int | None, llm_result, barcodes, ocr_result, known_senders) -> tuple[list[dict[str, Any]], str | None]:
        form_type = form_type_of(ocr_result, llm_result)
        fields = build_fields(llm_result, barcodes, known_senders, self._rules, page=page,
                              local_candidates=(ocr_result or {}).get("candidates", []),
                              ocr_numbers=(ocr_result or {}).get("unassigned_numbers", []),
                              sample_is_commitment=sample_is_commitment_on(ocr_result, form_type))
        return fields, form_type

    # ── Entry points ─────────────────────────────────────────────────────────

    def extract(self, form: dict[str, Any], provider: str | None = None, use_llm: bool | None = None) -> None:
        """Run all sources for one page, persist each result separately, then build the field rows.

        The page image is replaced by its preprocessed (upright, deskewed, highlighter-free) version first, so every
        source and the UI share one geometry. The LLM is the first configured provider that answers; `provider`
        forces one. use_llm defaults to llm_enabled; without it no LLM is called (no tokens) and only an LLM answer
        already stored for the page is merged. Raises on LLM failure — local results are already saved by then."""
        form_id, page = form["id"], form.get("page_number")
        use_llm = self._llm_enabled if use_llm is None else use_llm
        key = form.get("image_path")
        # A local copy of the page (S3: a temporary download) — OpenCV and the LLM clients read files.
        with self._files.local_path(key) as image_path:  # FileNotFoundError when the page image is missing
            views = preprocess(read_image(image_path), source_dpi=self._page_render_dpi, ocr=self._local.ocr)
            normalized = png_bytes(views.normalized)
            image_path.write_bytes(normalized)  # what the LLM reads below
            self._files.put(key, normalized, "image/png")  # what the lab worker sees
            self._extract_sources(form_id, page, views, image_path, provider, use_llm)

    def _extract_sources(self, form_id: int, page: int | None, views: PageViews, image_path: Path, provider: str | None,
                         use_llm: bool) -> None:
        store = self._store
        barcode_result = self._barcode_scan(views, page)
        ocr_result = self._ocr(views, barcode_result["items"], page)
        errors = {source: result["error"] for source, result in (("barcode", barcode_result), ("ocr", ocr_result)) if result["status"] == "error"}
        store.save_source_results(form_id, barcode_result=barcode_result, ocr_result=ocr_result, source_errors=errors or None)

        known_senders = self._known_senders()
        # Without a new LLM call, an answer already stored for this page (from an earlier run) is still merged.
        llm_result = (store.get_form(form_id, with_sources=True) or {}).get("sources", {}).get("llm_result")
        if use_llm:
            try:
                answer = self._llm.extract_from_image(image_path, known_senders, providers=[provider] if provider else None)
                llm_result = drop_irrelevant_numbers(answer)
            except Exception as exc:
                store.save_source_results(form_id, source_errors={**errors, "llm": user_facing_error(exc)})
                raise
            store.save_source_results(form_id, llm_result=llm_result)

        fields, form_type = self._fields(page, llm_result, barcode_result["items"], ocr_result, known_senders)
        store.save_extraction(form_id, fields, form_type=form_type)

    def reverify(self, form_id: int) -> bool:
        """Re-run the verification rules on the stored source results (no new LLM call). False if nothing is stored."""
        form = self._store.get_form(form_id, with_sources=True)
        sources = (form or {}).get("sources") or {}
        if not (sources.get("llm_result") or sources.get("ocr_result")):
            return False
        barcodes = (sources.get("barcode_result") or {}).get("items", [])
        fields, form_type = self._fields(form["page_number"], sources.get("llm_result"), barcodes, sources.get("ocr_result"),
                                         self._known_senders())
        self._store.save_extraction(form_id, fields, form_type=form_type)
        return True

    def extract_one(self, form_id: int, provider: str | None = None, use_llm: bool | None = None) -> str:
        """One-off extraction of a single form outside the queue (optionally with one provider). Returns its status."""
        store = self._store
        form = store.get_form(form_id)
        if form is None:
            raise ValueError(f"Form {form_id} not found")
        store.set_form_status(form_id, "processing")
        try:
            self.extract(form, provider=provider, use_llm=use_llm)
        except Exception as exc:
            logger.exception("One-off extraction failed for form %s", form_id)
            store.set_form_status(form_id, "failed", error=user_facing_error(exc))
        return store.get_form(form_id)["status"]
