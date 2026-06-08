# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for _cron_matches_now — all 5 cron fields evaluated correctly.

Day-of-week field follows standard cron convention:
  0 = Sunday, 1 = Monday, 2 = Tuesday, 3 = Wednesday,
  4 = Thursday, 5 = Friday, 6 = Saturday
"""

from datetime import datetime, timezone

# _cron_matches_now is a nested function inside _autonomous_loop_runner.
# Extract it by re-implementing it here identically so tests are deterministic
# without needing to spin up the full scheduler.  The authoritative source is
# workflow_scheduler.py — these tests validate the logic contract.


def _cron_matches_now_impl(cron_expr: str, now: datetime) -> bool:
    """Mirror of _cron_matches_now with an injected *now* for testing.

    Day-of-week uses standard cron convention (0=Sunday).
    Conversion to Python weekday(): ``(cron_dow - 1) % 7``
    """
    try:
        parts = cron_expr.split()
        if len(parts) < 5:
            return False
        minute_match = parts[0] == "*" or int(parts[0]) == now.minute
        hour_match = parts[1] == "*" or int(parts[1]) == now.hour
        dom_match = parts[2] == "*" or int(parts[2]) == now.day
        month_match = parts[3] == "*" or int(parts[3]) == now.month
        dow_match = parts[4] == "*" or (int(parts[4]) - 1) % 7 == now.weekday()
        return minute_match and hour_match and dom_match and month_match and dow_match
    except Exception:
        return False


def dt(year=2024, month=3, day=15, hour=2, minute=0, weekday_=4):
    """Helper — returns a fixed UTC datetime (2024-03-15 02:00 is a Friday, weekday()=4)."""
    # Verify the weekday matches expectations
    d = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    assert d.weekday() == weekday_, f"weekday mismatch: expected {weekday_}, got {d.weekday()}"
    return d


# 2024-03-15 02:00 UTC — Friday (weekday=4, standard cron dow=5)
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
    def test_friday_matches_standard_cron_5(self):
        # 2024-03-15 is Friday; standard cron 5 = Friday (Mon=1..Sat=6)
        # (5 - 1) % 7 = 4 = Python Friday weekday
        assert _cron_matches_now_impl("0 2 * * 5", NOW) is True

    def test_sunday_matches_standard_cron_0(self):
        # Standard cron 0 = Sunday; (0 - 1) % 7 = 6 = Python Sunday weekday
        sunday = datetime(2024, 3, 17, 4, 0, tzinfo=timezone.utc)  # 2024-03-17 is Sunday
        assert sunday.weekday() == 6, "2024-03-17 must be Sunday"
        assert _cron_matches_now_impl("0 4 * * 0", sunday) is True

    def test_monday_matches_standard_cron_1(self):
        # Standard cron 1 = Monday; (1 - 1) % 7 = 0 = Python Monday weekday
        monday = datetime(2024, 3, 18, 9, 0, tzinfo=timezone.utc)  # 2024-03-18 is Monday
        assert monday.weekday() == 0, "2024-03-18 must be Monday"
        assert _cron_matches_now_impl("0 9 * * 1", monday) is True

    def test_wrong_dow_no_match_on_friday(self):
        # Standard cron 1 = Monday — should not match Friday
        assert _cron_matches_now_impl("0 2 * * 1", NOW) is False

    def test_standard_cron_0_sunday_does_not_match_friday(self):
        # Standard cron 0 = Sunday — should not match Friday
        assert _cron_matches_now_impl("0 2 * * 0", NOW) is False

    def test_all_five_fields_exact_match_friday(self):
        # minute=0, hour=2, dom=15, month=3, dow=5 (standard cron Friday)
        assert _cron_matches_now_impl("0 2 15 3 5", NOW) is True

    def test_all_five_fields_wrong_dow(self):
        # standard cron 4 = Thursday — should not match Friday
        assert _cron_matches_now_impl("0 2 15 3 4", NOW) is False

    def test_mesh_pruner_cron_0_4_sunday(self):
        # "0 4 * * 0" is the mesh_pruner schedule — standard cron 0 = Sunday at 04:00
        # Must match Sunday, not Monday
        sunday = datetime(2024, 3, 17, 4, 0, tzinfo=timezone.utc)
        monday = datetime(2024, 3, 18, 4, 0, tzinfo=timezone.utc)
        assert sunday.weekday() == 6, "2024-03-17 must be Sunday"
        assert monday.weekday() == 0, "2024-03-18 must be Monday"
        assert _cron_matches_now_impl("0 4 * * 0", sunday) is True
        assert _cron_matches_now_impl("0 4 * * 0", monday) is False
