"""Persist source authorization reference and worker schedule.

Revision ID: 20261116_0003
Revises: 20261116_0002
"""

from alembic import op
import sqlalchemy as sa

revision = "20261116_0003"
down_revision = "20261116_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("marketplace_source")
    }
    if "permission_reference" not in columns:
        op.add_column(
            "marketplace_source",
            sa.Column("permission_reference", sa.Text(), nullable=True),
        )
    if "next_run_at" not in columns:
        op.add_column(
            "marketplace_source",
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        )
    indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("marketplace_source")
    }
    if "ix_marketplace_source_next_run_at" not in indexes:
        op.create_index(
            "ix_marketplace_source_next_run_at",
            "marketplace_source",
            ["next_run_at"],
        )


def downgrade() -> None:
    raise NotImplementedError("This data-preserving migration is intentionally forward-only.")
