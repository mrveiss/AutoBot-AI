# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for subagent dispatcher reflection pass (#4691).

Covers:
- Reflection disabled → original result returned unchanged
- Score >= threshold → original result returned unchanged
- Score < threshold → revised result returned
- LLM service unavailable → original result returned (graceful degradation)
- No regression on existing parallel dispatch flow
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestration.subagent_dispatcher import (
    SubagentDispatcher,
    SubagentTask,
    get_subagent_dispatcher,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    return resp


def _score_response(score: float, gaps: list) -> MagicMock:
    return _make_llm_response(json.dumps({"score": score, "gaps": gaps}))


# ---------------------------------------------------------------------------
# SubagentTask defaults
# ---------------------------------------------------------------------------


class TestSubagentTaskDefaults:
    def test_reflection_disabled_by_default(self):
        task = SubagentTask(task_id="t1", func=lambda: None)
        assert task.enable_reflection is False

    def test_reflection_threshold_default(self):
        task = SubagentTask(task_id="t1", func=lambda: None)
        assert task.reflection_threshold == 0.7

    def test_enable_reflection_flag(self):
        task = SubagentTask(
            task_id="t1",
            func=lambda: None,
            enable_reflection=True,
            reflection_threshold=0.8,
        )
        assert task.enable_reflection is True
        assert task.reflection_threshold == 0.8


# ---------------------------------------------------------------------------
# Reflection pass disabled → original result
# ---------------------------------------------------------------------------


class TestReflectionDisabled:
    @pytest.mark.asyncio
    async def test_disabled_skips_reflection(self):
        """enable_reflection=False → _reflection_pass never called."""
        orch = SubagentDispatcher()

        async def my_func():
            return "original"

        task = SubagentTask(task_id="t1", func=my_func, enable_reflection=False)

        with patch.object(orch, "_reflection_pass", new_callable=AsyncMock) as mock_rp:
            result = await orch._execute_task(task)

        mock_rp.assert_not_called()
        assert result == "original"


# ---------------------------------------------------------------------------
# Reflection: high score → original returned
# ---------------------------------------------------------------------------


class TestReflectionHighScore:
    @pytest.mark.asyncio
    async def test_high_score_returns_original(self):
        """Score >= threshold → original result returned unchanged."""
        orch = SubagentDispatcher()

        async def my_func():
            return "original result"

        task = SubagentTask(
            task_id="t1",
            func=my_func,
            enable_reflection=True,
            reflection_threshold=0.7,
            task_description="Summarise the document.",
        )

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=_score_response(0.9, []))

        with patch("orchestration.subagent_dispatcher._get_llm_service", return_value=mock_llm):
            result = await orch._execute_task(task)

        assert result == "original result"
        # Only the scoring call should have been made; no revision call.
        assert mock_llm.chat.call_count == 1


# ---------------------------------------------------------------------------
# Reflection: low score → revised result returned
# ---------------------------------------------------------------------------


class TestReflectionLowScore:
    @pytest.mark.asyncio
    async def test_low_score_returns_revised(self):
        """Score < threshold → one revision call, revised result returned."""
        orch = SubagentDispatcher()

        async def my_func():
            return "incomplete result"

        task = SubagentTask(
            task_id="t1",
            func=my_func,
            enable_reflection=True,
            reflection_threshold=0.7,
            task_description="Analyse all data points.",
        )

        mock_llm = MagicMock()
        score_resp = _score_response(0.4, ["Missing section A", "Missing conclusion"])
        revision_resp = _make_llm_response("revised and complete result")
        mock_llm.chat = AsyncMock(side_effect=[score_resp, revision_resp])

        with patch(
            "orchestration.subagent_dispatcher._get_llm_service",
            return_value=mock_llm,
        ):
            result = await orch._execute_task(task)

        assert result == "revised and complete result"
        assert mock_llm.chat.call_count == 2  # score + revision

    @pytest.mark.asyncio
    async def test_exactly_at_threshold_is_not_revised(self):
        """Score == threshold is treated as passing (>= check)."""
        orch = SubagentDispatcher()

        async def my_func():
            return "borderline result"

        task = SubagentTask(
            task_id="t1",
            func=my_func,
            enable_reflection=True,
            reflection_threshold=0.7,
            task_description="Write a summary.",
        )

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=_score_response(0.7, ["minor gap"]))

        with patch(
            "orchestration.subagent_dispatcher._get_llm_service",
            return_value=mock_llm,
        ):
            result = await orch._execute_task(task)

        assert result == "borderline result"
        assert mock_llm.chat.call_count == 1  # no revision


