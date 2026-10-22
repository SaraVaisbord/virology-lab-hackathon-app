from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from schemas.insights import CorrectionInsightsResponse
from services import insights_service

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/corrections", response_model=CorrectionInsightsResponse)
def correction_insights(
    since: datetime | None = Query(default=None, description="Events from this time (ISO 8601; no zone = UTC)"),
    until: datetime | None = Query(default=None, description="Events up to this time"),
    field_name: str | None = Query(default=None),
):
    """Recurring patterns in the lab worker's corrections, with what to check for each. No field values or images."""
    try:
        return insights_service.correction_insights(since=since, until=until, field_name=field_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
