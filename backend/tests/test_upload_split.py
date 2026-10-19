from __future__ import annotations

import hashlib

import pymupdf

from tests.conftest import DummyUpload, png_bytes


def _pdf_with_pages(page_count: int) -> bytes:
    with pymupdf.open() as doc:
        for _ in range(page_count):
            doc.new_page().insert_text((72, 72), "Sample form")
        return doc.tobytes()


def test_pdf_pages_become_forms_and_images(app_env):
    from services import upload_service

    result = upload_service.process_upload(DummyUpload("sample.pdf", _pdf_with_pages(3)))
    assert result["status"] == "created"
    assert len(result["form_ids"]) == 3
    assert len(list((app_env / "pages_img").glob("*_p*.png"))) == 3
    assert len(list((app_env / "uploads").glob("*sample.pdf"))) == 1


def test_png_and_jpeg_create_single_form_each(app_env):
    from services import upload_service

    png = upload_service.process_upload(DummyUpload("img.png", png_bytes()))
    jpeg = upload_service.process_upload(DummyUpload("img.jpeg", png_bytes(fmt="JPEG")))
    assert png["status"] == jpeg["status"] == "created"
    assert len(png["form_ids"]) == len(jpeg["form_ids"]) == 1


def test_duplicate_file_returns_duplicate(app_env):
    from services import upload_service

    data = png_bytes()
    first = upload_service.process_upload(DummyUpload("dup.png", data))
    second = upload_service.process_upload(DummyUpload("dup.png", data))
    assert second["status"] == "duplicate"
    assert second["form_ids"] == first["form_ids"]


def test_text_file_with_pdf_extension_is_rejected(app_env):
    from services import upload_service

    result = upload_service.process_upload(DummyUpload("bad.pdf", b"This is not a real PDF file"))
    assert result == {"filename": "bad.pdf", "status": "rejected", "form_ids": [], "error": "Unsupported file type."}


def test_large_file_rejected(app_env):
    import config
    from services import upload_service

    result = upload_service.process_upload(DummyUpload("big.pdf", b"A" * (config.MAX_FILE_SIZE + 1)))
    assert result["status"] == "rejected"
    assert f"{config.MAX_FILE_SIZE_MB}MB" in result["error"]


def test_partial_failure_cleans_rows_and_images(app_env, monkeypatch):
    from db.queries import find_forms_by_hash
    from services import upload_service

    pdf = _pdf_with_pages(3)
    real_add_form = upload_service.add_form
    calls = {"count": 0}

    def flaky_add_form(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 3:
            raise RuntimeError("page 3 failed")
        return real_add_form(*args, **kwargs)

    monkeypatch.setattr(upload_service, "add_form", flaky_add_form)
    assert upload_service.process_upload(DummyUpload("broken.pdf", pdf))["status"] == "rejected"
    assert find_forms_by_hash(hashlib.sha256(pdf).hexdigest()) == []
    assert list((app_env / "pages_img").glob("*_p*.png")) == []

    monkeypatch.setattr(upload_service, "add_form", real_add_form)
    retry = upload_service.process_upload(DummyUpload("broken.pdf", pdf))
    assert retry["status"] == "created" and len(retry["form_ids"]) == 3


def test_upload_endpoint_queues_and_image_is_served(client):
    response = client.post("/uploads", files=[("files", ("a.png", png_bytes(), "image/png"))])
    assert response.status_code == 200
    form_id = response.json()[0]["form_ids"][0]

    image = client.get(f"/forms/{form_id}/image")
    assert image.status_code == 200 and image.headers["content-type"].startswith("image/png")
    assert client.get("/forms/999999/image").status_code == 404
    assert client.get(f"/forms/{form_id}").json()["status"] == "uploaded"
