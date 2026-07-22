# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for async-path MemoryManager offloading in ContextAwareDecisionSystem
(#12101).

``MemoryManager.create_task_record/start_task/complete_task`` are sync
SQLite writes. ``_store_decision_in_memory`` is an async method called on
the event loop, so the create->start->complete sequence must be offloaded
via a single ``asyncio.to_thread`` call rather than calling the sync
MemoryManager methods directly.
"""

from unittest.mock import MagicMock, patch

import pytest

from context_aware_decision.models import Decision, DecisionContext
from context_aware_decision.system import ContextAwareDecisionSystem
from context_aware_decision.types import ConfidenceLevel, DecisionType


def _make_decision() -> Decision:
    return Decision(
        decision_id="dec-1",
        decision_type=DecisionType.AUTOMATION_ACTION,
        chosen_action={"action": "noop"},
        alternative_actions=[],
        confidence=0.9,
        confidence_level=ConfidenceLevel.HIGH,
        reasoning="test",
        supporting_evidence=[],
        risk_assessment={},
        expected_outcomes=[],
        monitoring_criteria=[],
        fallback_plan=None,
        requires_approval=False,
        timestamp=0.0,
    )


def _make_context() -> DecisionContext:
    return DecisionContext(
        decision_id="dec-1",
        decision_type=DecisionType.AUTOMATION_ACTION,
        primary_goal="test goal",
        context_elements=[],
        constraints=[],
        available_actions=[],
        risk_factors=[],
        user_preferences={},
        system_state={},
        historical_patterns=[],
        timestamp=0.0,
    )


@pytest.mark.asyncio
async def test_store_decision_offloads_memory_writes_to_thread():
    """_store_decision_in_memory must offload the create->start->complete
    sequence via asyncio.to_thread instead of blocking the event loop."""
    memory_manager = MagicMock()
    memory_manager.create_task_record.return_value = "task-1"
    system = ContextAwareDecisionSystem(memory_manager=memory_manager)

    decision = _make_decision()
    context = _make_context()

    with patch("context_aware_decision.system.asyncio.to_thread") as mock_to_thread:

        async def _immediate(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_to_thread.side_effect = _immediate

        await system._store_decision_in_memory(decision, context)

    mock_to_thread.assert_called_once()
    assert mock_to_thread.call_args.args[0] == system._record_decision_in_memory
    memory_manager.create_task_record.assert_called_once()
    memory_manager.start_task.assert_called_once_with("task-1")
    memory_manager.complete_task.assert_called_once()


@pytest.mark.asyncio
async def test_store_decision_swallows_errors_without_blocking():
    """Errors during the offloaded write are logged, not raised (matches
    prior behavior of the inline try/except)."""
    memory_manager = MagicMock()
    memory_manager.create_task_record.side_effect = RuntimeError("db locked")
    system = ContextAwareDecisionSystem(memory_manager=memory_manager)

    await system._store_decision_in_memory(_make_decision(), _make_context())

    memory_manager.create_task_record.assert_called_once()
