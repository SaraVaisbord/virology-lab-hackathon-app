from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from schemas.upload import UploadItemResponse
from services.upload_service import process_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=list[UploadItemResponse])
async def upload_files(files: list[UploadFile] = File(..., description="One or more files")) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for file in files:
        results.append(process_upload(file))
    return results
