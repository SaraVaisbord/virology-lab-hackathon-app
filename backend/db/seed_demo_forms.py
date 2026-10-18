from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .constants import FIELDS
from .queries import add_form, save_extraction
from .session import SessionLocal

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
PAGES_IMG_DIR = DATA_DIR / "pages_img"


def _ensure_placeholder_image(file_hash: str, form_id: int) -> Path:
    PAGES_IMG_DIR.mkdir(parents=True, exist_ok=True)
    target = PAGES_IMG_DIR / f"{file_hash}_p1.png"
    if not target.exists():
        image = Image.new("RGB", (1200, 1600), color=(245, 247, 250))
        image.save(target, format="PNG")
    return target


def _form_fields() -> list[dict[str, object]]:
    return [
        {
            "field_name": "first_name",
            "ocr_value": "אביה",
            "llm_value": "אבי",
            "status": "uncertain",
            "reason": "ה-OCR קרא את האותיות באופן חלקי; ה-LLM מזהה שם אחר",
            "value": "אבי",
            "bbox": json.dumps({"x": 88, "y": 95, "width": 180, "height": 30}),
            "page": 1,
            "x": 88,
            "y": 95,
            "width": 180,
            "height": 30,
        },
        {
            "field_name": "last_name",
            "ocr_value": "כהן",
            "llm_value": "כהן",
            "status": "confirmed",
            "reason": "הערך תואם בין OCR ל-LLM",
            "value": "כהן",
            "bbox": json.dumps({"x": 270, "y": 96, "width": 220, "height": 28}),
            "page": 1,
            "x": 270,
            "y": 96,
            "width": 220,
            "height": 28,
        },
        {
            "field_name": "id_number",
            "ocr_value": "937311",
            "llm_value": "937310",
            "status": "uncertain",
            "reason": "מספר תעודה שונה בין OCR ל-LLM; נדרש אישור",
            "value": "937310",
            "bbox": json.dumps({"x": 420, "y": 142, "width": 220, "height": 30}),
            "page": 1,
            "x": 420,
            "y": 142,
            "width": 220,
            "height": 30,
        },
        {
            "field_name": "central_number",
            "ocr_value": "C-505",
            "llm_value": "C-404",
            "status": "uncertain",
            "reason": "מספר מרכזי לא וודאי – קריאה לא ברורה באות C",
            "value": "C-404",
            "bbox": json.dumps({"x": 284, "y": 208, "width": 180, "height": 26}),
            "page": 1,
            "x": 284,
            "y": 208,
            "width": 180,
            "height": 26,
        },
        {
            "field_name": "received_date",
            "ocr_value": "09/07/2026",
            "llm_value": "09/07/2026",
            "status": "confirmed",
            "reason": "תאריך תואם",
            "value": "09/07/2026",
            "bbox": json.dumps({"x": 640, "y": 170, "width": 170, "height": 26}),
            "page": 1,
            "x": 640,
            "y": 170,
            "width": 170,
            "height": 26,
        },
        {
            "field_name": "sender",
            "ocr_value": "מרכז רפואי ברזילי",
            "llm_value": "המרכז הרפואי ע\"ש חיים שיבא - תל השומר",
            "status": "uncertain",
            "reason": "שם השולח אינו תואם; יש לבדוק מקור",
            "value": "המרכז הרפואי ע\"ש חיים שיבא - תל השומר",
            "bbox": json.dumps({"x": 98, "y": 255, "width": 260, "height": 28}),
            "page": 1,
            "x": 98,
            "y": 255,
            "width": 260,
            "height": 28,
        },
        {
            "field_name": "commitment_number",
            "ocr_value": "1002217",
            "llm_value": "1002218",
            "status": "uncertain",
            "reason": "מספר התחייבות שונה ב-1 ספרה, יש ווידוא ידני",
            "value": "1002218",
            "bbox": json.dumps({"x": 425, "y": 262, "width": 230, "height": 28}),
            "page": 1,
            "x": 425,
            "y": 262,
            "width": 230,
            "height": 28,
        },
    ]


def seed_demo_forms() -> dict[str, int | list[int]]:
    created = []
    with SessionLocal() as session:
        from sqlalchemy import select

        from .models import Form

        existing = session.execute(select(Form).order_by(Form.id.asc())).scalars().all()
        max_id = max((form.id for form in existing), default=62)
        if max_id < 63:
            max_id = 63

        for offset in range(1, 4):
            form_id = 63 + offset - 1
            form = session.get(Form, form_id)
            if form is None:
                file_hash = f"demo_seed_{offset:02d}"
                form = Form(
                    source_file=f"demo_seed_{offset:02d}.pdf",
                    file_hash=file_hash,
                    page_number=1,
                    image_path=f"pages_img/{file_hash}_p1.png",
                    status="extracted",
                    form_type="leumit",
                    raw_llm_json=json.dumps({"demo_seed": True, "seed_id": form_id}),
                )
                session.add(form)
                session.flush()
                created.append(form.id)
                _ensure_placeholder_image(file_hash, form.id)
            else:
                form.status = "extracted"
                form.form_type = "leumit"
                form.raw_llm_json = json.dumps({"demo_seed": True, "seed_id": form.id})
                _ensure_placeholder_image(form.file_hash, form.id)

            save_extraction(
                form_id=form.id,
                raw_llm_json=json.dumps({"demo_seed": True}),
                form_type="leumit",
                fields=_form_fields(),
            )

        if not created:
            form = session.get(Form, 63)
            if form is not None:
                form.raw_llm_json = json.dumps({"demo_seed": True, "seed_id": 63})
                form.status = "extracted"
                _ensure_placeholder_image(form.file_hash, form.id)
                save_extraction(
                    form_id=form.id,
                    raw_llm_json=json.dumps({"demo_seed": True}),
                    form_type="leumit",
                    fields=_form_fields(),
                )

    return {"created": created, "target_form_ids": [63, 64, 65]}


if __name__ == "__main__":
    print(seed_demo_forms())
