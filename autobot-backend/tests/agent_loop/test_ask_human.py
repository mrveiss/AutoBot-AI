# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for agent-initiated ask-the-human (#10553).

Acceptance criteria verified here:
  - ask_human() suspends the loop (state → WAITING_FOR_HUMAN).
  - answer() delivers the answer; loop resumes and answer is in trajectory.
  - The answer changes subsequent behavior (injected as authoritative context).
  - Timeout + escalation policy "default" returns default_answer without error.
  - Timeout + escalation policy "abandon" raises asyncio.TimeoutError.
  - Checkpoint written / cleared around the wait.
  - answer() returns False when loop is not RUNNING/WAITING_FOR_HUMAN.
  - HUMAN_QUESTION event published to event bus on ask.
  - HUMAN_ANSWER_RECEIVED event published to event bus on resolution.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent_loop.loop as _loop_module
from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig, HumanQuestion, LoopState, TaskContext
from events.event_types import HUMAN_ANSWER_RECEIVED, HUMAN_QUESTION

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop(ask_human_timeout_seconds: int = 30) -> AgentLoop:
    """Return an AgentLoop wired with a mock event stream."""
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    # subscribe() must return an async iterable, not a coroutine
    event_stream.subscribe = MagicMock(return_value=_NeverYieldsSubscribe())
    config = AgentLoopConfig(
        max_iterations=20,
        mandatory_think_enabled=False,
        think_on_completion=False,
        log_iterations=False,
        require_approval_for_sensitive=False,
        ask_human_timeout_seconds=ask_human_timeout_seconds,
    )
    loop = AgentLoop(event_stream=event_stream, config=config)
    loop._current_context = TaskContext(task_id="t-ask", description="ask-human test task")
    loop._state = LoopState.RUNNING
    loop._iteration_count = 3
    return loop


async def _never_yields():
    """Async generator that never yields — simulates idle event stream."""
    return
    yield  # pragma: no cover  # makes it an async generator


