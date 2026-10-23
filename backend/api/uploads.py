from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from api.dependencies import get_queue
from schemas.upload import UploadItemResponse
from services.extraction_queue import ExtractionQueue
from services.upload_service import process_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=list[UploadItemResponse])
def upload_files(files: list[UploadFile] = File(..., description="One or more files"), queue: ExtractionQueue = Depends(get_queue)):
    results = [process_upload(file) for file in files]
    if any(result["status"] == "created" for result in results):
        queue.notify()
    return results
