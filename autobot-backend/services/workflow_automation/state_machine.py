# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Explicit state-machine routing for workflow automation (#1380).

Replaces implicit hardcoded step sequencing with a data-driven
``WorkflowState`` model and ``route_next()`` dispatcher.  State is
persisted in Redis (keyed ``autobot:workflow:state:{id}``) and every
transition is logged to the :class:`ServiceMessageBus` for audit.

Usage::

    from services.workflow_automation.state_machine import (
        WorkflowStateMachine,
    )

    sm = WorkflowStateMachine()
    state = await sm.create(workflow_id="abc", goal="deploy app")
    state = await sm.transition(state, "executing", "browser-worker")
"""

import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from constants.redis_constants import REDIS_KEY
from pydantic import BaseModel, Field

from autobot_shared.message_bus import get_message_bus
from autobot_shared.models.service_message import ServiceMessage
from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Enums & Model
# ------------------------------------------------------------------


class WorkflowPhase(str, Enum):
    """Discrete phases a workflow can occupy."""

    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"  # #1402: approval gate
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETE = "complete"
    FAILED = "failed"


# Default routing table: phase → service that should act next
DEFAULT_ROUTING_TABLE: Dict[str, str] = {
    "planning": "main-backend",
    "awaiting_approval": "main-backend",  # #1402
    "executing": "main-backend",
    "validating": "main-backend",
}


class WorkflowState(BaseModel):
    """Inspectable state for a single workflow execution (#1380)."""

    workflow_id: str
    goal: str = ""
    current_step: str = Field(
        default=WorkflowPhase.PLANNING.value,
        description="Current phase of the workflow.",
    )
    active_service: str = Field(
        default="main-backend",
        description="Service that should act next.",
    )
    steps_completed: List[str] = Field(default_factory=list)
    done: bool = False
    errors: List[str] = Field(default_factory=list)
    routing_table: Dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_ROUTING_TABLE),
    )
    meta: Dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------
# Routing function
# ------------------------------------------------------------------


def route_next(state: WorkflowState) -> str:
    """Determine the next service based on current workflow state.

    Returns the service name from the routing table, or ``"complete"``
    if the workflow is done / the phase is not mapped.
    """
    if state.done or state.current_step in (
        WorkflowPhase.COMPLETE.value,
        WorkflowPhase.FAILED.value,
    ):
        return "complete"
    return state.routing_table.get(state.current_step, "complete")


# ------------------------------------------------------------------
# Redis keys
# ------------------------------------------------------------------

_STATE_TTL = 86400  # 24 hours


def _state_key(workflow_id: str) -> str:
    return f"{REDIS_KEY.NAMESPACE}:workflow:state:{workflow_id}"


# ------------------------------------------------------------------
# State Machine (persistence + transitions)
# ------------------------------------------------------------------


class WorkflowStateMachine:
    """Manages workflow state lifecycle with Redis persistence.

    Every transition is:
    1. Persisted to Redis (``autobot:workflow:state:{id}``, 24h TTL).
    2. Published to the :class:`ServiceMessageBus` as a
       ``workflow_step`` message for audit trail (#1379).
    """

    def __init__(self) -> None:
        self._redis: Any = None

    async def _get_redis(self) -> Any:
        if self._redis is None:
            self._redis = await get_redis_client(async_client=True, database="main")
        return self._redis

    # -- Create --------------------------------------------------------

    async def create(
        self,
        workflow_id: str,
        goal: str = "",
        routing_table: Optional[Dict[str, str]] = None,
    ) -> WorkflowState:
        """Create and persist a new workflow state."""
        state = WorkflowState(
            workflow_id=workflow_id,
            goal=goal,
            current_step=WorkflowPhase.PLANNING.value,
            active_service="main-backend",
        )
        if routing_table:
            state.routing_table = routing_table

        await self._persist(state)
        await self._log_transition(
            state, from_phase="init", to_phase=state.current_step
        )
        logger.info(
            "State machine created for workflow %s (goal=%s)",
            workflow_id,
            goal[:60],
        )
        return state

    # -- Transition ----------------------------------------------------

    async def transition(
        self,
        state: WorkflowState,
        to_phase: str,
        active_service: Optional[str] = None,
        step_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> WorkflowState:
        """Move *state* to *to_phase*, updating active service.

        If *step_id* is given it is appended to ``steps_completed``.
        If *error* is given it is appended to ``errors``.
        """
        from_phase = state.current_step
        state.current_step = to_phase

        if active_service:
            state.active_service = active_service
        else:
            state.active_service = route_next(state)

        if step_id:
            state.steps_completed.append(step_id)

        if error:
            state.errors.append(error)

        if to_phase in (
            WorkflowPhase.COMPLETE.value,
            WorkflowPhase.FAILED.value,
        ):
            state.done = True

        await self._persist(state)
        await self._log_transition(state, from_phase, to_phase)
        return state

    # -- Load ----------------------------------------------------------

    async def load(self, workflow_id: str) -> Optional[WorkflowState]:
        """Load workflow state from Redis."""
        redis = await self._get_redis()
        raw = await redis.get(_state_key(workflow_id))
        if raw is None:
            return None
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return WorkflowState.model_validate_json(text)

    # -- Delete --------------------------------------------------------

    async def delete(self, workflow_id: str) -> None:
        """Remove workflow state from Redis."""
        redis = await self._get_redis()
        await redis.delete(_state_key(workflow_id))

    # -- Internal helpers ----------------------------------------------

    async def _persist(self, state: WorkflowState) -> None:
        redis = await self._get_redis()
        await redis.set(
            _state_key(state.workflow_id),
            state.model_dump_json(),
            ex=_STATE_TTL,
        )

    async def _log_transition(
        self,
        state: WorkflowState,
        from_phase: str,
        to_phase: str,
    ) -> None:
        """Publish a ``workflow_step`` message to ServiceMessageBus."""
        try:
            bus = get_message_bus()
            content = json.dumps(
                {
                    "workflow_id": state.workflow_id,
                    "from_phase": from_phase,
                    "to_phase": to_phase,
                    "active_service": state.active_service,
                    "steps_completed": len(state.steps_completed),
                    "done": state.done,
                    "errors": state.errors[-1:],
                },
                default=str,
            )
            msg = ServiceMessage(
                sender="main-backend",
                receiver=state.active_service,
                msg_type="workflow_step",
                content=content,
                meta={"workflow_id": state.workflow_id},
            )
            await bus.publish(msg)
        except Exception as exc:
            logger.warning(
                "Failed to log state transition for %s: %s",
                state.workflow_id,
                exc,
            )
