# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Step-level Error Handlers and Workflow Checkpoint Management

Issue #2154.
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from constants.status_enums import TaskStatus
from tests.helpers.fake_redis import SyncHashFakeRedis

from .error_handler import (
    CHECKPOINT_TTL,
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


class TestWorkflowCheckpointManager:
    def _manager_with_fake_redis(self) -> WorkflowCheckpointManager:
        mgr = WorkflowCheckpointManager()
        mgr._redis = SyncHashFakeRedis()
        return mgr

    def test_save_and_load(self) -> None:
        mgr = self._manager_with_fake_redis()
        cp = StepCheckpoint(step_id="step1", status=TaskStatus.COMPLETED.value, output={"success": True})
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
            mgr.save("wf-2", StepCheckpoint(step_id=f"s{i}", status=TaskStatus.COMPLETED.value, output={}))
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

    # Issue #3231 -------------------------------------------------------

    def test_checkpoint_ttl_is_30_days(self) -> None:
        """CHECKPOINT_TTL must be at least 30 days for paused workflows."""
        assert CHECKPOINT_TTL >= 30 * 24 * 3600, (
            "CHECKPOINT_TTL is too short — paused workflows awaiting human " "approval must survive at least 30 days"
        )

    def test_save_sets_ttl(self) -> None:
        """Every save() must call expire() so the hash has a finite TTL."""
        mgr = self._manager_with_fake_redis()
        fake_redis = mgr._redis
        mgr.save("wf-ttl", StepCheckpoint(step_id="s1", status="completed", output={}))
        assert len(fake_redis.expire_calls) == 1
        key, ttl = fake_redis.expire_calls[0]
        assert "wf-ttl" in key
        assert ttl == CHECKPOINT_TTL

    def test_refresh_ttl_resets_expiry(self) -> None:
        """refresh_ttl() must call expire() with CHECKPOINT_TTL on the hash key."""
        mgr = self._manager_with_fake_redis()
        fake_redis = mgr._redis
        # Seed one checkpoint so the key exists.
        mgr.save("wf-resume", StepCheckpoint(step_id="s1", status="completed", output={}))
        initial_calls = len(fake_redis.expire_calls)

        mgr.refresh_ttl("wf-resume")

        new_calls = fake_redis.expire_calls[initial_calls:]
        assert len(new_calls) == 1, "refresh_ttl must call expire() exactly once"
        key, ttl = new_calls[0]
        assert "wf-resume" in key
        assert ttl == CHECKPOINT_TTL

    def test_refresh_ttl_redis_error_does_not_raise(self) -> None:
        """A Redis failure in refresh_ttl() must be logged, never raised (#3231)."""
        mgr = WorkflowCheckpointManager()
        bad_redis = MagicMock()
        bad_redis.expire.side_effect = ConnectionError("Redis down")
        mgr._redis = bad_redis
        # Must not raise
        mgr.refresh_ttl("wf-bad")


# ---------------------------------------------------------------------------
# StepErrorHandler tests
# ---------------------------------------------------------------------------


class TestStepErrorHandler:
    def _step(self, error_config: Dict[str, Any]) -> Dict[str, Any]:
        return {"id": "step_x", "action": "run", "error_config": error_config}

    @pytest.mark.asyncio
    async def test_abort_by_default(self) -> None:
        handler = StepErrorHandler()
        step = {"id": "s1", "action": "run"}
        outcome = await handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        assert outcome["action"] == StepErrorAction.ABORT

    @pytest.mark.asyncio
    async def test_skip_action(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "skip"})
        outcome = await handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        assert outcome["action"] == StepErrorAction.SKIP

    @pytest.mark.asyncio
    async def test_retry_below_max(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "retry", "max_retries": 3, "base_delay": 0.0})
        outcome = await handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        assert outcome["action"] == StepErrorAction.RETRY

    @pytest.mark.asyncio
    async def test_retry_exhausted_becomes_abort(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "retry", "max_retries": 3, "base_delay": 0.0})
        outcome = await handler.handle_error(step, ValueError("oops"), 3, {"workflow_id": "wf"})
        assert outcome["action"] == StepErrorAction.ABORT

    @pytest.mark.asyncio
    async def test_fallback_with_id(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "fallback", "fallback_step_id": "step_b"})
        outcome = await handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        assert outcome["action"] == StepErrorAction.FALLBACK
        assert outcome["fallback_id"] == "step_b"

    @pytest.mark.asyncio
    async def test_fallback_without_id_becomes_abort(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "fallback"})
        outcome = await handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        assert outcome["action"] == StepErrorAction.ABORT

    @pytest.mark.asyncio
    async def test_pause_action(self) -> None:
        handler = StepErrorHandler()
        step = self._step({"action": "pause"})
        outcome = await handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
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

    @pytest.mark.asyncio
    async def test_invalid_error_config_falls_back_to_abort(self) -> None:
        handler = StepErrorHandler()
        step = {
            "id": "s1",
            "action": "run",
            "error_config": {"action": "invalid_action"},
        }
        outcome = await handler.handle_error(step, ValueError("oops"), 1, {"workflow_id": "wf"})
        assert outcome["action"] == StepErrorAction.ABORT
