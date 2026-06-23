from datetime import datetime, timezone
from mjolnir.utils import iso_timestamp


def test_iso_timestamp_returns_utc_iso8601():
    fixed = datetime(2026, 6, 23, 13, 42, 0, tzinfo=timezone.utc)
    result = iso_timestamp(fixed)
    assert result == "2026-06-23T13:42:00Z"


def test_iso_timestamp_no_arg_uses_now():
    result = iso_timestamp()
    assert result.endswith("Z")
    assert len(result) == 20  # YYYY-MM-DDTHH:MM:SSZ
