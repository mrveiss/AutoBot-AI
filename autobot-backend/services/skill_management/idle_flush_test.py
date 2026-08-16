# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Idle-flush trigger for skill distillation (#13695).

Distillation ran on fixed crontabs, so a session ending at 09:00 was not
consolidated until the small hours — anything depending on distilled output was
stale for the rest of the working day. Idle-flush is an *additional* trigger,
not a replacement.

The first implementation derived idleness from the sessions' own ISO
``updated_at`` strings, and these tests supplied aware-UTC values. The real
listing emits **naive local time** (#13856), so read back as UTC the computed
age went negative east of UTC and *inverted* west of it — reporting a session
someone was actively typing into as long-idle. The tests were green because the
fixture used a shape production never emits.

So the signal is now the chats-directory mtime: epoch floats, no parsing, one
``os.stat``. These tests use real files and real mtimes rather than asserting
against a timestamp format, because the format was the bug.
"""

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.skill_management import skill_distillation_scheduler as sched
from services.skill_management.skill_distillation_scheduler import SkillDistillationScheduler


@pytest.fixture
def chats_dir(tmp_path):
    d = tmp_path / "chats"
    d.mkdir()
    return d


@pytest.fixture
def scheduler(monkeypatch, chats_dir):
    monkeypatch.setattr(sched, "IDLE_FLUSH_S", 900)
    s = SkillDistillationScheduler()
    manager = MagicMock()
    manager._get_chats_directory = MagicMock(return_value=str(chats_dir))
    s._get_chat_history_manager = AsyncMock(return_value=manager)
    return s


def _quiet_for(chats_dir, seconds: int) -> None:
    """Backdate the directory mtime, as a corpus untouched for *seconds*."""
    past = time.time() - seconds
    os.utime(chats_dir, (past, past))


class TestTheSignalIsTimezoneFree:
    """The blocker that made the first version a no-op on this host."""

    @pytest.mark.asyncio
    async def test_idleness_never_goes_negative(self, scheduler, chats_dir):
        """A freshly written corpus is 0s idle, never a negative age.

        With the ISO path, a naive-local timestamp read as UTC produced a
        negative `idle_for` east of UTC — so the trigger could never fire.
        """
        idle_for = await scheduler._corpus_idle_for()

        assert idle_for is not None
        assert idle_for >= 0.0
        assert idle_for < 5.0

    @pytest.mark.asyncio
    async def test_an_active_corpus_is_never_reported_as_idle(self, scheduler, chats_dir):
        """The dangerous inversion: west of UTC the old computation aged an
        actively-used session by hours and flushed mid-conversation."""
        (chats_dir / "sess.json").write_text("{}", encoding="utf-8")

        assert await scheduler._has_idle_pending() is False

    @pytest.mark.asyncio
    async def test_idleness_is_epoch_arithmetic(self, scheduler, chats_dir):
        """Idleness is `time.time() - st_mtime` — no zone is consulted.

        An earlier version of this parametrised over three timezones with
        `tzset()`. It had **zero** discriminating power (stripping the tz
        manipulation left all three passing) and it leaked: `delenv("TZ")` +
        `tzset()` drops the C-level zone, and monkeypatch restores the env var
        without a second `tzset()`, so every later test in that worker sees a
        different `time.localtime()`. On a runner that sets TZ that is #13856's
        own failure mode, manufactured by its own regression test.
        """
        _quiet_for(chats_dir, 1800)

        assert await scheduler._corpus_idle_for() == pytest.approx(1800, abs=5)


class TestIdleFlushFires:
    @pytest.mark.asyncio
    async def test_a_quiet_corpus_with_pending_work_triggers_a_flush(self, scheduler, chats_dir):
        _quiet_for(chats_dir, 1800)

        with patch.object(scheduler, "_read_cursor", new=AsyncMock(return_value=None)):
            with patch.object(scheduler, "_select_pending_sessions", new=AsyncMock(return_value=[{"id": "s-1"}])):
                assert await scheduler._has_idle_pending() is True

    @pytest.mark.asyncio
    async def test_a_quiet_corpus_with_nothing_pending_does_not(self, scheduler, chats_dir):
        _quiet_for(chats_dir, 1800)

        with patch.object(scheduler, "_read_cursor", new=AsyncMock(return_value=None)):
            with patch.object(scheduler, "_select_pending_sessions", new=AsyncMock(return_value=[])):
                assert await scheduler._has_idle_pending() is False

    @pytest.mark.asyncio
    async def test_disabled_by_zero(self, scheduler, chats_dir, monkeypatch):
        monkeypatch.setattr(sched, "IDLE_FLUSH_S", 0)
        _quiet_for(chats_dir, 99999)

        assert await scheduler._has_idle_pending() is False


class TestTheCheapGateComesFirst:
    """Blocker 3: the first version read and parsed every chat file on every
    leader cycle — 1.5s at 1000 conversations, every 10s.

    `list_sessions_fast` is not cheap despite the name: it opens and
    `json.loads` every chat file.
    """

    @pytest.mark.asyncio
    async def test_a_quiet_deployment_stops_listing_after_the_first_cycle(self, scheduler, chats_dir):
        """The steady state, which is the state idle-flush exists for.

        Recording the guard only on a *flush* left it unarmed whenever the
        cursor was caught up, so gates 1 and 2 passed forever and gate 3 read
        the whole corpus every 10s — measured at 20 listings in 20 cycles. The
        expensive path was the untested one.
        """
        _quiet_for(chats_dir, 1800)
        listings = {"n": 0}

        async def _select(cursor):
            listings["n"] += 1
            return []  # nothing pending: the normal state of an idle deployment

        with patch.object(scheduler, "_read_cursor", new=AsyncMock(return_value="c1")):
            with patch.object(scheduler, "_select_pending_sessions", new=_select):
                for _ in range(20):
                    await scheduler._has_idle_pending()

        assert listings["n"] == 1, f"corpus was listed {listings['n']}x in 20 cycles"

    @pytest.mark.asyncio
    async def test_an_active_corpus_never_lists_sessions(self, scheduler, chats_dir):
        select = AsyncMock(return_value=[{"id": "s-1"}])

        with patch.object(scheduler, "_select_pending_sessions", new=select):
            await scheduler._has_idle_pending()

        select.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_capped_listing_cannot_hide_an_active_session(self, scheduler, chats_dir):
        """Blocker 4: `_select_pending_sessions` caps at MAX_SESSIONS_PER_RUN,
        so the newest activity could fall outside the slice. A directory mtime
        is the newest write across *all* sessions and cannot be truncated."""
        (chats_dir / "active.json").write_text("{}", encoding="utf-8")
        select = AsyncMock(return_value=[{"id": f"old-{i}"} for i in range(10)])

        with patch.object(scheduler, "_select_pending_sessions", new=select):
            assert await scheduler._has_idle_pending() is False


class TestAPoisonedSessionCannotSpin:
    """Blocker 2: a conversation the pass cannot advance past re-triggered
    `run_once` every leader cycle — 10s instead of hourly, 360x LLM spend."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cursor",
        [
            "cursor-1",
            None,  # first-ever run, AND every Redis fault: _read_cursor swallows and returns None
        ],
        ids=["cursor-present", "cursor-none"],
    )
    async def test_a_stuck_conversation_cannot_respin(self, scheduler, chats_dir, cursor):
        """Both cursor states, because the first guard only worked for one.

        Keying the guard on the cursor left it inert when `_read_cursor`
        returned None — which is a first run *and* any Redis fault. During an
        outage the cursor also cannot advance, so the guard disengaged exactly
        when the spin becomes unbounded: 5/5 flushes instead of 1.
        """
        _quiet_for(chats_dir, 1800)

        with patch.object(scheduler, "_read_cursor", new=AsyncMock(return_value=cursor)):
            with patch.object(scheduler, "_select_pending_sessions", new=AsyncMock(return_value=[{"id": "poison"}])):
                fired = [await scheduler._has_idle_pending() for _ in range(5)]

        assert fired == [True, False, False, False, False], f"stuck conversation re-triggered the pass: {fired}"

    @pytest.mark.asyncio
    async def test_a_successful_pass_does_not_release_the_guard(self, scheduler, chats_dir):
        """`run_once` advances the cursor after every distilled session, so a
        cursor-released guard fired again on the very next cycle — draining a
        backlog at one pass per 10s and removing the spend bound
        DISTILLATION_INTERVAL_S exists to provide."""
        _quiet_for(chats_dir, 1800)
        moving = iter(["c1", "c2", "c3", "c4", "c5"])

        with patch.object(scheduler, "_read_cursor", new=AsyncMock(side_effect=lambda: next(moving))):
            with patch.object(scheduler, "_select_pending_sessions", new=AsyncMock(return_value=[{"id": "s"}])):
                fired = [await scheduler._has_idle_pending() for _ in range(5)]

        assert fired == [True, False, False, False, False], f"advancing cursor released the guard: {fired}"

    @pytest.mark.asyncio
    async def test_new_activity_then_quiet_allows_the_next_flush(self, scheduler, chats_dir):
        """The guard must not wedge the feature permanently shut."""
        _quiet_for(chats_dir, 1800)

        with patch.object(scheduler, "_read_cursor", new=AsyncMock(return_value=None)):
            with patch.object(scheduler, "_select_pending_sessions", new=AsyncMock(return_value=[{"id": "s"}])):
                assert await scheduler._has_idle_pending() is True
                assert await scheduler._has_idle_pending() is False

                # someone chats again, then goes quiet
                (chats_dir / "new.json").write_text("{}", encoding="utf-8")
                _quiet_for(chats_dir, 1800)

                assert await scheduler._has_idle_pending() is True


