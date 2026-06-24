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
    data_dir: Path = Path("/var/lib/mjolnir")
    path: Path = field(default=Path("/var/lib/mjolnir/mjolnir.db"), init=False)

    def __post_init__(self):
        object.__setattr__(self, "path", self.data_dir / self.filename)


@dataclass(frozen=True)
class WebConfig:
    bind_interface: str = "127.0.0.1"
    port: int = 8000
    require_auth: bool = False


@dataclass(frozen=True)
class NlmConfig:
    scan_interval_seconds: int = 30
    stage_pool_size: int = 4
    stage_memory_limit_mb: int = 128


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
        data_dir=Path(paths_data["data_dir"]) if "data_dir" in paths_data else PathsConfig().data_dir,
        log_dir=Path(paths_data["log_dir"]) if "log_dir" in paths_data else PathsConfig().log_dir,
    )

    filename = db_data.get("filename", "mjolnir.db")
    filename_path = Path(filename)
    if filename_path.is_absolute() or len(filename_path.parents) > 1:
        raise ValueError(
            f"db.filename must be a bare filename (no path components): {filename!r}"
        )

    db = DbConfig(**db_data, data_dir=paths.data_dir)

    web = WebConfig(**web_data)
    nlm = NlmConfig(**nlm_data)
    disk = DiskConfig(**disk_data)

    return BjornConfig(paths=paths, db=db, web=web, nlm=nlm, disk=disk)
