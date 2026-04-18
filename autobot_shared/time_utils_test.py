"""Unit tests for autobot_shared.time_utils — see #5170.

Both helpers ship as production code with implicit format invariants;
these tests pin the invariants so future format changes fail loudly.
"""
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from autobot_shared.time_utils import utc_timestamp, utc_timestamp_z


_Z_FMT = "%Y-%m-%dT%H:%M:%SZ"


def test_utc_timestamp_format() -> None:
    s = utc_timestamp()
    assert s.endswith("+00:00")
    assert "T" in s
    parsed = datetime.fromisoformat(s)
    assert parsed.tzinfo is not None


def test_utc_timestamp_round_trip() -> None:
    s = utc_timestamp()
    parsed = datetime.fromisoformat(s)
    assert parsed.isoformat() == s


def test_utc_timestamp_is_utc_not_local() -> None:
    """Regression guard: must use timezone.utc, not naive or local time.

    If the implementation regresses to ``datetime.now()`` the result will
    be tz-naive and ``fromisoformat`` will return a naive datetime — caught
    by the tzinfo assertion. If it regresses to ``datetime.now(local_tz)``
    the offset will be non-zero — caught by the offset assertion.
    """
    s = utc_timestamp()
    parsed = datetime.fromisoformat(s)
    assert parsed.tzinfo is not None, f"expected aware datetime, got naive: {s}"
    assert parsed.utcoffset() == timedelta(0), (
        f"expected UTC offset 0, got {parsed.utcoffset()} from {s}"
    )
    assert s.endswith("+00:00"), f"expected +00:00 suffix (UTC), got: {s}"


def test_utc_timestamp_z_format() -> None:
    s = utc_timestamp_z()
    assert len(s) == 20, f"expected exactly 20 chars, got {len(s)}: {s!r}"
    assert s.endswith("Z")
    assert "T" in s
    assert "+" not in s
    datetime.strptime(s, _Z_FMT)


def test_utc_timestamp_z_no_microseconds() -> None:
    """The on-disk workflow_versioning format depends on no microseconds."""
    s = utc_timestamp_z()
    assert "." not in s, f"unexpected microseconds in: {s!r}"


def test_utc_timestamp_z_round_trip() -> None:
    s = utc_timestamp_z()
    parsed = datetime.strptime(s, _Z_FMT)
    assert parsed.strftime(_Z_FMT) == s


def test_utc_timestamp_z_is_utc_not_local() -> None:
    """Regression guard: must use time.gmtime, not time.localtime.

    Mocks both with distinguishable struct_time values so the test fails
    if the implementation switches to localtime, regardless of the host's
    actual timezone (CI may run in UTC, where a naive comparison would
    silently pass).
    """
    fake_utc = time.struct_time((2026, 4, 18, 12, 0, 0, 0, 0, 0))
    fake_local = time.struct_time((2026, 4, 18, 14, 30, 45, 0, 0, 0))

    with patch("autobot_shared.time_utils.time.gmtime", return_value=fake_utc), \
            patch("autobot_shared.time_utils.time.localtime", return_value=fake_local):
        result = utc_timestamp_z()

    assert result == "2026-04-18T12:00:00Z", (
        f"expected gmtime-derived string, got {result!r} — implementation may use localtime"
    )
    assert "14:30:45" not in result
