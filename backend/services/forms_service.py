from __future__ import annotations

from pathlib import Path

from db.queries import get_form as db_get_form, list_forms_with_fields as db_list_forms_with_fields

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


def list_forms(status: str | None, limit: int, offset: int):
    rows = db_list_forms_with_fields(status=status, limit=limit, offset=offset)
    return list(reversed(rows))


def get_form(form_id: int):
    form = db_get_form(form_id)
    if form is None:
        return None
    return form


def get_form_image_path(form_id: int) -> Path | None:
    form = db_get_form(form_id)
    if form is None:
        return None

    raw_path = form.get("image_path") or ""
    candidates: list[Path] = []
    if raw_path:
        candidates.append(Path(raw_path))
        if raw_path.startswith("/"):
            candidates.append(Path(raw_path).resolve())
        else:
            candidates.append((DATA_DIR / raw_path).resolve())

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file() and str(candidate.resolve()).startswith(str(DATA_DIR.resolve())):
                return candidate.resolve()
        except OSError:
            continue

    return None
