# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for async-path MemoryManager offloading in ContextAwareDecisionSystem.

``MemoryManager`` task-write methods are sync SQLite writes that block the
event loop (#12101). Issue #12185 moved the offload into the MemoryManager
async task-write variants; ``_store_decision_in_memory`` now awaits those
variants (``acreate_task_record`` / ``astart_task`` / ``acomplete_task``)
rather than wrapping the sync methods in an inline ``asyncio.to_thread`` call.
"""

from unittest.mock import AsyncMock, MagicMock

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


def _memory_manager_with_async_writes() -> MagicMock:
    mm = MagicMock()
    mm.acreate_task_record = AsyncMock(return_value="task-1")
    mm.astart_task = AsyncMock(return_value=True)
    mm.acomplete_task = AsyncMock(return_value=True)
    return mm


@pytest.mark.asyncio
async def test_store_decision_uses_async_task_write_variants():
    """_store_decision_in_memory must await the create->start->complete sequence
    through the async task-write variants (which own the offload), never the
    loop-blocking sync methods directly."""
    memory_manager = _memory_manager_with_async_writes()
    system = ContextAwareDecisionSystem(memory_manager=memory_manager)

    await system._store_decision_in_memory(_make_decision(), _make_context())

    memory_manager.acreate_task_record.assert_awaited_once()
    memory_manager.astart_task.assert_awaited_once_with("task-1")
    memory_manager.acomplete_task.assert_awaited_once()
    # The sync (loop-blocking) methods must never be called directly.
    memory_manager.create_task_record.assert_not_called()
    memory_manager.start_task.assert_not_called()
    memory_manager.complete_task.assert_not_called()


@pytest.mark.asyncio
async def test_store_decision_swallows_errors_without_blocking():
    """Errors during the write are logged, not raised (inline try/except)."""
    memory_manager = _memory_manager_with_async_writes()
    memory_manager.acreate_task_record = AsyncMock(side_effect=RuntimeError("db locked"))
    system = ContextAwareDecisionSystem(memory_manager=memory_manager)

    await system._store_decision_in_memory(_make_decision(), _make_context())

    memory_manager.acreate_task_record.assert_awaited_once()
