# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Step-level Error Handlers and Workflow Checkpoint Management

Issue #2154.
"""

import asyncio
import json
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from constants.status_enums import TaskStatus

from .error_handler import (
    BackoffStrategy,
    StepCheckpoint,
    StepErrorAction,
    StepErrorConfig,
    StepErrorHandler,
    WorkflowCheckpointManager,
)

# ---------------------------------------------------------------------------
# StepErrorConfig tests
# ---------------------------------------------------------------------------


class TestStepErrorConfig:
    def test_defaults(self) -> None:
        cfg = StepErrorConfig()
        assert cfg.action == StepErrorAction.ABORT
        assert cfg.max_retries == 3
        assert cfg.base_delay == 1.0
        assert cfg.backoff == BackoffStrategy.EXPONENTIAL
        assert cfg.fallback_step_id is None

    def test_from_dict_full(self) -> None:
        cfg = StepErrorConfig.from_dict(
            {
                "action": "retry",
                "max_retries": 5,
                "base_delay": 2.0,
                "backoff": "linear",
                "fallback_step_id": "step_b",
            }
        )
        assert cfg.action == StepErrorAction.RETRY
        assert cfg.max_retries == 5
        assert cfg.base_delay == 2.0
        assert cfg.backoff == BackoffStrategy.LINEAR
        assert cfg.fallback_step_id == "step_b"

    def test_from_dict_partial_uses_defaults(self) -> None:
        cfg = StepErrorConfig.from_dict({"action": "skip"})
        assert cfg.action == StepErrorAction.SKIP
        assert cfg.max_retries == 3

    def test_from_dict_invalid_action_raises(self) -> None:
        with pytest.raises(ValueError):
            StepErrorConfig.from_dict({"action": "nonexistent"})


# ---------------------------------------------------------------------------
# StepCheckpoint tests
# ---------------------------------------------------------------------------


class TestStepCheckpoint:
    def test_round_trip(self) -> None:
        cp = StepCheckpoint(step_id="s1", status=TaskStatus.COMPLETED.value, output={"success": True})
        restored = StepCheckpoint.from_dict(cp.to_dict())
        assert restored.step_id == "s1"
        assert restored.status == TaskStatus.COMPLETED.value
        assert restored.output == {"success": True}

    def test_timestamp_is_populated(self) -> None:
        cp = StepCheckpoint(step_id="s1", status=TaskStatus.COMPLETED.value, output={})
        assert cp.timestamp != ""

    def test_to_dict_is_json_serialisable(self) -> None:
        cp = StepCheckpoint(step_id="s1", status=TaskStatus.COMPLETED.value, output={"k": "v"})
        serialised = json.dumps(cp.to_dict())
        assert "s1" in serialised


# ---------------------------------------------------------------------------
# WorkflowCheckpointManager tests
# ---------------------------------------------------------------------------


class _FakeRedis:
    """In-memory Redis substitute for checkpoint tests."""

    def __init__(self) -> None:
        self._hashes: Dict[str, Dict[str, str]] = {}

    def hset(self, key: str, field: str, value: str) -> None:
        self._hashes.setdefault(key, {})[field] = value

    def expire(self, key: str, ttl: int) -> None:
        pass  # TTL not needed in tests

    def hgetall(self, key: str) -> Dict[str, str]:
        return dict(self._hashes.get(key, {}))

    def delete(self, key: str) -> None:
        self._hashes.pop(key, None)


class TestWorkflowCheckpointManager:
    def _manager_with_fake_redis(self) -> WorkflowCheckpointManager:
        mgr = WorkflowCheckpointManager()
        mgr._redis = _FakeRedis()
        return mgr

    def test_save_and_load(self) -> None:
        mgr = self._manager_with_fake_redis()
        cp = StepCheckpoint(
            step_id="step1", status=TaskStatus.COMPLETED.value, output={"success": True}
        )
        mgr.save("wf-1", cp)

        loaded = mgr.load_all("wf-1")
        assert "step1" in loaded
        assert loaded["step1"].status == TaskStatus.COMPLETED.value
        assert loaded["step1"].output == {"success": True}

    def test_load_empty_when_no_checkpoints(self) -> None:
        mgr = self._manager_with_fake_redis()
        assert mgr.load_all("wf-unknown") == {}

    def test_save_multiple_steps(self) -> None:
        mgr = self._manager_with_fake_redis()
        for i in range(3):
            mgr.save(
                "wf-2", StepCheckpoint(step_id=f"s{i}", status=TaskStatus.COMPLETED.value, output={})
            )
        loaded = mgr.load_all("wf-2")
        assert set(loaded.keys()) == {"s0", "s1", "s2"}

    def test_clear_removes_all(self) -> None:
        mgr = self._manager_with_fake_redis()
        mgr.save("wf-3", StepCheckpoint(step_id="s1", status=TaskStatus.COMPLETED.value, output={}))
        mgr.clear("wf-3")
        assert mgr.load_all("wf-3") == {}

    def test_load_handles_corrupt_entry_gracefully(self) -> None:
        mgr = self._manager_with_fake_redis()
        # Manually write corrupt JSON
        mgr._redis.hset("autobot:workflow:checkpoint:wf-bad", "s1", "{not json}")
        loaded = mgr.load_all("wf-bad")
        assert loaded == {}

    def test_redis_error_on_load_returns_empty(self) -> None:
        mgr = WorkflowCheckpointManager()
        bad_redis = MagicMock()
        bad_redis.hgetall.side_effect = ConnectionError("Redis down")
        mgr._redis = bad_redis
        assert mgr.load_all("wf-fail") == {}

    def test_redis_error_on_save_logged_not_raised(self) -> None:
        mgr = WorkflowCheckpointManager()
        bad_redis = MagicMock()
        bad_redis.hset.side_effect = ConnectionError("Redis down")
        mgr._redis = bad_redis
        cp = StepCheckpoint(step_id="s1", status=TaskStatus.COMPLETED.value, output={})
        # Must not raise
        mgr.save("wf-fail", cp)


# ---------------------------------------------------------------------------
# StepErrorHandler tests
# ---------------------------------------------------------------------------


class TestStepErrorHandler:
    def _run(self, coro: Any) -> Any:
        return asyncio.get_event_loop().run_until_complete(coro)

    def _step(self, error_config: Dict[str, Any]) -> Dict[str, Any]:
        return {"id": "step_x", "action": "run", "error_config": error_config}

    def test_abort_by_default(self) -> None:
        handler = StepErrorHandler()
        step = {"id": "s1", "action": "run"}
        outcome = self._run(
            handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        )
        assert outcome["action"] == StepErrorAction.ABORT

    def test_skip_action(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "skip"})
        outcome = self._run(
            handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        )
        assert outcome["action"] == StepErrorAction.SKIP

    def test_retry_below_max(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "retry", "max_retries": 3, "base_delay": 0.0})
        outcome = self._run(
            handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        )
        assert outcome["action"] == StepErrorAction.RETRY

    def test_retry_exhausted_becomes_abort(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "retry", "max_retries": 3, "base_delay": 0.0})
        outcome = self._run(
            handler.handle_error(step, ValueError("oops"), 3, {"workflow_id": "wf"})
        )
        assert outcome["action"] == StepErrorAction.ABORT

    def test_fallback_with_id(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "fallback", "fallback_step_id": "step_b"})
        outcome = self._run(
            handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        )
        assert outcome["action"] == StepErrorAction.FALLBACK
        assert outcome["fallback_id"] == "step_b"

    def test_fallback_without_id_becomes_abort(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "fallback"})
        outcome = self._run(
            handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        )
        assert outcome["action"] == StepErrorAction.ABORT

    def test_pause_action(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "pause"})
        outcome = self._run(
            handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        )
        assert outcome["action"] == StepErrorAction.PAUSE

    def test_exponential_backoff_grows(self) -> None:
        handler = StepErrorHandler()
        cfg = StepErrorConfig(
            action=StepErrorAction.RETRY,
            base_delay=1.0,
            backoff=BackoffStrategy.EXPONENTIAL,
        )
        assert handler._compute_delay(cfg, 1) == 1.0
        assert handler._compute_delay(cfg, 2) == 2.0
        assert handler._compute_delay(cfg, 3) == 4.0

    def test_linear_backoff_grows(self) -> None:
        handler = StepErrorHandler()
        cfg = StepErrorConfig(
            action=StepErrorAction.RETRY,
            base_delay=2.0,
            backoff=BackoffStrategy.LINEAR,
        )
        assert handler._compute_delay(cfg, 1) == 2.0
        assert handler._compute_delay(cfg, 2) == 4.0
        assert handler._compute_delay(cfg, 3) == 6.0

    def test_invalid_error_config_falls_back_to_abort(self) -> None:
        handler = StepErrorHandler()
        step = {
            "id": "s1",
            "action": "run",
            "error_config": {"action": "invalid_action"},
        }
        outcome = self._run(
            handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        )
        assert outcome["action"] == StepErrorAction.ABORT
