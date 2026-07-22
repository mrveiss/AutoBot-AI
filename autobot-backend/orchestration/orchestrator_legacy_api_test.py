# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for async-path MemoryManager offloading in process_user_request (#12101).

``get_task_tracker().start_task/complete_task/fail_task`` are sync
backward-compatibility wrappers that perform sync SQLite MemoryManager
writes. When called directly from the async ``process_user_request`` path
they block the event loop. These tests assert the calls are offloaded via
``asyncio.to_thread``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestration.orchestrator_legacy_api import _DeprecatedRequestMixin


class _FakeOrchestrator(_DeprecatedRequestMixin):
    """Minimal stand-in exercising only the mixin's deprecated API."""

    def __init__(self):
        self.metrics = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_processing_time": 0.0,
            "average_response_time": 0.0,
        }
        self.classification_agent = None
        self.config = MagicMock(orchestrator_llm_model="test-model")
        self.llm_service = MagicMock()
        self.llm_service.chat = AsyncMock(return_value=MagicMock(content="hi"))
        self.run_workflow = AsyncMock(return_value={"type": "workflow_result"})


def _immediate_to_thread():
    async def _run(func, *args, **kwargs):
        return func(*args, **kwargs)

    return _run


@pytest.mark.asyncio
async def test_process_user_request_offloads_start_task_to_thread():
    from orchestrator import OrchestrationMode

    orch = _FakeOrchestrator()
    mock_tracker = MagicMock()

    with (
        patch("orchestration.orchestrator_legacy_api.get_task_tracker", return_value=mock_tracker),
        patch(
            "orchestration.orchestrator_legacy_api.asyncio.to_thread",
            side_effect=_immediate_to_thread(),
        ) as mock_to_thread,
    ):
        result = await orch.process_user_request("hello world", mode=OrchestrationMode.SIMPLE)

    assert result["success"] is True
    called_funcs = [call.args[0] for call in mock_to_thread.call_args_list]
    assert orch._start_request_tracking in called_funcs
    assert mock_tracker.complete_task in called_funcs
    mock_tracker.start_task.assert_called_once()
    mock_tracker.complete_task.assert_called_once()


@pytest.mark.asyncio
async def test_process_user_request_offloads_fail_task_to_thread_on_exception():
    from orchestrator import OrchestrationMode

    orch = _FakeOrchestrator()
    orch.llm_service.chat = AsyncMock(side_effect=RuntimeError("boom"))
    mock_tracker = MagicMock()

    with (
        patch("orchestration.orchestrator_legacy_api.get_task_tracker", return_value=mock_tracker),
        patch(
            "orchestration.orchestrator_legacy_api.asyncio.to_thread",
            side_effect=_immediate_to_thread(),
        ) as mock_to_thread,
    ):
        result = await orch.process_user_request("hello world", mode=OrchestrationMode.SIMPLE)

    assert result["success"] is False
    called_funcs = [call.args[0] for call in mock_to_thread.call_args_list]
    assert mock_tracker.fail_task in called_funcs
    mock_tracker.fail_task.assert_called_once()
