"""Add listing provenance, price history and collection metadata.

Revision ID: 20261116_0001
Revises:
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "20261116_0001"
down_revision = None
branch_labels = None
depends_on = None


SOURCES = (
    ("jiji", "Jiji Nigeria"),
    ("naijabargains", "NaijaBargains"),
    ("enytinplus", "EnytinPlus"),
    ("jax", "Jax.ng"),
    ("aae", "AAE.NG"),
    ("facebook_marketplace", "Facebook Marketplace"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "listing" not in existing_tables:
        op.create_table(
            "listing",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.String(length=80), nullable=False, server_default="legacy"),
            sa.Column("source_listing_id", sa.String(length=255), nullable=True),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("normalized_title", sa.String(length=500), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=120), nullable=False),
            sa.Column("subcategory", sa.String(length=120), nullable=True),
            sa.Column("brand", sa.String(length=120), nullable=True),
            sa.Column("model", sa.String(length=120), nullable=True),
            sa.Column("asking_price", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="NGN"),
            sa.Column("location", sa.String(length=200), nullable=False),
            sa.Column("state", sa.String(length=100), nullable=True),
            sa.Column("city", sa.String(length=100), nullable=True),
            sa.Column("locality", sa.String(length=120), nullable=True),
            sa.Column("source_name", sa.String(length=120), nullable=False),
            sa.Column("source_url", sa.String(), nullable=True),
            sa.Column("canonical_url", sa.String(length=2048), nullable=True),
            sa.Column("condition", sa.String(length=80), nullable=True),
            sa.Column("listing_status", sa.String(length=24), nullable=False, server_default="active"),
            sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_price_update_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("data_quality_score", sa.Float(), nullable=True),
            sa.Column("raw_source_reference", sa.Text(), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    else:
        columns = {column["name"] for column in inspector.get_columns("listing")}
        additions = (
            ("source_id", sa.String(length=80), False, "legacy"),
            ("source_listing_id", sa.String(length=255), True, None),
            ("normalized_title", sa.String(length=500), True, None),
            ("description", sa.Text(), True, None),
            ("subcategory", sa.String(length=120), True, None),
            ("brand", sa.String(length=120), True, None),
            ("model", sa.String(length=120), True, None),
            ("currency", sa.String(length=3), False, "NGN"),
            ("state", sa.String(length=100), True, None),
            ("city", sa.String(length=100), True, None),
            ("locality", sa.String(length=120), True, None),
            ("canonical_url", sa.String(length=2048), True, None),
            ("listing_status", sa.String(length=24), False, "active"),
            ("first_discovered_at", sa.DateTime(timezone=True), True, None),
            ("last_observed_at", sa.DateTime(timezone=True), True, None),
            ("last_price_update_at", sa.DateTime(timezone=True), True, None),
            ("data_quality_score", sa.Float(), True, None),
            ("raw_source_reference", sa.Text(), True, None),
        )
        for name, column_type, nullable, default in additions:
            if name in columns:
                continue
            server_default = sa.text(f"'{default}'") if default is not None else None
            op.add_column(
                "listing",
                sa.Column(name, column_type, nullable=nullable, server_default=server_default),
            )

        columns = {column["name"] for column in sa.inspect(bind).get_columns("listing")}
        if {"source_name", "source_id"}.issubset(columns):
            op.execute(
                sa.text(
                    "UPDATE listing SET source_id = 'legacy' "
                    "WHERE source_id IS NULL OR source_id = ''"
                )
            )
        if {"title", "normalized_title"}.issubset(columns):
            op.execute(
                sa.text(
                    "UPDATE listing SET normalized_title = title "
                    "WHERE normalized_title IS NULL"
                )
            )
        if {"observed_at", "first_discovered_at"}.issubset(columns):
            op.execute(
                sa.text(
                    "UPDATE listing SET first_discovered_at = observed_at "
                    "WHERE first_discovered_at IS NULL"
                )
            )
        if {"observed_at", "last_observed_at"}.issubset(columns):
            op.execute(
                sa.text(
                    "UPDATE listing SET last_observed_at = observed_at "
                    "WHERE last_observed_at IS NULL"
                )
            )

        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("listing")}
        if "uq_listing_source_external_id" not in indexes:
            op.create_index(
                "uq_listing_source_external_id",
                "listing",
                ["source_id", "source_listing_id"],
                unique=True,
            )

    if "price_observation" not in existing_tables:
        op.create_table(
            "price_observation",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("listing_id", sa.Integer(), sa.ForeignKey("listing.id"), nullable=False),
            sa.Column("asking_price", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="NGN"),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_price_observation_listing_id", "price_observation", ["listing_id"])
        op.create_index(
            "ix_price_observation_listing_time",
            "price_observation",
            ["listing_id", "observed_at"],
        )

    if "marketplace_source" not in existing_tables:
        op.create_table(
            "marketplace_source",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_key", sa.String(length=80), nullable=False, unique=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("access_method", sa.String(length=32), nullable=False, server_default="none"),
            sa.Column("permission_status", sa.String(length=24), nullable=False, server_default="unknown"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("minimum_interval_seconds", sa.Integer(), nullable=False, server_default="3600"),
            sa.Column("permitted_categories_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("permitted_fields_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("retention_days", sa.Integer(), nullable=True),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        source_table = sa.table(
            "marketplace_source",
            sa.column("source_key", sa.String()),
            sa.column("name", sa.String()),
            sa.column("access_method", sa.String()),
            sa.column("permission_status", sa.String()),
            sa.column("enabled", sa.Boolean()),
            sa.column("minimum_interval_seconds", sa.Integer()),
            sa.column("permitted_categories_json", sa.Text()),
            sa.column("permitted_fields_json", sa.Text()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(
            source_table,
            [
                {
                    "source_key": key,
                    "name": name,
                    "access_method": "none",
                    "permission_status": "unknown",
                    "enabled": False,
                    "minimum_interval_seconds": 3600,
                    "permitted_categories_json": "[]",
                    "permitted_fields_json": "[]",
                    "created_at": datetime.now(timezone.utc),
                }
                for key, name in SOURCES
            ],
        )

    if "collection_run" not in existing_tables:
        op.create_table(
            "collection_run",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "source_key",
                sa.String(length=80),
                sa.ForeignKey("marketplace_source.source_key"),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_summary", sa.Text(), nullable=True),
        )
        op.create_index("ix_collection_run_source_key", "collection_run", ["source_key"])

    listing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("listing")}
    for name, fields in (
        ("ix_listing_source_id", ["source_id"]),
        ("ix_listing_category_city", ["category", "city"]),
        ("ix_listing_model_brand", ["brand", "model"]),
        ("ix_listing_location", ["location"]),
        ("ix_listing_source_url", ["source_url"]),
        ("ix_listing_discovered", ["first_discovered_at"]),
        ("ix_listing_status_observed", ["listing_status", "last_observed_at"]),
        ("ix_listing_price", ["asking_price"]),
    ):
        if name not in listing_indexes:
            op.create_index(name, "listing", fields)
    if "uq_listing_source_external_id" not in listing_indexes:
        op.create_index(
            "uq_listing_source_external_id",
            "listing",
            ["source_id", "source_listing_id"],
            unique=True,
        )
    if "uq_listing_source_canonical_url" not in listing_indexes:
        op.create_index(
            "uq_listing_source_canonical_url",
            "listing",
            ["source_id", "canonical_url"],
            unique=True,
        )


def downgrade() -> None:
    raise NotImplementedError("This data-preserving foundation migration is intentionally forward-only.")
