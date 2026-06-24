"""Tests for the conditions collector (DB → SystemConditions)."""
import pytest

from mjolnir.ui.epd.collector import collect_conditions
from mjolnir.ui.epd.states import DisplayState
from mjolnir.ui.epd.selector import StateSelector
from mjolnir.config import BjornConfig, DbConfig, PathsConfig
from mjolnir.db.connection import ConnectionFactory
from mjolnir.db.migrations import MigrationRunner
from mjolnir.db.repositories import bundle_for


@pytest.fixture
def bundle_and_path(tmp_path):
    factory = ConnectionFactory(db_path=tmp_path / "x.db")
    conn = factory.connect()
    factory.apply_schema(conn)
    MigrationRunner(conn).initialize_fresh_db()
    return bundle_for(conn), tmp_path / "x.db", conn


def test_collect_default_conditions(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    # Fresh DB: view_only mode, no kill switch, no networks visible
    assert conditions.global_mode == "view_only"
    assert conditions.kill_switch_engaged is False
    assert conditions.networks_visible is False  # no networks discovered yet
    conn.close()


def test_collect_reflects_active_mode(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    bundle.system_state.set_global_mode("active")
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert conditions.global_mode == "active"
    conn.close()


def test_collect_reflects_kill_switch(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    bundle.system_state.engage_kill_switch()
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert conditions.kill_switch_engaged is True
    conn.close()


def test_collect_detects_networks_present(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    bundle.networks.create(ssid="SomeNet", security_type="WPA2")
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert conditions.networks_visible is True
    conn.close()


def test_collect_detects_exhausted_networks(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    net = bundle.networks.create(ssid="DoneNet", security_type="WPA2")
    bundle.networks.mark_exhausted(net.id, "all_stages_succeeded")
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert ("DoneNet", "all_stages_succeeded") in conditions.exhausted_in_range
    conn.close()


def test_collect_detects_blocklisted_nearby(bundle_and_path):
    bundle, db_path, conn = bundle_and_path
    net = bundle.networks.create(ssid="MyHome", security_type="WPA2")
    bundle.networks.update_scope_state(net.id, "blocklisted", reason="home", by="op")
    conditions = collect_conditions(bundle, kill_switch_event_set=False)
    assert conditions.blocklisted_nearby is True
    conn.close()
