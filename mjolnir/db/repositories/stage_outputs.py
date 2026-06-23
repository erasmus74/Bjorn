"""Repository for the stage_outputs table."""
import sqlite3

from mjolnir.utils import iso_timestamp


class StageOutputsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def set(self, network_id: int, stage_name: str, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO stage_outputs (network_id, stage_name, output_key, output_value, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(network_id, stage_name, output_key) DO UPDATE SET
                output_value = excluded.output_value,
                recorded_at = excluded.recorded_at
            """,
            (network_id, stage_name, key, value, iso_timestamp()),
        )

    def set_many(self, network_id: int, stage_name: str, items: dict[str, str]) -> None:
        when = iso_timestamp()
        rows = [(network_id, stage_name, k, v, when) for k, v in items.items()]
        self.conn.executemany(
            """
            INSERT INTO stage_outputs (network_id, stage_name, output_key, output_value, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(network_id, stage_name, output_key) DO UPDATE SET
                output_value = excluded.output_value,
                recorded_at = excluded.recorded_at
            """,
            rows,
        )

    def get(self, network_id: int, stage_name: str, key: str) -> str | None:
        cursor = self.conn.execute(
            """
            SELECT output_value FROM stage_outputs
            WHERE network_id = ? AND stage_name = ? AND output_key = ?
            """,
            (network_id, stage_name, key),
        )
        row = cursor.fetchone()
        return row["output_value"] if row else None

    def list_for_stage(self, network_id: int, stage_name: str) -> dict[str, str]:
        cursor = self.conn.execute(
            """
            SELECT output_key, output_value FROM stage_outputs
            WHERE network_id = ? AND stage_name = ?
            """,
            (network_id, stage_name),
        )
        return {row["output_key"]: row["output_value"] for row in cursor.fetchall()}
