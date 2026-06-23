"""Repository for the bssid_sightings table."""
import sqlite3
from dataclasses import dataclass

from mjolnir.utils import iso_timestamp


@dataclass
class BssidSighting:
    id: int
    bssid_id: int
    seen_at: str
    signal_dbm: int | None
    channel: int | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "BssidSighting":
        return cls(
            id=row["id"],
            bssid_id=row["bssid_id"],
            seen_at=row["seen_at"],
            signal_dbm=row["signal_dbm"],
            channel=row["channel"],
        )


class BssidSightingsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(self, bssid_id: int,
               signal_dbm: int | None = None,
               channel: int | None = None,
               when: str | None = None) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO bssid_sightings (bssid_id, seen_at, signal_dbm, channel)
            VALUES (?, ?, ?, ?)
            """,
            (bssid_id, when or iso_timestamp(), signal_dbm, channel),
        )
        return int(cursor.lastrowid)

    def list_for_bssid(self, bssid_id: int, limit: int = 100) -> list[BssidSighting]:
        cursor = self.conn.execute(
            """
            SELECT * FROM bssid_sightings
            WHERE bssid_id = ?
            ORDER BY seen_at DESC
            LIMIT ?
            """,
            (bssid_id, limit),
        )
        return [BssidSighting.from_row(r) for r in cursor.fetchall()]

    def count_for_bssid(self, bssid_id: int) -> int:
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM bssid_sightings WHERE bssid_id = ?",
            (bssid_id,),
        )
        return int(cursor.fetchone()[0])
