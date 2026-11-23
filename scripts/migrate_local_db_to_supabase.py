"""Copy the local MarketPulse SQLite database into the new Supabase project.

The destination URL is read from DATABASE_URL and is never printed.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool


PROJECT_REF = "rlgkujdkecbpjadhbdsm"
LOCAL_DB = Path(__file__).resolve().parents[1] / "backend" / "marketpulse.db"
BACKEND_DIR = LOCAL_DB.parent
APP_TABLES = (
    "marketplace_source",
    "listing",
    "price_observation",
    "collection_run",
    "audit_log",
)
SEQUENCE_TABLES = (
    "marketplace_source",
    "listing",
    "price_observation",
    "collection_run",
    "audit_log",
)


def safe_database_url(raw_url: str) -> URL:
    if not raw_url:
        raise ValueError("The hidden database URL was empty.")
    try:
        database_url = make_url(raw_url)
    except Exception:
        raise ValueError("That connection string could not be read. Copy the Session pooler URI.") from None

    if database_url.drivername in {"postgres", "postgresql"}:
        database_url = database_url.set(drivername="postgresql+psycopg")
    elif database_url.drivername != "postgresql+psycopg":
        raise ValueError("Use the PostgreSQL Session pooler URI from Supabase.")

    if not (database_url.host or "").endswith("pooler.supabase.com"):
        raise ValueError("Choose Session pooler in Supabase and copy its URI.")
    if PROJECT_REF not in (database_url.username or ""):
        raise ValueError("This URI does not identify the MarketPulse Supabase project.")

    query = dict(database_url.query)
    query["sslmode"] = "require"
    return database_url.set(query=query)


def sanitized_output(output: str) -> str:
    return re.sub(
        r"(?i)(?:postgres|postgresql)(?:\+psycopg)?://\S+",
        "[database URL hidden]",
        output,
    )


def run_alembic(python_executable: str, revision: str, database_url: str) -> None:
    child_environment = os.environ.copy()
    child_environment["DATABASE_URL"] = database_url
    result = subprocess.run(
        [python_executable, "-m", "alembic", "upgrade", revision],
        cwd=BACKEND_DIR,
        env=child_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        combined = sanitized_output(result.stdout + result.stderr)
        tail = "\n".join(combined.splitlines()[-18:])
        raise RuntimeError(
            f"Alembic could not prepare the database through {revision}.\n{tail}"
        )


def make_snapshot(destination: Path) -> dict[str, int]:
    with sqlite3.connect(LOCAL_DB) as local_connection:
        with sqlite3.connect(destination) as snapshot_connection:
            local_connection.backup(snapshot_connection)

    with sqlite3.connect(destination) as snapshot_connection:
        integrity = snapshot_connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError("The local database snapshot failed its integrity check.")

    snapshot_engine = create_engine(f"sqlite:///{destination.as_posix()}")
    try:
        available = set(inspect(snapshot_engine).get_table_names())
        missing = set(APP_TABLES) - available
        if missing:
            raise RuntimeError(
                "The local database is missing expected MarketPulse tables: "
                + ", ".join(sorted(missing))
            )
        with snapshot_engine.connect() as connection:
            return {
                table_name: connection.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar_one()
                for table_name in APP_TABLES
            }
    finally:
        snapshot_engine.dispose()


def ensure_destination_is_safe(engine) -> None:
    inspector = inspect(engine)
    available = set(inspector.get_table_names(schema="public"))
    for table_name in APP_TABLES:
        if table_name not in available:
            continue
        with engine.connect() as connection:
            count = connection.execute(
                text(f'SELECT COUNT(*) FROM public."{table_name}"')
            ).scalar_one()
        if count:
            if table_name == "marketplace_source":
                with engine.connect() as connection:
                    source_rows = connection.execute(
                        text(
                            "SELECT source_key, access_method, permission_status, enabled, "
                            "permitted_categories_json, permitted_fields_json, "
                            "permission_reference, last_success_at, next_run_at "
                            "FROM public.marketplace_source"
                        )
                    ).mappings().all()
                expected_seed_keys = {
                    "aae",
                    "enytinplus",
                    "facebook_marketplace",
                    "jax",
                    "jiji",
                    "naijabargains",
                }
                migration_seeds_only = (
                    {row["source_key"] for row in source_rows} == expected_seed_keys
                    and all(
                        row["access_method"] == "none"
                        and row["permission_status"] == "unknown"
                        and not row["enabled"]
                        and row["permitted_categories_json"] == "[]"
                        and row["permitted_fields_json"] == "[]"
                        and row["permission_reference"] is None
                        and row["last_success_at"] is None
                        and row["next_run_at"] is None
                        for row in source_rows
                    )
                )
                if migration_seeds_only:
                    continue
            raise RuntimeError(
                "The Supabase database already contains MarketPulse data. "
                f"Table {table_name} has {count} rows; nothing was overwritten."
            )

    if "alembic_version" in available:
        with engine.connect() as connection:
            revisions = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalars().all()
        supported = {"20261116_0006"}
        if any(revision not in supported for revision in revisions):
            raise RuntimeError(
                "The Supabase database has an unexpected Alembic revision; "
                "nothing was overwritten."
            )


def normalize_row(table_name: str, row: dict) -> dict:
    normalized = {}
    for name, value in row.items():
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)
        normalized[name] = value

    if table_name == "collection_run" and normalized.get("status") in {
        "queued",
        "running",
    }:
        normalized.update(
            status="failed",
            completed_at=datetime.now(timezone.utc),
            error_count=max(int(normalized.get("error_count") or 0), 1),
            error_summary="Local worker execution was not transferred to the hosted database.",
        )

    if table_name == "marketplace_source":
        source_key = normalized.get("source_key")
        if source_key == "facebook_marketplace":
            normalized.update(
                access_method="api",
                permission_status="approved",
                enabled=False,
                next_run_at=None,
            )
        elif source_key in {
            "aae",
            "enytinplus",
            "jax",
            "jiji",
            "naijabargains",
        }:
            normalized.update(
                access_method="authorized_web",
                permission_status="approved",
                enabled=True,
            )
    return normalized


def copy_data(snapshot_path: Path, destination_engine, expected: dict[str, int]) -> None:
    source_engine = create_engine(f"sqlite:///{snapshot_path.as_posix()}")
    try:
        source_metadata = MetaData()
        destination_metadata = MetaData()
        source_tables = {
            name: Table(name, source_metadata, autoload_with=source_engine)
            for name in APP_TABLES
        }
        destination_tables = {
            name: Table(
                name,
                destination_metadata,
                schema="public",
                autoload_with=destination_engine,
            )
            for name in APP_TABLES
        }

        for table_name in APP_TABLES:
            missing = set(source_tables[table_name].c.keys()) - set(
                destination_tables[table_name].c.keys()
            )
            if missing:
                raise RuntimeError(
                    f"The destination {table_name} table lacks columns: "
                    + ", ".join(sorted(missing))
                )

        with source_engine.connect() as source_connection:
            with destination_engine.begin() as destination_connection:
                # The foundation migration inserts six empty source placeholders.
                # Replace those defaults with the complete local approval records.
                destination_connection.execute(
                    text("DELETE FROM public.marketplace_source")
                )
                for table_name in APP_TABLES:
                    source_table = source_tables[table_name]
                    destination_table = destination_tables[table_name]
                    source_rows = source_connection.execute(
                        select(source_table)
                    ).mappings()
                    while True:
                        rows = source_rows.fetchmany(500)
                        if not rows:
                            break
                        payload = [
                            normalize_row(table_name, dict(row))
                            for row in rows
                        ]
                        destination_connection.execute(
                            destination_table.insert(),
                            payload,
                        )

                for table_name in SEQUENCE_TABLES:
                    destination_connection.execute(
                        text(
                            "SELECT setval("
                            f"pg_get_serial_sequence('public.{table_name}', 'id'), "
                            f"COALESCE(MAX(id), 1), COUNT(*) > 0) "
                            f"FROM public.{table_name}"
                        )
                    )

                connection = destination_connection
                connection.execute(
                    text(
                        "UPDATE public.marketplace_source "
                        "SET access_method = 'api', permission_status = 'approved', "
                        "enabled = FALSE, next_run_at = NULL "
                        "WHERE source_key = 'facebook_marketplace'"
                    )
                )
                connection.execute(
                    text(
                        "UPDATE public.marketplace_source "
                        "SET access_method = 'authorized_web', "
                        "permission_status = 'approved', enabled = TRUE "
                        "WHERE source_key IN "
                        "('aae', 'enytinplus', 'jax', 'jiji', 'naijabargains')"
                    )
                )

                expected_sources = {
                    "aae",
                    "enytinplus",
                    "facebook_marketplace",
                    "jax",
                    "jiji",
                    "naijabargains",
                }
                actual_sources = set(
                    connection.execute(
                        text("SELECT source_key FROM public.marketplace_source")
                    ).scalars()
                )
                if actual_sources != expected_sources:
                    raise RuntimeError(
                        "The local database did not contain the six expected "
                        "source records; the copy was rolled back."
                    )

                enabled = connection.execute(
                    text(
                        "SELECT COUNT(*) FROM public.marketplace_source "
                        "WHERE enabled = TRUE"
                    )
                ).scalar_one()
                facebook_enabled = connection.execute(
                    text(
                        "SELECT enabled FROM public.marketplace_source "
                        "WHERE source_key = 'facebook_marketplace'"
                    )
                ).scalar_one()
                if enabled != 5 or facebook_enabled:
                    raise RuntimeError(
                        "Source configuration verification failed; the copy was rolled back."
                    )

                for table_name, expected_count in expected.items():
                    count = connection.execute(
                        text(f'SELECT COUNT(*) FROM public."{table_name}"')
                    ).scalar_one()
                    if count != expected_count:
                        raise RuntimeError(
                            f"Row count verification failed for {table_name}; "
                            "the copy was rolled back."
                        )

                price_types = connection.execute(
                    text(
                        "SELECT table_name, data_type "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "AND column_name = 'asking_price' "
                        "AND table_name IN ('listing', 'price_observation')"
                    )
                ).all()
                if len(price_types) != 2 or any(
                    data_type != "bigint" for _, data_type in price_types
                ):
                    raise RuntimeError(
                        "Wide price-column verification failed; the copy was rolled back."
                    )

                row_security = connection.execute(
                    text(
                        "SELECT relname FROM pg_class "
                        "JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace "
                        "WHERE nspname = 'public' AND relrowsecurity = TRUE"
                    )
                ).scalars()
                protected_tables = set(row_security)
                required_protected = set(APP_TABLES) | {"alembic_version"}
                if not required_protected.issubset(protected_tables):
                    raise RuntimeError(
                        "Row-level security verification failed; the copy was rolled back."
                    )

                for table_name, expected_count in expected.items():
                    final_count = connection.execute(
                        text(f'SELECT COUNT(*) FROM public."{table_name}"')
                    ).scalar_one()
                    if final_count != expected_count:
                        raise RuntimeError(
                            f"Final row count verification failed for {table_name}."
                        )
    finally:
        source_engine.dispose()


def main() -> int:
    if not LOCAL_DB.is_file():
        raise RuntimeError(
            f"Local database not found at {LOCAL_DB}. Run this from the project that contains your backend data."
        )
    python_executable = sys.executable
    if not (BACKEND_DIR / "alembic.ini").is_file():
        raise RuntimeError("The backend migration configuration could not be found.")

    raw_url = os.environ.get("DATABASE_URL", "")
    database_url = safe_database_url(raw_url)
    rendered_url = database_url.render_as_string(hide_password=False)
    destination_engine = create_engine(
        database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
    )

    try:
        with destination_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        ensure_destination_is_safe(destination_engine)

        with tempfile.TemporaryDirectory(prefix="marketpulse-supabase-") as temp_dir:
            snapshot_path = Path(temp_dir) / "local-snapshot.sqlite"
            counts = make_snapshot(snapshot_path)
            run_alembic(
                python_executable,
                "head",
                f"sqlite:///{snapshot_path.resolve().as_posix()}",
            )
            print("Local SQLite snapshot created and upgraded safely.")

            # Keep the database at revision 0006 until the scheduled worker applies migration 0007.
            run_alembic(python_executable, "20261116_0006", rendered_url)
            print("Supabase schema initialized through revision 20261116_0006.")

            with destination_engine.begin() as connection:
                for table_name in ("listing", "price_observation"):
                    connection.execute(
                        text(
                            f'ALTER TABLE public."{table_name}" '
                            'ALTER COLUMN asking_price TYPE BIGINT '
                            'USING asking_price::BIGINT'
                        )
                    )
                all_tables = (*APP_TABLES, "alembic_version")
                for table_name in all_tables:
                    connection.execute(
                        text(
                            f'ALTER TABLE public."{table_name}" '
                            "ENABLE ROW LEVEL SECURITY"
                        )
                    )
                connection.execute(
                    text(
                        "REVOKE ALL PRIVILEGES ON TABLE "
                        + ", ".join(
                            f'public."{table_name}"' for table_name in all_tables
                        )
                        + " FROM anon, authenticated"
                    )
                )

            copy_data(snapshot_path, destination_engine, counts)
            with destination_engine.connect() as connection:
                final_counts = {
                    table_name: connection.execute(
                        text(f'SELECT COUNT(*) FROM public."{table_name}"')
                    ).scalar_one()
                    for table_name in APP_TABLES
                }
                revision = connection.execute(
                    text("SELECT version_num FROM public.alembic_version")
                ).scalar_one()
            if revision != "20261116_0006":
                raise RuntimeError(
                    "The destination revision changed unexpectedly; please stop and contact support."
                )

            print("\nSupabase migration completed and verified.")
            print(f"Database schema revision: {revision}")
            for table_name in APP_TABLES:
                print(f"{table_name}: {final_counts[table_name]} rows")
            print("Source setup: 5 authorized web sources enabled; Facebook API approved and disabled.")
            print("Both price columns: bigint. Public API access: blocked by row-level security.")
            return 0
    finally:
        destination_engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"\nMigration stopped safely: {sanitized_output(str(error))}", file=sys.stderr)
        raise SystemExit(1)
