# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One planner runner for every chat route (#21023, part of #20846).

The chat graph (``graph.py``), the legacy continuation loop (``manager._run_llm_iterations``) and
delegated subagents (``delegation`` drives that same loop) all plan through ``open_plan`` /
``PlanTracker``. Nothing here is gated: the caller checks ``config.llm.chat_planner_enabled``.

Advancing: one plan step per tool pass, decided per result status by ``STATUS_OUTCOME`` (the one table).
A pass with any failing result fails the current step (the planner blocks its dependents, so the plan
stops); otherwise a pass with a succeeding result completes it and starts the next executable step; a pass
whose results all wait (approval or delegation pending) changes nothing. Steps are capped at the turn's iteration
limit (``limits.MAX_CONTINUATION_ITERATIONS``), so a plan can never ask for more passes than the turn has.

Delegation: a subagent plans with ``cap // (depth + 1)`` steps and with none when that is under two, so
a delegated run gets a shallower plan and a nested one gets no plan.

State and events (``EVENT_STATE_DOCTRINE.md``): the plan body is durable in Redis (``autobot:plans:<id>``,
written by the planner); the graph state carries only ids and the rendered step block. The planner gets no
``event_stream`` -- that is the second bus the doctrine forbids -- so the plan reaches clients once, as the
existing ``agent.plan`` event on the one bus (``cot_events.emit_plan``); no new event type is added.
A canned fallback plan (the model wrote none) is treated as no plan.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from planner import LLMPlannerModule
from planner.planner import PlannerConfig
from planner.types import ExecutionPlan, PlanStep

from . import limits
from .planner_client import PlannerLLMClient

logger = get_logger(__name__)

#: A plan shorter than this is not worth a step-by-step block.
MIN_PLAN_STEPS = 2

ADVANCE, FAIL, WAIT = "advance", "fail", "wait"

#: What each tool-result status does to the current plan step. Every status the dispatch path can put in
#: an execution result is listed (``tool_handler``, ``tool_dispatch_guards``, ``mcp_approval_message``,
#: ``compose_tool_handler``); ``plan_status_table_21023_test`` fails when a new one appears unlisted.
#:   advance: the tool ran and produced a result (``completed`` is a finished delegate, ``executed`` compose).
#:   fail:    the tool did not run or was refused (``schema_error``, ``ast_rejected``, ``gated`` included).
#:   wait:    the result is not final yet (approval or delegation pending); the step stays current.
STATUS_OUTCOME: Dict[str, str] = {
    "success": ADVANCE,
    "completed": ADVANCE,
    "executed": ADVANCE,
    "error": FAIL,
    "schema_error": FAIL,
    "ast_rejected": FAIL,
    "gated": FAIL,
    "pending_approval": WAIT,
    "approval_required": WAIT,
    "pending_delegation": WAIT,
}
_NO_REDIS_LOGGED = False


def steps_for_depth(depth: int) -> int:
    """Plan length allowed at delegation ``depth`` (0 = the user's own turn); 0 means no plan."""
    cap = limits.MAX_CONTINUATION_ITERATIONS // (max(depth, 0) + 1)
    return cap if cap >= MIN_PLAN_STEPS else 0


def worth_planning(task: str) -> bool:
    """A turn shorter than ``chat_planner_min_message_chars`` ("hi", "thanks") skips the planner LLM call."""
    from autobot_shared.ssot_config import config

    return len((task or "").strip()) >= config.llm.chat_planner_min_message_chars


def planner_enabled() -> bool:
    """The SSOT switch for planning; read per call so a change needs no restart."""
    from autobot_shared.ssot_config import config

    return bool(config.llm.chat_planner_enabled)


def _build_planner(manager: Any, model: str, session_id: str, max_steps: int) -> LLMPlannerModule:
    return LLMPlannerModule(
        PlannerLLMClient(model, session_id),
        None,  # no second event bus; see the module docstring
        redis_client=getattr(manager, "redis_client", None),
        config=PlannerConfig(max_steps_per_plan=max_steps),
    )


def _step_block(plan: ExecutionPlan, step: Optional[PlanStep]) -> str:
    if step is None:
        return ""
    return (
        f"Plan step {step.step_number} of {plan.total_steps}: {step.description}. "
        "Work on this step now; the plan moves on once its tools have run."
    )


def with_guidance(prompt: str, block: str) -> str:
    """``prompt`` plus the step ``block`` as a Guidance paragraph (never a SystemMessage: #3260)."""
    return f"{prompt}\n\n[Guidance: {block}]" if block else prompt


