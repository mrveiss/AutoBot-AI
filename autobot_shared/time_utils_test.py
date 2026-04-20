"""Unit tests for autobot_shared.time_utils — see #5170.

Both helpers ship as production code with implicit format invariants;
these tests pin the invariants so future format changes fail loudly.
"""
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from autobot_shared.time_utils import now_utc, utc_timestamp, utc_timestamp_z


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


# ---------------------------------------------------------------------------
# now_utc() — tz-aware datetime helper for #5211 Pattern E migration
# ---------------------------------------------------------------------------


def test_now_utc_returns_aware_datetime() -> None:
    dt = now_utc()
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None, f"now_utc() must return tz-aware datetime, got naive: {dt}"


def test_now_utc_offset_is_zero() -> None:
    """Offset must be exactly UTC, not local timezone."""
    dt = now_utc()
    assert dt.utcoffset() == timedelta(0), (
        f"expected UTC offset 0, got {dt.utcoffset()} — implementation may use local tz"
    )


def test_now_utc_close_to_real_now() -> None:
    """Returned datetime should be within a small window of actual current UTC."""
    dt = now_utc()
    real_now = datetime.now(timezone.utc)
    delta = abs((real_now - dt).total_seconds())
    assert delta < 2.0, f"now_utc() returned {dt} but actual now is {real_now}, delta={delta}s"


def test_now_utc_usable_as_default_factory() -> None:
    """Smoke test: the helper works as a dataclass field default_factory.

    This is the primary use case (Pattern E migration). If now_utc were
    something other than a callable returning a datetime, this would
    explode at class definition or instance construction time.
    """
    from dataclasses import dataclass, field

    @dataclass
    class _Sample:
        timestamp: datetime = field(default_factory=now_utc)

    instance = _Sample()
    assert isinstance(instance.timestamp, datetime)
    assert instance.timestamp.tzinfo is not None
    assert instance.timestamp.utcoffset() == timedelta(0)


def test_now_utc_round_trip_via_utc_timestamp() -> None:
    """now_utc() + utc_timestamp() agree on tz-awareness — same canonical UTC."""
    dt = now_utc()
    s = utc_timestamp()
    parsed = datetime.fromisoformat(s)
    # Both should be in UTC (offset 0)
    assert dt.utcoffset() == parsed.utcoffset() == timedelta(0)
