from __future__ import annotations

import hashlib
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz
from PIL import Image
from alembic import command
from alembic.config import Config

from db.queries import delete_forms_by_hash, find_forms_by_hash
from services.upload_service import MAX_FILE_SIZE, process_upload

BASE_DIR = Path(__file__).resolve().parents[1]


def _data_dirs_for(tmp_path: Path):
    data_dir = tmp_path / "data"
    uploads_dir = data_dir / "uploads"
    pages_dir = data_dir / "pages_img"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    return data_dir, uploads_dir, pages_dir


def _upgrade_test_db(tmp_path, monkeypatch):
    data_dir, _, _ = _data_dirs_for(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    import importlib
    import db.session as session_module
    import db.queries as queries_module
    importlib.reload(session_module)
    importlib.reload(queries_module)

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")

    import services.upload_service as upload_service
    importlib.reload(upload_service)
    return data_dir


def _make_pdf_with_pages(page_count: int) -> bytes:
    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page()
        page.insert_text((72, 72), "Sample form")
    data = doc.write()
    doc.close()
    return data


def _make_png_bytes(size=(120, 80)) -> bytes:
    image = Image.new("RGB", size, color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _make_jpeg_bytes(size=(120, 80)) -> bytes:
    image = Image.new("RGB", size, color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class DummyFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.file = io.BytesIO(content)


def test_pdf_three_pages_creates_three_forms_and_images(tmp_path, monkeypatch):
    data_dir, uploads_dir, pages_dir = _data_dirs_for(tmp_path)
    _upgrade_test_db(tmp_path, monkeypatch)
    from services import upload_service
    importlib = __import__("importlib")
    importlib.reload(upload_service)

    pdf_bytes = _make_pdf_with_pages(3)
    result = upload_service.process_upload(DummyFile("sample.pdf", pdf_bytes))
    assert result["status"] == "created"
    assert len(result["form_ids"]) == 3
    assert len(list(pages_dir.glob("*_p*.png"))) == 3
    assert len(list(uploads_dir.glob("*sample.pdf"))) >= 1


def test_png_and_jpeg_create_single_form_each(tmp_path, monkeypatch):
    data_dir, uploads_dir, pages_dir = _data_dirs_for(tmp_path)
    _upgrade_test_db(tmp_path, monkeypatch)
    from services import upload_service
    __import__("importlib").reload(upload_service)

    png_result = upload_service.process_upload(DummyFile("img.png", _make_png_bytes()))
    jpeg_result = upload_service.process_upload(DummyFile("img.jpeg", _make_jpeg_bytes()))

    assert png_result["status"] == "created"
    assert len(png_result["form_ids"]) == 1
    assert jpeg_result["status"] == "created"
    assert len(jpeg_result["form_ids"]) == 1


def test_duplicate_file_returns_duplicate(tmp_path, monkeypatch):
    data_dir, uploads_dir, pages_dir = _data_dirs_for(tmp_path)
    _upgrade_test_db(tmp_path, monkeypatch)
    from services import upload_service
    __import__("importlib").reload(upload_service)

    data = _make_png_bytes()
    first = upload_service.process_upload(DummyFile("dup.png", data))
    second = upload_service.process_upload(DummyFile("dup.png", data))

    assert first["status"] == "created"
    assert second["status"] == "duplicate"
    assert second["form_ids"] == first["form_ids"]


def test_text_file_with_pdf_extension_is_rejected(tmp_path, monkeypatch):
    data_dir, uploads_dir, pages_dir = _data_dirs_for(tmp_path)
    _upgrade_test_db(tmp_path, monkeypatch)
    from services import upload_service
    __import__("importlib").reload(upload_service)

    fake_pdf = b"This is not a real PDF file"
    result = upload_service.process_upload(DummyFile("bad.pdf", fake_pdf))
    assert result["status"] == "rejected"
    assert result["error"] == "Unsupported file type."


def test_large_file_rejected(tmp_path, monkeypatch):
    data_dir, uploads_dir, pages_dir = _data_dirs_for(tmp_path)
    _upgrade_test_db(tmp_path, monkeypatch)
    from services import upload_service
    __import__("importlib").reload(upload_service)

    oversized = b"A" * (MAX_FILE_SIZE + 1)
    result = upload_service.process_upload(DummyFile("big.pdf", oversized))
    assert result["status"] == "rejected"
    assert "50MB" in result["error"]


def test_partial_failure_cleans_form_rows_and_images(tmp_path, monkeypatch):
    data_dir, uploads_dir, pages_dir = _data_dirs_for(tmp_path)
    _upgrade_test_db(tmp_path, monkeypatch)
    from services import upload_service
    __import__("importlib").reload(upload_service)

    pdf = _make_pdf_with_pages(3)
    original = DummyFile("broken.pdf", pdf)
    real_add_form = upload_service.add_form
    counter = {"calls": 0}

    def flaky_add_form(*args, **kwargs):
        counter["calls"] += 1
        if counter["calls"] == 3:
            raise RuntimeError("page 3 failed")
        return real_add_form(*args, **kwargs)

    monkeypatch.setattr(upload_service, "add_form", flaky_add_form)
    result = upload_service.process_upload(original)
    assert result["status"] == "rejected"
    assert find_forms_by_hash(hashlib.sha256(pdf).hexdigest()) == []
    assert list(pages_dir.glob("*_p*.png")) == []

    monkeypatch.setattr(upload_service, "add_form", real_add_form)
    retry = upload_service.process_upload(original)
    assert retry["status"] == "created"
    assert len(retry["form_ids"]) == 3


def test_get_image_returns_png_and_404_for_missing_form(tmp_path, monkeypatch):
    data_dir, uploads_dir, pages_dir = _data_dirs_for(tmp_path)
    _upgrade_test_db(tmp_path, monkeypatch)
    from services import upload_service
    __import__("importlib").reload(upload_service)

    png = _make_png_bytes()
    result = upload_service.process_upload(DummyFile("a.png", png))
    form_id = result["form_ids"][0]
    assert form_id > 0

    client = __import__("fastapi.testclient").testclient.TestClient(__import__("main").app)
    response = client.get(f"/forms/{form_id}/image")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")

    missing = client.get("/forms/999999/image")
    assert missing.status_code == 404


def test_limit_zero_is_rejected_by_api(tmp_path, monkeypatch):
    data_dir, uploads_dir, pages_dir = _data_dirs_for(tmp_path)
    _upgrade_test_db(tmp_path, monkeypatch)
    client = __import__("fastapi.testclient").testclient.TestClient(__import__("main").app)
    response = client.get("/forms?status=uploaded&limit=0&offset=0")
    assert response.status_code == 422
