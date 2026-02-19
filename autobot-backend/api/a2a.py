# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Protocol API Router

Issue #961: Exposes AutoBot as an A2A-compliant agent server.

Endpoints:
  GET  /api/a2a/agent-card        Agent Card (capabilities + skills)
  GET  /.well-known/agent.json    Canonical A2A discovery endpoint (root-level)
  POST /api/a2a/tasks             Submit a task
  GET  /api/a2a/tasks             List all tasks
  GET  /api/a2a/tasks/{id}        Get task status + artifacts
  DELETE /api/a2a/tasks/{id}      Cancel a task
  GET  /api/a2a/stats             Task statistics

The /.well-known/agent.json canonical URL is registered by
backend/initialization/endpoints.py using this router's card builder.
"""

import logging
from typing import Any, Dict, Optional

from a2a.agent_card import build_agent_card
from a2a.task_executor import execute_a2a_task
from a2a.task_manager import get_task_manager
from a2a.types import Task
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TaskSendRequest(BaseModel):
    """Body for POST /tasks — submit a new A2A task."""

    message: str = Field(..., description="The natural-language task to execute")
    context: Optional[Dict[str, Any]] = Field(
        None, description="Optional key-value context passed to the orchestrator"
    )


class TaskSendResponse(BaseModel):
    """Immediate response when a task is accepted."""

    id: str
    state: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_url(request: Request) -> str:
    """Derive the server base URL from the incoming request."""
    return str(request.base_url).rstrip("/")


def _task_response(task: Task) -> Dict[str, Any]:
    """Serialize a Task to a response dict."""
    return task.to_dict()


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------


@router.get(
    "/agent-card",
    summary="A2A Agent Card",
    tags=["a2a"],
    response_model=None,
)
async def get_agent_card(request: Request) -> Dict[str, Any]:
    """
    Return the A2A Agent Card describing AutoBot's capabilities and skills.

    Also served at /.well-known/agent.json for standard A2A discovery.
    """
    card = build_agent_card(_base_url(request))
    return card.to_dict()


# ---------------------------------------------------------------------------
# Task management
# ---------------------------------------------------------------------------


@router.post(
    "/tasks",
    summary="Submit A2A task",
    tags=["a2a"],
    status_code=202,
)
async def submit_task(
    body: TaskSendRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """
    Accept a task and begin execution asynchronously.

    Returns immediately with the task ID and initial state (submitted).
    Poll GET /tasks/{id} to retrieve results.
    """
    manager = get_task_manager()
    task = manager.create_task(body.message, body.context)

    background_tasks.add_task(
        execute_a2a_task,
        task.id,
        body.message,
        body.context,
    )

    logger.info("A2A task submitted: %s — %.60s", task.id, body.message)
    return {"id": task.id, "state": task.status.state.value}


@router.get(
    "/tasks",
    summary="List A2A tasks",
    tags=["a2a"],
)
async def list_tasks() -> list:
    """Return all A2A tasks with their current state and artifacts."""
    manager = get_task_manager()
    return [_task_response(t) for t in manager.list_tasks()]


@router.get(
    "/tasks/{task_id}",
    summary="Get A2A task",
    tags=["a2a"],
)
async def get_task(task_id: str) -> Dict[str, Any]:
    """Return a specific task by ID, including state and any artifacts."""
    manager = get_task_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return _task_response(task)


@router.delete(
    "/tasks/{task_id}",
    summary="Cancel A2A task",
    tags=["a2a"],
)
async def cancel_task(task_id: str) -> Dict[str, str]:
    """Cancel a pending or in-progress task."""
    manager = get_task_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    if not manager.cancel_task(task_id):
        raise HTTPException(
            status_code=409,
            detail=f"Task '{task_id}' is already in a terminal state",
        )
    return {"id": task_id, "state": "cancelled"}


@router.get(
    "/stats",
    summary="A2A task statistics",
    tags=["a2a"],
)
async def task_stats() -> Dict[str, Any]:
    """Return task counts broken down by state."""
    manager = get_task_manager()
    return {"counts": manager.stats(), "total": len(manager.list_tasks())}
