import pytest
from mjolnir.interfaces.bluetooth import BluetoothInterface
from mjolnir.interfaces.ble import BLEInterface


def test_bluetooth_interface_exists():
    iface = BluetoothInterface(adapter="hci0")
    assert iface.adapter == "hci0"


def test_bluetooth_interface_scan_raises_not_implemented():
    iface = BluetoothInterface(adapter="hci0")
    with pytest.raises(NotImplementedError):
        iface.scan()


def test_ble_interface_exists():
    iface = BLEInterface(adapter="hci0")
    assert iface.adapter == "hci0"


def test_ble_interface_scan_raises_not_implemented():
    iface = BLEInterface(adapter="hci0")
    with pytest.raises(NotImplementedError):
        iface.scan()
