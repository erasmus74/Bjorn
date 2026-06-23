"""Repository for the action_log table (append-only audit trail)."""
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from mjolnir.utils import iso_timestamp


@dataclass
class ActionLogEntry:
    id: int | None
    timestamp: str
    global_mode: str
    scope_basis: str
    action_type: str
    stage_name: str | None = None
    target_network_id: int | None = None
    target_bssid: str | None = None
    target_host_id: int | None = None
    target_service_id: int | None = None
    outcome: str = "started"
    details_json: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ActionLogEntry":
        return cls(
            id=row["id"],
            timestamp=row["timestamp"],
            global_mode=row["global_mode"],
            scope_basis=row["scope_basis"],
            action_type=row["action_type"],
            stage_name=row["stage_name"],
            target_network_id=row["target_network_id"],
            target_bssid=row["target_bssid"],
            target_host_id=row["target_host_id"],
            target_service_id=row["target_service_id"],
            outcome=row["outcome"],
            details_json=row["details_json"],
        )


class ActionLogRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(
        self,
        global_mode: str,
        scope_basis: str,
        action_type: str,
        outcome: str = "started",
        stage_name: str | None = None,
        target_network_id: int | None = None,
        target_bssid: str | None = None,
        target_host_id: int | None = None,
        target_service_id: int | None = None,
        details: dict[str, Any] | None = None,
        when: str | None = None,
    ) -> ActionLogEntry:
        details_json = json.dumps(details) if details is not None else None
        timestamp = when or iso_timestamp()
        cursor = self.conn.execute(
            """
            INSERT INTO action_log (
                timestamp, global_mode, scope_basis, action_type, stage_name,
                target_network_id, target_bssid, target_host_id, target_service_id,
                outcome, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, global_mode, scope_basis, action_type, stage_name,
             target_network_id, target_bssid, target_host_id, target_service_id,
             outcome, details_json),
        )
        return ActionLogEntry(
            id=int(cursor.lastrowid),
            timestamp=timestamp,
            global_mode=global_mode,
            scope_basis=scope_basis,
            action_type=action_type,
            stage_name=stage_name,
            target_network_id=target_network_id,
            target_bssid=target_bssid,
            target_host_id=target_host_id,
            target_service_id=target_service_id,
            outcome=outcome,
            details_json=details_json,
        )

    def list_recent(self, limit: int = 50) -> list[ActionLogEntry]:
        cursor = self.conn.execute(
            """
            SELECT * FROM action_log
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [ActionLogEntry.from_row(r) for r in cursor.fetchall()]

    def list_for_network(self, network_id: int, limit: int = 100) -> list[ActionLogEntry]:
        cursor = self.conn.execute(
            """
            SELECT * FROM action_log
            WHERE target_network_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (network_id, limit),
        )
        return [ActionLogEntry.from_row(r) for r in cursor.fetchall()]

    def count_total(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM action_log")
        return int(cursor.fetchone()[0])
