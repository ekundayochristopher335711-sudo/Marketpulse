"""Add source-scoped canonical URL identity.

Revision ID: 20261116_0006
Revises: 20261116_0005
"""

from alembic import op
import sqlalchemy as sa

revision = "20261116_0006"
down_revision = "20261116_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("listing")}
    if "canonical_url" not in columns:
        op.add_column(
            "listing",
            sa.Column("canonical_url", sa.String(length=2048), nullable=True),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("listing")}
    if "uq_listing_source_canonical_url" not in indexes:
        op.create_index(
            "uq_listing_source_canonical_url",
            "listing",
            ["source_id", "canonical_url"],
            unique=True,
        )


def downgrade() -> None:
    raise NotImplementedError("This data-preserving migration is intentionally forward-only.")
