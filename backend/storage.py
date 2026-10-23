"""Compatibility shim during the refactor — file storage is integrations/storage.py. Removed in its last step."""

from __future__ import annotations

import config
from integrations.storage import PAGES_PREFIX, UPLOADS_PREFIX, LocalStorage, S3Storage, Storage, build_storage, page_key, upload_key  # noqa: F401


def get_storage() -> Storage:
    """Built from the current config on every call (cheap), so tests can switch DATA_DIR."""
    return build_storage(config.STORAGE_BACKEND, config.DATA_DIR, config.S3_BUCKET, config.S3_PREFIX, config.AWS_REGION)
