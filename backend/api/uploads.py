from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from api.dependencies import get_container
from container import Container
from schemas.upload import UploadItemResponse

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=list[UploadItemResponse])
def upload_files(files: list[UploadFile] = File(..., description="One or more files"), container: Container = Depends(get_container)):
    results = []
    for file in files:
        file.file.seek(0)
        results.append(container.uploads.process_upload(file.filename or "", file.file.read()))
    if any(result["status"] == "created" for result in results):
        container.queue.notify()
    return results
