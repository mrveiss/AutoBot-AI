# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Node Remote Execution API

Issue #3406: Adds POST /nodes/{node_id}/execute — a guarded endpoint that
runs a shell script on the target node.  Commands are validated against an
injection-pattern denylist and an optional allowlist before execution.

Security model
--------------
- Shell injection patterns (backtick, process substitution, null-byte, etc.)
  are always rejected.
- An opt-in ALLOWED_COMMANDS_PATTERN env var restricts commands to an
  additional regex if set.
- The node must be ONLINE before a job is accepted.
- All executions are audit-logged via the standard node event system.
"""

import asyncio
import logging
import os
import re
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import EventSeverity, EventType, Node, NodeEvent, NodeStatus
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nodes", tags=["nodes-execution"])

# ---------------------------------------------------------------------------
# Security: static injection-pattern denylist
# ---------------------------------------------------------------------------

# Patterns that are unconditionally rejected regardless of allowlist.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"`"),  # backtick command substitution
    re.compile(r"\$\("),  # $(…) command substitution
    re.compile(r"<\("),  # process substitution <(…)
    re.compile(r">\("),  # process substitution >(…)
    re.compile(r"\x00"),  # null byte
    re.compile(r";\s*rm\s"),  # destructive rm chaining
    re.compile(r"\|\s*bash"),  # pipe-to-bash
    re.compile(r"\|\s*sh\b"),  # pipe-to-sh
    re.compile(r"curl\s.*\|\s*(bash|sh)"),  # curl-pipe-execute
    re.compile(r"wget\s.*-O\s*-"),  # wget stdout pipe
]

# Optional: set ALLOWED_COMMANDS_PATTERN to a regex; commands not matching
# are rejected.  Empty / unset means no additional restriction.
_ALLOWED_RE_SRC = os.getenv("ALLOWED_COMMANDS_PATTERN", "")
_ALLOWED_RE: re.Pattern | None = (
    re.compile(_ALLOWED_RE_SRC) if _ALLOWED_RE_SRC else None
)


def _validate_command(script: str) -> None:
    """Raise HTTPException 400 if *script* contains forbidden patterns."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(script):
            logger.warning("Command rejected — injection pattern: %s", pattern.pattern)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Command rejected: forbidden pattern detected",
            )
    if _ALLOWED_RE and not _ALLOWED_RE.search(script):
        logger.warning("Command rejected — not in allowlist: %.80s", script)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Command rejected: does not match configured allowlist",
        )


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class NodeExecuteRequest(BaseModel):
    """Body for POST /nodes/{node_id}/execute."""

    command: str = Field(
        ...,
        description="Shell command or script body to execute on the node.",
        min_length=1,
        max_length=32_768,
    )
    language: str = Field(
        default="bash",
        description="Interpreter: 'bash' or 'sh'.",
        pattern=r"^(bash|sh)$",
    )
    timeout: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="Maximum execution time in seconds (1–3600).",
    )


class NodeExecuteResponse(BaseModel):
    """Result of a remote execution job."""

    node_id: str
    job_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_online_node(node_id: str, db: AsyncSession) -> Node:
    """Fetch node and verify it is ONLINE; raise 404/409 otherwise."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id!r} not found",
        )
    if node.status != NodeStatus.ONLINE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node {node_id!r} is not ONLINE (status: {node.status})",
        )
    return node


async def _audit_execute_event(
    db: AsyncSession,
    node_id: str,
    job_id: str,
    exit_code: int,
    duration_ms: int,
    severity: EventSeverity,
) -> None:
    """Persist an audit NodeEvent for the remote-execute job."""
    event = NodeEvent(
        event_id=str(uuid.uuid4())[:16],
        node_id=node_id,
        event_type=EventType.MANUAL_ACTION.value,
        severity=severity.value,
        message=f"Remote execution job {job_id}: exit_code={exit_code}",
        details={
            "job_id": job_id,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
        },
    )
    db.add(event)
    await db.commit()


async def _run_locally(
    script: str, language: str, timeout: int
) -> tuple[int, str, str]:
    """Execute *script* in a subprocess; return (exit_code, stdout, stderr)."""
    interpreter = "/bin/bash" if language == "bash" else "/bin/sh"
    proc = await asyncio.create_subprocess_exec(
        interpreter,
        "-c",
        script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        raw_out, raw_err = await asyncio.wait_for(
            proc.communicate(), timeout=float(timeout)
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return 124, "", f"Execution timed out after {timeout}s"

    return (
        proc.returncode if proc.returncode is not None else 1,
        raw_out.decode("utf-8", errors="replace"),
        raw_err.decode("utf-8", errors="replace"),
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/{node_id}/execute",
    response_model=NodeExecuteResponse,
    summary="Execute a shell command on a fleet node",
)
async def execute_on_node(
    node_id: str,
    body: NodeExecuteRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> NodeExecuteResponse:
    """Run *body.command* on the node identified by *node_id*.

    The node must be ONLINE.  Commands are validated against the injection
    denylist before execution.  The result is audit-logged as a NodeEvent.

    Currently executes locally (this host is the manager node).  Future
    iterations will fan out via the SLM agent Redis queue when the target
    node is remote.
    """
    _validate_command(body.command)
    await _require_online_node(node_id, db)

    job_id = str(uuid.uuid4())[:16]
    logger.info(
        "Remote execute: node=%s job=%s language=%s timeout=%s",
        node_id,
        job_id,
        body.language,
        body.timeout,
    )

    t0 = time.monotonic()
    exit_code, stdout, stderr = await _run_locally(
        body.command, body.language, body.timeout
    )
    duration_ms = int((time.monotonic() - t0) * 1000)

    severity = EventSeverity.INFO if exit_code == 0 else EventSeverity.WARNING
    await _audit_execute_event(db, node_id, job_id, exit_code, duration_ms, severity)

    logger.info(
        "Remote execute done: node=%s job=%s exit=%d dur=%dms",
        node_id,
        job_id,
        exit_code,
        duration_ms,
    )

    return NodeExecuteResponse(
        node_id=node_id,
        job_id=job_id,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
    )
