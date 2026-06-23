"""InterfaceManager: single entry point for all hardware access.

Stages acquire interfaces through NetworkContext.interfaces. The kill
switch path calls halt_all_transmissions() which propagates to every
interface that may be transmitting.
"""
from dataclasses import dataclass, field

from mjolnir.interfaces.ble import BLEInterface
from mjolnir.interfaces.bluetooth import BluetoothInterface
from mjolnir.interfaces.wifi import WiFiInterface


@dataclass
class InterfaceManager:
    """Owns all hardware interfaces. Constructed once at startup."""
    wifi_ifname: str = "wlan0"
    bt_adapter: str = "hci0"
    ble_adapter: str = "hci0"
    _wifi: WiFiInterface | None = field(default=None, repr=False)
    _bluetooth: BluetoothInterface | None = field(default=None, repr=False)
    _ble: BLEInterface | None = field(default=None, repr=False)

    @property
    def wifi(self) -> WiFiInterface:
        if self._wifi is None:
            self._wifi = WiFiInterface(ifname=self.wifi_ifname)
        return self._wifi

    @property
    def bluetooth(self) -> BluetoothInterface:
        if self._bluetooth is None:
            self._bluetooth = BluetoothInterface(adapter=self.bt_adapter)
        return self._bluetooth

    @property
    def ble(self) -> BLEInterface:
        if self._ble is None:
            self._ble = BLEInterface(adapter=self.ble_adapter)
        return self._ble

    def halt_all_transmissions(self) -> None:
        """Kill-switch path. Propagates to every interface that supports halting.

        Each interface's halt_transmissions() must be safe to call when no
        transmission is in progress (no-op).
        """
        for iface in (self.wifi, self.bluetooth, self.ble):
            halt = getattr(iface, "halt_transmissions", None)
            if halt is not None:
                halt()
