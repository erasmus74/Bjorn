"""Repository objects for mjolnir DB tables."""
import sqlite3
from dataclasses import dataclass

from mjolnir.db.repositories.action_log import ActionLogRepository
from mjolnir.db.repositories.bssid_sightings import BssidSightingsRepository
from mjolnir.db.repositories.bssids import BssidsRepository
from mjolnir.db.repositories.networks import NetworksRepository
from mjolnir.db.repositories.stage_outputs import StageOutputsRepository
from mjolnir.db.repositories.stage_states import StageStatesRepository
from mjolnir.db.repositories.system_state import SystemStateRepository


@dataclass
class RepositoryBundle:
    """Bundle of all repositories sharing a single connection."""
    system_state: SystemStateRepository
    networks: NetworksRepository
    bssids: BssidsRepository
    bssid_sightings: BssidSightingsRepository
    stage_states: StageStatesRepository
    stage_outputs: StageOutputsRepository
    action_log: ActionLogRepository


def bundle_for(conn: sqlite3.Connection) -> RepositoryBundle:
    """Construct a RepositoryBundle over a single connection."""
    return RepositoryBundle(
        system_state=SystemStateRepository(conn),
        networks=NetworksRepository(conn),
        bssids=BssidsRepository(conn),
        bssid_sightings=BssidSightingsRepository(conn),
        stage_states=StageStatesRepository(conn),
        stage_outputs=StageOutputsRepository(conn),
        action_log=ActionLogRepository(conn),
    )
