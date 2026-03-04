# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for WorkflowStateMachine — Redis-persisted workflow state (#1380).

Covers:
- Pure function tests: route_next() for each step type
- WorkflowState defaults and JSON roundtrip
- Mock Redis tests for create, get, transition, complete, fail, list_active
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from api.workflow_state import (
    WorkflowState,
    WorkflowStateMachine,
    get_workflow_state_machine,
    route_next,
)

# ------------------------------------------------------------------ #
# Key constants (mirror implementation)
# ------------------------------------------------------------------ #
KEY_PREFIX = "autobot:workflow:"
ACTIVE_SET = "autobot:workflow:active"
COMPLETED_TTL = 7 * 24 * 3600  # 7 days


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def mock_redis():
    """Async Redis mock with common methods.

    ``get_redis_client(async_client=True)`` returns a coroutine,
    so the mock must also be awaitable.  We build a plain
    ``AsyncMock`` for the Redis client and a separate helper
    that returns it as an awaitable when used as a side-effect
    for the patched ``get_redis_client``.
    """
    mock = AsyncMock()
    mock.set = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.delete = AsyncMock(return_value=1)
    mock.sadd = AsyncMock(return_value=1)
    mock.srem = AsyncMock(return_value=1)
    mock.smembers = AsyncMock(return_value=set())
    mock.expire = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def sample_steps():
    """Typical workflow steps list."""
    return [
        {"name": "planning", "service": "main-backend"},
        {"name": "executing", "service": "browser-worker"},
        {"name": "validating", "service": "main-backend"},
    ]


# ================================================================== #
# Pure function tests: route_next()
# ================================================================== #


class TestRouteNext:
    """Tests for the route_next pure function."""

    def test_planning_routes_to_main_backend(self):
        state = WorkflowState(
            workflow_id="wf-1",
            goal="test",
            current_step="planning",
        )
        assert route_next(state) == "main-backend"

    def test_executing_default_routes_to_main_backend(self):
        state = WorkflowState(
            workflow_id="wf-2",
            goal="test",
            current_step="executing",
        )
        assert route_next(state) == "main-backend"

    def test_executing_with_custom_executor(self):
        state = WorkflowState(
            workflow_id="wf-3",
            goal="test",
            current_step="executing",
            metadata={"executor_service": "browser-worker"},
        )
        assert route_next(state) == "browser-worker"

    def test_validating_routes_to_main_backend(self):
        state = WorkflowState(
            workflow_id="wf-4",
            goal="test",
            current_step="validating",
        )
        assert route_next(state) == "main-backend"

    def test_done_routes_to_complete(self):
        state = WorkflowState(
            workflow_id="wf-5",
            goal="test",
            current_step="executing",
            done=True,
        )
        assert route_next(state) == "complete"

    def test_unknown_step_routes_to_complete(self):
        state = WorkflowState(
            workflow_id="wf-6",
            goal="test",
            current_step="unknown-step",
        )
        assert route_next(state) == "complete"

    def test_failed_step_routes_to_complete(self):
        state = WorkflowState(
            workflow_id="wf-7",
            goal="test",
            current_step="failed",
        )
        assert route_next(state) == "complete"


# ================================================================== #
# WorkflowState model tests
# ================================================================== #


class TestWorkflowState:
    """Tests for the WorkflowState Pydantic model."""

    def test_defaults(self):
        state = WorkflowState(workflow_id="wf-1", goal="do stuff")
        assert state.current_step == "planning"
        assert state.active_service == "main-backend"
        assert state.steps_completed == []
        assert state.steps_remaining == []
        assert state.mailbox == []
        assert state.done is False
        assert state.errors == []
        assert state.metadata == {}
        assert state.created_at is not None
        assert state.updated_at is not None

    def test_json_roundtrip(self):
        state = WorkflowState(
            workflow_id="wf-rt",
            goal="roundtrip test",
            current_step="executing",
            active_service="browser-worker",
            steps_completed=["planning"],
            steps_remaining=[{"name": "validating"}],
            metadata={"executor_service": "browser-worker"},
        )
        json_str = state.model_dump_json()
        restored = WorkflowState.model_validate_json(json_str)
        assert restored.workflow_id == state.workflow_id
        assert restored.goal == state.goal
        assert restored.current_step == state.current_step
        assert restored.active_service == state.active_service
        assert restored.steps_completed == state.steps_completed
        assert restored.steps_remaining == state.steps_remaining
        assert restored.metadata == state.metadata

    def test_timestamps_are_utc_iso(self):
        state = WorkflowState(workflow_id="wf-ts", goal="ts test")
        created = datetime.fromisoformat(state.created_at)
        updated = datetime.fromisoformat(state.updated_at)
        assert created.tzinfo is not None
        assert updated.tzinfo is not None


