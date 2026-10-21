"""separate sources: per-source results on forms, barcode/evidence/box_source on fields, 'conflict' status

Before this revision the LLM response and the barcodes were stored together in forms.raw_llm_json
({"llm": ..., "barcodes": [...]}) and the barcode value of a field was stored in ocr_value (there is no OCR).

Revision ID: c3d4e5f6a7b8
Revises: b7c1d2e3f4a5
Create Date: 2026-10-19 10:00:00
"""

import json

from alembic import op
import sqlalchemy as sa

from db.migration_utils import recreate_mode
from db.models import in_clause

revision = "c3d4e5f6a7b8"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None

# Frozen values as of this revision.
FIELD_STATUSES = ("confirmed", "conflict", "not_found", "uncertain", "unverified", "verified")
_PREVIOUS_FIELD_STATUSES = ("confirmed", "not_found", "uncertain", "unverified", "verified")
BOX_SOURCES = ("barcode", "llm", "ocr")


def _split_combined_results(conn) -> None:
    rows = conn.execute(sa.text("SELECT id, page_number, llm_result FROM forms WHERE llm_result IS NOT NULL")).fetchall()
    for form_id, page_number, raw in rows:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not (isinstance(data, dict) and "llm" in data):
            continue
        barcodes = [{**item, "page": page_number} for item in data.get("barcodes") or []]
        conn.execute(
            sa.text("UPDATE forms SET llm_result = :llm, barcode_result = :barcodes WHERE id = :id"),
            {
                "id": form_id,
                "llm": json.dumps(data["llm"], ensure_ascii=False),
                "barcodes": json.dumps({"status": "ok", "items": barcodes}, ensure_ascii=False),
            },
        )


def upgrade() -> None:
    with op.batch_alter_table("forms", recreate=recreate_mode()) as batch_op:
        batch_op.alter_column("raw_llm_json", new_column_name="llm_result", existing_type=sa.Text(), existing_nullable=True)
        batch_op.add_column(sa.Column("barcode_result", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("ocr_result", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("source_errors", sa.Text(), nullable=True))
    _split_combined_results(op.get_bind())

    with op.batch_alter_table("extracted_fields", recreate=recreate_mode()) as batch_op:
        batch_op.add_column(sa.Column("barcode_value", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("evidence", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("box_source", sa.String(length=16), nullable=True))
        batch_op.create_check_constraint(op.f("ck_extracted_fields_box_source"), f"(box_source IN {in_clause(BOX_SOURCES)} OR box_source IS NULL)")
        batch_op.drop_constraint(op.f("ck_extracted_fields_status"), type_="check")
        batch_op.create_check_constraint(op.f("ck_extracted_fields_status"), f"status IN {in_clause(FIELD_STATUSES)}")

    # ocr_value held barcode readings (no OCR engine existed) — move them to where they belong.
    op.execute("UPDATE extracted_fields SET barcode_value = ocr_value, ocr_value = NULL")


def downgrade() -> None:
    op.execute("UPDATE extracted_fields SET ocr_value = barcode_value WHERE barcode_value IS NOT NULL")
    op.execute("UPDATE extracted_fields SET status = 'uncertain' WHERE status = 'conflict'")
    with op.batch_alter_table("extracted_fields", recreate=recreate_mode()) as batch_op:
        batch_op.drop_constraint(op.f("ck_extracted_fields_status"), type_="check")
        batch_op.create_check_constraint(op.f("ck_extracted_fields_status"), f"status IN {in_clause(_PREVIOUS_FIELD_STATUSES)}")
        batch_op.drop_constraint(op.f("ck_extracted_fields_box_source"), type_="check")
        batch_op.drop_column("box_source")
        batch_op.drop_column("evidence")
        batch_op.drop_column("barcode_value")

    with op.batch_alter_table("forms", recreate=recreate_mode()) as batch_op:
        batch_op.drop_column("source_errors")
        batch_op.drop_column("ocr_result")
        batch_op.drop_column("barcode_result")
        batch_op.alter_column("llm_result", new_column_name="raw_llm_json", existing_type=sa.Text(), existing_nullable=True)
