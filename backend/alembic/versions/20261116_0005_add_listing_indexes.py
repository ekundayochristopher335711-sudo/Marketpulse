"""Add indexes used by listing search and history queries.

Revision ID: 20261116_0005
Revises: 20261116_0004
"""

from alembic import op
import sqlalchemy as sa

revision = "20261116_0005"
down_revision = "20261116_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("listing")}
    for name, fields in (
        ("ix_listing_model_brand", ["brand", "model"]),
        ("ix_listing_location", ["location"]),
        ("ix_listing_source_url", ["source_url"]),
        ("ix_listing_discovered", ["first_discovered_at"]),
    ):
        if name not in indexes:
            op.create_index(name, "listing", fields)


def downgrade() -> None:
    raise NotImplementedError("This data-preserving migration is intentionally forward-only.")
