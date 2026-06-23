"""Stage registry: tracks all Stage subclasses, provides filtering by mode."""
from mjolnir.stages.base import Stage


class StageRegistry:
    def __init__(self):
        self._stages: dict[str, type[Stage]] = {}

    def register(self, stage_cls: type[Stage]) -> type[Stage]:
        self._stages[stage_cls.name] = stage_cls
        return stage_cls

    def get(self, name: str) -> type[Stage] | None:
        return self._stages.get(name)

    def all_stages(self) -> list[type[Stage]]:
        return list(self._stages.values())

    def stages_eligible_for_mode(self, mode: str) -> list[type[Stage]]:
        if mode == "active":
            return self.all_stages()
        if mode == "view_only":
            return [s for s in self.all_stages() if s.operates_in_view_only]
        raise ValueError(f"unknown mode: {mode}")


registry = StageRegistry()
