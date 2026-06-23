"""Stage ABC and supporting types.

The Stage ABC is the contract every capability plugs into. Concrete
stages register themselves via @registry.register.

See docs/superpowers/specs/2026-06-23-nlm-and-architecture-design.md § Stage ABC.
"""
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Literal


class InterfaceType(Enum):
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    BLE = "ble"


class CheckpointPolicy(Enum):
    RESTART_SAFE = "restart_safe"
    CHECKPOINTABLE = "checkpointable"


@dataclass
class ResourceProfile:
    interfaces: list[InterfaceType] = field(default_factory=list)
    is_rf_transmitting: bool = False
    cpu_weight: Literal["light", "medium", "heavy"] = "light"
    est_duration_seconds: int = 60


@dataclass
class StageResult:
    status: Literal["succeeded", "failed", "permanently_failed", "partial"]
    error: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    retry_after_seconds: int | None = None


@dataclass
class Checkpoint:
    """Cooperative cancellation token passed to Stage.run().

    Stages poll is_cancelled() at natural break points. The NLM sets
    cancel_reason when activating the kill switch.
    """
    _event: threading.Event = field(default_factory=threading.Event)
    cancel_reason: str | None = None

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self, reason: str = "killed") -> None:
        self.cancel_reason = reason
        self._event.set()

    def reset(self) -> None:
        self._event.clear()
        self.cancel_reason = None


@dataclass
class NetworkContext:
    """Passed to every stage invocation. The only way a stage touches the world."""
    network: Any
    db: Any
    config: Any
    interfaces: Any
    audit: Any
    workdir: Path
    checkpoint: Checkpoint


class Stage(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    resources: ClassVar[ResourceProfile]
    checkpoint_policy: ClassVar[CheckpointPolicy]
    operates_in_view_only: ClassVar[bool] = False
    requires_extra_auth: ClassVar[bool] = False

    @abstractmethod
    def can_run(self, ctx: NetworkContext) -> bool: ...

    @abstractmethod
    def run(self, ctx: NetworkContext, checkpoint: Checkpoint) -> StageResult: ...

    def resume_from_checkpoint(
        self, ctx: NetworkContext, checkpoint_data: dict[str, Any]
    ) -> StageResult | None:
        return None

    def on_interrupt(self, ctx: NetworkContext) -> None:
        return None