# ---------------------------------------------------------------------------
# Reflection: LLM unavailable → graceful degradation
# ---------------------------------------------------------------------------


class TestReflectionLLMUnavailable:
    @pytest.mark.asyncio
    async def test_llm_import_error_returns_original(self):
        """LLM service unavailable → original result returned without error."""
        orch = SubagentDispatcher()

        async def my_func():
            return "original"

        task = SubagentTask(
            task_id="t1",
            func=my_func,
            enable_reflection=True,
            task_description="Some task.",
        )

        with patch(
            "orchestration.subagent_dispatcher._get_llm_service",
            side_effect=ImportError("no llm"),
        ):
            result = await orch._execute_task(task)

        assert result == "original"

    @pytest.mark.asyncio
    async def test_scoring_exception_returns_original(self):
        """Scoring LLM call raises → original result returned (score assumed 1.0)."""
        orch = SubagentDispatcher()

        async def my_func():
            return "original"

        task = SubagentTask(
            task_id="t1",
            func=my_func,
            enable_reflection=True,
            task_description="Some task.",
        )

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(side_effect=RuntimeError("llm error"))

        with patch(
            "orchestration.subagent_dispatcher._get_llm_service",
            return_value=mock_llm,
        ):
            result = await orch._execute_task(task)

        assert result == "original"


# ---------------------------------------------------------------------------
# No regression: existing parallel dispatch flow
# ---------------------------------------------------------------------------


class TestParallelDispatchNoRegression:
    @pytest.mark.asyncio
    async def test_spawn_parallel_tasks_no_reflection(self):
        """Parallel dispatch works correctly when reflection is disabled."""
        orch = SubagentDispatcher(max_parallel=3)
        call_order = []

        async def make_func(val):
            async def func():
                await asyncio.sleep(0)
                call_order.append(val)
                return val

            return func

        tasks = [
            SubagentTask(
                task_id=f"t{i}",
                func=await make_func(i),
                enable_reflection=False,
            )
            for i in range(3)
        ]

        results = await orch.spawn_parallel_tasks(tasks)

        assert len(results) == 3
        assert results["t0"] == 0
        assert results["t1"] == 1
        assert results["t2"] == 2

    @pytest.mark.asyncio
    async def test_spawn_parallel_honours_max_parallel(self):
        """max_parallel caps concurrency, not total task count.

        All tasks are processed; at most max_parallel run simultaneously.
        """
        import asyncio as _asyncio

        max_parallel = 2
        peak = 0
        active = 0

        orch = SubagentDispatcher(max_parallel=max_parallel)

        async def my_func():
            nonlocal peak, active
            active += 1
            peak = max(peak, active)
            await _asyncio.sleep(0.01)
            active -= 1
            return "ok"

        tasks = [SubagentTask(task_id=f"t{i}", func=my_func) for i in range(4)]
        results = await orch.spawn_parallel_tasks(tasks)

        # All 4 tasks complete (no truncation)
        assert len(results) == 4
        # Concurrency was bounded
        assert peak <= max_parallel

    @pytest.mark.asyncio
    async def test_task_exception_propagates_as_exception_result(self):
        """A failing task result is stored as an exception (existing behaviour)."""
        orch = SubagentDispatcher()

        async def bad_func():
            raise ValueError("boom")

        task = SubagentTask(task_id="bad", func=bad_func)
        results = await orch.spawn_parallel_tasks([task])
        assert isinstance(results["bad"], ValueError)


# ---------------------------------------------------------------------------
# get_subagent_orchestrator singleton
# ---------------------------------------------------------------------------


class TestGetSubagentDispatcher:
    def test_returns_singleton(self):
        import orchestration.subagent_dispatcher as mod

        mod._orchestrator_instance = None  # reset
        a = get_subagent_dispatcher()
        b = get_subagent_dispatcher()
        assert a is b

    def test_custom_max_parallel(self):
        import orchestration.subagent_dispatcher as mod

        mod._orchestrator_instance = None
        orch = get_subagent_dispatcher(max_parallel=5)
        assert orch.max_parallel == 5
        mod._orchestrator_instance = None  # clean up
