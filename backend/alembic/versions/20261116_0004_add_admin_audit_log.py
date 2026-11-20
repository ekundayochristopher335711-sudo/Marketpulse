"""Add administrative audit records.

Revision ID: 20261116_0004
Revises: 20261116_0003
"""

from alembic import op
import sqlalchemy as sa

revision = "20261116_0004"
down_revision = "20261116_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "audit_log" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("actor", sa.String(length=80), nullable=False),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("source_key", sa.String(length=80), nullable=True),
            sa.Column("details_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_audit_log_source_key", "audit_log", ["source_key"])
        op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    raise NotImplementedError("This audit-preserving migration is intentionally forward-only.")
