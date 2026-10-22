"""field events: the lab worker's corrections, one appended row per action (no field values are stored)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-22 12:00:00
"""

from alembic import op
import sqlalchemy as sa

from db.models import in_clause

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

# Frozen values as of this revision.
FIELDS = ("central_number", "commitment_number", "first_name", "id_number", "last_name", "received_date", "sender")
ACTIONS = ("add", "confirm", "delete", "edit", "replace")
CHANGE_KINDS = (
    "day_month_swap", "different_value", "filled_missing", "format_only", "none", "removed", "restored", "transposition",
    "typo", "wrong_field",
)
VALUE_ORIGINS = ("machine", "machine_confirmed", "manual")
FIELD_STATUSES = ("confirmed", "conflict", "not_found", "uncertain", "unverified", "verified")
CONFIDENCE_LEVELS = ("high", "low", "medium")
INVENTORY_KINDS = ("barcode", "handwritten", "printed", "sticker")


def upgrade() -> None:
    op.create_table(
        "field_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("form_id", sa.Integer(), nullable=False),
        sa.Column("field_id", sa.Integer(), nullable=True),
        sa.Column("previous_event_id", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("change_kind", sa.String(length=32), nullable=False),
        sa.Column("chars_changed", sa.Integer(), nullable=True),
        sa.Column("matched_field", sa.String(length=64), nullable=True),
        sa.Column("digit_swaps", sa.String(length=32), nullable=True),
        sa.Column("before_origin", sa.String(length=32), nullable=False),
        sa.Column("before_written_as", sa.String(length=16), nullable=True),
        sa.Column("before_status", sa.String(length=32), nullable=True),
        sa.Column("before_confidence", sa.String(length=16), nullable=True),
        sa.Column("before_sources", sa.String(length=64), nullable=True),
        sa.Column("correct_seen_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint(f"field_name IN {in_clause(FIELDS)}", name=op.f("ck_field_events_field_name")),
        sa.CheckConstraint(f"action IN {in_clause(ACTIONS)}", name=op.f("ck_field_events_action")),
        sa.CheckConstraint(f"change_kind IN {in_clause(CHANGE_KINDS)}", name=op.f("ck_field_events_change_kind")),
        sa.CheckConstraint(
            f"(matched_field IN {in_clause(FIELDS)} OR matched_field IS NULL)", name=op.f("ck_field_events_matched_field")
        ),
        sa.CheckConstraint(f"before_origin IN {in_clause(VALUE_ORIGINS)}", name=op.f("ck_field_events_before_origin")),
        sa.CheckConstraint(
            f"(before_status IN {in_clause(FIELD_STATUSES)} OR before_status IS NULL)", name=op.f("ck_field_events_before_status")
        ),
        sa.CheckConstraint(
            f"(before_confidence IN {in_clause(CONFIDENCE_LEVELS)} OR before_confidence IS NULL)",
            name=op.f("ck_field_events_before_confidence"),
        ),
        sa.CheckConstraint(
            f"(before_written_as IN {in_clause(INVENTORY_KINDS)} OR before_written_as IS NULL)",
            name=op.f("ck_field_events_before_written_as"),
        ),
        sa.ForeignKeyConstraint(["form_id"], ["forms.id"], name=op.f("fk_field_events_form_id_forms"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["field_id"], ["extracted_fields.id"], name=op.f("fk_field_events_field_id_extracted_fields"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["previous_event_id"], ["field_events.id"], name=op.f("fk_field_events_previous_event_id_field_events"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_field_events")),
    )
    op.create_index(op.f("ix_field_events_form_id"), "field_events", ["form_id"])
    op.create_index(op.f("ix_field_events_field_id"), "field_events", ["field_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_field_events_field_id"), table_name="field_events")
    op.drop_index(op.f("ix_field_events_form_id"), table_name="field_events")
    op.drop_table("field_events")
