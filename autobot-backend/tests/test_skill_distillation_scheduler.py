# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for SkillDistillationScheduler — Issue #12809

Covers the two properties the scheduler exists to guarantee:
  - the extraction pipeline is actually reached for finished conversations
  - the cursor advances only over conversations whose proposal call returned
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.skill_management.skill_distillation_scheduler import (
    SkillDistillationScheduler,
    get_skill_distillation_scheduler,
)
from services.skill_management.skill_extractor import ExtractedSkill


def _skill(name: str = "deploy_service", confidence: float = 0.9) -> ExtractedSkill:
    return ExtractedSkill(
        name=name,
        description="Deploy a service to staging",
        inputs=[],
        outputs=[],
        procedure="Step 1: ...",
        preconditions=[],
        edge_cases=[],
        confidence=confidence,
    )


def _history(count: int = 6):
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}"} for i in range(count)]


class _FakeRedis:
    """Minimal async Redis stand-in for cursor and leader-lease calls."""

    def __init__(self) -> None:
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, nx=False, px=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def eval(self, *_args):
        # redis-py's EVAL (server-side Lua for the atomic lease refresh), not Python's
        # builtin eval. Nothing here executes caller-supplied code.
        return 1


@pytest.fixture
def redis():
    fake = _FakeRedis()
    with patch(
        "services.skill_management.skill_distillation_scheduler.get_async_redis_client",
        AsyncMock(return_value=fake),
    ):
        yield fake


def _make_scheduler(extractor=None, proposer=None) -> SkillDistillationScheduler:
    scheduler = SkillDistillationScheduler(extractor=extractor, proposer=proposer)
    scheduler._list_existing_skills = MagicMock(return_value=[])
    return scheduler


def _epoch(iso: str) -> float:
    """#13948: the cursor stores epoch seconds, not the ISO string.

    These tests assert which conversation the cursor names, not how it is
    serialised — comparing the stored bytes pinned a format that had to change,
    because ISO strings are naive local time and stop ordering at a DST fallback.
    """
    from datetime import datetime

    return datetime.fromisoformat(iso).timestamp()


def _stored_cursor(redis) -> float | None:
    from services.skill_management.skill_distillation_scheduler import _cursor_to_epoch

    return _cursor_to_epoch(redis.store.get("skills:distillation:cursor"))


def _with_sessions(scheduler, sessions, history=None):
    """Point the scheduler at a fake chat history manager."""
    manager = MagicMock()
    manager.list_sessions_fast = AsyncMock(return_value=sessions)
    manager.get_session_messages = AsyncMock(return_value=history if history is not None else _history())
    scheduler._get_chat_history_manager = AsyncMock(return_value=manager)
    return manager


class TestDistillationPass:
    """The pipeline is reached, once per new conversation."""

    @pytest.mark.asyncio
    async def test_new_conversations_are_extracted_and_proposed(self, redis):
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(return_value={"proposed": ["deploy_service"]})

        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(
            scheduler,
            [
                {"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"},
                {"id": "chat-b", "updatedAt": "2026-07-27T11:00:00"},
            ],
        )

        result = await scheduler.run_once()

        assert result["sessions_seen"] == 2
        assert result["sessions_distilled"] == 2
        assert extractor.extract_skills.await_count == 2
        assert proposer.propose_skills.await_count == 2
        assert result["proposed"] == ["deploy_service", "deploy_service"]

    @pytest.mark.asyncio
    async def test_already_distilled_conversations_are_skipped(self, redis):
        redis.store["skills:distillation:cursor"] = "2026-07-27T10:00:00"
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[])
        scheduler = _make_scheduler(extractor, MagicMock())
        _with_sessions(
            scheduler,
            [
                {"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"},  # at cursor
                {"id": "chat-b", "updatedAt": "2026-07-27T11:00:00"},  # after cursor
            ],
        )

        result = await scheduler.run_once()

        assert result["sessions_seen"] == 1
        assert extractor.extract_skills.await_count == 1

    @pytest.mark.asyncio
    async def test_short_conversation_is_not_sent_to_the_llm(self, redis):
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[])
        scheduler = _make_scheduler(extractor, MagicMock())
        _with_sessions(
            scheduler,
            [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}],
            history=_history(2),
        )

        result = await scheduler.run_once()

        extractor.extract_skills.assert_not_awaited()
        # Still counts as processed, so the cursor moves past it.
        assert result["sessions_distilled"] == 1

    @pytest.mark.asyncio
    async def test_no_extracted_skills_is_a_clean_outcome(self, redis):
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock()
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])

        result = await scheduler.run_once()

        proposer.propose_skills.assert_not_awaited()
        assert result["sessions_distilled"] == 1
        assert _stored_cursor(redis) == _epoch("2026-07-27T10:00:00")

    @pytest.mark.asyncio
    async def test_existing_skills_are_passed_as_prior_art(self, redis):
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[])
        scheduler = _make_scheduler(extractor, MagicMock())
        scheduler._list_existing_skills = MagicMock(return_value=[{"name": "deploy", "description": "d"}])
        _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])

        await scheduler.run_once()

        _history_arg, existing = extractor.extract_skills.await_args.args
        assert existing == [{"name": "deploy", "description": "d"}]


