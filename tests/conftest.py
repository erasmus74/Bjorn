"""Shared pytest fixtures."""
import sqlite3
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Per-test temp directory for filesystem state."""
    return tmp_path


@pytest.fixture
def fresh_db(temp_dir: Path) -> Iterator[sqlite3.Connection]:
    """A sqlite3 connection to a fresh in-temp-dir DB, schema applied."""
    from mjolnir.db.connection import ConnectionFactory
    factory = ConnectionFactory(db_path=temp_dir / "test.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    yield conn
    conn.close()
