from __future__ import annotations

from pathlib import Path

import config


def resolve_image_path(raw_path: str | None) -> Path | None:
    """Resolve a stored (data-dir relative) image path, refusing anything outside the data directory."""
    if not raw_path:
        return None
    data_dir = config.DATA_DIR.resolve()
    candidate = Path(raw_path)
    candidate = (candidate if candidate.is_absolute() else data_dir / candidate).resolve()
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None
