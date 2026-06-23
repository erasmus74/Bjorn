import json
import pytest
from mjolnir.audit.logger import AuditLogger, ScopeBasis
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def logger(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    # Pre-seed networks so action_log FK constraints on target_network_id pass.
    # Networks are auto-incremented; capture IDs for tests that reference them.
    net1 = bundle.networks.create(ssid="seed-net-1")
    for _ in range(40):
        bundle.networks.create(ssid="filler")
    net42 = bundle.networks.create(ssid="seed-net-42")
    assert net1.id == 1
    assert net42.id == 42
    return AuditLogger(action_log=bundle.action_log, system_state=bundle.system_state)


def test_log_offensive_started_writes_row(logger):
    logger.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE,
        action_type="ssh_brute.started",
        stage_name="credential_attack",
        target_network_id=1,
        outcome="started",
        details={"wordlist": "rockyou.txt"},
    )
    rows = logger.action_log.list_recent(limit=1)
    assert len(rows) == 1
    assert rows[0].action_type == "ssh_brute.started"
    assert rows[0].global_mode == "view_only"


def test_log_offensive_global_mode_captured_at_log_time(logger):
    logger.system_state.set_global_mode("active")
    logger.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE,
        action_type="x.started",
        outcome="started",
    )
    rows = logger.action_log.list_recent(limit=1)
    assert rows[0].global_mode == "active"


def test_scope_basis_enum_serializes_to_value(logger):
    logger.log_offensive_action(
        scope_basis=ScopeBasis.KILLED_BY_OPERATOR,
        action_type="y.failed",
        outcome="failed",
    )
    rows = logger.action_log.list_recent(limit=1)
    assert rows[0].scope_basis == "killed-by-operator"


def test_log_mode_transition(logger):
    logger.log_mode_transition(from_mode="view_only", to_mode="active",
                                scope_basis=ScopeBasis.OPERATOR_CONFIRMED_ACTIVE_MODE)
    rows = logger.action_log.list_recent(limit=1)
    assert rows[0].action_type == "mode_transition"
    details = json.loads(rows[0].details_json)
    assert details["from"] == "view_only"
    assert details["to"] == "active"


def test_network_authorized_scope_basis_appends_network_id(logger):
    logger.log_offensive_action(
        scope_basis=ScopeBasis.OPERATOR_AUTHORIZED_NETWORK,
        action_type="z.started",
        target_network_id=42,
        outcome="started",
    )
    rows = logger.action_log.list_recent(limit=1)
    assert rows[0].scope_basis == "operator-authorized-network-N42"
