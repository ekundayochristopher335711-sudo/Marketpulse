"""Drop a redundant non-unique marketplace source index.

Revision ID: 20261116_0002
Revises: 20261116_0001
"""

from alembic import op
import sqlalchemy as sa

revision = "20261116_0002"
down_revision = "20261116_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("marketplace_source")
    }
    if "ix_marketplace_source_source_key" in indexes:
        op.drop_index("ix_marketplace_source_source_key", table_name="marketplace_source")


def downgrade() -> None:
    raise NotImplementedError("This data-preserving migration is intentionally forward-only.")
