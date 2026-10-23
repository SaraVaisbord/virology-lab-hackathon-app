from __future__ import annotations

import hashlib

import pymupdf

from tests.conftest import png_bytes


def _pdf_with_pages(page_count: int) -> bytes:
    with pymupdf.open() as doc:
        for _ in range(page_count):
            doc.new_page().insert_text((72, 72), "Sample form")
        return doc.tobytes()


def test_pdf_pages_become_forms_and_images(settings, container):

    result = container.uploads.process_upload("sample.pdf", _pdf_with_pages(3))
    assert result["status"] == "created"
    assert len(result["form_ids"]) == 3
    assert len(list((settings.data_dir / "pages_img").glob("*_p*.png"))) == 3
    assert len(list((settings.data_dir / "uploads").glob("*sample.pdf"))) == 1


def test_png_and_jpeg_create_single_form_each(container):

    png = container.uploads.process_upload("img.png", png_bytes())
    jpeg = container.uploads.process_upload("img.jpeg", png_bytes(fmt="JPEG"))
    assert png["status"] == jpeg["status"] == "created"
    assert len(png["form_ids"]) == len(jpeg["form_ids"]) == 1


def test_duplicate_file_returns_duplicate(container):

    data = png_bytes()
    first = container.uploads.process_upload("dup.png", data)
    second = container.uploads.process_upload("dup.png", data)
    assert second["status"] == "duplicate"
    assert second["form_ids"] == first["form_ids"]


def test_text_file_with_pdf_extension_is_rejected(container):

    result = container.uploads.process_upload("bad.pdf", b"This is not a real PDF file")
    assert result == {"filename": "bad.pdf", "status": "rejected", "form_ids": [], "error": "Unsupported file type."}


def test_large_file_rejected(container):
    settings = container.settings
    result = container.uploads.process_upload("big.pdf", b"A" * (settings.max_file_size + 1))
    assert result["status"] == "rejected"
    assert f"{settings.max_file_size_mb}MB" in result["error"]


def test_partial_failure_cleans_rows_and_images(settings, monkeypatch, container):
    pdf = _pdf_with_pages(3)
    real_add_form = container.forms.add_form
    calls = {"count": 0}

    def flaky_add_form(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 3:
            raise RuntimeError("page 3 failed")
        return real_add_form(*args, **kwargs)

    monkeypatch.setattr(container.forms, "add_form", flaky_add_form)
    assert container.uploads.process_upload("broken.pdf", pdf)["status"] == "rejected"
    assert container.forms.find_forms_by_hash(hashlib.sha256(pdf).hexdigest()) == []
    assert list((settings.data_dir / "pages_img").glob("*_p*.png")) == []

    monkeypatch.setattr(container.forms, "add_form", real_add_form)
    retry = container.uploads.process_upload("broken.pdf", pdf)
    assert retry["status"] == "created" and len(retry["form_ids"]) == 3


def test_upload_endpoint_queues_and_image_is_served(client):
    response = client.post("/uploads", files=[("files", ("a.png", png_bytes(), "image/png"))])
    assert response.status_code == 200
    form_id = response.json()[0]["form_ids"][0]

    image = client.get(f"/forms/{form_id}/image")
    assert image.status_code == 200 and image.headers["content-type"].startswith("image/png")
    assert client.get("/forms/999999/image").status_code == 404
    assert client.get(f"/forms/{form_id}").json()["status"] == "uploaded"


def test_a_failed_upload_tells_the_client_only_a_general_message(container, monkeypatch, caplog):
    """The technical error (paths, internals) goes to the server log; the client gets the general message."""
    import logging

    from domain.vocabulary import UPLOAD_FAILED_MESSAGE

    def broken(*args, **kwargs):
        raise RuntimeError("could not write C:/internal/path/secret.png")

    monkeypatch.setattr(container.forms, "add_form", broken)
    with caplog.at_level(logging.ERROR):
        result = container.uploads.process_upload("ישראל ישראלי.pdf", _pdf_with_pages(1))
    assert result["status"] == "rejected" and result["error"] == UPLOAD_FAILED_MESSAGE
    assert "C:/internal/path/secret.png" in caplog.text  # full details in the server log
    assert "ישראל ישראלי" not in caplog.text  # the file name (it may name a patient) is not logged
