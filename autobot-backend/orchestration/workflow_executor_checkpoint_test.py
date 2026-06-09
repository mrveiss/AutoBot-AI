# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for Issue #3825: _save_checkpoint exception must not propagate.

A checkpoint failure after a successful step must be swallowed (logged as
WARNING) so that the step is not reported as failed.
"""

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestration.workflow_executor import WorkflowExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor() -> WorkflowExecutor:
    """Return a minimally configured WorkflowExecutor."""
    return WorkflowExecutor(
        agent_registry={},
        agent_interactions=[],
        reserve_agent_callback=lambda _: None,
        release_agent_callback=lambda _: None,
        update_performance_callback=lambda _a, _b, _c: None,
    )


def _make_execution_context(workflow_id: str = "wf-1") -> Dict[str, Any]:
    return {
        "workflow_id": workflow_id,
        "step_results": {},
        "step_outputs": {},
        "agents_involved": set(),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_failure_does_not_propagate_in_execute_step_with_agent():
    """
    Issue #3825: if _save_checkpoint raises inside _execute_step_with_agent,
    the exception must be swallowed and the step result must reflect success.
    """
    executor = _make_executor()
    execution_context = _make_execution_context()
    step: Dict[str, Any] = {"id": "step-1", "status": None, "result": None}
    successful_result = {"success": True, "output": "done"}

    # Checkpoint storage raises a transient error.
    executor._checkpoint_manager.save = MagicMock(side_effect=OSError("Redis unavailable"))

    async def _fake_retry(s, ec, ctx):
        return successful_result

    with patch.object(executor, "_execute_step_with_retry", side_effect=_fake_retry):
        # Must not raise, even though _save_checkpoint raises internally.
        await executor._execute_step_with_agent(step, execution_context, {})

    # Step result correctly stored as successful.
    assert execution_context["step_results"]["step-1"] is successful_result
    assert step["status"] == "completed"


@pytest.mark.asyncio
async def test_checkpoint_success_called_once_on_happy_path():
    """
    Issue #3825: sanity — _save_checkpoint is still invoked when it does not raise.
    """
    executor = _make_executor()
    execution_context = _make_execution_context()
    step: Dict[str, Any] = {"id": "step-2", "status": None, "result": None}
    successful_result = {"success": True, "output": "done"}

    save_spy = MagicMock()
    executor._checkpoint_manager.save = save_spy

    async def _fake_retry(s, ec, ctx):
        return successful_result

    with patch.object(executor, "_execute_step_with_retry", side_effect=_fake_retry):
        await executor._execute_step_with_agent(step, execution_context, {})

    save_spy.assert_called_once()


@pytest.mark.asyncio
async def test_checkpoint_not_called_when_step_fails():
    """
    Issue #3825: _save_checkpoint must not be called when the step fails.
    """
    executor = _make_executor()
    execution_context = _make_execution_context()
    step: Dict[str, Any] = {"id": "step-3", "status": None, "result": None}
    failed_result = {"success": False, "error": "agent error"}

    save_spy = MagicMock()
    executor._checkpoint_manager.save = save_spy

    async def _fake_retry(s, ec, ctx):
        return failed_result

    with (
        patch.object(executor, "_execute_step_with_retry", side_effect=_fake_retry),
        patch.object(executor, "_send_step_failure_notification", new_callable=AsyncMock),
    ):
        await executor._execute_step_with_agent(step, execution_context, {})

    save_spy.assert_not_called()
    assert step["status"] == "failed"
