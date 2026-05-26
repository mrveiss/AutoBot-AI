# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for GH#6628: error_boundaries severity-aware retry in agent loop.

Covers the acceptance criteria:
  - classify_error() returns correct ErrorSeverity for known error types
  - CRITICAL errors halt immediately (0 retries), no think-tool call
  - RETRY-class (LOW) errors respect their larger retry budget
  - Per-severity budgets are configurable in AgentLoopConfig
  - Backward compat: default budgets match legacy max_consecutive_errors for MEDIUM
  - fatal_reason appears in _build_result when a critical error fires
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig, LoopState, TaskContext
from utils.error_boundaries.types import (
    ErrorSeverity,
    classify_error,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop(**config_kwargs) -> AgentLoop:
    """Return an AgentLoop wired with minimal mock dependencies."""
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    think_tool = MagicMock()
    think_tool.think = AsyncMock(return_value=MagicMock())
    config = AgentLoopConfig(
        mandatory_think_enabled=False,  # disabled by default; override per-test
        **config_kwargs,
    )
    loop = AgentLoop(event_stream=event_stream, think_tool=think_tool, config=config)
    loop._current_context = TaskContext(task_id="t1", description="test")
    loop._state = LoopState.RUNNING
    return loop


# ---------------------------------------------------------------------------
# Unit: classify_error
# ---------------------------------------------------------------------------


class TestClassifyError:
    def test_retry_type_is_low(self):
        assert classify_error(ConnectionError()) is ErrorSeverity.LOW
        assert classify_error(TimeoutError()) is ErrorSeverity.LOW

    def test_critical_type(self):
        assert classify_error(MemoryError()) is ErrorSeverity.CRITICAL

    def test_high_severity_non_retry(self):
        # OSError is HIGH but not in RETRY_ERROR_TYPES
        assert classify_error(OSError()) is ErrorSeverity.HIGH

    def test_medium_severity(self):
        assert classify_error(ValueError()) is ErrorSeverity.MEDIUM
        assert classify_error(TypeError()) is ErrorSeverity.MEDIUM
        assert classify_error(AttributeError()) is ErrorSeverity.MEDIUM

    def test_unknown_error_is_low(self):
        assert classify_error(Exception("generic")) is ErrorSeverity.LOW


# ---------------------------------------------------------------------------
# Unit: _max_retries_for_severity
# ---------------------------------------------------------------------------


class TestMaxRetriesForSeverity:
    def test_defaults(self):
        loop = _make_loop()
        assert loop._max_retries_for_severity(ErrorSeverity.CRITICAL) == 0
        assert loop._max_retries_for_severity(ErrorSeverity.HIGH) == 1
        assert loop._max_retries_for_severity(ErrorSeverity.MEDIUM) == 3
        assert loop._max_retries_for_severity(ErrorSeverity.LOW) == 5

    def test_custom_config(self):
        loop = _make_loop(max_retries_low=10, max_retries_high=2)
        assert loop._max_retries_for_severity(ErrorSeverity.LOW) == 10
        assert loop._max_retries_for_severity(ErrorSeverity.HIGH) == 2


# ---------------------------------------------------------------------------
# Integration: critical error halts immediately, no retry
# ---------------------------------------------------------------------------


class TestCriticalErrorHalts:
    @pytest.mark.asyncio
    async def test_memory_error_halts_no_retry(self):
        loop = _make_loop()
        result = await loop._handle_iteration_error(MemoryError("OOM"))

        assert result is False
        assert loop._fatal_error is not None
        assert "MemoryError" in loop._fatal_reason
        assert loop._consecutive_errors == 0  # counter NOT incremented for CRITICAL

    @pytest.mark.asyncio
    async def test_critical_sets_should_continue_false(self):
        loop = _make_loop()
        await loop._handle_iteration_error(MemoryError("OOM"))
        assert loop._should_continue() is False

    @pytest.mark.asyncio
    async def test_critical_does_not_call_think_tool(self):
        loop = _make_loop(mandatory_think_enabled=True)
        await loop._handle_iteration_error(MemoryError("OOM"))
        loop.think_tool.think.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fatal_reason_in_build_result(self):
        loop = _make_loop()
        await loop._handle_iteration_error(MemoryError("OOM"))
        loop._state = LoopState.FAILED
        built = loop._build_result([])
        assert "fatal_reason" in built
        assert "MemoryError" in built["fatal_reason"]


# ---------------------------------------------------------------------------
# Integration: RETRY-class (LOW) errors respect larger budget
# ---------------------------------------------------------------------------


class TestRetryClassBudget:
    @pytest.mark.asyncio
    async def test_network_error_retries_up_to_low_budget(self):
        loop = _make_loop(max_retries_low=5)
        for i in range(1, 5):
            result = await loop._handle_iteration_error(ConnectionError("timeout"))
            assert result is True, f"Should still retry on attempt {i}"

        # 5th attempt exhausts budget
        result = await loop._handle_iteration_error(ConnectionError("timeout"))
        assert result is False

    @pytest.mark.asyncio
    async def test_fatal_reason_absent_when_budget_exhausted(self):
        """Budget exhaustion is not a fatal critical error — no fatal_reason."""
        loop = _make_loop(max_retries_low=1)
        await loop._handle_iteration_error(ConnectionError("net"))
        loop._state = LoopState.FAILED
        built = loop._build_result([])
        assert "fatal_reason" not in built


# ---------------------------------------------------------------------------
# Integration: backward compat — MEDIUM uses legacy default (3)
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    @pytest.mark.asyncio
    async def test_medium_error_retries_three_times(self):
        loop = _make_loop()
        for i in range(1, 3):
            result = await loop._handle_iteration_error(ValueError("bad value"))
            assert result is True

        # 3rd attempt exhausts MEDIUM budget (default=3)
        result = await loop._handle_iteration_error(ValueError("bad value"))
        assert result is False

    @pytest.mark.asyncio
    async def test_existing_tests_pass_with_default_medium_config(self):
        """Verify max_consecutive_errors=3 default is preserved as MEDIUM budget."""
        config = AgentLoopConfig()
        assert config.max_retries_medium == 3
        assert config.max_consecutive_errors == 3


# ---------------------------------------------------------------------------
# Integration: fallback hook called for FALLBACK_ERROR_TYPES
# ---------------------------------------------------------------------------


class TestFallbackHook:
    @pytest.mark.asyncio
    async def test_fallback_strategy_called_for_fallback_error(self):
        loop = _make_loop()
        with patch.object(loop, "_try_fallback_strategy", new_callable=AsyncMock) as mock_fallback:
            await loop._handle_iteration_error(ValueError("val"))
            mock_fallback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fallback_strategy_not_called_for_high_error(self):
        loop = _make_loop()
        with patch.object(loop, "_try_fallback_strategy", new_callable=AsyncMock) as mock_fallback:
            await loop._handle_iteration_error(OSError("disk"))
            mock_fallback.assert_not_awaited()
