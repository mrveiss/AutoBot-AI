# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cooperative cancellation checkpoints in execute_a2a_task (#16174, #15950).

`cancel_task` only flips a state in Redis -- it never interrupts a running
executor. These tests drive `execute_a2a_task` against a real work-claim
registry (fakeredis) and a fake `TaskManager` whose `get_task` reflects a
state a test can flip mid-run, the same way a concurrent cancel request would.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from a2a.task_executor import execute_a2a_task
from a2a.types import TaskState
from autobot_shared.coordination.work_claims import list_claims


class _FakeTaskManager:
    """Just enough of TaskManager's surface for the executor to drive."""

    def __init__(self, initial: TaskState = TaskState.SUBMITTED):
        self.state = initial
        self.artifacts: list = []
        self.update_state_calls: list[tuple] = []

    def get_task(self, task_id):
        return SimpleNamespace(status=SimpleNamespace(state=self.state))

    def update_state(self, task_id, state, message=None):
        self.update_state_calls.append((state, message))
        self.state = state

    def publish_event(self, *_args, **_kwargs):
        pass

    def add_artifact(self, task_id, artifact):
        self.artifacts.append(artifact)

    def cancel(self):
        self.state = TaskState.CANCELLED


@pytest_asyncio.fixture
async def claim_registry(monkeypatch):
    """A real work-claim registry over an in-process Redis (see task_executor_trust_test.py)."""
    fakeredis_async = pytest.importorskip("fakeredis.aioredis")
    from autobot_shared.coordination import work_claims

    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)
    monkeypatch.setattr(work_claims, "get_async_redis_client", AsyncMock(return_value=client))
    yield client
    await client.flushall()


def _scrub_ok(text: str = "ok"):
    result = MagicMock()
    result.text = text
    result.redaction_count = 0
    return result


