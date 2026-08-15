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

    # #14255: the failure counter. Stateful rather than a MagicMock, because
    # "counted" and "never written" are indistinguishable to a mock, and the
    # whole mechanism is a count crossing a threshold.
    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, _ttl):
        return key in self.store

    async def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0


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
    # #14077: distillation reads via `load_session`, not the wrapper — the
    # wrapper swallows PermissionError/ValueError into [] (see #1906).
    manager.load_session = AsyncMock(return_value=history if history is not None else _history())
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

        assert result == {"sessions_seen": 0, "sessions_distilled": 0, "proposed": [], "quarantined": 0}
        assert _stored_cursor(redis) is None


class TestAnUnreadableConversationIsNotProcessed:
    """#14077: `_load_history` returned `[]` both for *nothing to distil* and
    for *could not read it*, so the caller advanced the cursor past
    conversations it had never opened — and reported them as distilled.

    Driven through `run_once` against the real cursor, because the defect is in
    what the cursor does, not in what the loader returns.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "failure",
        [PermissionError("chat file unreadable"), ValueError("could not decrypt session")],
        ids=["permission-denied", "corrupted"],
    )
    async def test_an_unreadable_session_file_stops_the_pass(self, redis, failure):
        """The production case: the manager is healthy, one file cannot be read.

        This is what `get_session_messages` swallowed into `[]` — #1906 built
        `load_session` to raise here *precisely* so a caller could tell this
        apart from an empty conversation, and routing through the wrapper threw
        that away.

        Parametrised over both exception types the wrapper catches, since a fix
        covering one and not the other would look identical from outside.
        """
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(return_value={"proposed": ["deploy_service"]})
        scheduler = _make_scheduler(extractor, proposer)
        manager = _with_sessions(
            scheduler,
            [
                {"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"},
                {"id": "chat-b", "updatedAt": "2026-07-27T11:00:00"},
            ],
        )
        # One healthy manager throughout, as production has. Only the read fails.
        manager.load_session = AsyncMock(side_effect=failure)

        result = await scheduler.run_once()

        assert _stored_cursor(redis) is None, "cursor advanced past a conversation nobody read"
        assert result["sessions_distilled"] == 0, "unread conversations must not report as distilled"

    @pytest.mark.asyncio
    async def test_an_unavailable_manager_stops_the_pass_and_holds_the_cursor(self, redis):
        """The narrower case that started this issue."""
        scheduler = _make_scheduler(MagicMock(), MagicMock())
        _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])
        manager = scheduler._get_chat_history_manager.return_value
        scheduler._get_chat_history_manager = AsyncMock(side_effect=[manager, None, None])

        result = await scheduler.run_once()

        assert _stored_cursor(redis) is None
        assert result["sessions_distilled"] == 0

    @pytest.mark.asyncio
    async def test_a_genuinely_short_conversation_still_advances(self, redis):
        """The case that must STAY working — a fix that stopped on every empty
        history would re-offer short conversations forever."""
        extractor = MagicMock()
        proposer = MagicMock()
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(
            scheduler,
            [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}],
            history=[{"role": "user", "content": "hi"}],
        )

        await scheduler.run_once()

        assert _stored_cursor(redis) == _epoch("2026-07-27T10:00:00")


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


class TestQuarantineAfterRepeatedFailures:
    """#14255: a conversation that cannot be read must not starve the queue.

    The pass stops on a failure so a transient fault costs nothing — that is
    right, and `test_failure_stops_the_pass_instead_of_skipping_ahead` pins it.
    But an oldest-first queue plus a cursor that never advances means a
    permanently unreadable conversation re-sorts to the front every run and
    blocks every newer one, with silence as the only symptom.

    Both directions are asserted here on purpose. A fix that only proves
    "eventually skips" turns the scheduler into "skip everything that errors",
    which is the defect #14247 removed.
    """

    async def test_a_transient_failure_still_stops_the_pass(self, redis):
        """One failure is not evidence of anything. The cursor must hold."""
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(side_effect=RuntimeError("SLM unreachable"))
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])

        result = await scheduler.run_once()

        assert result["sessions_distilled"] == 0
        assert result["quarantined"] == 0
        assert _stored_cursor(redis) is None

    async def test_the_same_conversation_is_quarantined_once_it_keeps_failing(self, redis):
        """After MAX_CONSECUTIVE_FAILURES passes, the queue moves on."""
        from services.skill_management.skill_distillation_scheduler import MAX_CONSECUTIVE_FAILURES

        for _ in range(MAX_CONSECUTIVE_FAILURES):
            extractor = MagicMock()
            extractor.extract_skills = AsyncMock(return_value=[_skill()])
            proposer = MagicMock()
            proposer.propose_skills = AsyncMock(side_effect=RuntimeError("corrupt history"))
            scheduler = _make_scheduler(extractor, proposer)
            _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])
            result = await scheduler.run_once()

        assert result["quarantined"] == 1
        assert _stored_cursor(redis) is not None, "the cursor must advance past a quarantined session"

    async def test_a_newer_conversation_is_reached_after_a_quarantine(self, redis):
        """The point of the escape hatch: healthy work behind the blockage runs."""
        from services.skill_management.skill_distillation_scheduler import MAX_CONSECUTIVE_FAILURES

        redis.store[f"skills:distillation:failures:chat-a"] = MAX_CONSECUTIVE_FAILURES - 1
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(
            side_effect=[RuntimeError("corrupt history"), {"proposed": ["later_skill"]}]
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

        assert result["quarantined"] == 1
        assert result["sessions_distilled"] == 1
        assert "later_skill" in result["proposed"]

    async def test_a_success_forgets_earlier_failures(self, redis):
        """Otherwise the count is cumulative, and a conversation that fails
        intermittently over months is eventually quarantined despite always
        recovering."""
        from services.skill_management.skill_distillation_scheduler import MAX_CONSECUTIVE_FAILURES

        redis.store["skills:distillation:failures:chat-a"] = MAX_CONSECUTIVE_FAILURES - 1
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(return_value={"proposed": ["a_skill"]})
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])

        await scheduler.run_once()

        assert "skills:distillation:failures:chat-a" not in redis.store

    async def test_quarantining_is_announced_not_silent(self, redis, caplog):
        """A silent skip would reinstate the defect #14247 removed — a
        conversation reported as handled when it was not — one level up."""
        from services.skill_management.skill_distillation_scheduler import MAX_CONSECUTIVE_FAILURES

        redis.store["skills:distillation:failures:chat-a"] = MAX_CONSECUTIVE_FAILURES - 1
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(side_effect=RuntimeError("corrupt history"))
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])

        with caplog.at_level("WARNING"):
            await scheduler.run_once()

        assert any("quarantin" in record.message.lower() for record in caplog.records)
        assert any("chat-a" in str(record.args) for record in caplog.records)

    async def test_an_unavailable_redis_stops_the_pass_rather_than_quarantining(self, monkeypatch):
        """Without a durable count there is no evidence anything is unrecoverable.

        A Redis outage would otherwise quarantine every failing conversation at
        once — turning an infrastructure blip into permanent data loss, which is
        far worse than the head-of-line block this mechanism exists to prevent.
        Fail closed: the pass stops, which is the pre-#14255 behaviour.

        This is the direction a mutation caught: returning True on `redis is
        None` left all 22 other tests green, because every one of them has a
        working fake.
        """
        import services.skill_management.skill_distillation_scheduler as mod

        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(side_effect=RuntimeError("corrupt history"))
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(
            scheduler,
            [
                {"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"},
                {"id": "chat-b", "updatedAt": "2026-07-27T11:00:00"},
            ],
        )
        monkeypatch.setattr(mod, "get_async_redis_client", AsyncMock(return_value=None))

        result = await scheduler.run_once()

        assert result["quarantined"] == 0
        assert result["sessions_distilled"] == 0
        assert proposer.propose_skills.await_count == 1, "the pass continued past the failure"

    async def test_the_summary_shape_is_the_same_on_both_paths(self, redis):
        """An empty pass is the common case. A caller reading
        result["quarantined"] must not KeyError on it — and an equality
        assertion on the busy path alone would never notice."""
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(return_value={"proposed": ["a_skill"]})

        empty = _make_scheduler(extractor, proposer)
        _with_sessions(empty, [])
        busy = _make_scheduler(extractor, proposer)
        _with_sessions(busy, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])

        assert set((await empty.run_once())) == set((await busy.run_once()))

    async def test_a_quarantined_conversation_gets_a_fresh_budget_if_it_returns(self, redis):
        """The counter must not survive the quarantine that consumed it.

        The queue is keyed on updated_at, so an edited conversation re-enters it.
        Left at the threshold, its FIRST new failure would quarantine it again —
        the opposite of "N failures is evidence, one is not", and unfair to
        exactly the conversation someone just repaired.
        """
        from services.skill_management.skill_distillation_scheduler import MAX_CONSECUTIVE_FAILURES

        redis.store["skills:distillation:failures:chat-a"] = MAX_CONSECUTIVE_FAILURES - 1
        extractor = MagicMock()
        extractor.extract_skills = AsyncMock(return_value=[_skill()])
        proposer = MagicMock()
        proposer.propose_skills = AsyncMock(side_effect=RuntimeError("corrupt history"))
        scheduler = _make_scheduler(extractor, proposer)
        _with_sessions(scheduler, [{"id": "chat-a", "updatedAt": "2026-07-27T10:00:00"}])

        result = await scheduler.run_once()

        assert result["quarantined"] == 1
        assert (
            "skills:distillation:failures:chat-a" not in redis.store
        ), "the count survived the quarantine, so one more failure would re-quarantine immediately"
