"""Small utility helpers used across mjolnir."""
from datetime import datetime, timezone


def iso_timestamp(when: datetime | None = None) -> str:
    """Return an ISO-8601 UTC timestamp string with second precision.

    Format: YYYY-MM-DDTHH:MM:SSZ  (lexicographically sortable).
    """
    if when is None:
        when = datetime.now(timezone.utc)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