class TestDurableCursor:
    """The cursor never advances past work that did not land."""

    @pytest.mark.asyncio
    async def test_cursor_advances_only_after_a_successful_proposal(self, redis):
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(return_value={"proposed": ["deploy_service"]})
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])

        await scheduler.run_once()

        assert _stored_cursor(redis) == _epoch("2026-07-27T10:00:00")

    @pytest.mark.asyncio
    async def test_failed_proposal_leaves_the_cursor_untouched(self, redis):
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(side_effect=RuntimeError("SLM unreachable"))
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])

        result = await scheduler.run_once()

        assert result["sessions_distilled"] == 0
        assert "skills:distillation:cursor" not in redis.store

    @pytest.mark.asyncio
    async def test_failure_stops_the_pass_instead_of_skipping_ahead(self, redis):
        """A later conversation must not advance the cursor past a failed earlier one."""
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(
            side_effect=[RuntimeError("SLM unreachable"), {"proposed": ["later_skill"]}]
        )
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(
            scheduler,
            [
                {"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"},
                {"id": "chat-b", "updatedAt": "2026-07-27T11:00:00"},
            ],
        )

        result = await scheduler.run_once()

        assert result["sessions_distilled"] == 0
        assert proposer.propose_skills.await_count == 1
        assert "skills:distillation:cursor" not in redis.store

    @pytest.mark.asyncio
    async def test_partial_pass_keeps_the_last_successful_position(self, redis):
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(side_effect=[{"proposed": ["first"]}, RuntimeError("SLM unreachable")])
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(
            scheduler,
            [
                {"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"},
                {"id": "chat-b", "updatedAt": "2026-07-27T11:00:00"},
            ],
        )

        result = await scheduler.run_once()

        assert result["sessions_distilled"] == 1
        assert _stored_cursor(redis) == _epoch("2026-07-27T10:00:00")

    @pytest.mark.asyncio
    async def test_each_conversation_gets_its_own_position_not_the_first(self, redis):
        """#13925: the cursor must carry the position of the conversation just
        completed.

        The tests above assert the cursor *stops* correctly. None asserted the
        *value* written per conversation, so writing `pending[0]`'s timestamp
        every time — a plausible off-by-one — left the suite green while every
        conversation after the first was re-distilled on the next run, forever.
        """
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(return_value={"proposed": ["deploy_service"]})
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(
            scheduler,
            [
                {"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"},
                {"id": "chat-b", "updatedAt": "2026-07-27T11:00:00"},
                {"id": "chat-c", "updatedAt": "2026-07-27T12:00:00"},
            ],
        )

        await scheduler.run_once()

        assert _stored_cursor(redis) == _epoch("2026-07-27T12:00:00")

    @pytest.mark.asyncio
    async def test_the_cursor_advances_per_conversation_not_once_at_the_end(self, redis):
        """#13925: a crash mid-pass must leave the cursor on the last completed
        conversation, which only holds if it is written as the pass goes.

        Batching the write to the end of the loop passes every value-based
        assertion — the final cursor is identical — while losing the whole
        pass's progress to a crash. Only the write *sequence* distinguishes them.
        """
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(return_value={"proposed": ["deploy_service"]})
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(
            scheduler,
            [
                {"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"},
                {"id": "chat-b", "updatedAt": "2026-07-27T11:00:00"},
            ],
        )

        # Wrapped rather than replaced, so serialisation still runs for real.
        written: list[float] = []
        real_write = scheduler._write_cursor

        async def _recording(updated_at):
            written.append(updated_at)
            await real_write(updated_at)

        scheduler._write_cursor = _recording

        await scheduler.run_once()

        assert written == [_epoch("2026-07-27T10:00:00"), _epoch("2026-07-27T11:00:00")]
        assert _stored_cursor(redis) == _epoch("2026-07-27T11:00:00")

    @pytest.mark.asyncio
    async def test_an_empty_pass_leaves_the_cursor_alone(self, redis):
        """#13925: nothing pending must not touch the cursor. Writing a default
        would move it over unprocessed conversations."""
        scheduler = _make_scheduler(MagicMock(), MagicMock())
        _with_sessions(scheduler, [])

        result = await scheduler.run_once()

        assert result == {"sessions_seen": 0, "sessions_distilled": 0, "proposed": []}
        assert _stored_cursor(redis) is None


class TestLifecycle:
    """The feature ships inert and is process-wide."""

    @pytest.mark.asyncio
    async def test_start_is_a_noop_while_the_flag_is_off(self):
        scheduler = SkillDistillationScheduler()
        with patch("services.skill_management.skill_distillation_scheduler.DISTILLATION_ENABLED", False):
            started = await scheduler.start()
        assert started is False
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_start_spawns_the_leader_loop_when_enabled(self):
        scheduler = SkillDistillationScheduler()
        with (
            patch("services.skill_management.skill_distillation_scheduler.DISTILLATION_ENABLED", True),
            patch.object(scheduler, "_leader_loop", AsyncMock()),
        ):
            started = await scheduler.start()
            assert started is True
            assert scheduler._task is not None
            await scheduler.stop()
        assert scheduler._task is None

    def test_get_scheduler_is_a_singleton(self):
        assert get_skill_distillation_scheduler() is get_skill_distillation_scheduler()


class TestSchedulerRegistry:
    """A scheduler that is registered must also have a startup path (#12809, #12810)."""

    def test_distillation_job_is_registered(self):
        from services.scheduler_registry import REGISTRY

        job = next((j for j in REGISTRY if j.name == "SkillDistillationScheduler"), None)
        assert job is not None
        assert job.runtime == "leader_elected"
        assert job.owner_file == "services/skill_management/skill_distillation_scheduler.py"

    def test_lifespan_starts_the_registered_job(self):
        """Guards the failure mode where a job is registered, described, and never started."""
        from pathlib import Path

        lifespan = Path(__file__).resolve().parents[1] / "initialization" / "lifespan.py"
        source = lifespan.read_text(encoding="utf-8")
        assert "_init_skill_distillation_scheduler" in source
        assert "await _init_skill_distillation_scheduler(app)" in source
