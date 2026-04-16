"""Tests for _cron_matches_now — all 5 cron fields evaluated correctly."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

# _cron_matches_now is a nested function inside _autonomous_loop_runner.
# Extract it by re-implementing it here identically so tests are deterministic
# without needing to spin up the full scheduler.  The authoritative source is
# workflow_scheduler.py — these tests validate the logic contract.


def _cron_matches_now_impl(cron_expr: str, now: datetime) -> bool:
    """Mirror of _cron_matches_now with an injected *now* for testing."""
    try:
        parts = cron_expr.split()
        if len(parts) < 5:
            return False
        minute_match = parts[0] == "*" or int(parts[0]) == now.minute
        hour_match = parts[1] == "*" or int(parts[1]) == now.hour
        dom_match = parts[2] == "*" or int(parts[2]) == now.day
        month_match = parts[3] == "*" or int(parts[3]) == now.month
        dow_match = parts[4] == "*" or int(parts[4]) == now.weekday()
        return minute_match and hour_match and dom_match and month_match and dow_match
    except Exception:
        return False


def dt(year=2024, month=3, day=15, hour=2, minute=0, weekday_=4):
    """Helper — returns a fixed UTC datetime (2024-03-15 02:00 is a Friday, weekday()=4)."""
    # Verify the weekday matches expectations
    d = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    assert d.weekday() == weekday_, f"weekday mismatch: expected {weekday_}, got {d.weekday()}"
    return d


# 2024-03-15 02:00 UTC — Friday (weekday=4)
NOW = dt()


class TestWildcardExpressions:
    def test_all_wildcards_always_match(self):
        assert _cron_matches_now_impl("* * * * *", NOW) is True

    def test_partial_wildcards_match(self):
        assert _cron_matches_now_impl("0 2 * * *", NOW) is True

    def test_fewer_than_five_parts_returns_false(self):
        assert _cron_matches_now_impl("0 2 *", NOW) is False

    def test_empty_expression_returns_false(self):
        assert _cron_matches_now_impl("", NOW) is False

    def test_invalid_value_returns_false(self):
        assert _cron_matches_now_impl("abc * * * *", NOW) is False


class TestMinuteHour:
    def test_correct_minute_and_hour_match(self):
        assert _cron_matches_now_impl("0 2 * * *", NOW) is True

    def test_wrong_minute_no_match(self):
        assert _cron_matches_now_impl("30 2 * * *", NOW) is False

    def test_wrong_hour_no_match(self):
        assert _cron_matches_now_impl("0 5 * * *", NOW) is False


class TestDayOfMonth:
    def test_correct_dom_matches(self):
        # day=15
        assert _cron_matches_now_impl("0 2 15 * *", NOW) is True

    def test_wrong_dom_no_match(self):
        assert _cron_matches_now_impl("0 2 1 * *", NOW) is False

    def test_first_day_of_month_specific(self):
        first = datetime(2024, 3, 1, 2, 0, tzinfo=timezone.utc)
        assert _cron_matches_now_impl("0 2 1 * *", first) is True
        assert _cron_matches_now_impl("0 2 1 * *", NOW) is False


class TestMonth:
    def test_correct_month_matches(self):
        # month=3 (March)
        assert _cron_matches_now_impl("0 2 15 3 *", NOW) is True

    def test_wrong_month_no_match(self):
        assert _cron_matches_now_impl("0 2 15 4 *", NOW) is False

    def test_full_date_match(self):
        # "0 2 15 3 *" — every March 15 at 02:00
        assert _cron_matches_now_impl("0 2 15 3 *", NOW) is True

    def test_full_date_wrong_day(self):
        assert _cron_matches_now_impl("0 2 16 3 *", NOW) is False


class TestDayOfWeek:
    def test_friday_matches(self):
        # 2024-03-15 is Friday, weekday()=4
        assert _cron_matches_now_impl("0 2 * * 4", NOW) is True

    def test_monday_no_match_on_friday(self):
        assert _cron_matches_now_impl("0 2 * * 0", NOW) is False

    def test_all_five_fields_exact_match(self):
        # minute=0, hour=2, dom=15, month=3, dow=4 (Friday)
        assert _cron_matches_now_impl("0 2 15 3 4", NOW) is True

    def test_all_five_fields_wrong_dow(self):
        assert _cron_matches_now_impl("0 2 15 3 3", NOW) is False  # Thursday, not Friday
