"""DisplayManager: ties selector + renderer + driver together.

Polls system conditions (via a caller-provided SystemConditions), selects
the current state, renders it, and sends to the driver. Skips refresh
when state + overlay unchanged since last render (e-Paper wears out;
don't refresh needlessly).
"""
from dataclasses import dataclass

from mjolnir.ui.epd.driver import EPDDriver
from mjolnir.ui.epd.selector import StateSelector, SystemConditions
from mjolnir.ui.epd.states import DisplayState, render_state


@dataclass
class DisplayManager:
    driver: EPDDriver
    selector: StateSelector = None  # type: ignore[assignment]  # set in __post_init__
    current_state: DisplayState | None = None
    current_overlay: bool = False

    def __post_init__(self):
        if self.selector is None:
            self.selector = StateSelector()

    def update(self, conditions: SystemConditions) -> None:
        """Select state from conditions; render + display if changed."""
        state, overlay = self.selector.select(conditions)

        if state == self.current_state and overlay == self.current_overlay:
            return  # no change — skip refresh

        image = render_state(state, conditions, overlay=overlay)
        self.driver.display(image)
        self.current_state = state
        self.current_overlay = overlay

    def shutdown(self) -> None:
        """Clear the display and put the driver to sleep."""
        self.driver.clear()
        self.driver.sleep()
