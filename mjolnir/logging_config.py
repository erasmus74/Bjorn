"""Structured logging setup for mjolnir.

JSON format in production (machine-parseable, ships to log aggregators).
Text format in development (human-readable). Configured via setup_logging()
called at daemon startup.
"""
import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge extra fields: anything in record.__dict__ not part of the
        # standard LogRecord attribute set.
        standard = set(vars(logging.LogRecord(
            "x", 0, "x", 0, "x", None, None
        )).keys())
        for key, value in vars(record).items():
            if key not in standard and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(format: str = "text", level: int = logging.INFO) -> logging.Logger:
    """Configure the root mjolnir logger. Returns it for chaining."""
    logger = logging.getLogger("mjolnir")
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    if format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
