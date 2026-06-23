"""Schema migrations for mjolnir.

Migrations are forward-only and versioned. Each migration is a callable
that takes a sqlite3.Connection. The current schema version is tracked
in system_state('schema_version').
"""
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mjolnir.utils import iso_timestamp

CURRENT_SCHEMA_VERSION = 1

_SCHEMA_SQL_PATH = Path(__file__).parent / "schema.sql"


@dataclass
class Migration:
    version: int
    description: str
    apply: Callable[[sqlite3.Connection], None]


# Future migrations will be appended here as the schema evolves. Example:
# def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
#     conn.execute("ALTER TABLE networks ADD COLUMN new_col TEXT")
#
# _MIGRATIONS: list[Migration] = [
#     Migration(version=2, description="add new_col", apply=_migrate_v1_to_v2),
# ]

_MIGRATIONS: list[Migration] = []


class MigrationRunner:
    """Applies pending migrations to bring DB up to CURRENT_SCHEMA_VERSION."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def initialize_fresh_db(self) -> None:
        """Apply schema and seed system_state defaults on a fresh DB. Idempotent."""
        # Schema is CREATE IF NOT EXISTS — safe to apply on every call.
        self.conn.executescript(_SCHEMA_SQL_PATH.read_text())
        defaults = [
            ("global_mode", "view_only"),
            ("kill_switch_engaged", ""),
            ("schema_version", str(CURRENT_SCHEMA_VERSION)),
        ]
        for key, value in defaults:
            self.conn.execute(
                """
                INSERT INTO system_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (key, value, iso_timestamp()),
            )

    def get_schema_version(self) -> int:
        cursor = self.conn.execute(
            "SELECT value FROM system_state WHERE key = 'schema_version'"
        )
        row = cursor.fetchone()
        if row is None:
            return 0
        return int(row["value"])

    def _set_schema_version(self, version: int) -> None:
        self.conn.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES ('schema_version', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (str(version), iso_timestamp()),
        )

    def run_pending_migrations(self) -> list[str]:
        """Apply all migrations newer than the current schema version. Returns descriptions."""
        current = self.get_schema_version()
        applied: list[str] = []
        for migration in sorted(_MIGRATIONS, key=lambda m: m.version):
            if migration.version <= current:
                continue
            self.conn.execute("BEGIN")
            try:
                migration.apply(self.conn)
                self._set_schema_version(migration.version)
                self.conn.execute("COMMIT")
                applied.append(migration.description)
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return applied
