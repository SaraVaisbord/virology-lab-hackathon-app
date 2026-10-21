"""rejected values: what the lab worker deleted, so re-extraction never puts it back

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-21 12:00:00
"""

from alembic import op
import sqlalchemy as sa

from db.migration_utils import recreate_mode

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("forms") as batch_op:
        batch_op.add_column(sa.Column("rejected_values", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("forms", recreate=recreate_mode()) as batch_op:
        batch_op.drop_column("rejected_values")
