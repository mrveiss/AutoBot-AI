# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Idle-flush trigger for skill distillation (#13695).

Distillation ran on fixed crontabs, so a session ending at 09:00 was not
consolidated until the small hours — anything depending on distilled output was
stale for the rest of the working day.

Idle-flush is an *additional* trigger, not a replacement. These pin that, and
pin the deliberate absence of the two knobs #13695 excluded.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.skill_management import skill_distillation_scheduler as sched
from services.skill_management.skill_distillation_scheduler import SkillDistillationScheduler


def _iso(seconds_ago: int) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


@pytest.fixture
def scheduler(monkeypatch):
    monkeypatch.setattr(sched, "IDLE_FLUSH_S", 900)
    return SkillDistillationScheduler()


class TestIdleFlushFires:
    @pytest.mark.asyncio
    async def test_a_quiet_pending_conversation_triggers_a_flush(self, scheduler):
        """AC: distilled without waiting for the next cron tick."""
        with patch.object(scheduler, "_read_cursor", new_callable=AsyncMock, return_value=None):
            with patch.object(
                scheduler,
                "_select_pending_sessions",
                new_callable=AsyncMock,
                return_value=[{"id": "s-1", "updated_at": _iso(1800)}],
            ):
                assert await scheduler._has_idle_pending() is True

    @pytest.mark.asyncio
    async def test_a_still_active_conversation_does_not(self, scheduler):
        """Quiet is the trigger — an in-progress session must not be flushed
        mid-conversation, which would distil a partial workflow."""
        with patch.object(scheduler, "_read_cursor", new_callable=AsyncMock, return_value=None):
            with patch.object(
                scheduler,
                "_select_pending_sessions",
                new_callable=AsyncMock,
                return_value=[{"id": "s-1", "updated_at": _iso(60)}],
            ):
                assert await scheduler._has_idle_pending() is False

    @pytest.mark.asyncio
    async def test_nothing_pending_means_no_flush(self, scheduler):
        with patch.object(scheduler, "_read_cursor", new_callable=AsyncMock, return_value=None):
            with patch.object(scheduler, "_select_pending_sessions", new_callable=AsyncMock, return_value=[]):
                assert await scheduler._has_idle_pending() is False

    @pytest.mark.asyncio
    async def test_the_newest_conversation_decides(self, scheduler):
        """An old pending item does not license flushing while another is active."""
        with patch.object(scheduler, "_read_cursor", new_callable=AsyncMock, return_value=None):
            with patch.object(
                scheduler,
                "_select_pending_sessions",
                new_callable=AsyncMock,
                return_value=[
                    {"id": "old", "updated_at": _iso(9999)},
                    {"id": "active", "updated_at": _iso(5)},
                ],
            ):
                assert await scheduler._has_idle_pending() is False


class TestReusesLeaderElectionAndCursor:
    @pytest.mark.asyncio
    async def test_the_idle_check_consults_the_durable_cursor(self, scheduler):
        """AC: the cursor is reused, not duplicated.

        Without it the idle path would have its own notion of "unprocessed" and
        could re-distil what the cron already handled.
        """
        with patch.object(scheduler, "_read_cursor", new_callable=AsyncMock, return_value="2026-01-01") as cursor:
            with patch.object(scheduler, "_select_pending_sessions", new_callable=AsyncMock, return_value=[]) as select:
                await scheduler._has_idle_pending()

        cursor.assert_awaited_once()
        assert select.await_args.args[0] == "2026-01-01"

    @pytest.mark.asyncio
    async def test_a_non_leader_never_flushes(self, scheduler):
        """AC: two workers racing produce one pass, not two.

        The idle check sits inside the `is_leader` guard, so only the lease
        holder can reach `run_once` — the same election the interval uses.
        """
        import inspect

        source = inspect.getsource(SkillDistillationScheduler._leader_loop)

        assert "self._lease.is_leader and (" in source
        assert "_has_idle_pending" in source

    @pytest.mark.asyncio
    async def test_a_failing_idle_check_falls_back_to_the_interval(self, scheduler):
        """A broken idle check must degrade to pre-#13695 behaviour, not stop
        distillation."""
        with patch.object(scheduler, "_read_cursor", new_callable=AsyncMock, side_effect=RuntimeError("redis down")):
            assert await scheduler._has_idle_pending() is False


class TestCronBackstopSurvives:
    def test_the_interval_still_triggers_independently(self):
        """AC: idle-flush is additional, not a replacement.

        A session that never goes idle, or a worker that dies mid-flush, must
        still be swept.
        """
        import inspect

        source = inspect.getsource(SkillDistillationScheduler._leader_loop)

        assert "elapsed >= DISTILLATION_INTERVAL_S or" in source, "interval must remain an independent trigger"

    def test_disabling_idle_flush_leaves_the_interval_alone(self, scheduler, monkeypatch):
        monkeypatch.setattr(sched, "IDLE_FLUSH_S", 0)

        import asyncio

        assert asyncio.run(scheduler._has_idle_pending()) is False


class TestTheExcludedKnobsStayExcluded:
    """AC: no debounce delay and no min/max interval band.

    This criterion exists to stop the decision being quietly reversed during
    implementation — #13251 must land before those knobs can be tuned against
    anything.
    """

    def test_no_debounce_or_interval_band_constants_were_added(self):
        import inspect

        source = inspect.getsource(sched)

        for forbidden in ("DEBOUNCE", "MIN_INTERVAL", "MAX_INTERVAL", "INTERVAL_BAND"):
            assert forbidden not in source, f"{forbidden} is deferred behind #13251"

    def test_idle_flush_is_a_single_knob(self):
        assert isinstance(sched.IDLE_FLUSH_S, int)
        assert sched.IDLE_FLUSH_S > 0, "a sane default, not a hardcoded literal at the call site"
