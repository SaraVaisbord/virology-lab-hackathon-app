import json
from pathlib import Path


def test_extract_for_form_success(tmp_path, monkeypatch):
    # Create a fake upload file
    upload = tmp_path / "hash123_sample.pdf"
    upload.write_bytes(b"%PDF-1.4 fake")

    import services.extraction_service as extraction_service

    # Monkeypatch _find_uploaded_file to return our file
    monkeypatch.setattr(extraction_service, "_find_uploaded_file", lambda fh: upload)

    # Mock barcode_reader.scan_file
    def fake_scan(path):
        return {"file": str(path), "pages": 1, "found": 1, "barcodes": [{"data": "ABC", "page": 1}]}

    monkeypatch.setattr(extraction_service.barcode_reader, "scan_file", fake_scan)

    # Mock ai_extractor.extract_from_pdf
    fake_ai = {
        "pages_analyzed": 1,
        "barcodes": [{"value": "ABC", "page": 1}],
        "commitment_numbers": [{"value": "C-1"}],
    }
    monkeypatch.setattr(extraction_service.ai_extractor, "extract_from_pdf", lambda p: fake_ai)

    # Mock DB persistence functions
    import db.queries as queries
    monkeypatch.setattr(queries, "save_extraction", lambda *args, **kwargs: None)
    monkeypatch.setattr(queries, "set_form_status", lambda *args, **kwargs: None)

    form = {"id": 1, "file_hash": "hash123", "source_file": "sample.pdf"}
    result = extraction_service.extract_for_form(form)
    assert result["status"] == "extracted"
    assert "comparison" in result


def test_extract_for_form_missing_upload(monkeypatch):
    import services.extraction_service as extraction_service
    # Ensure no uploads
    monkeypatch.setattr(extraction_service, "_find_uploaded_file", lambda fh: None)
    import db.queries as queries
    monkeypatch.setattr(queries, "set_form_status", lambda *a, **k: None)

    form = {"id": 2, "file_hash": "no-such"}
    result = extraction_service.extract_for_form(form)
    assert result["status"] == "failed"
