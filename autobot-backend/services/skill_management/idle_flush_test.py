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

    def test_the_scheduler_no_longer_depends_on_timestamp_parsing(self):
        """Guards the fix itself, as a dependency invariant.

        The whole point of the rework is that no scheduling decision is derived
        from an emitted timestamp string. Reintroducing `parse_utc_iso` — or
        `datetime.now()` arithmetic against one — reinherits #13856, whose
        symptom is invisible in a UTC test environment and only appears as a
        no-op east of UTC or a mid-conversation flush west of it.

        Asserted structurally because that is what makes it detectable *here*
        rather than in whichever timezone deploys it.
        """
        import inspect

        source = inspect.getsource(sched)

        assert "parse_utc_iso" not in source, "the idle path must not parse emitted timestamps (#13856)"
        assert "datetime.now" not in source, "idleness is epoch-float arithmetic, not wall-clock parsing"


class TestIdleFlushFires:
    @pytest.mark.asyncio
    async def test_a_quiet_corpus_with_pending_work_triggers_a_flush(self, scheduler, chats_dir):
        _quiet_for(chats_dir, 1800)

        with patch.object(scheduler, "_read_cursor", new=AsyncMock(return_value=None)):
            with patch.object(
                scheduler, "_select_pending_sessions", new=AsyncMock(return_value=[{"id": "s-1"}])
            ):
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
    leader cycle — 1.5s at 1000 conversations, every 10s."""

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
    async def test_a_second_flush_waits_for_the_cursor_to_move(self, scheduler, chats_dir):
        _quiet_for(chats_dir, 1800)
        pending = AsyncMock(return_value=[{"id": "poison"}])

        with patch.object(scheduler, "_read_cursor", new=AsyncMock(return_value="cursor-1")):
            with patch.object(scheduler, "_select_pending_sessions", new=pending):
                first = await scheduler._has_idle_pending()
                second = await scheduler._has_idle_pending()
                third = await scheduler._has_idle_pending()

        assert first is True
        assert (second, third) == (False, False), "a stuck conversation re-triggered the pass every cycle"

    @pytest.mark.asyncio
    async def test_a_moved_cursor_allows_the_next_flush(self, scheduler, chats_dir):
        """The guard must not wedge the feature shut once real progress is made."""
        _quiet_for(chats_dir, 1800)
        pending = AsyncMock(return_value=[{"id": "s-2"}])

        with patch.object(scheduler, "_select_pending_sessions", new=pending):
            with patch.object(scheduler, "_read_cursor", new=AsyncMock(return_value="cursor-1")):
                assert await scheduler._has_idle_pending() is True
            with patch.object(scheduler, "_read_cursor", new=AsyncMock(return_value="cursor-2")):
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
    def test_the_interval_still_triggers_independently(self):
        """Idle-flush is additional, not a replacement — a session that never
        goes idle, or a worker that dies mid-flush, must still be swept."""
        import inspect

        source = inspect.getsource(SkillDistillationScheduler._leader_loop)

        assert "elapsed >= DISTILLATION_INTERVAL_S or" in source


class TestTheExcludedKnobsStayExcluded:
    """No debounce delay and no min/max interval band, until #13251 makes
    recall quality measurable. The cursor guard is a correctness check, not a
    tuning constant."""

    def test_no_debounce_or_interval_band_constants_were_added(self):
        import inspect

        source = inspect.getsource(sched)

        for forbidden in ("DEBOUNCE", "MIN_INTERVAL", "MAX_INTERVAL", "INTERVAL_BAND"):
            assert forbidden not in source, f"{forbidden} is deferred behind #13251"

    def test_idle_flush_is_a_single_knob(self):
        assert isinstance(sched.IDLE_FLUSH_S, int)
        assert sched.IDLE_FLUSH_S > 0
