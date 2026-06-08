# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for WorkflowMemory.  Issue #3019."""

import json
from unittest.mock import MagicMock, patch

import pytest

from orchestration.workflow_memory import (
    DEFAULT_TTL_SECONDS,
    MEMORY_KEY_PREFIX,
    WorkflowMemory,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_redis_mock() -> MagicMock:
    """Return a MagicMock that mimics a synchronous Redis client."""
    mock = MagicMock()
    # hgetall returns an empty dict by default so get_all tests start clean.
    mock.hgetall.return_value = {}
    # hget returns None by default (key absent).
    mock.hget.return_value = None
    # hdel returns 0 by default (key absent).
    mock.hdel.return_value = 0
    return mock


@pytest.fixture()
def redis_mock() -> MagicMock:
    return _make_redis_mock()


@pytest.fixture()
def memory(redis_mock: MagicMock) -> WorkflowMemory:
    """WorkflowMemory with a patched Redis client."""
    wm = WorkflowMemory(workflow_id="wf-test-123")
    wm._redis = redis_mock
    return wm


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestWorkflowMemoryInit:
    def test_redis_key_built_correctly(self):
        wm = WorkflowMemory(workflow_id="abc")
        assert wm._redis_key == f"{MEMORY_KEY_PREFIX}abc"

    def test_default_ttl(self):
        wm = WorkflowMemory(workflow_id="abc")
        assert wm._ttl == DEFAULT_TTL_SECONDS

    def test_custom_ttl(self):
        wm = WorkflowMemory(workflow_id="abc", ttl_seconds=120)
        assert wm._ttl == 120

    def test_empty_workflow_id_raises(self):
        with pytest.raises(ValueError, match="workflow_id"):
            WorkflowMemory(workflow_id="")


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


class TestWorkflowMemorySet:
    def test_set_stores_json(self, memory: WorkflowMemory, redis_mock: MagicMock):
        memory.set("my_key", {"a": 1})
        redis_mock.hset.assert_called_once_with(memory._redis_key, "my_key", json.dumps({"a": 1}))

    def test_set_refreshes_ttl(self, memory: WorkflowMemory, redis_mock: MagicMock):
        memory.set("k", "v")
        redis_mock.expire.assert_called_with(memory._redis_key, memory._ttl)

    def test_set_empty_key_raises(self, memory: WorkflowMemory):
        with pytest.raises(ValueError, match="key"):
            memory.set("", "value")

    def test_set_various_types(self, memory: WorkflowMemory, redis_mock: MagicMock):
        for value in [42, 3.14, True, None, [1, 2], {"x": "y"}]:
            memory.set("k", value)
            _, _, stored = redis_mock.hset.call_args[0]
            assert json.loads(stored) == value

    def test_set_propagates_redis_error(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hset.side_effect = ConnectionError("Redis down")
        with pytest.raises(ConnectionError):
            memory.set("k", "v")


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestWorkflowMemoryGet:
    def test_get_returns_deserialised_value(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hget.return_value = json.dumps({"result": "ok"}).encode()
        assert memory.get("k") == {"result": "ok"}

    def test_get_returns_default_when_absent(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hget.return_value = None
        assert memory.get("missing") is None

    def test_get_custom_default(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hget.return_value = None
        assert memory.get("missing", default=42) == 42

    def test_get_handles_str_bytes(self, memory: WorkflowMemory, redis_mock: MagicMock):
        # Redis may return raw bytes; get() must decode them.
        redis_mock.hget.return_value = b'"hello"'
        assert memory.get("k") == "hello"

    def test_get_returns_default_on_corrupt_json(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hget.return_value = b"not-json{{{"
        assert memory.get("k", default="fallback") == "fallback"

    def test_get_returns_default_on_redis_error(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hget.side_effect = ConnectionError("Redis down")
        assert memory.get("k", default="safe") == "safe"


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


class TestWorkflowMemoryGetAll:
    def test_get_all_empty(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hgetall.return_value = {}
        assert memory.get_all() == {}

    def test_get_all_returns_dict(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hgetall.return_value = {
            b"key1": json.dumps("value1").encode(),
            b"key2": json.dumps({"nested": True}).encode(),
        }
        result = memory.get_all()
        assert result == {"key1": "value1", "key2": {"nested": True}}

    def test_get_all_skips_corrupt_entries(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hgetall.return_value = {
            b"good": json.dumps(1).encode(),
            b"bad": b"not-json{{",
        }
        result = memory.get_all()
        # Corrupt entry is silently skipped; good entry is returned.
        assert result == {"good": 1}
        assert "bad" not in result

    def test_get_all_returns_empty_on_redis_error(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hgetall.side_effect = ConnectionError("Redis down")
        assert memory.get_all() == {}


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestWorkflowMemoryDelete:
    def test_delete_existing_key_returns_true(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hdel.return_value = 1
        assert memory.delete("k") is True
        redis_mock.hdel.assert_called_once_with(memory._redis_key, "k")

    def test_delete_absent_key_returns_false(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hdel.return_value = 0
        assert memory.delete("missing") is False

    def test_delete_propagates_redis_error(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.hdel.side_effect = ConnectionError("Redis down")
        with pytest.raises(ConnectionError):
            memory.delete("k")


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


class TestWorkflowMemoryClear:
    def test_clear_deletes_hash(self, memory: WorkflowMemory, redis_mock: MagicMock):
        memory.clear()
        redis_mock.delete.assert_called_once_with(memory._redis_key)

    def test_clear_propagates_redis_error(self, memory: WorkflowMemory, redis_mock: MagicMock):
        redis_mock.delete.side_effect = ConnectionError("Redis down")
        with pytest.raises(ConnectionError):
            memory.clear()


# ---------------------------------------------------------------------------
# Isolation between workflows
# ---------------------------------------------------------------------------


class TestWorkflowMemoryIsolation:
    def test_different_workflow_ids_use_different_keys(self):
        wm_a = WorkflowMemory(workflow_id="alpha")
        wm_b = WorkflowMemory(workflow_id="beta")
        assert wm_a._redis_key != wm_b._redis_key

    def test_writes_do_not_bleed_across_instances(self):
        """Each WorkflowMemory targets its own Redis key — no cross-contamination."""
        mock_a = _make_redis_mock()
        mock_b = _make_redis_mock()

        wm_a = WorkflowMemory(workflow_id="wf-a")
        wm_b = WorkflowMemory(workflow_id="wf-b")
        wm_a._redis = mock_a
        wm_b._redis = mock_b

        wm_a.set("shared_key", "from_a")
        wm_b.set("shared_key", "from_b")

        # Each mock was called with its own workflow key, not the other's.
        mock_a.hset.assert_called_with(wm_a._redis_key, "shared_key", json.dumps("from_a"))
        mock_b.hset.assert_called_with(wm_b._redis_key, "shared_key", json.dumps("from_b"))


# ---------------------------------------------------------------------------
# TTL / auto-expiry
# ---------------------------------------------------------------------------


class TestWorkflowMemoryTTL:
    def test_expire_called_with_correct_ttl(self, memory: WorkflowMemory, redis_mock: MagicMock):
        memory.set("k", "v")
        redis_mock.expire.assert_called_with(memory._redis_key, DEFAULT_TTL_SECONDS)

    def test_custom_ttl_respected(self, redis_mock: MagicMock):
        wm = WorkflowMemory(workflow_id="wf-ttl", ttl_seconds=60)
        wm._redis = redis_mock
        wm.set("k", "v")
        redis_mock.expire.assert_called_with(wm._redis_key, 60)

    def test_ttl_not_refreshed_on_get(self, memory: WorkflowMemory, redis_mock: MagicMock):
        """get() is read-only — it must not bump the TTL."""
        redis_mock.hget.return_value = json.dumps("x").encode()
        memory.get("k")
        redis_mock.expire.assert_not_called()

    def test_ttl_refresh_failure_does_not_raise(self, memory: WorkflowMemory, redis_mock: MagicMock):
        """A TTL refresh failure must be logged but must not propagate."""
        redis_mock.expire.side_effect = ConnectionError("Redis down")
        # set() should still succeed even when expire() fails.
        memory.set("k", "v")  # must not raise


# ---------------------------------------------------------------------------
# Lazy Redis initialisation
# ---------------------------------------------------------------------------


class TestWorkflowMemoryLazyRedis:
    def test_redis_not_initialised_on_construction(self):
        """get_redis_client() must not be called until the first operation."""
        with patch("orchestration.workflow_memory.get_redis_client") as mock_factory:
            wm = WorkflowMemory(workflow_id="lazy-test")
            mock_factory.assert_not_called()
            assert wm._redis is None

    def test_redis_initialised_on_first_operation(self):
        """get_redis_client() is called exactly once across multiple operations."""
        fake_redis = _make_redis_mock()
        with patch("orchestration.workflow_memory.get_redis_client", return_value=fake_redis) as mock_factory:
            wm = WorkflowMemory(workflow_id="lazy-test")
            wm.set("k", "v")
            wm.get("k")
            wm.get_all()
            mock_factory.assert_called_once_with(async_client=False, database="workflows")


# ---------------------------------------------------------------------------
# Issue #3099: Auto-injection into agent context
# ---------------------------------------------------------------------------


class TestWorkflowMemoryAutoInjection:
    """Verify that _execute_coordinated_step injects shared_memory findings."""

    @pytest.mark.asyncio
    async def test_prior_findings_injected_into_context(self):
        """When shared_memory has data, it appears in context['prior_agent_findings']."""
        from unittest.mock import AsyncMock, MagicMock

        from orchestration.workflow_executor import WorkflowExecutor

        executor = WorkflowExecutor.__new__(WorkflowExecutor)
        executor.logger = MagicMock()

        mock_memory = MagicMock()
        mock_memory.get_all.return_value = {"step1": "found data"}

        execution_context = {
            "shared_memory": mock_memory,
            "agents_involved": set(),
            "interactions": [],
        }
        context: dict = {}
        step = {"id": "step2", "assigned_agent": None}

        # _simulate_step_execution raises NotImplementedError; we just need
        # to verify the context was updated before the call.
        executor._simulate_step_execution = AsyncMock(side_effect=NotImplementedError("stub"))
        executor._create_agent_interaction = MagicMock(return_value=None)

        with pytest.raises(NotImplementedError):
            await executor._execute_coordinated_step(step, execution_context, context)

        assert context["prior_agent_findings"] == {"step1": "found data"}

    @pytest.mark.asyncio
    async def test_empty_memory_not_injected(self):
        """When shared_memory is empty, no prior_agent_findings key is added."""
        from unittest.mock import AsyncMock, MagicMock

        from orchestration.workflow_executor import WorkflowExecutor

        executor = WorkflowExecutor.__new__(WorkflowExecutor)
        executor.logger = MagicMock()

        mock_memory = MagicMock()
        mock_memory.get_all.return_value = {}

        execution_context = {
            "shared_memory": mock_memory,
            "agents_involved": set(),
            "interactions": [],
        }
        context: dict = {}
        step = {"id": "step2", "assigned_agent": None}

        executor._simulate_step_execution = AsyncMock(side_effect=NotImplementedError("stub"))
        executor._create_agent_interaction = MagicMock(return_value=None)

        with pytest.raises(NotImplementedError):
            await executor._execute_coordinated_step(step, execution_context, context)

        assert "prior_agent_findings" not in context
