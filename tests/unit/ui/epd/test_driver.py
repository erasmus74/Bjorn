"""Tests for the EPD driver protocol + Fake implementation."""
import pytest
from PIL import Image

from mjolnir.ui.epd.driver import FakeEPDDriver, EPDDriver


def test_fake_driver_is_an_epd_driver():
    fake = FakeEPDDriver(width=122, height=250)
    assert isinstance(fake, EPDDriver)


def test_fake_driver_init_records_call():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    assert fake.calls == ["init"]


def test_fake_driver_display_records_image():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    img = Image.new("1", (122, 250), 255)
    fake.display(img)
    assert fake.last_image is img
    assert "display" in fake.calls


def test_fake_driver_clear_records_call():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    fake.clear()
    assert "clear" in fake.calls


def test_fake_driver_sleep_records_call():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    fake.sleep()
    assert "sleep" in fake.calls


def test_fake_driver_dimensions():
    fake = FakeEPDDriver(width=122, height=250)
    assert fake.width == 122
    assert fake.height == 250


def test_fake_driver_rejects_wrong_size_image():
    fake = FakeEPDDriver(width=122, height=250)
    fake.init()
    wrong_size = Image.new("1", (100, 100), 255)
    with pytest.raises(ValueError, match="size"):
        fake.display(wrong_size)
