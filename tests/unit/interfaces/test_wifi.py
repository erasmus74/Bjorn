from pathlib import Path

import pytest
from mjolnir.interfaces.wifi import WiFiInterface, parse_iw_scan_output


# Real `iw dev wlan0 scan` output captured from a Pi Zero 2W running DietPi
# (iw 6.x). The synthetic SAMPLE_IW_OUTPUT below does NOT match this format —
# real iw emits `BSS <mac>(on wlan0)`, `SSID: <name>`, and
# `DS Parameter set: channel N`, none of which the original parser handled.
# This fixture is the regression guard for that hardware-acceptance finding.
_REAL_FIXTURE = (
    Path(__file__).parent / "fixtures" / "iw_scan_dietpi_real.txt"
).read_text()

# Expected from the captured fixture (6 BSSIDs, one hidden).
_REAL_EXPECTED = {
    "60:22:32:99:32:52": {"ssid": "alwayschooselove", "channel": 11, "signal": -34, "security": "WPA3"},
    "48:a2:e6:d3:9f:86": {"ssid": "NewThermostat_D39F86", "channel": 1, "signal": -79, "security": "open"},
    "ac:8f:a9:56:d4:b4": {"ssid": "Babbler", "channel": 1, "signal": -76, "security": "WPA2"},
    "98:40:d4:0b:1c:aa": {"ssid": "freethetitty", "channel": 2, "signal": -59, "security": "WPA3"},
    "a8:97:cd:8b:2d:c0": {"ssid": "Satin's Wee Fee", "channel": 4, "signal": -68, "security": "WPA2"},
    "66:22:32:99:32:52": {"ssid": "", "channel": 11, "signal": -36, "security": "WPA2"},
}


def test_parse_real_iw_extracts_all_bssids():
    results = parse_iw_scan_output(_REAL_FIXTURE)
    bssids = {r.bssid for r in results}
    assert bssids == set(_REAL_EXPECTED.keys())


def test_parse_real_iw_extracts_ssids():
    results = {r.bssid: r for r in parse_iw_scan_output(_REAL_FIXTURE)}
    for bssid, expected in _REAL_EXPECTED.items():
        assert results[bssid].ssid == expected["ssid"], bssid


def test_parse_real_iw_hidden_network_has_empty_ssid():
    results = {r.bssid: r for r in parse_iw_scan_output(_REAL_FIXTURE)}
    assert results["66:22:32:99:32:52"].ssid == ""


def test_parse_real_iw_extracts_channels():
    results = {r.bssid: r for r in parse_iw_scan_output(_REAL_FIXTURE)}
    for bssid, expected in _REAL_EXPECTED.items():
        assert results[bssid].channel == expected["channel"], bssid


def test_parse_real_iw_extracts_signal():
    results = {r.bssid: r for r in parse_iw_scan_output(_REAL_FIXTURE)}
    for bssid, expected in _REAL_EXPECTED.items():
        assert results[bssid].signal_dbm == expected["signal"], bssid


def test_parse_real_iw_classifies_security():
    results = {r.bssid: r for r in parse_iw_scan_output(_REAL_FIXTURE)}
    for bssid, expected in _REAL_EXPECTED.items():
        assert results[bssid].security_type == expected["security"], bssid


SAMPLE_IW_OUTPUT = """
BSS aa:bb:cc:dd:ee:01 on wlan0	assoc:0
	freq: 2437
	chan: 6
	signal: -42.00 dBm
	last seen: 1000 ms ago
	Super Net
.capabilities:ESS Privacy SpectrumMgt ShortSlotTime
	RSN:	 * Version: 1
		 * Group cipher: CCMP
		 * Pairwise ciphers: CCMP
		 * Authentication suites: PSK
BSS aa:bb:cc:dd:ee:02 on wlan0	assoc:0
	freq: 5180
	chan: 36
	signal: -55.00 dBm
	last seen: 1000 ms ago
	Another Net
.capabilities:ESS Privacy SpectrumMgt ShortSlotTime
	RSN:	 * Version: 1
		 * Group cipher: CCMP
		 * Pairwise ciphers: CCMP
		 * Authentication suites: SAE
BSS aa:bb:cc:dd:ee:03 on wlan0	assoc:0
	freq: 2412
	chan: 1
	signal: -68.00 dBm
	last seen: 1000 ms ago
	Open Net
.capabilities:ESS ShortSlotTime
"""


def test_parse_iw_output_extracts_three_bssids():
    results = parse_iw_scan_output(SAMPLE_IW_OUTPUT)
    assert len(results) == 3


def test_parse_iw_output_extracts_bssid_mac():
    results = parse_iw_scan_output(SAMPLE_IW_OUTPUT)
    bssids = {r.bssid for r in results}
    assert "aa:bb:cc:dd:ee:01" in bssids
    assert "aa:bb:cc:dd:ee:02" in bssids
    assert "aa:bb:cc:dd:ee:03" in bssids


def test_parse_iw_output_extracts_signal_dbm():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:01"].signal_dbm == -42
    assert results["aa:bb:cc:dd:ee:02"].signal_dbm == -55


def test_parse_iw_output_extracts_channel():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:01"].channel == 6
    assert results["aa:bb:cc:dd:ee:02"].channel == 36


def test_parse_iw_output_extracts_ssid():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:01"].ssid == "Super Net"
    assert results["aa:bb:cc:dd:ee:03"].ssid == "Open Net"


def test_parse_iw_output_classifies_security_wpa2_psk():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:01"].security_type == "WPA2"


def test_parse_iw_output_classifies_security_wpa3_sae():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:02"].security_type == "WPA3"


def test_parse_iw_output_classifies_security_open():
    results = {r.bssid: r for r in parse_iw_scan_output(SAMPLE_IW_OUTPUT)}
    assert results["aa:bb:cc:dd:ee:03"].security_type == "open"


def test_parse_iw_output_empty_input():
    results = parse_iw_scan_output("")
    assert results == []


def test_parse_iw_output_handles_hidden_ssid():
    """AP with no SSID line — hidden network."""
    hidden_output = """
BSS aa:bb:cc:dd:ee:04 on wlan0
	freq: 2412
	chan: 1
	signal: -70.00 dBm
.capabilities:ESS Privacy
"""
    results = parse_iw_scan_output(hidden_output)
    assert len(results) == 1
    assert results[0].ssid == ""
    assert results[0].security_type == "WPA2"


def test_wifi_interface_constructor_requires_ifname():
    iface = WiFiInterface(ifname="wlan0")
    assert iface.ifname == "wlan0"


def test_wifi_interface_scan_calls_subprocess(monkeypatch, tmp_path):
    """scan() shells out to `iw`; we mock subprocess.run and verify the call."""
    captured = {}

    class FakeResult:
        stdout = SAMPLE_IW_OUTPUT
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeResult()

    import mjolnir.interfaces.wifi as wifi_mod
    monkeypatch.setattr(wifi_mod.subprocess, "run", fake_run)

    iface = WiFiInterface(ifname="wlan0")
    result = iface.scan()

    assert captured["cmd"] == ["iw", "dev", "wlan0", "scan"]
    assert len(result.observations) == 3
