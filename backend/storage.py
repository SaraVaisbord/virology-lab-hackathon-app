"""Where uploaded files and page images live — never in the database (it stores only the key).

    local   a folder under config.DATA_DIR (development, tests)
    s3      a private S3 bucket (AWS: block-public-access, encrypted; the pod reaches it through its IAM role)

Keys are relative, slash-separated paths: "pages_img/<hash>_p1.png", "uploads/<hash>_<name>".
"""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Iterator, Protocol

import config

PAGES_PREFIX = "pages_img"
UPLOADS_PREFIX = "uploads"


def page_key(file_hash: str, page_number: int) -> str:
    return f"{PAGES_PREFIX}/{file_hash}_p{page_number}.png"


def upload_key(file_hash: str, filename: str) -> str:
    return f"{UPLOADS_PREFIX}/{file_hash}_{filename}"


def _safe_key(key: str) -> str:
    """Refuse absolute paths and '..' — a stored key must never reach outside the storage."""
    path = PurePosixPath((key or "").replace("\\", "/"))
    if not key or path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:  # also "C:/…"
        raise ValueError(f"Invalid storage key: {key!r}")
    return path.as_posix()


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def local_path(self, key: str): ...  # context manager → Path of a local copy (FileNotFoundError if missing)


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / _safe_key(key)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def delete_prefix(self, prefix: str) -> None:
        folder, _, name_start = _safe_key(prefix).rpartition("/")
        for path in (self.root / folder).glob(f"{name_start}*"):
            path.unlink(missing_ok=True)

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        yield path


class S3Storage:
    def __init__(self, bucket: str, prefix: str = "") -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{_safe_key(key)}" if self.prefix else _safe_key(key)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        _s3_client().put_object(Bucket=self.bucket, Key=self._key(key), Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes | None:
        client = _s3_client()
        try:
            return client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except client.exceptions.NoSuchKey:
            return None

    def delete_prefix(self, prefix: str) -> None:
        client = _s3_client()
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self._key(prefix)):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        """OpenCV / the LLM clients read files: download to a temporary file, removed afterwards."""
        data = self.get(key)
        if data is None:
            raise FileNotFoundError(key)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / PurePosixPath(_safe_key(key)).name
            path.write_bytes(data)
            yield path


@lru_cache(maxsize=1)
def _s3_client():
    import boto3  # only needed with STORAGE_BACKEND=s3

    return boto3.client("s3", region_name=config.AWS_REGION or None)


def get_storage() -> Storage:
    """Built from the current config on every call (cheap), so tests can switch DATA_DIR."""
    if config.STORAGE_BACKEND == "s3":
        if not config.S3_BUCKET:
            raise RuntimeError("STORAGE_BACKEND=s3 needs S3_BUCKET")
        return S3Storage(config.S3_BUCKET, config.S3_PREFIX)
    return LocalStorage(config.DATA_DIR)
