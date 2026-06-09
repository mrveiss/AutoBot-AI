# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for analytics_conversation timestamp helpers (#5420, #5427).

PR #5414 (#5398) migrated the parser from
`datetime.fromisoformat(s.replace("Z", "+00:00"))` to `parse_utc_iso(s)`,
making the parsed value always tz-aware. The downstream consumer
`_is_session_in_range` still stripped tzinfo with `.replace(tzinfo=None)`,
producing `naive >= aware` TypeError unconditionally (#5420).

#5427 also deleted the duplicate `_parse_session_timestamp` wrapper —
only `_parse_timestamp` remains. These tests exercise the unified helper.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.analytics_conversation import (
    _is_session_in_range,
    _parse_timestamp,
)


def test_parse_timestamp_returns_aware_for_offset_input() -> None:
    """+00:00 input → aware datetime."""
    parsed = _parse_timestamp("2026-04-20T12:00:00+00:00")
    assert parsed is not None
    assert parsed.tzinfo is not None


def test_parse_timestamp_returns_aware_for_z_suffix() -> None:
    """Z suffix input → aware datetime (parse_utc_iso handles this)."""
    parsed = _parse_timestamp("2026-04-20T12:00:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None


def test_parse_timestamp_returns_aware_for_naive_input() -> None:
    """Naive input → aware datetime (parse_utc_iso assumes UTC)."""
    parsed = _parse_timestamp("2026-04-20T12:00:00")
    assert parsed is not None
    assert parsed.tzinfo is not None, (
        "parse_utc_iso must promote naive input to aware to keep " "_is_session_in_range comparison consistent"
    )


def test_parse_timestamp_returns_passthrough_for_datetime_object() -> None:
    """Datetime object input is returned unchanged (existing contract)."""
    dt = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
    assert _parse_timestamp(dt) is dt


def test_parse_timestamp_returns_none_for_falsy_input() -> None:
    assert _parse_timestamp(None) is None
    assert _parse_timestamp("") is None


def test_parse_timestamp_returns_none_on_invalid_input() -> None:
    """Malformed string returns None (existing contract)."""
    assert _parse_timestamp("not-a-date") is None


def test_is_session_in_range_aware_vs_aware_no_typeerror() -> None:
    """The #5420 regression: aware ts vs aware cutoff must not TypeError.

    Pre-#5414, `.replace(tzinfo=None)` worked because the parser sometimes
    returned naive. Post-#5414, the parser is always aware, so stripping
    tzinfo created `naive >= aware` TypeError on every call. The fix
    removed `.replace(tzinfo=None)` since both sides are now aware.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    session_recent = {"created_at": datetime.now(tz=timezone.utc).isoformat()}
    # Must not raise TypeError
    assert _is_session_in_range(session_recent, cutoff) is True


def test_is_session_in_range_old_session_excluded() -> None:
    """Old session (before cutoff) returns False."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    old_iso = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()
    session = {"created_at": old_iso}
    assert _is_session_in_range(session, cutoff) is False


def test_is_session_in_range_naive_input_promoted_to_aware() -> None:
    """Naive input string flows through parse_utc_iso → aware → comparable."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    # Naive ISO string (no tz suffix) — parse_utc_iso assumes UTC
    naive_iso = (datetime.now(tz=timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
    session = {"created_at": naive_iso}
    # Must not raise; ts (now aware UTC) is within last hour → True
    assert _is_session_in_range(session, cutoff) is True


def test_is_session_in_range_unparseable_timestamp_returns_true() -> None:
    """Existing contract: include sessions with unparseable timestamps."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    session = {"created_at": "garbage"}
    assert _is_session_in_range(session, cutoff) is True


def test_is_session_in_range_uses_timestamp_fallback() -> None:
    """If created_at is missing, fall back to timestamp field."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    session = {"timestamp": datetime.now(tz=timezone.utc).isoformat()}
    assert _is_session_in_range(session, cutoff) is True
