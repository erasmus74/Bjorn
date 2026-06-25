"""Tests for structured logging setup."""
import json
import logging

import pytest

from mjolnir.logging_config import setup_logging


def test_setup_logging_json_format(capsys):
    logger = setup_logging(format="json", level=logging.INFO)
    logger.info("test message", extra={"event": "test_event"})

    output = capsys.readouterr().err.strip()
    record = json.loads(output)
    assert record["message"] == "test message"
    assert record["event"] == "test_event"
    assert "timestamp" in record


def test_setup_logging_text_format(capsys):
    logger = setup_logging(format="text", level=logging.INFO)
    logger.info("hello")

    output = capsys.readouterr().err
    assert "hello" in output
    assert "INFO" in output


def test_setup_logging_respects_level():
    logger = setup_logging(format="text", level=logging.WARNING)
    assert logger.level == logging.WARNING
