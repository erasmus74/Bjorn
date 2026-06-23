import pytest
from mjolnir.interfaces.manager import InterfaceManager
from mjolnir.interfaces.wifi import WiFiInterface
from mjolnir.interfaces.bluetooth import BluetoothInterface
from mjolnir.interfaces.ble import BLEInterface


def test_interface_manager_constructs_default_interfaces():
    mgr = InterfaceManager()
    assert isinstance(mgr.wifi, WiFiInterface)
    assert isinstance(mgr.bluetooth, BluetoothInterface)
    assert isinstance(mgr.ble, BLEInterface)


def test_interface_manager_wifi_ifname_configurable():
    mgr = InterfaceManager(wifi_ifname="wlan1")
    assert mgr.wifi.ifname == "wlan1"


def test_interface_manager_halt_all_transmissions_noop_when_idle():
    """No active transmissions → halt is a no-op."""
    mgr = InterfaceManager()
    mgr.halt_all_transmissions()  # must not raise


def test_interface_manager_halt_all_transmissions_calls_wifi_halt(monkeypatch):
    """When WiFi is transmitting, halt propagates."""
    mgr = InterfaceManager()
    called = {"halted": False}

    def fake_halt(self):
        called["halted"] = True

    monkeypatch.setattr(WiFiInterface, "halt_transmissions", fake_halt, raising=False)
    mgr.halt_all_transmissions()
    assert called["halted"]


def test_interface_manager_wifi_property_returns_same_instance():
    mgr = InterfaceManager()
    w1 = mgr.wifi
    w2 = mgr.wifi
    assert w1 is w2
