from pathlib import Path
import pytest
from mjolnir.config import BjornConfig, DbConfig, PathsConfig, load_config


def test_load_config_defaults_from_minimal_file(tmp_path: Path):
    config_path = tmp_path / "empty.toml"
    config_path.write_text("")
    cfg = load_config(config_path)
    assert isinstance(cfg, BjornConfig)
    assert cfg.web.bind_interface == "127.0.0.1"
    assert cfg.web.port == 8000
    assert cfg.nlm.stage_pool_size == 4
    assert cfg.disk.warning_gb == 8


def test_default_stage_memory_limit_exceeds_daemon_resident_footprint(tmp_path: Path):
    """A stage runs in a forked child that inherits the daemon's full VM
    mapping. With Flask resident the parent VmSize is ~208 MB on a Pi Zero
    2W, so an RLIMIT_AS below that kills the child before it does any work
    (the daemon then discovers nothing). The default must clear that
    footprint with headroom. Measured on hardware: 128 MB failed, 256 MB
    worked. See Bug D / ACCEPTANCE-RUNBOOK."""
    config_path = tmp_path / "empty.toml"
    config_path.write_text("")
    cfg = load_config(config_path)
    assert cfg.nlm.stage_memory_limit_mb >= 256


def test_load_config_overrides(tmp_path: Path):
    config_path = tmp_path / "custom.toml"
    config_path.write_text("""
[web]
bind_interface = "tailscale0"
port = 9000

[nlm]
stage_pool_size = 2
""")
    cfg = load_config(config_path)
    assert cfg.web.bind_interface == "tailscale0"
    assert cfg.web.port == 9000
    assert cfg.nlm.stage_pool_size == 2


def test_load_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.toml")


def test_db_path_resolves_against_data_dir(tmp_path: Path):
    config_path = tmp_path / "c.toml"
    config_path.write_text("""
[paths]
data_dir = "/opt/mjolnir/data"
""")
    cfg = load_config(config_path)
    assert cfg.db.path == Path("/opt/mjolnir/data/mjolnir.db")


def test_dbconfig_default_path_matches_data_dir_default():
    cfg = DbConfig(data_dir=PathsConfig().data_dir)
    assert cfg.path == Path("/var/lib/mjolnir/mjolnir.db")


def test_dbconfig_path_follows_custom_data_dir():
    cfg = DbConfig(data_dir=Path("/opt/data"))
    assert cfg.path == Path("/opt/data/mjolnir.db")


def test_dbconfig_path_with_custom_filename(tmp_path: Path):
    cfg = DbConfig(filename="custom.db", data_dir=tmp_path)
    assert cfg.path == tmp_path / "custom.db"


def test_load_config_rejects_absolute_filename(tmp_path: Path):
    config_path = tmp_path / "bad.toml"
    config_path.write_text("""
[db]
filename = "/etc/passwd"
""")
    with pytest.raises(ValueError, match="bare filename"):
        load_config(config_path)


def test_load_config_rejects_filename_with_directory(tmp_path: Path):
    config_path = tmp_path / "bad.toml"
    config_path.write_text("""
[db]
filename = "subdir/x.db"
""")
    with pytest.raises(ValueError, match="bare filename"):
        load_config(config_path)
