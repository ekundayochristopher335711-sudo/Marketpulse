import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from sqlalchemy.engine import URL


BACKEND_DIR = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def test_upgrade_preserves_legacy_listing_and_marks_sources_unapproved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy.sqlite"
            connection = sqlite3.connect(database_path)
            connection.execute(
                """
                CREATE TABLE listing (
                    id INTEGER NOT NULL PRIMARY KEY,
                    title VARCHAR NOT NULL,
                    category VARCHAR NOT NULL,
                    asking_price INTEGER NOT NULL,
                    location VARCHAR NOT NULL,
                    source_name VARCHAR NOT NULL,
                    source_url VARCHAR,
                    condition VARCHAR,
                    observed_at DATETIME NOT NULL,
                    is_demo BOOLEAN NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO listing
                    (id, title, category, asking_price, location, source_name,
                     observed_at, is_demo)
                VALUES (1, 'Legacy laptop', 'Computers', 250000, 'Lagos',
                        'Old source', '2026-11-15 12:00:00', 0)
                """
            )
            connection.commit()
            connection.close()

            environment = os.environ.copy()
            environment["DATABASE_URL"] = str(
                URL.create("sqlite", database=str(database_path))
            )
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=BACKEND_DIR,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            connection = sqlite3.connect(database_path)
            row = connection.execute(
                """
                SELECT title, source_id, normalized_title, first_discovered_at,
                       last_observed_at
                FROM listing WHERE id = 1
                """
            ).fetchone()
            sources = connection.execute(
                """
                SELECT COUNT(*), SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END)
                FROM marketplace_source
                """
            ).fetchone()
            revision = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            connection.close()

            self.assertEqual(row[0:3], ("Legacy laptop", "legacy", "Legacy laptop"))
            self.assertIsNotNone(row[3])
            self.assertIsNotNone(row[4])
            self.assertEqual(sources, (6, 0))
            self.assertEqual(revision[0], "20261123_0007")
