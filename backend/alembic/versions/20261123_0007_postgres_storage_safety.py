"""Use wide price columns and protect backend tables in PostgreSQL.

Revision ID: 20261123_0007
Revises: 20261116_0006
"""

from alembic import op
import sqlalchemy as sa

revision = "20261123_0007"
down_revision = "20261116_0006"
branch_labels = None
depends_on = None

APP_TABLES = (
    "listing",
    "price_observation",
    "marketplace_source",
    "collection_run",
    "audit_log",
    "alembic_version",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name in ("listing", "price_observation"):
        columns = {
            column["name"]: column for column in sa.inspect(bind).get_columns(table_name)
        }
        price_column = columns.get("asking_price")
        if price_column is None or isinstance(price_column["type"], sa.BigInteger):
            continue
        op.alter_column(
            table_name,
            "asking_price",
            existing_type=price_column["type"],
            type_=sa.BigInteger(),
            existing_nullable=False,
        )

    roles = set(
        bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        ).scalars()
    )
    for table_name in APP_TABLES:
        if not sa.inspect(bind).has_table(table_name, schema="public"):
            continue
        op.execute(
            sa.text(
                f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY'
            )
        )
        if roles:
            role_list = ", ".join(roles)
            op.execute(
                sa.text(
                    f'REVOKE ALL PRIVILEGES ON TABLE public."{table_name}" '
                    f"FROM {role_list}"
                )
            )


def downgrade() -> None:
    raise NotImplementedError("Storage and access hardening is intentionally forward-only.")
