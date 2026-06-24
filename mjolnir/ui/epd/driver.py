"""EPD driver abstraction.

EPDDriver is the protocol every display backend implements. Two impls:
  - FakeEPDDriver: records calls in memory; used in CI tests
  - RealEPDDriver: wraps v1's waveshare_epd library; used on Pi hardware
"""
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from PIL import Image


@runtime_checkable
class EPDDriver(Protocol):
    width: int
    height: int

    def init(self) -> None: ...

    def display(self, image: Image.Image) -> None: ...

    def clear(self) -> None: ...

    def sleep(self) -> None: ...


@dataclass
class FakeEPDDriver:
    """In-memory driver for tests. Records every call."""
    width: int
    height: int
    calls: list[str] = field(default_factory=list)
    last_image: Image.Image | None = None
    _initialized: bool = False

    def init(self) -> None:
        self.calls.append("init")
        self._initialized = True

    def display(self, image: Image.Image) -> None:
        if image.size != (self.width, self.height):
            raise ValueError(
                f"image size {image.size} does not match display {(self.width, self.height)}"
            )
        self.calls.append("display")
        self.last_image = image

    def clear(self) -> None:
        self.calls.append("clear")

    def sleep(self) -> None:
        self.calls.append("sleep")


class RealEPDDriver:
    """Wraps v1's waveshare_epd library. Only importable on Pi hardware.

    The waveshare_epd package is vendored at resources/waveshare_epd/.
    This driver is NOT exercised in CI (no hardware); tests use FakeEPDDriver.
    """

    def __init__(self, epd_type: str = "epd2in13_V4"):
        self._epd_type = epd_type
        self._epd = None
        self.width = 122
        self.height = 250

    def init(self) -> None:
        import importlib
        module = importlib.import_module(f"resources.waveshare_epd.{self._epd_type}")
        self._epd = module.EPD()
        self._epd.init(self._epd.FULL_UPDATE)
        self.width = self._epd.width
        self.height = self._epd.height

    def display(self, image: Image.Image) -> None:
        if self._epd is None:
            raise RuntimeError("init() not called")
        if image.size != (self.width, self.height):
            raise ValueError(
                f"image size {image.size} does not match display {(self.width, self.height)}"
            )
        self._epd.display(self._epd.getbuffer(image))

    def clear(self) -> None:
        if self._epd is None:
            raise RuntimeError("init() not called")
        self._epd.Clear()

    def sleep(self) -> None:
        if self._epd is None:
            raise RuntimeError("init() not called")
        self._epd.sleep()
