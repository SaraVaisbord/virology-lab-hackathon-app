from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

import config
from db import queries
from db.constants import FIELD_LABELS, FORM_COLUMN_LABELS, FORM_STATUS_LABELS, MULTI_VALUE_FIELDS

_MULTI_VALUE_SEPARATOR = ", "
_DATE_FORMAT = "yyyy-mm-dd hh:mm"
_MIN_COLUMN_WIDTH = 12


def _field_values(form: dict[str, Any]) -> dict[str, str]:
    values: dict[str, list[str]] = {}
    for field in form["fields"]:
        value = field.get("value") or field.get("llm_value")
        if value:
            values.setdefault(field["field_name"], []).append(str(value))
    return {
        name: _MULTI_VALUE_SEPARATOR.join(items) if name in MULTI_VALUE_FIELDS else items[0]
        for name, items in values.items()
    }


def build_forms_workbook(filters: queries.FormFilters) -> bytes:
    rows, _total = queries.list_forms(filters, limit=config.EXPORT_MAX_ROWS)

    wb = Workbook()
    ws = wb.active
    ws.title = "Forms"
    ws.sheet_view.rightToLeft = True

    form_columns = list(FORM_COLUMN_LABELS)
    field_columns = list(FIELD_LABELS)
    ws.append([FORM_COLUMN_LABELS[c] for c in form_columns] + [FIELD_LABELS[c] for c in field_columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for form in rows:
        values = _field_values(form)
        form_cells = [FORM_STATUS_LABELS.get(form["status"], form["status"]) if c == "status" else form.get(c) for c in form_columns]
        ws.append(form_cells + [values.get(c) for c in field_columns])

    for column_cells in ws.columns:
        width = _MIN_COLUMN_WIDTH
        for cell in column_cells:
            cell.alignment = Alignment(horizontal="right", vertical="center")
            if isinstance(cell.value, datetime):
                cell.number_format = _DATE_FORMAT
            if cell.value is not None:
                width = max(width, len(str(cell.value)) + 2)
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
