"""BluetoothInterface: stub for sub-project #1 (BT tether)."""
from dataclasses import dataclass


@dataclass
class BluetoothInterface:
    """Placeholder. Methods raise NotImplementedError until sub-project #1."""
    adapter: str = "hci0"

    def scan(self):
        raise NotImplementedError("BluetoothInterface not implemented until sub-project #1")
