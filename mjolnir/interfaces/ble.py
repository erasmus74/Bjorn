"""BLEInterface: stub for future BLE recon/attack work."""
from dataclasses import dataclass


@dataclass
class BLEInterface:
    """Placeholder. Methods raise NotImplementedError."""
    adapter: str = "hci0"

    def scan(self):
        raise NotImplementedError("BLEInterface not implemented")