class PlanTracker:
    """A turn's plan: ids plus the rendered block. Rebuilt from graph state with ``tracker_from_state``."""

    def __init__(self, planner: LLMPlannerModule, plan_id: str, step_id: Optional[str], block: str = ""):
        self.planner = planner
        self.plan_id = plan_id
        self.step_id = step_id
        self.block = block
        self.done = 0
        self.total = 0

    def state_update(self) -> Dict[str, Any]:
        """The ``ChatState`` fields for this plan."""
        progress = {"done": self.done, "total": self.total, "complete": self.step_id is None, "block": self.block}
        return {"plan_id": self.plan_id, "current_step_id": self.step_id, "plan_progress": progress}

    async def _refresh(self, plan: ExecutionPlan) -> None:
        step = plan.get_current_step()
        self.step_id = step.step_id if step else None
        self.block = _step_block(plan, step)
        self.done, self.total = plan.completed_steps, plan.total_steps

    async def start_first(self) -> None:
        """Start the first executable step."""
        plan = await self.planner.get_plan(self.plan_id)
        if plan is not None:
            await self._start_next(plan)

    async def _start_next(self, plan: ExecutionPlan) -> None:
        ready = plan.get_next_executable_steps()
        if ready:
            await self.planner.start_step(plan.plan_id, ready[0].step_id)
        await self._refresh(plan)

    async def advance(self, new_entries: List[Dict[str, Any]]) -> None:
        """Complete or fail the current step from the tool results of the pass that just ran."""
        ran = [e for e in new_entries or [] if STATUS_OUTCOME.get(e.get("status")) in (ADVANCE, FAIL)]
        if not self.step_id or not ran:
            return
        try:
            await self._settle(ran)
        except Exception:
            logger.exception("plan %s: could not advance (the turn continues without plan state)", self.plan_id)
            self.step_id, self.block = None, ""

    async def _settle(self, ran: List[Dict[str, Any]]) -> None:
        failed = [e for e in ran if STATUS_OUTCOME[e["status"]] == FAIL]
        if failed:
            await self.planner.fail_step(self.plan_id, self.step_id, str(failed[0].get("error") or "tool error"))
        else:
            tools = [str(e["tool"]) for e in ran if e.get("tool")]
            await self.planner.complete_step(self.plan_id, self.step_id, tools_used=tools)
        plan = await self.planner.get_plan(self.plan_id)
        if failed or plan is None:
            self.step_id, self.block = None, ""
        else:
            await self._start_next(plan)

    def with_block(self, prompt: str) -> str:
        """``prompt`` with the current step appended."""
        return with_guidance(prompt, self.block)


async def _create(planner: LLMPlannerModule, task: str) -> Optional[ExecutionPlan]:
    try:
        return await asyncio.wait_for(planner.create_plan(task), timeout=limits.PLANNER_TIMEOUT_SECONDS)
    except Exception:
        logger.exception("chat planner: no plan this turn (the turn runs without one)")
        return None


def _log_no_redis_once() -> None:
    """Without Redis a plan cannot be read back per node, so it is not made (and not announced)."""
    global _NO_REDIS_LOGGED
    if not _NO_REDIS_LOGGED:
        _NO_REDIS_LOGGED = True
        logger.info("chat planner: no Redis client, so a plan cannot be tracked; turns run without a plan")


async def open_plan(manager: Any, *, session_id: str, task: str, model: str, depth: int = 0) -> Optional[PlanTracker]:
    """Plan ``task`` for this turn, start its first step, emit ``agent.plan``; ``None`` = run without a plan."""
    max_steps = steps_for_depth(depth)
    if not max_steps or not task or not worth_planning(task):
        return None
    if getattr(manager, "redis_client", None) is None:
        _log_no_redis_once()
        return None
    planner = _build_planner(manager, model, session_id, max_steps)
    plan = await _create(planner, task)
    if plan is None or plan.metadata.get("fallback") or plan.total_steps < MIN_PLAN_STEPS:
        return None
    from .cot_events import emit_plan

    tracker = PlanTracker(planner, plan.plan_id, None)
    await tracker.start_first()
    emit_plan([s.description for s in plan.steps], session_id=session_id)
    return tracker


def tracker_from_state(manager: Any, state: Dict[str, Any]) -> Optional[PlanTracker]:
    """The turn's tracker from ``plan_id`` / ``current_step_id`` / ``plan_progress`` in graph state."""
    plan_id = state.get("plan_id")
    if not plan_id:
        return None
    progress = state.get("plan_progress") or {}
    model = (state.get("llm_params") or {}).get("selected_model", "")
    planner = _build_planner(manager, model, state.get("session_id", ""), limits.MAX_CONTINUATION_ITERATIONS)
    tracker = PlanTracker(planner, plan_id, state.get("current_step_id"), progress.get("block", ""))
    tracker.done, tracker.total = progress.get("done", 0), progress.get("total", 0)
    return tracker


class NoPlan:
    """The tracker of a run with no plan: every call is a no-op, so callers need no ``if plan`` branches."""

    async def advance(self, new_entries: List[Dict[str, Any]]) -> None:
        return None

    def with_block(self, prompt: str) -> str:
        return prompt


async def open_for_ctx(manager: Any, ctx: Any) -> "PlanTracker | NoPlan":
    """The plan for a legacy-loop or delegated run (``ctx`` is its ``LLMIterationContext``); ``NoPlan`` when off."""
    if not planner_enabled():
        return NoPlan()
    depth = int((ctx.context or {}).get("delegation_depth", 0))
    tracker = await open_plan(
        manager, session_id=ctx.session_id, task=ctx.message or "", model=ctx.selected_model, depth=depth
    )
    return tracker or NoPlan()
