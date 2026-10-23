"""File storage: page images and uploads live outside the database (local folder or private S3 bucket)."""

from __future__ import annotations

import io

import pytest

from integrations import storage
from integrations.storage import LocalStorage, S3Storage, page_key


def test_local_storage_round_trip_and_prefix_delete(tmp_path):
    files = LocalStorage(tmp_path)
    files.put(page_key("abc", 1), b"one", "image/png")
    files.put(page_key("abc", 2), b"two", "image/png")
    files.put(page_key("xyz", 1), b"other", "image/png")
    assert files.get("pages_img/abc_p1.png") == b"one"
    with files.local_path("pages_img/abc_p2.png") as path:
        assert path.read_bytes() == b"two"
    files.delete_prefix("pages_img/abc_")
    assert files.get("pages_img/abc_p1.png") is None and files.get("pages_img/xyz_p1.png") == b"other"
    with pytest.raises(FileNotFoundError):
        with files.local_path("pages_img/abc_p1.png"):
            pass


@pytest.mark.parametrize("key", ["../app.db", "/etc/passwd", "C:/Windows/x.png", "pages_img/../../x", ""])
def test_keys_never_leave_the_storage(tmp_path, key):
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).get(key)


class _FakeS3:
    """The few S3 calls storage.py makes, in memory."""

    class exceptions:  # noqa: N801 — mirrors boto3's client.exceptions
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def get_object(self, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.objects:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)][0])}

    def get_paginator(self, _name):
        fake = self

        class _Paginator:
            def paginate(self, Bucket, Prefix):  # noqa: N803
                yield {"Contents": [{"Key": key} for bucket, key in fake.objects if bucket == Bucket and key.startswith(Prefix)]}

        return _Paginator()

    def delete_objects(self, Bucket, Delete):  # noqa: N803
        for item in Delete["Objects"]:
            self.objects.pop((Bucket, item["Key"]), None)


def test_s3_storage_uses_the_bucket_and_prefix(monkeypatch):
    fake = _FakeS3()
    files = S3Storage("lab-bucket", prefix="forms", new_client=lambda: fake)
    files.put(page_key("abc", 1), b"page", "image/png")
    assert fake.objects[("lab-bucket", "forms/pages_img/abc_p1.png")] == (b"page", "image/png")
    assert files.get("pages_img/abc_p1.png") == b"page" and files.get("pages_img/none.png") is None
    with files.local_path("pages_img/abc_p1.png") as path:  # a temporary local copy for OpenCV / the LLM
        assert path.read_bytes() == b"page"
    assert not path.exists()  # removed afterwards
    files.delete_prefix("pages_img/abc_")
    assert fake.objects == {}


def test_upload_and_image_endpoint_go_through_the_configured_storage(client, monkeypatch):
    """With STORAGE_BACKEND=s3 nothing is written to the local data folder — the page is served from the bucket."""
    import config
    from tests.conftest import png_bytes

    fake = _FakeS3()
    monkeypatch.setattr(storage, "_boto3_client", lambda region: fake)
    monkeypatch.setattr(config, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(config, "S3_BUCKET", "lab-bucket")
    monkeypatch.setattr(config, "S3_PREFIX", "")

    response = client.post("/uploads", files={"files": ("scan.png", png_bytes(), "image/png")})
    assert response.status_code == 200, response.text
    (form_id,) = response.json()[0]["form_ids"]
    keys = {key for _bucket, key in fake.objects}
    assert any(key.startswith("uploads/") for key in keys) and any(key.startswith("pages_img/") for key in keys)
    assert not (config.DATA_DIR / "pages_img").exists()

    image = client.get(f"/forms/{form_id}/image")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")