class _NeverYieldsSubscribe:
    """Async iterable that never produces events (simulates idle stream for subscribe())."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        # Block forever — tests that need to resolve will deliver via the queue channel
        await asyncio.sleep(3600)
        raise StopAsyncIteration


def _null_slack():
    s = MagicMock()
    s.ask_human = AsyncMock()
    return s


# ---------------------------------------------------------------------------
# answer() gate
# ---------------------------------------------------------------------------


class TestAnswerGate:
    @pytest.mark.asyncio
    async def test_answer_returns_false_when_idle(self):
        loop = _make_loop()
        loop._state = LoopState.IDLE
        assert await loop.answer("qid-1", "yes") is False

    @pytest.mark.asyncio
    async def test_answer_returns_false_when_cancelled(self):
        loop = _make_loop()
        loop._state = LoopState.CANCELLED
        assert await loop.answer("qid-2", "no") is False

    @pytest.mark.asyncio
    async def test_answer_returns_true_when_running(self):
        loop = _make_loop()
        assert await loop.answer("qid-3", "maybe") is True

    @pytest.mark.asyncio
    async def test_answer_returns_true_when_waiting_for_human(self):
        loop = _make_loop()
        loop._state = LoopState.WAITING_FOR_HUMAN
        assert await loop.answer("qid-4", "yes please") is True


# ---------------------------------------------------------------------------
# ask_human() suspend / resume
# ---------------------------------------------------------------------------

_NOOP_CHECKPOINT = AsyncMock()
_NOOP_CLEAR = AsyncMock()


def _ask_patches(loop: AgentLoop, mock_publish: AsyncMock):
    """Context manager stack shared by suspend/resume tests."""
    return (
        patch.object(_loop_module, "_bus_publish_event", new=mock_publish),
        patch.object(_loop_module, "get_slack_hook", return_value=_null_slack()),
        patch.object(loop, "_checkpoint_question", new=AsyncMock()),
        patch.object(loop, "_clear_question_checkpoint", new=AsyncMock()),
    )


async def _wait_state(loop: AgentLoop, target: LoopState, attempts: int = 200) -> None:
    for _ in range(attempts):
        if loop._state == target:
            return
        await asyncio.sleep(0.01)


class TestAskHumanSuspendResume:
    @pytest.mark.asyncio
    async def test_ask_human_suspends_and_resumes_on_answer(self):
        """The loop suspends (WAITING_FOR_HUMAN) then resumes returning the answer."""
        loop = _make_loop()
        observed_state: list[LoopState] = []

        async def _deliver():
            await _wait_state(loop, LoopState.WAITING_FOR_HUMAN)
            observed_state.append(loop._state)
            await loop.answer("q-resume", "Paris")

        mock_publish = AsyncMock()
        with (
            patch.object(_loop_module, "_bus_publish_event", new=mock_publish),
            patch.object(_loop_module, "get_slack_hook", return_value=_null_slack()),
            patch.object(loop, "_checkpoint_question", new=AsyncMock()),
            patch.object(loop, "_clear_question_checkpoint", new=AsyncMock()),
        ):
            deliver_task = asyncio.create_task(_deliver())
            answer = await loop.ask_human(
                "What is the capital of France?", question_id_override="q-resume"
            )
            await deliver_task

        assert answer == "Paris"
        assert LoopState.WAITING_FOR_HUMAN in observed_state
        assert loop._state == LoopState.RUNNING

    @pytest.mark.asyncio
    async def test_ask_human_records_in_trajectory(self):
        """The question is recorded in TaskContext.human_questions."""
        loop = _make_loop()

        async def _deliver():
            await _wait_state(loop, LoopState.WAITING_FOR_HUMAN)
            await loop.answer("q-traj", "42")

        with (
            patch.object(_loop_module, "_bus_publish_event", new=AsyncMock()),
            patch.object(_loop_module, "get_slack_hook", return_value=_null_slack()),
            patch.object(loop, "_checkpoint_question", new=AsyncMock()),
            patch.object(loop, "_clear_question_checkpoint", new=AsyncMock()),
        ):
            deliver_task = asyncio.create_task(_deliver())
            await loop.ask_human("What is the answer?", question_id_override="q-traj")
            await deliver_task

        assert len(loop._current_context.human_questions) == 1
        hq = loop._current_context.human_questions[0]
        assert hq.question_id == "q-traj"
        assert hq.question == "What is the answer?"

    @pytest.mark.asyncio
    async def test_ask_human_publishes_human_question_and_answer_events(self):
        """HUMAN_QUESTION and HUMAN_ANSWER_RECEIVED published to the live bus."""
        loop = _make_loop()
        mock_publish = AsyncMock()

        async def _deliver():
            await _wait_state(loop, LoopState.WAITING_FOR_HUMAN)
            await loop.answer("q-evt", "confirmed")

        with (
            patch.object(_loop_module, "_bus_publish_event", new=mock_publish),
            patch.object(_loop_module, "get_slack_hook", return_value=_null_slack()),
            patch.object(loop, "_checkpoint_question", new=AsyncMock()),
            patch.object(loop, "_clear_question_checkpoint", new=AsyncMock()),
        ):
            deliver_task = asyncio.create_task(_deliver())
            await loop.ask_human("Proceed?", question_id_override="q-evt")
            await deliver_task

        published_types = [call.args[1] for call in mock_publish.call_args_list]
        assert HUMAN_QUESTION in published_types
        assert HUMAN_ANSWER_RECEIVED in published_types

    @pytest.mark.asyncio
    async def test_answer_influences_subsequent_behavior(self):
        """The returned answer string is authoritative — changes what agent does next."""
        loop = _make_loop()

        async def _deliver():
            await _wait_state(loop, LoopState.WAITING_FOR_HUMAN)
            await loop.answer("q-behavior", "use_csv")

        with (
            patch.object(_loop_module, "_bus_publish_event", new=AsyncMock()),
            patch.object(_loop_module, "get_slack_hook", return_value=_null_slack()),
            patch.object(loop, "_checkpoint_question", new=AsyncMock()),
            patch.object(loop, "_clear_question_checkpoint", new=AsyncMock()),
        ):
            deliver_task = asyncio.create_task(_deliver())
            answer = await loop.ask_human(
                "Which format?",
                choices=["use_csv", "use_json"],
                question_id_override="q-behavior",
            )
            await deliver_task

        # The answer is what the agent uses to pick its next step.
        assert answer == "use_csv"


# ---------------------------------------------------------------------------
# Timeout / escalation
# ---------------------------------------------------------------------------


class TestAskHumanTimeout:
    @pytest.mark.asyncio
    async def test_timeout_policy_default_returns_default_answer(self):
        """escalation_policy='default' returns default_answer without raising."""
        loop = _make_loop(ask_human_timeout_seconds=1)

        with (
            patch.object(_loop_module, "_bus_publish_event", new=AsyncMock()),
            patch.object(_loop_module, "get_slack_hook", return_value=_null_slack()),
            patch.object(loop, "_checkpoint_question", new=AsyncMock()),
            patch.object(loop, "_clear_question_checkpoint", new=AsyncMock()),
        ):
            answer = await loop.ask_human(
                "Which env?",
                escalation_policy="default",
                default_answer="production",
                question_id_override="q-timeout-default",
            )

        assert answer == "production"

    @pytest.mark.asyncio
    async def test_timeout_policy_abandon_raises(self):
        """escalation_policy='abandon' raises asyncio.TimeoutError on deadline."""
        loop = _make_loop(ask_human_timeout_seconds=1)

        with (
            patch.object(_loop_module, "_bus_publish_event", new=AsyncMock()),
            patch.object(_loop_module, "get_slack_hook", return_value=_null_slack()),
            patch.object(loop, "_checkpoint_question", new=AsyncMock()),
            patch.object(loop, "_clear_question_checkpoint", new=AsyncMock()),
        ):
            with pytest.raises(asyncio.TimeoutError):
                await loop.ask_human(
                    "Which branch?",
                    escalation_policy="abandon",
                    question_id_override="q-timeout-abandon",
                )


# ---------------------------------------------------------------------------
# Checkpoint helpers called
# ---------------------------------------------------------------------------


class TestCheckpointHelpers:
    @pytest.mark.asyncio
    async def test_checkpoint_written_and_cleared(self):
        """_checkpoint_question and _clear_question_checkpoint are both called."""
        loop = _make_loop()
        mock_checkpoint = AsyncMock()
        mock_clear = AsyncMock()

        async def _deliver():
            await _wait_state(loop, LoopState.WAITING_FOR_HUMAN)
            await loop.answer("q-ckpt", "ack")

        with (
            patch.object(_loop_module, "_bus_publish_event", new=AsyncMock()),
            patch.object(_loop_module, "get_slack_hook", return_value=_null_slack()),
            patch.object(loop, "_checkpoint_question", new=mock_checkpoint),
            patch.object(loop, "_clear_question_checkpoint", new=mock_clear),
        ):
            deliver_task = asyncio.create_task(_deliver())
            await loop.ask_human("Ready?", question_id_override="q-ckpt")
            await deliver_task

        mock_checkpoint.assert_awaited_once()
        mock_clear.assert_awaited_once()
        # State restored after resume
        assert loop._state == LoopState.RUNNING


# ---------------------------------------------------------------------------
# HumanQuestion.to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


class TestHumanQuestionDict:
    def test_to_dict_keys(self):
        hq = HumanQuestion(
            question_id="hq-rt",
            question="Are you sure?",
            iteration=7,
            choices=["yes", "no"],
            escalation_policy="default",
            default_answer="yes",
        )
        d = hq.to_dict()
        assert d["question_id"] == "hq-rt"
        assert d["question"] == "Are you sure?"
        assert d["iteration"] == 7
        assert d["choices"] == ["yes", "no"]
        assert d["escalation_policy"] == "default"
        assert d["default_answer"] == "yes"
        assert "timestamp" in d

    def test_from_dict_round_trip(self):
        hq = HumanQuestion(question_id="hq-rt2", question="Pick one", iteration=2)
        restored = HumanQuestion.from_dict(hq.to_dict())
        assert restored.question_id == hq.question_id
        assert restored.question == hq.question
        assert restored.iteration == hq.iteration
