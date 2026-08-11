# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The distillation cursor must not depend on local time (#13948).

`_select_pending_sessions` compared `updated_at <= cursor` **lexicographically**,
justified by a comment saying ISO-8601 sorts lexicographically. That holds only at
a fixed UTC offset, and the values are naive *local* time
(`datetime.fromtimestamp(st_mtime).isoformat()`, the #13856 shape).

At the autumn DST fallback the local clock repeats an hour. A session written in
the repeated hour renders as a string that compares *below* a cursor already
advanced past it, so it is skipped — permanently, once a year, with nothing in
the logs. The cursor's whole stated guarantee is "bounded re-work, never a
silently skipped conversation", and that is precisely what broke.

The tests below use a real DST boundary rather than a synthetic offset, because
the bug only exists where a wall clock repeats.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from services.skill_management.skill_distillation_scheduler import (
    SkillDistillationScheduler,
    _cursor_to_epoch,
    _entry_epoch,
    _iso_to_epoch,
)

# 2026-10-25 in Europe/Riga: 03:59:59 local occurs twice — once at UTC+3, then
# again at UTC+2 after the clocks go back.
_TZ = ZoneInfo("Europe/Riga")
_FIRST_PASS = datetime(2026, 10, 25, 3, 30, tzinfo=_TZ, fold=0)
_SECOND_PASS = datetime(2026, 10, 25, 3, 30, tzinfo=_TZ, fold=1)


def _entry(session_id: str, when: datetime) -> dict:
    """A listing entry as `session_listing` builds it: naive-local ISO + raw mtime."""
    return {
        "id": session_id,
        "updatedAt": when.replace(tzinfo=None).isoformat(),
        "lastModified": when.replace(tzinfo=None).isoformat(),
        "updatedAtEpoch": when.timestamp(),
    }


class TestTheDstRepeatedHour:
    def test_the_repeated_hour_is_genuinely_ambiguous_as_a_string(self):
        """The premise. Without this the rest of the file proves nothing."""
        first = _entry("a", _FIRST_PASS)
        second = _entry("b", _SECOND_PASS)

        assert first["updatedAt"] == second["updatedAt"], "the wall clock repeats"
        assert first["updatedAtEpoch"] != second["updatedAtEpoch"], "the instants differ"
        assert second["updatedAtEpoch"] - first["updatedAtEpoch"] == 3600

    def test_a_session_in_the_repeated_hour_is_still_selected(self):
        """AC: the second pass sorts *after* a cursor set from the first.

        Lexicographically the two strings are equal, so `updated_at <= cursor`
        dropped the later session for good.
        """
        cursor = _entry_epoch(_entry("a", _FIRST_PASS))
        later = _entry_epoch(_entry("b", _SECOND_PASS))

        assert later > cursor, "the later instant must not compare as already distilled"

    def test_the_old_string_comparison_would_have_skipped_it(self):
        """Pins the defect itself, so a revert to string compare fails here."""
        first = _entry("a", _FIRST_PASS)
        second = _entry("b", _SECOND_PASS)

        assert second["updatedAt"] <= first["updatedAt"], "string compare drops the later session"


class TestOrderingKey:
    def test_the_raw_epoch_wins_over_the_ambiguous_string(self):
        entry = _entry("a", _SECOND_PASS)
        entry["updatedAt"] = "1999-01-01T00:00:00"  # stale/ambiguous string

        assert _entry_epoch(entry) == _SECOND_PASS.timestamp()

    def test_an_entry_without_an_epoch_falls_back_to_the_iso_string(self):
        """Older producers may not carry the field; ordering must still work."""
        when = datetime(2026, 6, 1, 12, 0)

        assert _entry_epoch({"id": "a", "updatedAt": when.isoformat()}) == when.timestamp()

    def test_lastmodified_is_accepted_when_updatedat_is_absent(self):
        when = datetime(2026, 6, 1, 12, 0)

        assert _entry_epoch({"id": "a", "lastModified": when.isoformat()}) == when.timestamp()

    @pytest.mark.parametrize("bad", [None, "", "not-a-date", {}, []])
    def test_an_unusable_timestamp_yields_none_rather_than_a_guess(self, bad):
        assert _entry_epoch({"id": "a", "updatedAt": bad}) is None

    def test_a_boolean_epoch_is_not_treated_as_a_number(self):
        """`True` is an int in Python; reading it as epoch 1.0 would rewind the cursor to 1970."""
        assert _entry_epoch({"id": "a", "updatedAtEpoch": True, "updatedAt": ""}) is None


class TestTheDurableCursorMigrates:
    """A reset re-distils the whole corpus at real LLM cost, so it must never happen."""

    def test_a_legacy_iso_cursor_is_read_not_discarded(self):
        """AC: the existing stored value is handled, not silently reset."""
        legacy = "2026-06-01T12:00:00"

        assert _cursor_to_epoch(legacy) == datetime(2026, 6, 1, 12, 0).timestamp()

    def test_the_current_epoch_format_round_trips(self):
        epoch = 1780000000.5

        assert _cursor_to_epoch(repr(epoch)) == epoch

    def test_an_absent_cursor_is_a_first_run_not_an_error(self):
        assert _cursor_to_epoch(None) is None

    def test_an_unparseable_cursor_reads_as_a_first_run(self):
        """Worst case is re-distillation, which the durable-cursor design accepts."""
        assert _cursor_to_epoch("garbage") is None

    def test_a_legacy_cursor_still_excludes_everything_before_it(self):
        """Migration must not re-distil the whole corpus either."""
        cursor = _cursor_to_epoch("2026-06-01T12:00:00")
        older = _entry_epoch(_entry("old", datetime(2026, 5, 1, 12, 0, tzinfo=_TZ)))
        newer = _entry_epoch(_entry("new", datetime(2026, 7, 1, 12, 0, tzinfo=_TZ)))

        assert older <= cursor, "already-distilled conversations stay distilled"
        assert newer > cursor


class TestIsoParsing:
    def test_a_naive_iso_string_is_read_in_local_time(self):
        when = datetime(2026, 3, 3, 9, 15)

        assert _iso_to_epoch(when.isoformat()) == when.timestamp()

    @pytest.mark.parametrize("bad", [None, "", 12345, "2026-13-45T99:99:99"])
    def test_unusable_input_yields_none(self, bad):
        assert _iso_to_epoch(bad) is None


class TestTheSelectionGate:
    """End to end through `_select_pending_sessions`, which is what the AC names."""

    @staticmethod
    def _scheduler(sessions):
        scheduler = SkillDistillationScheduler.__new__(SkillDistillationScheduler)
        manager = MagicMock()
        manager.list_sessions_fast = AsyncMock(return_value=sessions)
        scheduler._get_chat_history_manager = AsyncMock(return_value=manager)
        return scheduler

    def test_a_session_written_in_the_repeated_hour_is_selected(self):
        """AC: the defect, through the real selection path.

        The cursor sits on the first pass through 03:30. The second pass renders
        as the same local string, so the old comparison dropped it for good.
        """
        scheduler = self._scheduler([_entry("second-pass", _SECOND_PASS)])
        cursor = _entry_epoch(_entry("first-pass", _FIRST_PASS))

        pending = asyncio.run(scheduler._select_pending_sessions(cursor))

        assert [p["id"] for p in pending] == ["second-pass"]

    def test_already_distilled_sessions_are_not_reselected(self):
        """The other half — the cursor still has to exclude what it covered."""
        scheduler = self._scheduler([_entry("first-pass", _FIRST_PASS)])
        cursor = _entry_epoch(_entry("first-pass", _FIRST_PASS))

        assert asyncio.run(scheduler._select_pending_sessions(cursor)) == []

    def test_selection_is_ordered_oldest_first(self):
        """The cursor advances per session, so out-of-order selection strands work."""
        scheduler = self._scheduler([_entry("b", _SECOND_PASS), _entry("a", _FIRST_PASS)])

        pending = asyncio.run(scheduler._select_pending_sessions(None))

        assert [p["id"] for p in pending] == ["a", "b"]

    def test_a_session_with_no_usable_timestamp_is_skipped_loudly(self, caplog):
        """It cannot advance the cursor, so distilling it would repeat every run."""
        scheduler = self._scheduler([{"id": "no-time", "updatedAt": "not-a-date"}])

        with caplog.at_level("WARNING"):
            pending = asyncio.run(scheduler._select_pending_sessions(None))

        assert pending == []
        assert any("no-time" in r.message for r in caplog.records), "the skip must not be silent"


class TestTheCursorRoundTrips:
    """Write then read must name the same instant — the pair is the contract."""

    @staticmethod
    def _redis_backed(monkeypatch):
        store: dict = {}

        class _FakeRedis:
            async def get(self, key):
                return store.get(key)

            async def set(self, key, value):
                # redis-py encodes to bytes on the wire; mimic that so the test
                # cannot pass on a Python object that would never survive Redis.
                store[key] = value.encode() if isinstance(value, str) else str(value).encode()

        async def _client(**_kwargs):
            return _FakeRedis()

        monkeypatch.setattr("services.skill_management.skill_distillation_scheduler.get_async_redis_client", _client)
        return SkillDistillationScheduler.__new__(SkillDistillationScheduler), store

    def test_a_written_cursor_reads_back_as_the_same_instant(self, monkeypatch):
        scheduler, _store = self._redis_backed(monkeypatch)
        written = _SECOND_PASS.timestamp()

        asyncio.run(scheduler._write_cursor(written))
        read_back = asyncio.run(scheduler._read_cursor())

        assert read_back == written

    def test_the_round_trip_still_separates_the_two_repeated_hours(self, monkeypatch):
        """The whole point, end to end through Redis serialisation."""
        scheduler, _store = self._redis_backed(monkeypatch)

        asyncio.run(scheduler._write_cursor(_FIRST_PASS.timestamp()))
        cursor = asyncio.run(scheduler._read_cursor())

        assert _SECOND_PASS.timestamp() > cursor, "the second pass must still be pending"

    def test_sub_second_precision_survives(self, monkeypatch):
        """st_mtime is fractional; truncating it would re-distil or skip a session."""
        scheduler, _store = self._redis_backed(monkeypatch)

        asyncio.run(scheduler._write_cursor(1780000000.75))

        assert asyncio.run(scheduler._read_cursor()) == 1780000000.75
