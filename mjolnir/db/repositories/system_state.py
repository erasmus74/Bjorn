"""Repository for the system_state key/value table."""
import sqlite3
from typing import Any

from mjolnir.utils import iso_timestamp


class SystemStateRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, key: str) -> str | None:
        cursor = self.conn.execute(
            "SELECT value FROM system_state WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: Any) -> None:
        self.conn.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, str(value), iso_timestamp()),
        )

    def get_global_mode(self) -> str:
        return self.get("global_mode") or "view_only"

    def set_global_mode(self, mode: str) -> None:
        if mode not in ("view_only", "active"):
            raise ValueError(f"invalid global mode: {mode!r} (must be 'view_only' or 'active')")
        self.set("global_mode", mode)

    def engage_kill_switch(self) -> None:
        self.set("kill_switch_engaged", iso_timestamp())

    def release_kill_switch(self) -> None:
        self.set("kill_switch_engaged", "")

    def is_kill_switch_engaged(self) -> bool:
        val = self.get("kill_switch_engaged")
        return val is not None and val != ""
