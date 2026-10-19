from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from schemas.upload import UploadItemResponse
from services.extraction_queue import extraction_queue
from services.upload_service import process_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=list[UploadItemResponse])
def upload_files(files: list[UploadFile] = File(..., description="One or more files")):
    results = [process_upload(file) for file in files]
    if any(result["status"] == "created" for result in results):
        extraction_queue.notify()
    return results
