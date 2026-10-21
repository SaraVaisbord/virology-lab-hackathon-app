from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

import config
from db import queries
from db.constants import EXPORT_MODE_LABELS
from schemas.forms import AddFieldRequest, ConfirmFieldRequest, FormDetailResponse, FormsPage, FormsSummary
from services.export_service import build_forms_workbook
from services.extraction_queue import extraction_queue
from storage import UPLOADS_PREFIX, get_storage

router = APIRouter(prefix="/forms", tags=["forms"])

_COLUMN_FILTER_PREFIX = "filter_"
_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EXPORT_FILENAME = "forms_export.xlsx"


def form_filters(
    request: Request,
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    sort_by: str = Query(default="id"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> queries.FormFilters:
    """Filters shared by the table and the export: status, free text, per-column filters (filter_<column>) and sort."""
    column_filters = {
        key.removeprefix(_COLUMN_FILTER_PREFIX): value
        for key, value in request.query_params.items()
        if key.startswith(_COLUMN_FILTER_PREFIX)
    }
    return queries.FormFilters(status=status, query=query, column_filters=column_filters, sort_by=sort_by, sort_dir=sort_dir)


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=FormsPage)
def list_forms(
    filters: queries.FormFilters = Depends(form_filters),
    limit: int = Query(default=config.DEFAULT_PAGE_SIZE, ge=1, le=config.MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    try:
        items, total = queries.list_forms(filters, limit=limit, offset=offset)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/summary", response_model=FormsSummary)
def forms_summary():
    return {**queries.forms_summary(), "queue": extraction_queue.state()}


@router.get("/export")
def export_forms(
    mode: str = Query(default="all"),
    filters: queries.FormFilters = Depends(form_filters),
):
    if mode not in EXPORT_MODE_LABELS:
        raise HTTPException(status_code=400, detail=f"Unknown export mode: {mode!r}")
    if mode == "all":
        filters = queries.FormFilters(sort_by=filters.sort_by, sort_dir=filters.sort_dir)
    elif mode == "approved":
        filters = queries.FormFilters(status="approved", sort_by=filters.sort_by, sort_dir=filters.sort_dir)

    try:
        content = build_forms_workbook(filters)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename={_EXPORT_FILENAME}"},
    )


@router.get("/{form_id}", response_model=FormDetailResponse)
def get_form(form_id: int):
    form = queries.get_form(form_id, with_sources=True)
    if form is None:
        raise HTTPException(status_code=404, detail="Form not found")
    return form


@router.get("/{form_id}/image")
def get_form_image(form_id: int):
    form = queries.get_form(form_id)
    try:
        data = get_storage().get(form["image_path"]) if form else None
    except ValueError:  # a key that points outside the storage
        data = None
    if data is None:
        raise HTTPException(status_code=404, detail="Image not found")
    # private: the page may hold patient data — browsers must not keep it in shared caches
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.patch("/{form_id}/fields/{field_id}/confirm", response_model=FormDetailResponse)
def confirm_field(form_id: int, field_id: int, payload: ConfirmFieldRequest):
    corrected = payload.corrected_value.strip() if payload.corrected_value else None
    try:
        return queries.confirm_field(form_id=form_id, field_id=field_id, corrected_value=corrected)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{form_id}/fields", response_model=FormDetailResponse)
def add_field(form_id: int, payload: AddFieldRequest):
    """A value typed by the lab worker — works whether or not the form was (or could be) extracted."""
    try:
        return queries.add_manual_field(
            form_id, payload.field_name, payload.value, replace=payload.replace,
            box=payload.box.model_dump() if payload.box else None, picked_from=payload.picked_from,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.delete("/{form_id}/fields/{field_id}", response_model=FormDetailResponse)
def delete_field(form_id: int, field_id: int):
    try:
        return queries.delete_field(form_id, field_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{form_id}", status_code=204)
def delete_form(form_id: int):
    """Delete a form (one page) with its fields and its page image; the uploaded file goes with its last page."""
    try:
        removed = queries.delete_form(form_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    files = get_storage()
    files.delete(removed["image_path"])
    if removed["last_page_of_upload"]:
        files.delete_prefix(f"{UPLOADS_PREFIX}/{removed['file_hash']}_")
    return Response(status_code=204)


@router.post("/{form_id}/retry", response_model=FormDetailResponse)
def retry_extraction(form_id: int):
    try:
        queries.requeue_form(form_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    extraction_queue.notify()
    return queries.get_form(form_id, with_sources=True)
