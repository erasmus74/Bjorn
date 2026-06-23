import pytest
from mjolnir.interfaces.wifi import WiFiInterface, parse_iw_scan_output


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
