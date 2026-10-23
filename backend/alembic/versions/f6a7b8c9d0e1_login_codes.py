"""login codes: the one-time login code waiting to be entered, kept in the database (hash only) so it works across
server restarts and replicas

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-23 12:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("salt", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_login_codes_attempts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_codes")),
    )
    op.create_index(op.f("ix_login_codes_expires_at"), "login_codes", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_login_codes_expires_at"), table_name="login_codes")
    op.drop_table("login_codes")
