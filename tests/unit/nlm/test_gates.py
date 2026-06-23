"""Tests for the data-availability GateEvaluator."""
import pytest

from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for
from mjolnir.nlm.gates import GateEvaluator, GateResult


@pytest.fixture
def evaluator_and_bundle(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    bundle = bundle_for(conn)
    return GateEvaluator(bundle), bundle


def test_passive_scan_gate_always_satisfied(evaluator_and_bundle):
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X")
    result = evaluator.evaluate(stage_name="passive_scan", network_id=net.id)
    assert result.satisfied is True


def test_unknown_stage_gate_fails_closed(evaluator_and_bundle):
    """Stages we don't know about get an 'unknown_stage' result — fail-closed
    is safer than fail-open."""
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X")
    result = evaluator.evaluate(stage_name="nonexistent_stage", network_id=net.id)
    assert result.satisfied is False
    assert "unknown" in result.reason.lower()


def test_wifi_probe_gate_requires_recent_last_seen(evaluator_and_bundle):
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X")
    # Network was just created so last_seen is recent — gate satisfied
    result = evaluator.evaluate(stage_name="wifi_probe", network_id=net.id)
    assert result.satisfied is True


def test_wifi_probe_gate_fails_when_stale(evaluator_and_bundle):
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X")
    # Set last_seen to a very old timestamp (well over the 5-minute threshold)
    bundle.networks.update_last_seen(net.id, "2020-01-01T00:00:00Z")
    result = evaluator.evaluate(stage_name="wifi_probe", network_id=net.id)
    assert result.satisfied is False
    assert "stale" in result.reason.lower()


def test_wifi_crack_gate_skipped_when_open(evaluator_and_bundle):
    """Open networks don't need cracking."""
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="OpenNet", security_type="open")
    result = evaluator.evaluate(stage_name="wifi_crack", network_id=net.id)
    assert result.satisfied is False
    assert "open" in result.reason.lower()


def test_wifi_crack_gate_skipped_when_already_cracked(evaluator_and_bundle):
    """If we already have a wifi_psk credential for this network, no need to crack."""
    evaluator, bundle = evaluator_and_bundle
    net = bundle.networks.create(ssid="X", security_type="WPA2")
    bundle.action_log.conn.execute(
        "INSERT INTO credentials (network_id, cred_type, secret, discovered_at) VALUES (?, ?, ?, ?)",
        (net.id, "wifi_psk", "somepassword", "2026-06-23T00:00:00Z"),
    )
    result = evaluator.evaluate(stage_name="wifi_crack", network_id=net.id)
    assert result.satisfied is False
    assert "already" in result.reason.lower()