# ================================================================== #
# WorkflowStateMachine tests (mock Redis)
# ================================================================== #


class TestWorkflowStateMachineCreate:
    """Tests for WorkflowStateMachine.create()."""

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_create_returns_state(self, mock_get_redis, mock_redis, sample_steps):
        mock_get_redis.return_value = mock_redis
        sm = WorkflowStateMachine()

        state = await sm.create("wf-new", "build a widget", sample_steps)

        assert state.workflow_id == "wf-new"
        assert state.goal == "build a widget"
        assert state.current_step == "planning"
        assert state.steps_remaining == sample_steps
        assert state.done is False

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_create_persists_to_redis(
        self, mock_get_redis, mock_redis, sample_steps
    ):
        mock_get_redis.return_value = mock_redis
        sm = WorkflowStateMachine()

        await sm.create("wf-persist", "persist test", sample_steps)

        key = f"{KEY_PREFIX}wf-persist"
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == key

        # Verify stored JSON deserializes back
        stored_json = call_args[0][1]
        restored = WorkflowState.model_validate_json(stored_json)
        assert restored.workflow_id == "wf-persist"

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_create_adds_to_active_set(
        self, mock_get_redis, mock_redis, sample_steps
    ):
        mock_get_redis.return_value = mock_redis
        sm = WorkflowStateMachine()

        await sm.create("wf-active", "active test", sample_steps)

        mock_redis.sadd.assert_called_once_with(ACTIVE_SET, "wf-active")


