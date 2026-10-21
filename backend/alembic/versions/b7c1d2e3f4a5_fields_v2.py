"""fields v2: complete status constraints, float coordinates, confidence, drop redundant columns

Revision ID: b7c1d2e3f4a5
Revises: ea99c03b9c61
Create Date: 2026-10-18 23:00:00
"""

from alembic import op
import sqlalchemy as sa

from db.migration_utils import recreate_mode
from db.models import in_clause

revision = "b7c1d2e3f4a5"
down_revision = "ea99c03b9c61"
branch_labels = None
depends_on = None

# Frozen values as of this revision — migrations must not change when db/constants.py changes later.
FORM_STATUSES = ("approved", "extracted", "failed", "processing", "uploaded")
FIELD_STATUSES = ("confirmed", "not_found", "uncertain", "unverified", "verified")
CONFIDENCE_LEVELS = ("high", "low", "medium")

_OLD_FORM_STATUSES = ("extracted", "failed", "processing", "uploaded")
_OLD_FIELD_STATUSES = ("confirmed", "uncertain", "unverified", "verified")
_COORDINATES = ("x", "y", "width", "height")


def upgrade() -> None:
    with op.batch_alter_table("forms", recreate=recreate_mode()) as batch_op:
        batch_op.drop_constraint(op.f("ck_forms_status"), type_="check")
        batch_op.create_check_constraint(op.f("ck_forms_status"), f"status IN {in_clause(FORM_STATUSES)}")

    # Keep whatever the model read before dropping the duplicate column.
    op.execute("UPDATE extracted_fields SET llm_value = raw_value WHERE llm_value IS NULL")
    # Old coordinates were raw pixels of an unknown image size — they cannot be normalized.
    op.execute("UPDATE extracted_fields SET x = NULL, y = NULL, width = NULL, height = NULL")

    with op.batch_alter_table("extracted_fields", recreate=recreate_mode()) as batch_op:
        batch_op.drop_constraint(op.f("ck_extracted_fields_status"), type_="check")
        batch_op.create_check_constraint(op.f("ck_extracted_fields_status"), f"status IN {in_clause(FIELD_STATUSES)}")
        batch_op.add_column(sa.Column("confidence", sa.String(length=16), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_extracted_fields_confidence"),
            f"(confidence IN {in_clause(CONFIDENCE_LEVELS)} OR confidence IS NULL)",
        )
        for column in _COORDINATES:
            batch_op.alter_column(column, type_=sa.Float(), existing_type=sa.Text(), existing_nullable=True,
                                  postgresql_using=f"{column}::double precision")  # all NULL by now
        batch_op.drop_column("raw_value")
        batch_op.drop_column("bbox")


def downgrade() -> None:
    with op.batch_alter_table("extracted_fields", recreate=recreate_mode()) as batch_op:
        batch_op.add_column(sa.Column("bbox", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("raw_value", sa.Text(), nullable=True))
        for column in _COORDINATES:
            batch_op.alter_column(column, type_=sa.Text(), existing_type=sa.Float(), existing_nullable=True,
                                  postgresql_using=f"{column}::text")
        batch_op.drop_constraint(op.f("ck_extracted_fields_confidence"), type_="check")
        batch_op.drop_column("confidence")
        batch_op.drop_constraint(op.f("ck_extracted_fields_status"), type_="check")
        batch_op.create_check_constraint(op.f("ck_extracted_fields_status"), f"status IN {in_clause(_OLD_FIELD_STATUSES)}")

    op.execute("UPDATE extracted_fields SET raw_value = llm_value")

    with op.batch_alter_table("forms", recreate=recreate_mode()) as batch_op:
        batch_op.drop_constraint(op.f("ck_forms_status"), type_="check")
        batch_op.create_check_constraint(op.f("ck_forms_status"), f"status IN {in_clause(_OLD_FORM_STATUSES)}")
