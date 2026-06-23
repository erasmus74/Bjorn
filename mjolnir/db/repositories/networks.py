"""Repository for the networks table."""
import sqlite3
from dataclasses import dataclass

from mjolnir.utils import iso_timestamp


@dataclass
class Network:
    id: int | None
    ssid: str
    disambiguator: int
    security_type: str | None
    scope_state: str
    blocklist_reason: str | None
    scope_changed_at: str | None
    scope_changed_by: str | None
    current_stage: str | None
    exhausted: int
    exhausted_reason: str | None
    persistence_authorized: int
    persistence_authorized_at: str | None
    persistence_authorized_by: str | None
    operator_notes_summary: str | None
    ess_color_tag: str | None
    first_seen: str
    last_seen: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Network":
        return cls(
            id=row["id"],
            ssid=row["ssid"],
            disambiguator=row["disambiguator"],
            security_type=row["security_type"],
            scope_state=row["scope_state"],
            blocklist_reason=row["blocklist_reason"],
            scope_changed_at=row["scope_changed_at"],
            scope_changed_by=row["scope_changed_by"],
            current_stage=row["current_stage"],
            exhausted=row["exhausted"],
            exhausted_reason=row["exhausted_reason"],
            persistence_authorized=row["persistence_authorized"],
            persistence_authorized_at=row["persistence_authorized_at"],
            persistence_authorized_by=row["persistence_authorized_by"],
            operator_notes_summary=row["operator_notes_summary"],
            ess_color_tag=row["ess_color_tag"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )


class NetworksRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, ssid: str, security_type: str | None = None,
               first_seen: str | None = None) -> Network:
        when = first_seen or iso_timestamp()
        disambiguator = self._next_disambiguator(ssid)
        cursor = self.conn.execute(
            """
            INSERT INTO networks (ssid, disambiguator, security_type, first_seen)
            VALUES (?, ?, ?, ?)
            """,
            (ssid, disambiguator, security_type, when),
        )
        net_id = cursor.lastrowid
        return self.get_by_id(net_id)

    def _next_disambiguator(self, ssid: str) -> int:
        cursor = self.conn.execute(
            "SELECT MAX(disambiguator) AS m FROM networks WHERE ssid = ?", (ssid,)
        )
        row = cursor.fetchone()
        if row["m"] is None:
            return 1
        return int(row["m"]) + 1

    def get_by_id(self, network_id: int) -> Network | None:
        cursor = self.conn.execute(
            "SELECT * FROM networks WHERE id = ?", (network_id,)
        )
        row = cursor.fetchone()
        return Network.from_row(row) if row else None

    def find_by_ssid(self, ssid: str) -> list[Network]:
        cursor = self.conn.execute(
            "SELECT * FROM networks WHERE ssid = ? ORDER BY disambiguator",
            (ssid,),
        )
        return [Network.from_row(r) for r in cursor.fetchall()]

    def update_scope_state(self, network_id: int, state: str,
                           reason: str | None = None, by: str | None = None) -> None:
        self.conn.execute(
            """
            UPDATE networks
            SET scope_state = ?, blocklist_reason = ?,
                scope_changed_at = ?, scope_changed_by = ?
            WHERE id = ?
            """,
            (state, reason, iso_timestamp(), by, network_id),
        )

    def mark_exhausted(self, network_id: int, reason: str) -> None:
        self.conn.execute(
            "UPDATE networks SET exhausted = 1, exhausted_reason = ? WHERE id = ?",
            (reason, network_id),
        )

    def update_last_seen(self, network_id: int, when: str | None = None) -> None:
        self.conn.execute(
            "UPDATE networks SET last_seen = ? WHERE id = ?",
            (when or iso_timestamp(), network_id),
        )

    def set_current_stage(self, network_id: int, stage_name: str | None) -> None:
        self.conn.execute(
            "UPDATE networks SET current_stage = ? WHERE id = ?",
            (stage_name, network_id),
        )

    def authorize_persistence(self, network_id: int, by: str) -> None:
        self.conn.execute(
            """
            UPDATE networks
            SET persistence_authorized = 1,
                persistence_authorized_at = ?,
                persistence_authorized_by = ?
            WHERE id = ?
            """,
            (iso_timestamp(), by, network_id),
        )

    def revoke_persistence_authorization(self, network_id: int) -> None:
        self.conn.execute(
            """
            UPDATE networks
            SET persistence_authorized = 0,
                persistence_authorized_at = NULL,
                persistence_authorized_by = NULL
            WHERE id = ?
            """,
            (network_id,),
        )

    def list_eligible_for_processing(self) -> list[Network]:
        cursor = self.conn.execute(
            """
            SELECT * FROM networks
            WHERE scope_state = 'enabled' AND exhausted = 0
            ORDER BY last_seen DESC
            """
        )
        return [Network.from_row(r) for r in cursor.fetchall()]
