# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Protocol API Router

Issue #961: Exposes AutoBot as an A2A-compliant agent server.
Issue #968: Adds signed agent card, trace context, caller_id, rate limiting,
            audit log endpoint, and capability verification endpoint.

Endpoints:
  GET  /api/a2a/agent-card              Agent Card (capabilities + skills)
  GET  /api/a2a/agent-card/signed       Signed Agent Card (HMAC-verified identity)
  GET  /.well-known/agent.json          Canonical A2A discovery endpoint (root-level)
  POST /api/a2a/tasks                   Submit a task
  GET  /api/a2a/tasks                   List all tasks
  GET  /api/a2a/tasks/{id}              Get task status + artifacts
  GET  /api/a2a/tasks/{id}/trace        Full audit trace for a task
  DELETE /api/a2a/tasks/{id}            Cancel a task
  GET  /api/a2a/stats                   Task statistics
  GET  /api/a2a/capabilities            Verify local capability claims
  POST /api/a2a/capabilities/verify     Verify a remote agent's capabilities
"""

import logging
import os
import time
from typing import Any, Dict, Optional

from a2a.agent_card import build_agent_card
from a2a.capability_verifier import verify_local_card, verify_remote_card
from a2a.security import SecurityCardSigner
from a2a.task_executor import execute_a2a_task
from a2a.task_manager import get_task_manager
from a2a.tracing import extract_caller_id, new_trace_id
from a2a.types import Task
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Rate limiting (simple in-process token bucket per IP)
# ---------------------------------------------------------------------------

_RATE_LIMIT = int(os.environ.get("AUTOBOT_A2A_RATE_LIMIT", "30"))  # per minute
_rate_buckets: Dict[str, list] = {}  # ip → [timestamps]


def _check_rate_limit(remote_addr: str) -> None:
    """
    Enforce a per-IP rate limit on task submissions.

    Raises HTTP 429 if the caller has exceeded _RATE_LIMIT requests/minute.
    Uses a sliding window stored in _rate_buckets (in-process, per worker).
    """
    now = time.time()
    window_start = now - 60
    bucket = _rate_buckets.get(remote_addr, [])
    bucket = [t for t in bucket if t > window_start]
    if len(bucket) >= _RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"A2A rate limit exceeded ({_RATE_LIMIT} tasks/min). Try again later.",
        )
    bucket.append(now)
    _rate_buckets[remote_addr] = bucket


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
    trace_id: str


class RemoteVerifyRequest(BaseModel):
    """Body for POST /capabilities/verify."""

    url: str = Field(..., description="Base URL of the remote agent to verify")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_url(request: Request) -> str:
    """Derive the server base URL from the incoming request."""
    return str(request.base_url).rstrip("/")


def _task_response(task: Task) -> Dict[str, Any]:
    """Serialize a Task to a response dict."""
    return task.to_dict()


def _remote_addr(request: Request) -> str:
    """Extract the real client IP (respects X-Forwarded-For from nginx)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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


@router.get(
    "/agent-card/signed",
    summary="Signed A2A Agent Card",
    tags=["a2a"],
    response_model=None,
)
async def get_signed_agent_card(request: Request) -> Dict[str, Any]:
    """
    Return the A2A Agent Card with an HMAC-SHA256 signature.

    Issue #968: Allows remote agents to verify AutoBot's identity and ensure
    the card has not been tampered with (rug-pull attack prevention).

    Requires AUTOBOT_A2A_SECRET to be configured.  Returns 503 if the secret
    is not available.

    Response shape::

        {
          "card":      { ...agent card... },
          "issued_at": 1700000000,
          "signature": "abcdef1234..."
        }
    """
    card = build_agent_card(_base_url(request))
    try:
        signed = SecurityCardSigner.sign(card.to_dict())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return signed


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
    request: Request,
    x_a2a_agent_id: Optional[str] = Header(None, alias="X-A2A-Agent-Id"),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """
    Accept a task and begin execution asynchronously.

    Issue #968 additions:
    - Rate limiting per source IP (AUTOBOT_A2A_RATE_LIMIT tasks/min, default 30)
    - caller_id extracted from X-A2A-Agent-Id header, JWT sub, or IP fallback
    - trace_id generated and returned in response + X-A2A-Trace-Id header

    Returns immediately with the task ID, trace ID, and initial state.
    Poll GET /tasks/{id} to retrieve results.
    """
    addr = _remote_addr(request)
    _check_rate_limit(addr)

    jwt_sub = _extract_jwt_sub(authorization)
    caller_id = extract_caller_id(x_a2a_agent_id, jwt_sub, addr)
    trace_id = new_trace_id()

    manager = get_task_manager()
    task = manager.create_task(
        body.message,
        context=body.context,
        caller_id=caller_id,
        trace_id=trace_id,
    )

    background_tasks.add_task(
        execute_a2a_task,
        task.id,
        body.message,
        body.context,
    )

    logger.info(
        "A2A task submitted: %s trace=%s caller=%s — %.60s",
        task.id,
        trace_id[:8],
        caller_id,
        body.message,
    )
    return {
        "id": task.id,
        "state": task.status.state.value,
        "traceId": trace_id,
    }


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


@router.get(
    "/tasks/{task_id}/trace",
    summary="Get A2A task audit trace",
    tags=["a2a"],
)
async def get_task_trace(task_id: str) -> Dict[str, Any]:
    """
    Return the full distributed trace (audit log) for a task.

    Issue #968: Provides visibility into which agent submitted the task,
    every state transition, and timing — addressing the observability
    blind spot in A2A identified in security research.
    """
    manager = get_task_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    audit = manager.get_audit_log(task_id)
    return {
        "task_id": task_id,
        "trace": task.trace_context.to_dict() if task.trace_context else None,
        "events": audit or [],
    }


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


# ---------------------------------------------------------------------------
# Capability verification (Issue #968)
# ---------------------------------------------------------------------------


@router.get(
    "/capabilities",
    summary="Verify local capability claims",
    tags=["a2a"],
)
async def local_capabilities() -> Dict[str, Any]:
    """
    Verify that every skill advertised in AutoBot's Agent Card is backed
    by a live registered agent.

    Issue #968: Addresses the A2A capability negotiation gap — claimed skills
    are checked against DEFAULT_AGENT_CAPABILITIES at runtime.
    """
    report = verify_local_card()
    return report.to_dict()


@router.post(
    "/capabilities/verify",
    summary="Verify a remote agent's capabilities",
    tags=["a2a"],
)
async def verify_remote_capabilities(body: RemoteVerifyRequest) -> Dict[str, Any]:
    """
    Fetch and sanity-check a remote agent's skill claims.

    Issue #968: Fetches /.well-known/agent.json from the remote URL and
    verifies each claimed skill has sufficient metadata (id, description,
    and at least tags or examples).  Results are cached for 5 minutes.
    """
    report = await verify_remote_card(body.url)
    return report.to_dict()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_jwt_sub(authorization: Optional[str]) -> Optional[str]:
    """Extract the JWT subject claim without full validation."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return _decode_jwt_sub(token)


def _decode_jwt_sub(token: str) -> Optional[str]:
    """
    Decode the JWT sub claim without signature verification.

    We only use this for audit/logging — full auth is enforced upstream.
    Returns None on any decode error.
    """
    try:
        import base64
        import json as _json

        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1] + "=="
        payload = base64.urlsafe_b64decode(payload_b64)
        claims = _json.loads(payload)
        return claims.get("sub")
    except Exception:
        return None
