from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from api.dependencies import get_container
from config import Settings
from container import Container
from db.repositories import FormFilters
from schemas.forms import AddFieldRequest, ConfirmFieldRequest, FormDetailResponse, FormsPage, FormsSummary

_COLUMN_FILTER_PREFIX = "filter_"
_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EXPORT_FILENAME = "forms_export.xlsx"


def form_filters(
    request: Request,
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    sort_by: str = Query(default="id"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> FormFilters:
    """Filters shared by the table and the export: status, free text, per-column filters (filter_<column>) and sort."""
    column_filters = {
        key.removeprefix(_COLUMN_FILTER_PREFIX): value
        for key, value in request.query_params.items()
        if key.startswith(_COLUMN_FILTER_PREFIX)
    }
    return FormFilters(status=status, query=query, column_filters=column_filters, sort_by=sort_by, sort_dir=sort_dir)


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def create_router(settings: Settings) -> APIRouter:
    """The /forms routes; the page size limits are part of the API contract, so they come from the settings here."""
    router = APIRouter(prefix="/forms", tags=["forms"])

    @router.get("", response_model=FormsPage)
    def list_forms(
        filters: FormFilters = Depends(form_filters),
        limit: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
        offset: int = Query(default=0, ge=0),
        container: Container = Depends(get_container),
    ):
        try:
            items, total = container.listing.list_forms(filters, limit=limit, offset=offset)
        except ValueError as exc:
            raise _bad_request(exc) from exc
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @router.get("/summary", response_model=FormsSummary)
    def forms_summary(container: Container = Depends(get_container)):
        return {**container.listing.forms_summary(), "queue": container.queue.state()}

    @router.get("/export")
    def export_forms(
        mode: str = Query(default="all"),
        filters: FormFilters = Depends(form_filters),
        container: Container = Depends(get_container),
    ):
        try:
            content = container.exports.build_forms_workbook(mode, filters)
        except ValueError as exc:
            raise _bad_request(exc) from exc
        return Response(
            content=content,
            media_type=_XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f"attachment; filename={_EXPORT_FILENAME}"},
        )

    @router.get("/{form_id}", response_model=FormDetailResponse)
    def get_form(form_id: int, container: Container = Depends(get_container)):
        form = container.forms.get_form(form_id, with_sources=True)
        if form is None:
            raise HTTPException(status_code=404, detail="Form not found")
        return form

    @router.get("/{form_id}/image")
    def get_form_image(form_id: int, container: Container = Depends(get_container)):
        form = container.forms.get_form(form_id)
        try:
            data = container.storage.get(form["image_path"]) if form else None
        except ValueError:  # a key that points outside the storage
            data = None
        if data is None:
            raise HTTPException(status_code=404, detail="Image not found")
        # private: the page may hold patient data — browsers must not keep it in shared caches
        return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})

    @router.patch("/{form_id}/fields/{field_id}/confirm", response_model=FormDetailResponse)
    def confirm_field(form_id: int, field_id: int, payload: ConfirmFieldRequest, container: Container = Depends(get_container)):
        try:
            return container.reviews.confirm_field(form_id, field_id, payload.corrected_value)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/{form_id}/fields", response_model=FormDetailResponse)
    def add_field(form_id: int, payload: AddFieldRequest, container: Container = Depends(get_container)):
        """A value typed by the lab worker — works whether or not the form was (or could be) extracted."""
        try:
            return container.reviews.add_field(
                form_id, payload.field_name, payload.value, replace=payload.replace,
                box=payload.box.model_dump() if payload.box else None, picked_from=payload.picked_from,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise _bad_request(exc) from exc

    @router.delete("/{form_id}/fields/{field_id}", response_model=FormDetailResponse)
    def delete_field(form_id: int, field_id: int, container: Container = Depends(get_container)):
        try:
            return container.reviews.delete_field(form_id, field_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.delete("/{form_id}", status_code=204)
    def delete_form(form_id: int, container: Container = Depends(get_container)):
        """Delete a form (one page) with its fields and its page image; the uploaded file goes with its last page."""
        try:
            container.reviews.delete_form(form_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(status_code=204)

    @router.post("/{form_id}/retry", response_model=FormDetailResponse)
    def retry_extraction(form_id: int, container: Container = Depends(get_container)):
        try:
            return container.reviews.retry(form_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
