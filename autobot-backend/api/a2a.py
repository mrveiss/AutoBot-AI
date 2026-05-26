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
  GET  /api/a2a/tasks/{id}/stream       SSE event stream for a task (Issue #4554)
  GET  /api/a2a/tasks/{id}/trace        Full audit trace for a task
  DELETE /api/a2a/tasks/{id}            Cancel a task
  GET  /api/a2a/stats                   Task statistics
  GET  /api/a2a/capabilities            Verify local capability claims
  POST /api/a2a/capabilities/verify     Verify a remote agent's capabilities
"""

import asyncio
import json
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from a2a.agent_card import build_agent_card
from a2a.capability_verifier import verify_local_card, verify_remote_card
from a2a.security import SecurityCardSigner
from a2a.task_executor import execute_a2a_task
from a2a.task_manager import get_task_manager
from a2a.tracing import extract_caller_id, new_trace_id
from a2a.trust_score import Capability, TrustAccessDenied, get_trust_manager
from a2a.types import Task
from api.schemas_agent import (
    A2AAgentCardResponse,
    A2ACancelTaskResponse,
    A2ACapabilitiesResponse,
    A2ASignedAgentCardResponse,
    A2AStatsResponse,
    A2ASubmitTaskResponse,
    A2ATaskResponse,
    A2ATaskTraceResponse,
    RemoteVerifyRequest,
    TaskSendRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(
    dependencies=[Depends(check_admin_permission)],
)

# ---------------------------------------------------------------------------
# Rate limiting — per-IP sliding window via shared IPRateLimiter (#7270/#7271)
# ---------------------------------------------------------------------------
#
# #7270: pre-fix, this was an in-process dict with the same multi-worker
# undercount that #6588 fixed for /v1/chat/completions. State is now shared
# across all uvicorn workers via Redis sorted-set; the in-process fallback
# is reserved for Redis outages only.

from autobot_shared.rate_limit import IPRateLimiter

_a2a_limiter = IPRateLimiter(
    key_prefix="ratelimit:a2a",
    limit_env="AUTOBOT_A2A_RATE_LIMIT",
    default_limit=30,
    window_seconds=60,
)


# ---------------------------------------------------------------------------
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
    response_model=A2AAgentCardResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_card",
    error_code_prefix="A2A",
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
    response_model=A2ASignedAgentCardResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_signed_agent_card",
    error_code_prefix="A2A",
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
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    return signed


# ---------------------------------------------------------------------------
# Task management
# ---------------------------------------------------------------------------


@router.post(
    "/tasks",
    summary="Submit A2A task",
    tags=["a2a"],
    status_code=202,
    response_model=A2ASubmitTaskResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="submit_task",
    error_code_prefix="A2A",
)
async def submit_task(
    body: TaskSendRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    x_a2a_agent_id: str | None = Header(None, alias="X-A2A-Agent-Id"),
    authorization: str | None = Header(None),
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
    await _a2a_limiter.check_or_429(addr)

    jwt_sub = _extract_jwt_sub(authorization)
    caller_id = extract_caller_id(x_a2a_agent_id, jwt_sub, addr)
    trace_id = new_trace_id()

    # Issue #7358: gate task submission by behavioural trust level.
    # Peers that have not yet earned LIMITED trust (≥ 0.30 score) are
    # restricted to discovery endpoints only.
    if x_a2a_agent_id:
        try:
            get_trust_manager().require_capability(x_a2a_agent_id, Capability.SUBMIT_TASKS)
        except TrustAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail=f"Peer trust level insufficient for task submission: {exc.level.value}",
            ) from exc

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
    response_model=List[A2ATaskResponse],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_tasks",
    error_code_prefix="A2A",
)
async def list_tasks() -> list:
    """Return all A2A tasks with their current state and artifacts."""
    manager = get_task_manager()
    return [_task_response(t) for t in manager.list_tasks()]


@router.get(
    "/tasks/{task_id}",
    summary="Get A2A task",
    tags=["a2a"],
    response_model=A2ATaskResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_task",
    error_code_prefix="A2A",
)
async def get_task(task_id: str) -> Dict[str, Any]:
    """Return a specific task by ID, including state and any artifacts."""
    manager = get_task_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return _task_response(task)


@router.get(
    "/tasks/{task_id}/stream",
    summary="Stream A2A task events (SSE)",
    tags=["a2a"],
    response_model=None,  # StreamingResponse — cannot be described by a Pydantic schema
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stream_task_events",
    error_code_prefix="A2A",
)
async def stream_task_events(task_id: str) -> StreamingResponse:
    """
    Server-Sent Events stream for a task.

    Issue #4554: Eliminates polling loops — clients subscribe once and receive
    push notifications for each state transition and artifact addition in real
    time via Redis pub/sub.

    Events::

        data: {"event": "state_change",   "state": "working",   "task_id": "…"}
        data: {"event": "artifact_added", "artifact_type": "text", "task_id": "…"}
        data: {"event": "state_change",   "state": "completed", "terminal": true, …}

    The stream closes automatically when a terminal event is received.
    A comment-line heartbeat is sent every 15 s to keep proxies alive.
    """
    manager = get_task_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    async def _event_generator():
        from autobot_shared.redis_client import get_async_redis_client

        _TERMINAL_STATES = {"completed", "failed", "cancelled"}
        channel = f"a2a:events:{task_id}"

        redis = await get_async_redis_client(database="main")
        if redis is None:
            yield 'data: {"event":"error","message":"Redis unavailable"}\n\n'
            return

        pubsub = redis.pubsub()
        # Subscribe BEFORE reading current state so events published in the
        # gap between subscribe and the snapshot are not lost.
        await pubsub.subscribe(channel)

        # Yield the current state immediately so the client is never blind.
        # (Intentional: if a state_change event also arrives via pub/sub in
        # this window, clients will receive the state twice — that is safe
        # because state_change events are idempotent.)
        current = manager.get_task(task_id)
        if current is None:
            yield 'data: {"event":"error","message":"Task expired"}\n\n'
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            return
        initial_payload = json.dumps(
            {
                "event": "state_change",
                "state": current.status.state.value,
                "task_id": task_id,
            }
        )
        yield f"data: {initial_payload}\n\n"
        if current.status.state.value in _TERMINAL_STATES:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            return

        # Feed pub/sub messages into an asyncio.Queue so we can apply a
        # heartbeat timeout without blocking the event loop.
        queue: asyncio.Queue = asyncio.Queue()

        async def _reader():
            try:
                async for msg in pubsub.listen():
                    if msg["type"] == "message":
                        data = msg["data"]
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")
                        await queue.put(data)
                        try:
                            if json.loads(data).get("terminal"):
                                await queue.put(None)  # sentinel — stop the loop
                                return
                        except Exception:
                            logger.debug("Could not parse pub/sub payload for task %s", task_id)
            except Exception as exc:
                logger.warning("pubsub listener error for task %s: %s", task_id, exc)
                await queue.put(None)  # unblock the outer loop on Redis failure

        reader_task = asyncio.create_task(_reader())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if item is None:
                    break
                yield f"data: {item}\n\n"
        finally:
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


@router.get(
    "/tasks/{task_id}/trace",
    summary="Get A2A task audit trace",
    tags=["a2a"],
    response_model=A2ATaskTraceResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_task_trace",
    error_code_prefix="A2A",
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
    response_model=A2ACancelTaskResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_task",
    error_code_prefix="A2A",
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
    response_model=A2AStatsResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="task_stats",
    error_code_prefix="A2A",
)
async def task_stats() -> Dict[str, Any]:
    """Return task counts broken down by state."""
    manager = get_task_manager()
    tasks = manager.list_tasks()
    counts: Dict[str, int] = {}
    for t in tasks:
        k = t.status.state.value
        counts[k] = counts.get(k, 0) + 1
    return {"counts": counts, "total": len(tasks)}


# ---------------------------------------------------------------------------
# Capability verification (Issue #968)
# ---------------------------------------------------------------------------


@router.get(
    "/capabilities",
    summary="Verify local capability claims",
    tags=["a2a"],
    response_model=A2ACapabilitiesResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="local_capabilities",
    error_code_prefix="A2A",
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
    response_model=A2ACapabilitiesResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="verify_remote_capabilities",
    error_code_prefix="A2A",
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


def _extract_jwt_sub(authorization: str | None) -> str | None:
    """Extract the JWT subject claim without full validation."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return _decode_jwt_sub(token)


def _decode_jwt_sub(token: str) -> str | None:
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
    except Exception as exc:
        logger.debug("JWT sub decode failed: %s", exc)
        return None
