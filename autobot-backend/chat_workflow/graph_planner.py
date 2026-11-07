# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The planner's seams in the chat graph (#21023, part of #20846); the logic is ``plan_runner``'s.

``create_plan`` is a graph node between knowledge search and generation. With
``config.llm.chat_planner_enabled`` off (the default) it returns at once and touches nothing.
"""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from autobot_shared.logging_manager import get_logger
from chat_workflow import plan_runner

logger = get_logger(__name__)

#: ``ChatState`` values for "no plan"; reset every turn (the checkpointer carries state between turns).
NO_PLAN: Dict[str, Any] = {"plan_id": None, "current_step_id": None, "plan_progress": {}}


async def create_plan(state: Dict[str, Any], config: RunnableConfig) -> dict:
    """Write the turn's plan, start step one and put its ids in state; no-op when planning is off."""
    if state.get("error") or not plan_runner.planner_enabled():
        return {}
    manager = config["configurable"]["manager"]
    tracker = await plan_runner.open_plan(
        manager,
        session_id=state["session_id"],
        task=state["user_message"],
        model=state["llm_params"]["selected_model"],
    )
    return tracker.state_update() if tracker else dict(NO_PLAN)


async def advance_after_tools(manager, state: Dict[str, Any], new_entries: list) -> dict:
    """Settle the current step from this pass's tool results; the state update ({} when the turn has no plan)."""
    tracker = plan_runner.tracker_from_state(manager, state)
    if tracker is None:
        return {}
    await tracker.advance(new_entries)
    return tracker.state_update()


def with_plan_step(prompt: str, state: Dict[str, Any]) -> str:
    """``prompt`` plus the current plan step, from the block already in state (no I/O)."""
    return plan_runner.with_guidance(prompt, (state.get("plan_progress") or {}).get("block", ""))
