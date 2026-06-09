# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for autobot_shared.time_utils — see #5170.

Both helpers ship as production code with implicit format invariants;
these tests pin the invariants so future format changes fail loudly.
"""

from datetime import datetime, timedelta, timezone

from autobot_shared.time_utils import (
    now_utc,
    parse_utc_iso,
    utc_timestamp,
)

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
    assert parsed.utcoffset() == timedelta(0), f"expected UTC offset 0, got {parsed.utcoffset()} from {s}"
    assert s.endswith("+00:00"), f"expected +00:00 suffix (UTC), got: {s}"


def test_now_utc_returns_aware_datetime() -> None:
    dt = now_utc()
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None, f"now_utc() must return tz-aware datetime, got naive: {dt}"


def test_now_utc_offset_is_zero() -> None:
    """Offset must be exactly UTC, not local timezone."""
    dt = now_utc()
    assert dt.utcoffset() == timedelta(
        0
    ), f"expected UTC offset 0, got {dt.utcoffset()} — implementation may use local tz"


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


# ---------------------------------------------------------------------------
# parse_utc_iso() — defensive parser for #5350 cutoff/since consumers
# ---------------------------------------------------------------------------


def test_parse_utc_iso_canonical_offset() -> None:
    """+00:00 form (canonical) round-trips and stays aware."""
    parsed = parse_utc_iso("2026-04-21T12:34:56.789012+00:00")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


def test_parse_utc_iso_z_suffix() -> None:
    """Z suffix (legacy) is accepted and becomes aware UTC."""
    parsed = parse_utc_iso("2026-04-21T12:34:56Z")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


def test_parse_utc_iso_naive_string_assumed_utc() -> None:
    """Naive input (no offset/suffix) is tagged as UTC — prevents TypeError vs aware."""
    parsed = parse_utc_iso("2026-04-21T12:34:56")
    assert parsed.tzinfo is not None, "naive input must be promoted to aware"
    assert parsed.utcoffset() == timedelta(0)


def test_parse_utc_iso_comparable_with_now_utc() -> None:
    """The whole point: parsed value compares cleanly against now_utc() — no TypeError."""
    parsed = parse_utc_iso("2026-04-21T12:34:56")  # naive input
    cutoff = now_utc()
    # Must not raise TypeError: can't compare offset-naive and offset-aware datetimes
    assert (parsed < cutoff) or (parsed >= cutoff)


def test_parse_utc_iso_invalid_raises() -> None:
    """Malformed input raises ValueError (caller handles)."""
    import pytest

    with pytest.raises(ValueError):
        parse_utc_iso("not-a-date")


def test_parse_utc_iso_non_string_raises_value_error() -> None:
    """#5464: non-str input raises ValueError — NOT AttributeError.

    Pre-#5464, ``parse_utc_iso(123)`` raised ``AttributeError`` from the
    inner ``.replace()`` call, escaping the common
    ``except (ValueError, TypeError)`` adopter pattern. The 13+ call sites
    across PRs #5377, #5414, #5434, #5453, #5462 all kept the migration-
    preserving exception handler expecting compatibility with
    ``datetime.fromisoformat``'s ``TypeError``/``ValueError`` surface.

    Post-#5464, the isinstance guard raises ``ValueError`` so adopters'
    handlers catch it uniformly.
    """
    import pytest

    for bad_input in (123, 12.5, {"a": 1}, [1, 2, 3], None):
        with pytest.raises(ValueError, match="expected str"):
            parse_utc_iso(bad_input)  # type: ignore[arg-type]


def test_parse_utc_iso_non_string_does_not_raise_attribute_error() -> None:
    """Explicit regression guard: the failure mode must NOT be AttributeError.

    This is the exact escape path that prompted #5464 — if the isinstance
    check is ever removed, this test fails with AttributeError leaking.
    """
    import pytest

    try:
        parse_utc_iso(123)  # type: ignore[arg-type]
    except AttributeError:
        pytest.fail(
            "parse_utc_iso must not raise AttributeError on non-str input "
            "(that's the #5464 bug — adopters' except clauses don't catch it)"
        )
    except ValueError:
        pass  # expected
