"""Typed configuration loader for mjolnir."""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PathsConfig:
    data_dir: Path = Path("/var/lib/mjolnir")
    log_dir: Path = Path("/var/log/mjolnir")


@dataclass(frozen=True)
class DbConfig:
    filename: str = "mjolnir.db"
    wal_checkpoint_interval_seconds: int = 3600
    path: Path = Path("/var/lib/mjolnir/mjolnir.db")


@dataclass(frozen=True)
class WebConfig:
    bind_interface: str = "127.0.0.1"
    port: int = 8000
    require_auth: bool = False


@dataclass(frozen=True)
class NlmConfig:
    scan_interval_seconds: int = 30
    stage_pool_size: int = 4
    stage_memory_limit_mb: int = 25


@dataclass(frozen=True)
class DiskConfig:
    warning_gb: int = 8
    hard_stop_gb: int = 16


@dataclass(frozen=True)
class BjornConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    db: DbConfig = field(default_factory=DbConfig)
    web: WebConfig = field(default_factory=WebConfig)
    nlm: NlmConfig = field(default_factory=NlmConfig)
    disk: DiskConfig = field(default_factory=DiskConfig)


def load_config(path: Path) -> BjornConfig:
    """Load typed config from a TOML file. Missing file raises FileNotFoundError."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as f:
        raw = tomllib.load(f)

    paths_data = raw.get("paths", {})
    db_data = raw.get("db", {})
    web_data = raw.get("web", {})
    nlm_data = raw.get("nlm", {})
    disk_data = raw.get("disk", {})

    paths = PathsConfig(
        data_dir=Path(paths_data.get("data_dir", "/var/lib/mjolnir")),
        log_dir=Path(paths_data.get("log_dir", "/var/log/mjolnir")),
    )

    db = DbConfig(
        filename=db_data.get("filename", "mjolnir.db"),
        wal_checkpoint_interval_seconds=db_data.get("wal_checkpoint_interval_seconds", 3600),
        path=paths.data_dir / db_data.get("filename", "mjolnir.db"),
    )

    web = WebConfig(
        bind_interface=web_data.get("bind_interface", "127.0.0.1"),
        port=web_data.get("port", 8000),
        require_auth=web_data.get("require_auth", False),
    )

    nlm = NlmConfig(
        scan_interval_seconds=nlm_data.get("scan_interval_seconds", 30),
        stage_pool_size=nlm_data.get("stage_pool_size", 4),
        stage_memory_limit_mb=nlm_data.get("stage_memory_limit_mb", 25),
    )

    disk = DiskConfig(
        warning_gb=disk_data.get("warning_gb", 8),
        hard_stop_gb=disk_data.get("hard_stop_gb", 16),
    )

    return BjornConfig(paths=paths, db=db, web=web, nlm=nlm, disk=disk)
