# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for error_handler.py.

Issue #2154: Resume-from-failure and step-level error handlers.

Coverage
--------
- StepErrorHandler: retry with linear/exponential backoff, skip, fallback, pause, abort
- WorkflowCheckpointManager: save/load/clear round-trip (Redis mocked)
- WorkflowExecutor integration: checkpoint skip, error config wired in
"""

from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestration.error_handler import (
    BackoffStrategy,
    StepCheckpoint,
    StepErrorAction,
    StepErrorConfig,
    StepErrorHandler,
    WorkflowCheckpointManager,
)
from orchestration.workflow_executor import WorkflowExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor(**kwargs) -> WorkflowExecutor:
    """Build a WorkflowExecutor with no-op callbacks."""
    return WorkflowExecutor(
        agent_registry={},
        agent_interactions=[],
        reserve_agent_callback=lambda _: None,
        release_agent_callback=lambda _: None,
        update_performance_callback=lambda _agent, _ok, _t: None,
        **kwargs,
    )


def _make_step(step_id: str, error_config: Optional[StepErrorConfig] = None) -> Dict[str, Any]:
    return {
        "id": step_id,
        "action": "test_action",
        "inputs": {},
        "assigned_agent": None,
        **({"error_config": error_config} if error_config else {}),
    }


# ---------------------------------------------------------------------------
# StepErrorHandler — RETRY
# ---------------------------------------------------------------------------


class TestStepErrorHandlerRetry:
    @pytest.mark.asyncio
    async def test_retry_within_limit_returns_continue(self):
        handler = StepErrorHandler()
        config = StepErrorConfig(
            action=StepErrorAction.RETRY,
            max_retries=3,
            base_delay=0.0,
            backoff=BackoffStrategy.EXPONENTIAL,
        )
        result = await handler.handle_error("s1", RuntimeError("boom"), config, attempt=1)
        assert result.action == StepErrorAction.RETRY
        assert result.should_continue is True

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_abort(self):
        handler = StepErrorHandler()
        config = StepErrorConfig(
            action=StepErrorAction.RETRY,
            max_retries=2,
            base_delay=0.0,
        )
        result = await handler.handle_error("s1", RuntimeError("boom"), config, attempt=3)
        assert result.action == StepErrorAction.ABORT
        assert result.should_continue is False

    @pytest.mark.asyncio
    async def test_linear_backoff_delay(self):
        """Linear delay for attempt 3 with base 1.0 should be 3.0 s."""
        config = StepErrorConfig(
            action=StepErrorAction.RETRY,
            max_retries=5,
            base_delay=1.0,
            backoff=BackoffStrategy.LINEAR,
        )
        delay = StepErrorHandler._compute_delay(config, attempt=3)
        assert delay == 3.0

    @pytest.mark.asyncio
    async def test_exponential_backoff_delay(self):
        """Exponential delay for attempt 4 with base 1.0 should be 8.0 s."""
        config = StepErrorConfig(
            action=StepErrorAction.RETRY,
            max_retries=5,
            base_delay=1.0,
            backoff=BackoffStrategy.EXPONENTIAL,
        )
        delay = StepErrorHandler._compute_delay(config, attempt=4)
        assert delay == 8.0

    @pytest.mark.asyncio
    async def test_delay_capped_at_60(self):
        config = StepErrorConfig(
            action=StepErrorAction.RETRY,
            max_retries=20,
            base_delay=1.0,
            backoff=BackoffStrategy.EXPONENTIAL,
        )
        delay = StepErrorHandler._compute_delay(config, attempt=15)
        assert delay == 60.0


# ---------------------------------------------------------------------------
# StepErrorHandler — SKIP / FALLBACK / PAUSE / ABORT
# ---------------------------------------------------------------------------


class TestStepErrorHandlerOtherActions:
    @pytest.mark.asyncio
    async def test_skip_returns_continue(self):
        handler = StepErrorHandler()
        result = await handler.handle_error(
            "s2", ValueError("bad"), StepErrorConfig(action=StepErrorAction.SKIP)
        )
        assert result.action == StepErrorAction.SKIP
        assert result.should_continue is True

    @pytest.mark.asyncio
    async def test_fallback_with_target(self):
        handler = StepErrorHandler()
        config = StepErrorConfig(
            action=StepErrorAction.FALLBACK, fallback_step_id="step_recovery"
        )
        result = await handler.handle_error("s3", OSError("disk"), config)
        assert result.action == StepErrorAction.FALLBACK
        assert result.should_continue is True
        assert result.fallback_step_id == "step_recovery"

    @pytest.mark.asyncio
    async def test_fallback_without_target_becomes_abort(self):
        handler = StepErrorHandler()
        config = StepErrorConfig(action=StepErrorAction.FALLBACK, fallback_step_id=None)
        result = await handler.handle_error("s3", OSError("disk"), config)
        assert result.action == StepErrorAction.ABORT
        assert result.should_continue is False

    @pytest.mark.asyncio
    async def test_pause_stops_continuation(self):
        handler = StepErrorHandler()
        result = await handler.handle_error(
            "s4", TimeoutError("slow"), StepErrorConfig(action=StepErrorAction.PAUSE)
        )
        assert result.action == StepErrorAction.PAUSE
        assert result.should_continue is False

    @pytest.mark.asyncio
    async def test_abort_stops_continuation(self):
        handler = StepErrorHandler()
        result = await handler.handle_error(
            "s5", RuntimeError("fatal"), StepErrorConfig(action=StepErrorAction.ABORT)
        )
        assert result.action == StepErrorAction.ABORT
        assert result.should_continue is False


# ---------------------------------------------------------------------------
# WorkflowCheckpointManager — Redis mocked
# ---------------------------------------------------------------------------


class TestWorkflowCheckpointManager:
    def _make_manager(self, fake_redis):
        mgr = WorkflowCheckpointManager()
        mgr._redis = lambda: fake_redis
        return mgr

    def _make_fake_redis(self, stored: Optional[Dict[str, bytes]] = None):
        store = dict(stored or {})
        fake = MagicMock()
        fake.setex = MagicMock(side_effect=lambda k, _ttl, v: store.update({k: v}))
        fake.keys = MagicMock(side_effect=lambda pattern: list(store.keys()))
        fake.mget = MagicMock(side_effect=lambda keys: [store.get(k) for k in keys])
        fake.delete = MagicMock(side_effect=lambda *keys: [store.pop(k, None) for k in keys])
        return fake, store

    def test_save_and_load_roundtrip(self):
        fake_redis, _ = self._make_fake_redis()
        mgr = self._make_manager(fake_redis)

        mgr.save_checkpoint("exec1", "step_a", {"success": True, "value": 42})
        checkpoints = mgr.load_checkpoints("exec1")

        assert "step_a" in checkpoints
        cp = checkpoints["step_a"]
        assert isinstance(cp, StepCheckpoint)
        assert cp.step_id == "step_a"
        assert cp.output == {"success": True, "value": 42}
        assert cp.status == "completed"

    def test_load_empty_when_no_checkpoints(self):
        fake_redis, _ = self._make_fake_redis()
        mgr = self._make_manager(fake_redis)
        assert mgr.load_checkpoints("exec_none") == {}

    def test_clear_deletes_all_keys(self):
        fake_redis, store = self._make_fake_redis()
        mgr = self._make_manager(fake_redis)

        mgr.save_checkpoint("exec2", "step_x", {"ok": True})
        mgr.save_checkpoint("exec2", "step_y", {"ok": True})
        assert len(mgr.load_checkpoints("exec2")) == 2

        mgr.clear_checkpoints("exec2")
        # After clear the store is empty (delete was called)
        fake_redis.delete.assert_called()

    def test_save_failure_does_not_raise(self):
        fake_redis = MagicMock()
        fake_redis.setex.side_effect = ConnectionError("Redis down")
        mgr = WorkflowCheckpointManager()
        mgr._redis = lambda: fake_redis
        # Must not raise
        mgr.save_checkpoint("exec3", "step_z", {"ok": True})

    def test_load_failure_returns_empty(self):
        fake_redis = MagicMock()
        fake_redis.keys.side_effect = ConnectionError("Redis down")
        mgr = WorkflowCheckpointManager()
        mgr._redis = lambda: fake_redis
        assert mgr.load_checkpoints("exec4") == {}

    def test_get_resume_point_returns_none(self):
        """get_resume_point always returns None; executor uses load_checkpoints."""
        fake_redis, _ = self._make_fake_redis()
        mgr = self._make_manager(fake_redis)
        mgr.save_checkpoint("exec5", "step_a", {"ok": True})
        assert mgr.get_resume_point("exec5") is None

    def test_multiple_steps_loaded(self):
        fake_redis, _ = self._make_fake_redis()
        mgr = self._make_manager(fake_redis)
        for i in range(5):
            mgr.save_checkpoint("exec6", f"step_{i}", {"index": i})
        checkpoints = mgr.load_checkpoints("exec6")
        assert len(checkpoints) == 5


# ---------------------------------------------------------------------------
# WorkflowExecutor integration
# ---------------------------------------------------------------------------


class TestWorkflowExecutorCheckpointSkip:
    """Verify that a step listed in the checkpoint map is skipped."""

    @pytest.mark.asyncio
    async def test_checkpointed_step_is_skipped(self):
        """_execute_step_with_agent must replay checkpoint without calling the executor."""
        executor = _make_executor()

        step = _make_step("step_a")
        exec_ctx: Dict[str, Any] = {
            "workflow_id": "wf1",
            "step_results": {},
            "agents_involved": set(),
            "interactions": [],
        }
        checkpoint_map = {
            "step_a": StepCheckpoint(
                step_id="step_a",
                status="completed",
                output={"success": True, "result": "cached"},
            )
        }

        # Patch _execute_coordinated_step so we can confirm it is NOT called
        executor._execute_coordinated_step = AsyncMock()

        await executor._execute_step_with_agent(step, exec_ctx, {}, checkpoints=checkpoint_map)

        executor._execute_coordinated_step.assert_not_called()
        assert step["status"] == "completed"
        assert exec_ctx["step_results"]["step_a"]["result"] == "cached"


class TestWorkflowExecutorErrorConfig:
    """Verify StepErrorConfig is read and applied during execution."""

    @pytest.mark.asyncio
    async def test_skip_config_marks_step_not_completed(self):
        executor = _make_executor()
        step = _make_step("step_b", error_config=StepErrorConfig(action=StepErrorAction.SKIP))
        exec_ctx: Dict[str, Any] = {
            "workflow_id": "wf2",
            "step_results": {},
            "agents_involved": set(),
            "interactions": [],
        }

        # Make the inner step always raise
        executor._execute_coordinated_step = AsyncMock(side_effect=RuntimeError("always fails"))

        await executor._execute_step_with_agent(step, exec_ctx, {})

        assert step["status"] == "failed"
        result = exec_ctx["step_results"]["step_b"]
        assert result.get("skipped") is True
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_abort_config_sets_failed_result(self):
        executor = _make_executor()
        step = _make_step("step_c", error_config=StepErrorConfig(action=StepErrorAction.ABORT))
        exec_ctx: Dict[str, Any] = {
            "workflow_id": "wf3",
            "step_results": {},
            "agents_involved": set(),
            "interactions": [],
        }

        executor._execute_coordinated_step = AsyncMock(side_effect=RuntimeError("fatal"))

        await executor._execute_step_with_agent(step, exec_ctx, {})

        assert step["status"] == "failed"
        assert exec_ctx["step_results"]["step_c"]["success"] is False

    @pytest.mark.asyncio
    async def test_retry_config_calls_executor_multiple_times(self):
        executor = _make_executor()
        step = _make_step(
            "step_d",
            error_config=StepErrorConfig(
                action=StepErrorAction.RETRY,
                max_retries=2,
                base_delay=0.0,
            ),
        )
        exec_ctx: Dict[str, Any] = {
            "workflow_id": "wf4",
            "step_results": {},
            "agents_involved": set(),
            "interactions": [],
        }

        call_count = 0

        async def _fail_twice(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return {"success": True, "result": "ok"}

        executor._execute_coordinated_step = _fail_twice

        await executor._execute_step_with_agent(step, exec_ctx, {})

        assert call_count == 3
        assert step["status"] == "completed"
        assert exec_ctx["step_results"]["step_d"]["success"] is True


class TestWorkflowExecutorResumeSignature:
    """Verify execute_coordinated_workflow accepts resume/execution_id parameters."""

    @pytest.mark.asyncio
    async def test_execute_accepts_resume_flag(self):
        """Calling with resume=True and pre-loaded checkpoints must not raise."""
        mock_cp_mgr = MagicMock()
        mock_cp_mgr.load_checkpoints.return_value = {}
        mock_cp_mgr.save_checkpoint = MagicMock()
        mock_cp_mgr.clear_checkpoints = MagicMock()

        executor = _make_executor(checkpoint_manager=mock_cp_mgr)

        # Patch inner step execution to succeed immediately
        executor._execute_coordinated_step = AsyncMock(
            return_value={"success": True, "result": "done"}
        )

        steps = [_make_step("s1"), _make_step("s2")]
        result = await executor.execute_coordinated_workflow(
            workflow_id="wf_resume",
            steps=steps,
            context={},
            execution_id="exec_resume",
            resume=True,
        )

        mock_cp_mgr.load_checkpoints.assert_called_once_with("exec_resume")
        assert result["status"] in ("completed", "partially_completed", "failed")
