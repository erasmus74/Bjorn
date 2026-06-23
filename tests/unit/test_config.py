from pathlib import Path
import pytest
from mjolnir.config import BjornConfig, load_config


def test_load_config_defaults_from_minimal_file(tmp_path: Path):
    config_path = tmp_path / "empty.toml"
    config_path.write_text("")
    cfg = load_config(config_path)
    assert isinstance(cfg, BjornConfig)
    assert cfg.web.bind_interface == "127.0.0.1"
    assert cfg.web.port == 8000
    assert cfg.nlm.stage_pool_size == 4
    assert cfg.disk.warning_gb == 8


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