class TestWorkflowStateMachineGet:
    """Tests for WorkflowStateMachine.get()."""

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_get_existing(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        state = WorkflowState(workflow_id="wf-exist", goal="exists")
        mock_redis.get.return_value = state.model_dump_json()
        sm = WorkflowStateMachine()

        result = await sm.get("wf-exist")

        assert result is not None
        assert result.workflow_id == "wf-exist"
        assert result.goal == "exists"
        mock_redis.get.assert_called_once_with(f"{KEY_PREFIX}wf-exist")

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_get_missing_returns_none(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        mock_redis.get.return_value = None
        sm = WorkflowStateMachine()

        result = await sm.get("wf-missing")

        assert result is None


class TestWorkflowStateMachineTransition:
    """Tests for WorkflowStateMachine.transition()."""

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_transition_updates_step(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        original = WorkflowState(
            workflow_id="wf-tr",
            goal="transition test",
            current_step="planning",
        )
        mock_redis.get.return_value = original.model_dump_json()
        sm = WorkflowStateMachine()

        result = await sm.transition("wf-tr", "executing", "plan done")

        assert result.current_step == "executing"
        assert "planning" in result.steps_completed

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_transition_updates_active_service(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        original = WorkflowState(
            workflow_id="wf-svc",
            goal="svc test",
            current_step="planning",
        )
        mock_redis.get.return_value = original.model_dump_json()
        sm = WorkflowStateMachine()

        result = await sm.transition("wf-svc", "executing")

        # active_service should be set via route_next
        assert result.active_service == route_next(result)

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_transition_persists_updated_state(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        original = WorkflowState(
            workflow_id="wf-p",
            goal="persist",
            current_step="planning",
        )
        mock_redis.get.return_value = original.model_dump_json()
        sm = WorkflowStateMachine()

        await sm.transition("wf-p", "executing")

        key = f"{KEY_PREFIX}wf-p"
        mock_redis.set.assert_called_once()
        assert mock_redis.set.call_args[0][0] == key

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_transition_missing_workflow_raises(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        mock_redis.get.return_value = None
        sm = WorkflowStateMachine()

        with pytest.raises(ValueError, match="not found"):
            await sm.transition("wf-gone", "executing")


class TestWorkflowStateMachineComplete:
    """Tests for WorkflowStateMachine.complete()."""

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_complete_marks_done(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        original = WorkflowState(
            workflow_id="wf-done",
            goal="complete test",
            current_step="validating",
        )
        mock_redis.get.return_value = original.model_dump_json()
        sm = WorkflowStateMachine()

        result = await sm.complete("wf-done")

        assert result.done is True
        assert result.current_step == "complete"

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_complete_removes_from_active_set(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        original = WorkflowState(
            workflow_id="wf-rm",
            goal="remove test",
            current_step="validating",
        )
        mock_redis.get.return_value = original.model_dump_json()
        sm = WorkflowStateMachine()

        await sm.complete("wf-rm")

        mock_redis.srem.assert_called_once_with(ACTIVE_SET, "wf-rm")

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_complete_sets_ttl(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        original = WorkflowState(
            workflow_id="wf-ttl",
            goal="ttl test",
            current_step="validating",
        )
        mock_redis.get.return_value = original.model_dump_json()
        sm = WorkflowStateMachine()

        await sm.complete("wf-ttl")

        key = f"{KEY_PREFIX}wf-ttl"
        mock_redis.expire.assert_called_once_with(key, COMPLETED_TTL)


class TestWorkflowStateMachineFail:
    """Tests for WorkflowStateMachine.fail()."""

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_fail_marks_failed(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        original = WorkflowState(
            workflow_id="wf-fail",
            goal="fail test",
            current_step="executing",
        )
        mock_redis.get.return_value = original.model_dump_json()
        sm = WorkflowStateMachine()

        result = await sm.fail("wf-fail", "something broke")

        assert result.current_step == "failed"
        assert result.done is True
        assert "something broke" in result.errors

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_fail_appends_to_existing_errors(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        original = WorkflowState(
            workflow_id="wf-multi-err",
            goal="multi error",
            current_step="executing",
            errors=["first error"],
        )
        mock_redis.get.return_value = original.model_dump_json()
        sm = WorkflowStateMachine()

        result = await sm.fail("wf-multi-err", "second error")

        assert len(result.errors) == 2
        assert result.errors[0] == "first error"
        assert result.errors[1] == "second error"

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_fail_missing_workflow_raises(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        mock_redis.get.return_value = None
        sm = WorkflowStateMachine()

        with pytest.raises(ValueError, match="not found"):
            await sm.fail("wf-ghost", "oops")


class TestWorkflowStateMachineListActive:
    """Tests for WorkflowStateMachine.list_active()."""

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_list_active_empty(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        mock_redis.smembers.return_value = set()
        sm = WorkflowStateMachine()

        result = await sm.list_active()

        assert result == []

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_list_active_returns_states(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        s1 = WorkflowState(workflow_id="wf-a1", goal="goal 1")
        s2 = WorkflowState(workflow_id="wf-a2", goal="goal 2")

        mock_redis.smembers.return_value = {b"wf-a1", b"wf-a2"}

        async def fake_get(key):
            if key == f"{KEY_PREFIX}wf-a1":
                return s1.model_dump_json()
            if key == f"{KEY_PREFIX}wf-a2":
                return s2.model_dump_json()
            return None

        mock_redis.get.side_effect = fake_get
        sm = WorkflowStateMachine()

        result = await sm.list_active()

        assert len(result) == 2
        ids = {s.workflow_id for s in result}
        assert ids == {"wf-a1", "wf-a2"}

    @pytest.mark.asyncio
    @patch("api.workflow_state.get_redis_client", new_callable=AsyncMock)
    async def test_list_active_skips_missing(self, mock_get_redis, mock_redis):
        mock_get_redis.return_value = mock_redis
        s1 = WorkflowState(workflow_id="wf-ok", goal="ok")
        mock_redis.smembers.return_value = {
            b"wf-ok",
            b"wf-stale",
        }

        async def fake_get(key):
            if key == f"{KEY_PREFIX}wf-ok":
                return s1.model_dump_json()
            return None

        mock_redis.get.side_effect = fake_get
        sm = WorkflowStateMachine()

        result = await sm.list_active()

        assert len(result) == 1
        assert result[0].workflow_id == "wf-ok"


# ================================================================== #
# Singleton factory test
# ================================================================== #


class TestGetWorkflowStateMachine:
    """Tests for get_workflow_state_machine singleton."""

    def test_returns_same_instance(self):
        a = get_workflow_state_machine()
        b = get_workflow_state_machine()
        assert a is b

    def test_returns_workflow_state_machine(self):
        result = get_workflow_state_machine()
        assert isinstance(result, WorkflowStateMachine)
