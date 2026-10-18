from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class BBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class ValueCandidate(BaseModel):
    value: str
    confidence: Optional[str] = None
    page: Optional[int] = None
    bbox: Optional[BBox] = None


class BarcodeCandidate(BaseModel):
    value: str
    type_guess: Optional[str] = None
    confidence: Optional[str] = None
    page: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None


class ExtractionResult(BaseModel):
    pages_analyzed: int
    barcodes: List[BarcodeCandidate] = []
    commitment_numbers: List[ValueCandidate] = []
    central_numbers: List[ValueCandidate] = []
    patient_names: List[ValueCandidate] = []
    id_numbers: List[ValueCandidate] = []
    sender_organizations: List[ValueCandidate] = []
    received_dates: List[ValueCandidate] = []
    uncertain_fields: List[dict] = []
    notes: Optional[str] = None
    _model: Optional[str] = None
    _source_file: Optional[str] = None
