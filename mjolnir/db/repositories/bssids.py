"""Repository for the bssids table."""
import sqlite3
from dataclasses import dataclass

from mjolnir.utils import iso_timestamp


@dataclass
class Bssid:
    id: int | None
    network_id: int
    bssid: str
    security_type: str | None
    channel: int | None
    last_signal_dbm: int | None
    first_seen: str
    last_seen: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Bssid":
        return cls(
            id=row["id"],
            network_id=row["network_id"],
            bssid=row["bssid"],
            security_type=row["security_type"],
            channel=row["channel"],
            last_signal_dbm=row["last_signal_dbm"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )


class BssidsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, network_id: int, bssid: str,
               security_type: str | None = None,
               channel: int | None = None,
               signal_dbm: int | None = None) -> Bssid:
        when = iso_timestamp()
        self.conn.execute(
            """
            INSERT INTO bssids (network_id, bssid, security_type, channel,
                                last_signal_dbm, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bssid) DO UPDATE SET
                last_signal_dbm = excluded.last_signal_dbm,
                channel = COALESCE(excluded.channel, bssids.channel),
                security_type = COALESCE(excluded.security_type, bssids.security_type),
                last_seen = excluded.last_seen
            """,
            (network_id, bssid, security_type, channel, signal_dbm, when, when),
        )
        return self.get_by_bssid(bssid)

    def get_by_bssid(self, bssid: str) -> Bssid | None:
        cursor = self.conn.execute(
            "SELECT * FROM bssids WHERE bssid = ?", (bssid,)
        )
        row = cursor.fetchone()
        return Bssid.from_row(row) if row else None

    def list_for_network(self, network_id: int) -> list[Bssid]:
        cursor = self.conn.execute(
            "SELECT * FROM bssids WHERE network_id = ? ORDER BY last_seen DESC",
            (network_id,),
        )
        return [Bssid.from_row(r) for r in cursor.fetchall()]

    def find_by_bssid_set(self, bssids: set[str]) -> list[Bssid]:
        if not bssids:
            return []
        placeholders = ",".join("?" * len(bssids))
        cursor = self.conn.execute(
            f"SELECT * FROM bssids WHERE bssid IN ({placeholders})",
            tuple(bssids),
        )
        return [Bssid.from_row(r) for r in cursor.fetchall()]
