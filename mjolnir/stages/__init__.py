"""Stage framework: ABC, registry, supporting types."""
from mjolnir.stages.base import (
    Checkpoint,
    CheckpointPolicy,
    InterfaceType,
    NetworkContext,
    ResourceProfile,
    Stage,
    StageResult,
)
from mjolnir.stages.passive_scan import PassiveScanStage
from mjolnir.stages.registry import StageRegistry, registry

# Auto-register built-in stages so the NLM discovers them at import time.
registry.register(PassiveScanStage)

__all__ = [
    "Checkpoint",
    "CheckpointPolicy",
    "InterfaceType",
    "NetworkContext",
    "PassiveScanStage",
    "ResourceProfile",
    "Stage",
    "StageResult",
    "StageRegistry",
    "registry",
]
