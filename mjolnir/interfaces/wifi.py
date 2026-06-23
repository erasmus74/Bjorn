"""WiFiInterface: passive scan via `iw dev <ifname> scan`.

The parser is a pure function (parse_iw_scan_output) so it can be tested
without actually running `iw`. The WiFiInterface class is a thin shell
that invokes `iw` and feeds output to the parser.
"""
import re
import subprocess
from dataclasses import dataclass

from mjolnir.interfaces.types import BssidObservation, ScanResult
from mjolnir.utils import iso_timestamp

_BSS_HEADER_RE = re.compile(r"^BSS ([0-9a-fA-F:]{17})\s+on\s+\S+")
_SIGNAL_RE = re.compile(r"^\tsignal:\s+(-?\d+\.\d+)\s+dBm")
_CHAN_RE = re.compile(r"^\tchan:\s+(\d+)")
_SSID_LINE_RE = re.compile(r"^\t([^\t]+)$")
_PRIVACY_RE = re.compile(r"capabilities:.*Privacy")
_RSN_AUTH_PSK_RE = re.compile(r"Authentication suites:\s*PSK")
_RSN_AUTH_SAE_RE = re.compile(r"Authentication suites:\s*SAE")


def parse_iw_scan_output(output: str) -> list[BssidObservation]:
    """Parse `iw dev <if> scan` output into structured observations.

    Pure function — no I/O. Tests feed captured output.
    """
    observations: list[BssidObservation] = []
    current: dict | None = None
    when = iso_timestamp()

    for line in output.splitlines():
        bss_match = _BSS_HEADER_RE.match(line)
        if bss_match:
            if current is not None:
                observations.append(_finalize_observation(current, when))
            current = {
                "bssid": bss_match.group(1).lower(),
                "signal_dbm": None,
                "channel": None,
                "ssid": None,
                "has_privacy": False,
                "auth_psk": False,
                "auth_sae": False,
            }
            continue

        if current is None:
            continue

        signal_m = _SIGNAL_RE.match(line)
        if signal_m:
            current["signal_dbm"] = int(float(signal_m.group(1)))
            continue

        chan_m = _CHAN_RE.match(line)
        if chan_m:
            current["channel"] = int(chan_m.group(1))
            continue

        if _PRIVACY_RE.search(line):
            current["has_privacy"] = True
            continue

        if _RSN_AUTH_PSK_RE.search(line):
            current["auth_psk"] = True
            continue

        if _RSN_AUTH_SAE_RE.search(line):
            current["auth_sae"] = True
            continue

        ssid_m = _SSID_LINE_RE.match(line)
        if ssid_m and current["ssid"] is None:
            text = ssid_m.group(1).strip()
            # Exclude key:value lines (freq:, chan:, etc.) and capability blobs
            if text and ": " not in text and "capabilities:" not in text:
                current["ssid"] = text

    if current is not None:
        observations.append(_finalize_observation(current, when))

    return observations


def _finalize_observation(d: dict, when: str) -> BssidObservation:
    ssid = d.get("ssid") or ""
    if d.get("auth_sae"):
        sec = "WPA3"
    elif d.get("auth_psk"):
        sec = "WPA2"
    elif d.get("has_privacy"):
        sec = "WPA2"
    else:
        sec = "open"
    return BssidObservation(
        bssid=d["bssid"],
        ssid=ssid,
        signal_dbm=d["signal_dbm"] if d["signal_dbm"] is not None else -100,
        channel=d["channel"] or 0,
        security_type=sec,
        first_seen=when,
        last_seen=when,
    )


@dataclass
class WiFiInterface:
    """Passive WiFi interface wrapper. Calls `iw dev <ifname> scan`."""
    ifname: str

    def scan(self) -> ScanResult:
        result = subprocess.run(
            ["iw", "dev", self.ifname, "scan"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return ScanResult(observations=[], scanned_at=iso_timestamp())
        observations = parse_iw_scan_output(result.stdout)
        return ScanResult(observations=observations, scanned_at=iso_timestamp())

    def halt_transmissions(self) -> None:
        """Kill-switch hook. Passive scan mode has no transmissions to halt;
        future monitor-mode work (deauth, evil AP) will override."""
        return
