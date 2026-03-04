# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Redis-persisted WorkflowStateMachine with explicit routing (#1380).

Replaces the in-memory ``active_workflows`` dict in ``api/workflow.py``
with a crash-recoverable, Redis-backed state machine.  Each workflow is
stored as a JSON blob under ``autobot:workflow:{workflow_id}`` in the
``workflows`` Redis database.  Active workflow IDs are tracked in a
Redis Set at ``autobot:workflow:active``.

Usage::

    from api.workflow_state import get_workflow_state_machine

    sm = get_workflow_state_machine()
    state = await sm.create("wf-1", "deploy browser", steps)
    state = await sm.transition("wf-1", "executing", "plan done")
    state = await sm.complete("wf-1")
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from autobot_shared.models.service_message import ServiceMessage
from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

KEY_PREFIX = "autobot:workflow:"
ACTIVE_SET = "autobot:workflow:active"
COMPLETED_TTL = 7 * 24 * 3600  # 7 days in seconds
REDIS_DATABASE = "workflows"


# ------------------------------------------------------------------ #
# Pydantic model
# ------------------------------------------------------------------ #


class WorkflowState(BaseModel):
    """Persistent workflow state with explicit routing."""

    workflow_id: str
    goal: str
    current_step: str = "planning"
    active_service: str = "main-backend"
    steps_completed: List[str] = Field(default_factory=list)
    steps_remaining: List[Dict] = Field(default_factory=list)
    mailbox: List[ServiceMessage] = Field(default_factory=list)
    done: bool = False
    errors: List[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict = Field(default_factory=dict)


# ------------------------------------------------------------------ #
# Pure routing function
# ------------------------------------------------------------------ #


def route_next(state: WorkflowState) -> str:
    """Determine next service based on current state.

    Returns the service name responsible for the current step,
    or ``"complete"`` when the workflow is finished or the step
    is unrecognised.
    """
    if state.done:
        return "complete"

    routing = {
        "planning": "main-backend",
        "executing": state.metadata.get("executor_service", "main-backend"),
        "validating": "main-backend",
    }
    return routing.get(state.current_step, "complete")


# ------------------------------------------------------------------ #
# State machine
# ------------------------------------------------------------------ #


class WorkflowStateMachine:
    """Redis-persisted workflow state with routing logic."""

    def _key(self, workflow_id: str) -> str:
        """Build the Redis key for a workflow."""
        return f"{KEY_PREFIX}{workflow_id}"

    async def _redis(self):
        """Get async Redis client for workflows db."""
        return await get_redis_client(async_client=True, database=REDIS_DATABASE)

    async def _persist(self, state: WorkflowState) -> None:
        """Serialize and store *state* in Redis."""
        redis = await self._redis()
        await redis.set(
            self._key(state.workflow_id),
            state.model_dump_json(),
        )

    async def create(
        self,
        workflow_id: str,
        goal: str,
        steps: List[Dict],
    ) -> WorkflowState:
        """Create a new workflow, persist it, add to active set."""
        state = WorkflowState(
            workflow_id=workflow_id,
            goal=goal,
            steps_remaining=steps,
        )
        state.active_service = route_next(state)

        redis = await self._redis()
        await redis.set(self._key(workflow_id), state.model_dump_json())
        await redis.sadd(ACTIVE_SET, workflow_id)

        logger.info(
            "Workflow %s created (goal=%s, steps=%d)",
            workflow_id,
            goal,
            len(steps),
        )
        return state

    async def get(self, workflow_id: str) -> Optional[WorkflowState]:
        """Retrieve a workflow from Redis, or *None*."""
        redis = await self._redis()
        raw = await redis.get(self._key(workflow_id))
        if raw is None:
            return None
        return WorkflowState.model_validate_json(raw)

    async def transition(
        self,
        workflow_id: str,
        new_step: str,
        result: str = "",
    ) -> WorkflowState:
        """Move workflow to *new_step*, record previous step."""
        state = await self.get(workflow_id)
        if state is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        state.steps_completed.append(state.current_step)
        state.current_step = new_step
        state.active_service = route_next(state)
        state.updated_at = datetime.now(timezone.utc).isoformat()

        await self._persist(state)

        logger.info(
            "Workflow %s transitioned to %s",
            workflow_id,
            new_step,
        )
        return state

    async def complete(self, workflow_id: str) -> WorkflowState:
        """Mark workflow done, remove from active, set TTL."""
        state = await self.get(workflow_id)
        if state is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        state.done = True
        state.current_step = "complete"
        state.active_service = route_next(state)
        state.updated_at = datetime.now(timezone.utc).isoformat()

        redis = await self._redis()
        await redis.set(self._key(workflow_id), state.model_dump_json())
        await redis.srem(ACTIVE_SET, workflow_id)
        await redis.expire(self._key(workflow_id), COMPLETED_TTL)

        logger.info("Workflow %s completed", workflow_id)
        return state

    async def fail(self, workflow_id: str, error: str) -> WorkflowState:
        """Mark workflow failed, append error."""
        state = await self.get(workflow_id)
        if state is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        state.current_step = "failed"
        state.done = True
        state.errors.append(error)
        state.active_service = route_next(state)
        state.updated_at = datetime.now(timezone.utc).isoformat()

        await self._persist(state)

        logger.warning("Workflow %s failed: %s", workflow_id, error)
        return state

    async def list_active(self) -> List[WorkflowState]:
        """Return all active workflow states."""
        redis = await self._redis()
        ids = await redis.smembers(ACTIVE_SET)

        states: List[WorkflowState] = []
        for raw_id in ids:
            wf_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else raw_id
            state = await self.get(wf_id)
            if state is not None:
                states.append(state)
        return states


# ------------------------------------------------------------------ #
# Singleton factory
# ------------------------------------------------------------------ #

_instance: Optional[WorkflowStateMachine] = None


def get_workflow_state_machine() -> WorkflowStateMachine:
    """Return the singleton WorkflowStateMachine instance."""
    global _instance
    if _instance is None:
        _instance = WorkflowStateMachine()
    return _instance
