# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The distillation pass and its durable cursor (#13925).

`SkillDistillationScheduler` (#12809) shipped with no test file. #13695 added
one, covering only the idle-flush trigger — so the scheduler's original surface,
including the property its module docstring calls load-bearing, was unpinned:

    the cursor advances past a conversation only after its proposal call has
    returned, so a crash mid-pass re-offers the remainder rather than silently
    skipping it — bounded re-work, never a lost conversation.

That is the difference between re-doing work and losing it, and a refactor could
have inverted it silently. These tests pin it, plus the `run_once` surface
around it.

Written after #13948 showed the cost of the gap: the cursor comparison is
timezone-dependent and skips an hour of conversations at the autumn DST
fallback, which no test could have caught because no test looked at the cursor.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.skill_management import skill_distillation_scheduler as sched
from services.skill_management.skill_distillation_scheduler import SkillDistillationScheduler


def _session(sid: str, updated: str) -> dict:
    return {"id": sid, "updated_at": updated}


@pytest.fixture
def scheduler(monkeypatch):
    monkeypatch.setattr(sched, "MIN_MESSAGES_TO_DISTILL", 2)
    s = SkillDistillationScheduler()
    s._write_cursor = AsyncMock()
    s._read_cursor = AsyncMock(return_value=None)
    s._load_history = AsyncMock(return_value=[{"role": "user"}, {"role": "assistant"}])
    s._list_existing_skills = MagicMock(return_value=[])
    return s


def _extractor(skills=("workflow-a",)):
    e = MagicMock()
    e.extract_skills = AsyncMock(return_value=list(skills))
    return e


def _proposer(names=("workflow-a",)):
    p = MagicMock()
    p.propose_skills = AsyncMock(return_value={"proposed": list(names)})
    return p


class TestTheCursorOnlyPassesCompletedWork:
    """The durability property, stated in the module docstring and never pinned."""

    @pytest.mark.asyncio
    async def test_the_cursor_advances_once_per_completed_conversation(self, scheduler):
        scheduler._select_pending_sessions = AsyncMock(
            return_value=[_session("s1", "t1"), _session("s2", "t2"), _session("s3", "t3")]
        )
        scheduler._get_extractor = MagicMock(return_value=_extractor())
        scheduler._get_proposer = MagicMock(return_value=_proposer())

        result = await scheduler.run_once()

        assert [c.args[0] for c in scheduler._write_cursor.await_args_list] == ["t1", "t2", "t3"]
        assert result["sessions_distilled"] == 3

    @pytest.mark.asyncio
    async def test_a_failure_stops_the_pass_and_leaves_the_cursor_behind_it(self, scheduler):
        """The load-bearing case.

        Advancing past a conversation whose proposal did not land would drop it
        permanently and silently. The pass must stop, so the next run re-offers
        it and everything after it.
        """
        scheduler._select_pending_sessions = AsyncMock(
            return_value=[_session("ok", "t1"), _session("boom", "t2"), _session("later", "t3")]
        )
        extractor = _extractor()
        extractor.extract_skills = AsyncMock(side_effect=[["a"], RuntimeError("extractor down"), ["c"]])
        scheduler._get_extractor = MagicMock(return_value=extractor)
        scheduler._get_proposer = MagicMock(return_value=_proposer())

        result = await scheduler.run_once()

        advanced = [c.args[0] for c in scheduler._write_cursor.await_args_list]
        assert advanced == ["t1"], f"cursor moved past a failed conversation: {advanced}"
        assert result["sessions_distilled"] == 1
        assert result["sessions_seen"] == 3

    @pytest.mark.asyncio
    async def test_the_third_conversation_is_never_attempted_after_a_failure(self, scheduler):
        """Stopping means stopping — not skipping the failure and carrying on,
        which would advance the cursor past it via the later success."""
        scheduler._select_pending_sessions = AsyncMock(return_value=[_session("boom", "t1"), _session("later", "t2")])
        extractor = _extractor()
        extractor.extract_skills = AsyncMock(side_effect=RuntimeError("down"))
        scheduler._get_extractor = MagicMock(return_value=extractor)
        proposer = _proposer()
        scheduler._get_proposer = MagicMock(return_value=proposer)

        await scheduler.run_once()

        scheduler._write_cursor.assert_not_awaited()
        proposer.propose_skills.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_proposal_failure_also_stops_the_pass(self, scheduler):
        """Not just extraction — the cursor's contract is 'after the proposal
        call has returned', so a proposer fault must hold it too."""
        scheduler._select_pending_sessions = AsyncMock(return_value=[_session("s1", "t1")])
        scheduler._get_extractor = MagicMock(return_value=_extractor())
        proposer = _proposer()
        proposer.propose_skills = AsyncMock(side_effect=RuntimeError("SLM unreachable"))
        scheduler._get_proposer = MagicMock(return_value=proposer)

        result = await scheduler.run_once()

        scheduler._write_cursor.assert_not_awaited()
        assert result["sessions_distilled"] == 0


class TestProcessedButUnproductiveStillAdvances:
    """A conversation that teaches nothing is *processed*, not failed. Holding
    the cursor on it would re-offer it every run forever."""

    @pytest.mark.asyncio
    async def test_a_conversation_too_short_to_distil_advances_the_cursor(self, scheduler):
        scheduler._select_pending_sessions = AsyncMock(return_value=[_session("tiny", "t1")])
        scheduler._load_history = AsyncMock(return_value=[{"role": "user"}])  # below MIN
        extractor = _extractor()
        scheduler._get_extractor = MagicMock(return_value=extractor)
        scheduler._get_proposer = MagicMock(return_value=_proposer())

        await scheduler.run_once()

        scheduler._write_cursor.assert_awaited_once_with("t1")
        extractor.extract_skills.assert_not_awaited()  # skipped before paying for the load

    @pytest.mark.asyncio
    async def test_a_conversation_yielding_no_skills_advances_the_cursor(self, scheduler):
        scheduler._select_pending_sessions = AsyncMock(return_value=[_session("dull", "t1")])
        scheduler._get_extractor = MagicMock(return_value=_extractor(skills=[]))
        proposer = _proposer()
        scheduler._get_proposer = MagicMock(return_value=proposer)

        await scheduler.run_once()

        scheduler._write_cursor.assert_awaited_once_with("t1")
        proposer.propose_skills.assert_not_awaited()  # nothing to propose


class TestRunOnceSurface:
    @pytest.mark.asyncio
    async def test_nothing_pending_writes_no_cursor_and_reports_zero(self, scheduler):
        scheduler._select_pending_sessions = AsyncMock(return_value=[])

        result = await scheduler.run_once()

        assert result == {"sessions_seen": 0, "sessions_distilled": 0, "proposed": []}
        scheduler._write_cursor.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_pass_reads_the_cursor_before_selecting(self, scheduler):
        """The cursor is the SSOT for 'unprocessed' — selecting without it would
        re-distil the whole corpus at real LLM cost."""
        scheduler._read_cursor = AsyncMock(return_value="2026-01-01T00:00:00")
        select = AsyncMock(return_value=[])
        scheduler._select_pending_sessions = select

        await scheduler.run_once()

        scheduler._read_cursor.assert_awaited_once()
        assert select.await_args.args[0] == "2026-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_proposed_names_are_accumulated_across_conversations(self, scheduler):
        scheduler._select_pending_sessions = AsyncMock(return_value=[_session("s1", "t1"), _session("s2", "t2")])
        scheduler._get_extractor = MagicMock(return_value=_extractor())
        proposer = _proposer()
        proposer.propose_skills = AsyncMock(side_effect=[{"proposed": ["a"]}, {"proposed": ["b", "c"]}])
        scheduler._get_proposer = MagicMock(return_value=proposer)

        result = await scheduler.run_once()

        assert result["proposed"] == ["a", "b", "c"]
