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

# Real `iw` emits the BSSID glued to the interface, e.g.
# `BSS 60:22:32:99:32:52(on wlan0) -- associated`, while older/synthetic
# samples use `BSS <mac> on wlan0`. Anchor only on the MAC so both parse.
_BSS_HEADER_RE = re.compile(r"^BSS ([0-9a-fA-F:]{17})")
_SIGNAL_RE = re.compile(r"^\tsignal:\s+(-?\d+\.\d+)\s+dBm")
# Channel: synthetic output uses `chan: N`; real `iw` reports it as part of
# the `DS Parameter set: channel N` information element.
_CHAN_RE = re.compile(r"^\tchan:\s+(\d+)")
_DS_CHAN_RE = re.compile(r"DS Parameter set: channel (\d+)")
# Real `iw` labels the SSID explicitly (`SSID: name`); the name itself may
# contain `: `, so this is parsed before the bare-line heuristic.
_SSID_KV_RE = re.compile(r"^\tSSID: (.*)$")
_SSID_LINE_RE = re.compile(r"^\t([^\t]+)$")
# `capability:` is singular in real `iw`; older samples used `capabilities:`.
_PRIVACY_RE = re.compile(r"capabilit(?:y|ies):.*Privacy")
# In real output the suites line lists multiple tokens, e.g.
# `Authentication suites: PSK SAE`, so search the whole line for each token.
_RSN_AUTH_PSK_RE = re.compile(r"Authentication suites:.*\bPSK\b")
_RSN_AUTH_SAE_RE = re.compile(r"Authentication suites:.*\bSAE\b")


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

        ds_chan_m = _DS_CHAN_RE.search(line)
        if ds_chan_m and not current["channel"]:
            current["channel"] = int(ds_chan_m.group(1))
            continue

        if _PRIVACY_RE.search(line):
            current["has_privacy"] = True
            continue

        # A single suites line may list both, e.g. `... suites: PSK SAE`.
        # Check both without short-circuiting so WPA3 (SAE) isn't masked
        # by WPA2 (PSK) appearing first on the same line.
        matched_auth = False
        if _RSN_AUTH_PSK_RE.search(line):
            current["auth_psk"] = True
            matched_auth = True
        if _RSN_AUTH_SAE_RE.search(line):
            current["auth_sae"] = True
            matched_auth = True
        if matched_auth:
            continue

        # Real `iw` tags the SSID explicitly. Take it verbatim (an empty
        # value means a hidden network broadcasting a blank SSID).
        ssid_kv_m = _SSID_KV_RE.match(line)
        if ssid_kv_m and current["ssid"] is None:
            current["ssid"] = ssid_kv_m.group(1)
            continue

        ssid_m = _SSID_LINE_RE.match(line)
        if ssid_m and current["ssid"] is None:
            text = ssid_m.group(1).strip()
            # Bare-line fallback for synthetic samples. Exclude key:value
            # lines (freq:, chan:, `Foo:` sub-headers) and capability blobs.
            if text and ": " not in text and not text.endswith(":") and "capabilities:" not in text:
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
