"""Repository for the stage_states table."""
import sqlite3
from dataclasses import dataclass

from mjolnir.utils import iso_timestamp


@dataclass
class StageState:
    network_id: int
    stage_name: str
    status: str
    attempts: int
    last_attempt_at: str | None
    completed_at: str | None
    failure_reason: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "StageState":
        return cls(
            network_id=row["network_id"],
            stage_name=row["stage_name"],
            status=row["status"],
            attempts=row["attempts"],
            last_attempt_at=row["last_attempt_at"],
            completed_at=row["completed_at"],
            failure_reason=row["failure_reason"],
        )


class StageStatesRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_or_create(self, network_id: int, stage_name: str) -> StageState:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO stage_states (network_id, stage_name, status)
            VALUES (?, ?, 'pending')
            """,
            (network_id, stage_name),
        )
        cursor = self.conn.execute(
            "SELECT * FROM stage_states WHERE network_id = ? AND stage_name = ?",
            (network_id, stage_name),
        )
        return StageState.from_row(cursor.fetchone())

    def _update(self, network_id: int, stage_name: str,
                status: str, reason: str | None = None) -> None:
        if status == "running":
            self.conn.execute(
                """
                UPDATE stage_states
                SET status = ?, attempts = attempts + 1, last_attempt_at = ?,
                    failure_reason = NULL
                WHERE network_id = ? AND stage_name = ?
                """,
                (status, iso_timestamp(), network_id, stage_name),
            )
        elif status in ("succeeded", "permanently_failed"):
            self.conn.execute(
                """
                UPDATE stage_states
                SET status = ?, completed_at = ?, failure_reason = ?
                WHERE network_id = ? AND stage_name = ?
                """,
                (status, iso_timestamp(), reason, network_id, stage_name),
            )
        else:
            self.conn.execute(
                """
                UPDATE stage_states
                SET status = ?, failure_reason = ?
                WHERE network_id = ? AND stage_name = ?
                """,
                (status, reason, network_id, stage_name),
            )

    def mark_running(self, network_id: int, stage_name: str) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "running")

    def mark_succeeded(self, network_id: int, stage_name: str) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "succeeded")

    def mark_failed(self, network_id: int, stage_name: str, reason: str | None = None) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "failed", reason)

    def mark_permanently_failed(self, network_id: int, stage_name: str, reason: str | None = None) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "permanently_failed", reason)

    def mark_skipped(self, network_id: int, stage_name: str, reason: str | None = None) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "skipped", reason)

    def mark_pending(self, network_id: int, stage_name: str) -> None:
        self.get_or_create(network_id, stage_name)
        self._update(network_id, stage_name, "pending")

    def list_in_state(self, status: str) -> list[StageState]:
        cursor = self.conn.execute(
            "SELECT * FROM stage_states WHERE status = ?", (status,)
        )
        return [StageState.from_row(r) for r in cursor.fetchall()]