class TestDegradesToTheInterval:
    @pytest.mark.asyncio
    async def test_a_missing_chats_directory_is_not_an_error(self, scheduler):
        manager = MagicMock()
        manager._get_chats_directory = MagicMock(return_value="/nonexistent/path")
        scheduler._get_chat_history_manager = AsyncMock(return_value=manager)

        assert await scheduler._corpus_idle_for() is None
        assert await scheduler._has_idle_pending() is False

    @pytest.mark.asyncio
    async def test_no_manager_degrades_quietly(self, scheduler):
        scheduler._get_chat_history_manager = AsyncMock(return_value=None)

        assert await scheduler._has_idle_pending() is False

    @pytest.mark.asyncio
    async def test_a_failing_check_falls_back_to_the_interval(self, scheduler, chats_dir):
        _quiet_for(chats_dir, 1800)

        with patch.object(scheduler, "_read_cursor", new=AsyncMock(side_effect=RuntimeError("redis down"))):
            assert await scheduler._has_idle_pending() is False


class TestCronBackstopSurvives:
    """Idle-flush is additional, not a replacement — a session that never goes
    idle, or a worker that dies mid-flush, must still be swept.

    Driven rather than grepped: the previous version asserted a source
    substring, which a black reflow breaks and which proves nothing about
    whether the branch runs.
    """

    @pytest.mark.asyncio
    async def test_the_interval_triggers_a_pass_with_idle_flush_disabled(self, scheduler, monkeypatch):
        monkeypatch.setattr(sched, "IDLE_FLUSH_S", 0)
        monkeypatch.setattr(sched, "DISTILLATION_INTERVAL_S", 0)

        ran = asyncio.Event()
        scheduler._enabled = AsyncMock(return_value=True)
        scheduler._lease = MagicMock()
        scheduler._lease.is_leader = True
        scheduler._lease.refresh_s = 0.01
        scheduler._lease.poll_s = 0.01
        scheduler._lease.update_leadership = AsyncMock()
        scheduler.run_once = AsyncMock(side_effect=lambda: ran.set())

        task = asyncio.create_task(scheduler._leader_loop())
        try:
            await asyncio.wait_for(ran.wait(), timeout=2.0)
        finally:
            task.cancel()

        scheduler.run_once.assert_awaited()


class TestTheExcludedKnobsStayExcluded:
    """No debounce delay and no min/max interval band, until #13251 makes
    recall quality measurable. The cursor guard is a correctness check, not a
    tuning constant."""

    def test_idle_flush_is_a_single_knob(self):
        # Type, not value: 0 is the documented disable, so asserting > 0 would
        # redden the suite for any operator or runner that sets it.
        assert isinstance(sched.IDLE_FLUSH_S, int)