@pytest.mark.asyncio
async def test_cancelled_before_orchestration_skips_the_orchestrator_call(claim_registry):
    """AC1: a checkpoint before the expensive call stops it from ever starting."""
    tm = _FakeTaskManager()
    orchestrator = MagicMock()
    orchestrator.process_request = AsyncMock(return_value={"response": "should never run"})

    def _scrub_then_cancel(text, **_kwargs):
        tm.cancel()
        return _scrub_ok(text)

    with (
        patch("a2a.task_executor.get_task_manager", return_value=tm),
        patch("a2a.task_executor.get_trust_manager", return_value=MagicMock()),
        patch("a2a.task_executor.scrub_outbound", side_effect=_scrub_then_cancel),
        patch("agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True),
    ):
        await execute_a2a_task("task-cp1", "do something", context={"declared_scopes": ["path:a/b"]})

    orchestrator.process_request.assert_not_called()
    assert TaskState.COMPLETED not in [s for s, _m in tm.update_state_calls]
    assert [c.scope for c in await list_claims()] == [], "scope must be released once the checkpoint aborts"


@pytest.mark.asyncio
async def test_already_cancelled_before_the_first_checkpoint_does_nothing(claim_registry):
    """The "before scrub" checkpoint, not just the later ones (#16174 review).

    Every other test in this file cancels mid-run, inside `scrub_outbound` or
    `process_request`'s side effect -- so removing the *first* checkpoint
    (the one before either runs) would leave them all green. `execute_a2a_task`
    itself unconditionally moves the task to WORKING before anything else
    (task_executor.py:98), so an initial CANCELLED state cannot survive to the
    checkpoint -- cancelling from *inside* that update_state call is the only
    way to have the task be CANCELLED by the time "before scrub" checks it.
    """
    tm = _FakeTaskManager()

    def _cancel_once_working(task_id, state, message=None):
        tm.update_state_calls.append((state, message))
        tm.state = TaskState.CANCELLED if state == TaskState.WORKING else state

    tm.update_state = _cancel_once_working
    scrub = MagicMock(side_effect=AssertionError("scrub_outbound must not run once already cancelled"))
    orchestrator = MagicMock()
    orchestrator.process_request = AsyncMock(side_effect=AssertionError("process_request must not run"))

    with (
        patch("a2a.task_executor.get_task_manager", return_value=tm),
        patch("a2a.task_executor.get_trust_manager", return_value=MagicMock()),
        patch("a2a.task_executor.scrub_outbound", scrub),
        patch("agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True),
    ):
        await execute_a2a_task("task-cp0", "do something", context={"declared_scopes": ["path:a/b"]})

    scrub.assert_not_called()
    orchestrator.process_request.assert_not_called()
    assert tm.artifacts == [], "no artifact must be stored once already cancelled"
    assert [c.scope for c in await list_claims()] == [], "scope must be released, never having done any work"


@pytest.mark.asyncio
async def test_scope_stays_held_while_the_orchestrator_call_is_still_running(claim_registry):
    """AC3: cancelling mid-call must not free the scope while work is still in flight."""
    tm = _FakeTaskManager()
    held_when_cancelled: list[str] = []

    async def _process(*_args, **_kwargs):
        tm.cancel()  # a cancel request arrives while this call is still running
        held_when_cancelled.extend(c.scope for c in await list_claims())
        return {"response": "still finishes this call"}

    orchestrator = MagicMock()
    orchestrator.process_request = AsyncMock(side_effect=_process)

    with (
        patch("a2a.task_executor.get_task_manager", return_value=tm),
        patch("a2a.task_executor.get_trust_manager", return_value=MagicMock()),
        patch("a2a.task_executor.scrub_outbound", return_value=_scrub_ok()),
        patch("agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True),
    ):
        await execute_a2a_task("task-cp2", "do something", context={"declared_scopes": ["path:a/b"]})

    assert "path:a/b" in held_when_cancelled, "the scope must still be held while the orchestrator call is running"


@pytest.mark.asyncio
async def test_cancelled_during_orchestration_performs_no_further_work_and_releases(claim_registry):
    """AC2: once the next checkpoint sees the cancellation, no more work runs and the scope frees."""
    tm = _FakeTaskManager()

    async def _process(*_args, **_kwargs):
        tm.cancel()
        return {"response": "produced but must be discarded"}

    orchestrator = MagicMock()
    orchestrator.process_request = AsyncMock(side_effect=_process)
    eval_mock = AsyncMock()

    with (
        patch("a2a.task_executor.get_task_manager", return_value=tm),
        patch("a2a.task_executor.get_trust_manager", return_value=MagicMock()),
        patch("a2a.task_executor.scrub_outbound", return_value=_scrub_ok()),
        patch("a2a.task_executor.evaluate_task_output", new=eval_mock),
        patch("agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True),
    ):
        await execute_a2a_task("task-cp3", "do something", context={"declared_scopes": ["path:a/b"]})

    eval_mock.assert_not_called()
    assert tm.artifacts == [], "no response/metadata artifact must be stored once cancelled"
    assert TaskState.COMPLETED not in [s for s, _m in tm.update_state_calls]
    assert [c.scope for c in await list_claims()] == [], "scope must be released once the checkpoint aborts"


@pytest.mark.asyncio
async def test_never_cancelled_still_completes_normally(claim_registry):
    """Contrast: without a cancellation, the run reaches COMPLETED as before."""
    tm = _FakeTaskManager()
    orchestrator = MagicMock()
    orchestrator.process_request = AsyncMock(return_value={"response": "hello"})
    eval_pass = MagicMock(passed=True, confidence=0.9, eval_reason=None)

    with (
        patch("a2a.task_executor.get_task_manager", return_value=tm),
        patch("a2a.task_executor.get_trust_manager", return_value=MagicMock()),
        patch("a2a.task_executor.scrub_outbound", return_value=_scrub_ok("hello")),
        patch("a2a.task_executor.evaluate_task_output", new=AsyncMock(return_value=eval_pass)),
        patch("agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True),
    ):
        await execute_a2a_task("task-cp4", "do something", context={"declared_scopes": ["path:a/b"]})

    assert TaskState.COMPLETED in [s for s, _m in tm.update_state_calls]
    assert [c.scope for c in await list_claims()] == [], "scope releases on normal completion too"
