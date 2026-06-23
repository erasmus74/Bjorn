"""SQLite connection factory with mjolnir-standard PRAGMAs."""
import sqlite3
from pathlib import Path

_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-2000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
)

_SCHEMA_SQL_PATH = Path(__file__).parent / "schema.sql"


class ConnectionFactory:
    """Creates SQLite connections configured for mjolnir's workload."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,
            timeout=5.0,
        )
        conn.row_factory = sqlite3.Row
        for pragma in _PRAGMAS:
            conn.execute(pragma)
        return conn

    def apply_schema(self, conn: sqlite3.Connection) -> None:
        """Apply schema.sql to the connection. Idempotent (uses CREATE IF NOT EXISTS)."""
        sql = _SCHEMA_SQL_PATH.read_text()
        conn.executescript(sql)
