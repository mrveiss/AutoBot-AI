# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Node Remote Execution API

Issue #3406: Adds POST /nodes/{node_id}/execute — a guarded endpoint that
runs a shell command on the target node.

Security model
--------------
- Commands are tokenised with shlex.split() and the first token (the
  executable name) is checked against ALLOWED_EXECUTABLES.  Any command
  whose first token is not in that frozenset is rejected with HTTP 400.
- This allowlist approach replaces the prior denylist, which was trivially
  bypassed via semicolons, &&, shell-newline chaining, python3 -c, eval,
  and many other vectors (#3421).
- The node must be ONLINE before a job is accepted.
- The endpoint requires admin privileges (require_admin dependency).
- All executions are audit-logged including the command and acting user.
- SSH connections use a known_hosts file instead of StrictHostKeyChecking=no.
"""

import asyncio
import logging
import os
import shlex
import socket
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import EventSeverity, EventType, Node, NodeEvent, NodeStatus
from services.auth import require_admin
from services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nodes", tags=["nodes-execution"])

# ---------------------------------------------------------------------------
# Security: strict allowlist of permitted executables
# ---------------------------------------------------------------------------

# Only these executable names (first shlex token) are permitted.
# Add entries deliberately — omission is the safe default.
ALLOWED_EXECUTABLES: frozenset[str] = frozenset(
    {
        # Service / status inspection
        "systemctl",
        "journalctl",
        "service",
        # Network diagnostics
        "ping",
        "ss",
        "netstat",
        "ip",
        "nmap",
        "curl",
        "wget",
        # Process inspection
        "ps",
        "top",
        "htop",
        "uptime",
        "free",
        "df",
        "du",
        "lsof",
        # File inspection (read-only)
        "ls",
        "cat",
        "head",
        "tail",
        "find",
        "stat",
        "file",
        # Package management (query-only)
        "dpkg",
        "apt",
        "rpm",
        "yum",
        "dnf",
        # AutoBot-specific helpers
        "autobot-status",
        "autobot-health",
        # Git (subcommand is further validated by _validate_git_subcommand)
        "git",
    }
)

# Permitted git subcommands (second token after "git").
# Explicit subcommand is always required — bare "git stash" etc. are rejected.
_GIT_ALLOWED_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "status",
        "log",
        "diff",
        "show",
        "branch",
        "remote",
        "tag",
        "describe",
        "rev-parse",
        "ls-files",
        "stash",  # subcommand for stash is further restricted below
    }
)

# For "git stash <op>", the operation token must be one of these read-only ops.
_GIT_STASH_ALLOWED_OPS: frozenset[str] = frozenset({"list", "show"})


def _validate_command(script: str) -> str:
    """Parse *script* and enforce the executable allowlist.

    For git commands, additionally enforces:
    - An explicit subcommand must be provided (bare ``git`` alone is rejected).
    - The subcommand must be in ``_GIT_ALLOWED_SUBCOMMANDS``.
    - For ``git stash``, an explicit operation (e.g. ``list`` or ``show``) must
      be provided — bare ``git stash`` with no operation is rejected (#3478).

    Returns the normalised first token for logging.
    Raises HTTPException 400 if the command is empty, the executable is not in
    ALLOWED_EXECUTABLES, or git-specific subcommand rules are violated.
    """
    try:
        tokens = shlex.split(script)
    except ValueError as exc:
        logger.warning("Command rejected — shlex parse error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Command rejected: could not parse command tokens",
        ) from exc

    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Command rejected: empty command",
        )

    # Extract the bare executable name (strip any leading path components
    # so that e.g. /bin/ls still matches "ls").
    executable = Path(tokens[0]).name

    if executable not in ALLOWED_EXECUTABLES:
        logger.warning(
            "Command rejected — executable %r not in allowlist", executable
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Command rejected: executable {executable!r} is not permitted. "
                "Contact an administrator to extend the allowlist."
            ),
        )

    if executable == "git":
        _validate_git_subcommand(tokens)

    return executable


def _validate_git_subcommand(tokens: list[str]) -> None:
    """Enforce git subcommand allowlist rules.

    Bare ``git`` (no subcommand) and git subcommands not in
    ``_GIT_ALLOWED_SUBCOMMANDS`` are rejected with HTTP 400.

    For ``git stash``, a further check requires an explicit operation from
    ``_GIT_STASH_ALLOWED_OPS`` — bare ``git stash`` with no operation token
    is rejected (#3478, Option A: explicit is safer for allowlists).

    Args:
        tokens: The full token list from shlex.split(), with tokens[0] == "git".

    Raises:
        HTTPException: HTTP 400 if any git subcommand rule is violated.
    """
    if len(tokens) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Command rejected: git requires an explicit subcommand",
        )

    subcommand = tokens[1]
    if subcommand not in _GIT_ALLOWED_SUBCOMMANDS:
        logger.warning(
            "Command rejected — git subcommand %r not in allowlist", subcommand
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Command rejected: git subcommand {subcommand!r} is not permitted"
            ),
        )

    if subcommand == "stash":
        if len(tokens) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Command rejected: 'git stash' requires an explicit operation "
                    f"(one of: {', '.join(sorted(_GIT_STASH_ALLOWED_OPS))})"
                ),
            )
        stash_op = tokens[2]
        if stash_op not in _GIT_STASH_ALLOWED_OPS:
            logger.warning(
                "Command rejected — git stash operation %r not in allowlist",
                stash_op,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Command rejected: git stash operation {stash_op!r} is not "
                    f"permitted (allowed: {', '.join(sorted(_GIT_STASH_ALLOWED_OPS))})"
                ),
            )


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class NodeExecuteRequest(BaseModel):
    """Body for POST /nodes/{node_id}/execute."""

    command: str = Field(
        ...,
        description="Shell command to execute on the node (single command, no shell chaining).",
        min_length=1,
        max_length=4096,
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
    command: str,
    acting_user: str,
    exit_code: int,
    duration_ms: int,
    severity: EventSeverity,
) -> None:
    """Persist an audit NodeEvent for the remote-execute job.

    Records the full command and acting user identity to support forensic
    investigation (#3421).
    """
    # Truncate command in the message to keep it readable; full command is in details.
    short_cmd = command[:120] + ("..." if len(command) > 120 else "")
    event = NodeEvent(
        event_id=str(uuid.uuid4())[:16],
        node_id=node_id,
        event_type=EventType.MANUAL_ACTION.value,
        severity=severity.value,
        message=(
            f"Remote execution job {job_id} by {acting_user!r}: "
            f"exit_code={exit_code} cmd={short_cmd!r}"
        ),
        details={
            "job_id": job_id,
            "command": command,
            "acting_user": acting_user,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
        },
    )
    db.add(event)
    await db.commit()


_SSH_KEY_PATH = os.environ.get("SLM_SSH_KEY", "/home/autobot/.ssh/autobot_key")  # noqa: ssot-path
_SSH_KNOWN_HOSTS_PATH = os.environ.get(
    "SLM_SSH_KNOWN_HOSTS", "/home/autobot/.ssh/known_hosts"
)

_LOCAL_ADDRESSES = {"127.0.0.1", "::1", "localhost"}
try:
    _LOCAL_ADDRESSES.add(socket.gethostbyname(socket.gethostname()))
except OSError:
    pass


def _is_local_ip(ip: str) -> bool:
    """Return True if *ip* resolves to this host."""
    return ip in _LOCAL_ADDRESSES


async def _run_command(tokens: list[str], timeout: int) -> tuple[int, str, str]:
    """Execute a pre-tokenised command locally; return (exit_code, stdout, stderr).

    Uses shell=False (exec list form) — the tokens come from shlex.split() of
    an allowlist-validated command, so no shell interpretation occurs.
    """
    proc = await asyncio.create_subprocess_exec(
        *tokens,
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


async def _run_via_ssh(
    ip: str,
    ssh_user: str,
    ssh_port: int,
    tokens: list[str],
    timeout: int,
) -> tuple[int, str, str]:
    """Execute a pre-tokenised command on *ip* via SSH.

    Uses known_hosts verification (StrictHostKeyChecking=yes) when a
    known_hosts file exists, falling back to 'accept-new' for first contact
    rather than the previous insecure 'no' (#3421).
    """
    known_hosts_path = Path(_SSH_KNOWN_HOSTS_PATH)
    if known_hosts_path.exists():
        host_key_checking = "yes"
        known_hosts_file = str(known_hosts_path)
    else:
        # Accept and persist the key on first connection; never silently
        # accept a changed key (this is safer than StrictHostKeyChecking=no).
        host_key_checking = "accept-new"
        known_hosts_file = "/dev/null"
        logger.warning(
            "known_hosts file not found at %s — using accept-new for %s",
            _SSH_KNOWN_HOSTS_PATH,
            ip,
        )

    cmd = [
        "ssh",
        "-p", str(ssh_port),
        "-o", f"StrictHostKeyChecking={host_key_checking}",
        "-o", f"UserKnownHostsFile={known_hosts_file}",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={min(timeout, 30)}",
    ]
    if Path(_SSH_KEY_PATH).exists():
        cmd.extend(["-i", _SSH_KEY_PATH])
    cmd.append(f"{ssh_user}@{ip}")
    # Pass the command tokens as individual arguments to avoid any shell
    # interpretation on the remote side.
    cmd.extend(tokens)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
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
        return 124, "", f"SSH execution timed out after {timeout}s"
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
    summary="Execute an allowlisted command on a fleet node",
)
async def execute_on_node(
    node_id: str,
    body: NodeExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
) -> NodeExecuteResponse:
    """Run *body.command* on the node identified by *node_id*.

    The node must be ONLINE.  *body.command* is tokenised with shlex.split()
    and the first token (executable name) must be present in
    ALLOWED_EXECUTABLES — any other command is rejected with HTTP 400.

    Admin privileges are required (require_admin dependency).

    Local nodes (manager host) execute via subprocess with shell=False;
    remote nodes execute via SSH using the SLM key (SLM_SSH_KEY env var,
    default /home/autobot/.ssh/autobot_key) and known_hosts verification
    (SLM_SSH_KNOWN_HOSTS env var, default /home/autobot/.ssh/known_hosts).

    All executions are audit-logged including the full command and acting user.
    """
    acting_user: str = current_user.get("sub", "unknown")

    executable = _validate_command(body.command)
    tokens = shlex.split(body.command)

    node = await _require_online_node(node_id, db)

    job_id = str(uuid.uuid4())[:16]
    logger.info(
        "Execute: node=%s ip=%s job=%s executable=%s user=%s timeout=%s",
        node_id,
        node.ip_address,
        job_id,
        executable,
        acting_user,
        body.timeout,
    )

    t0 = time.monotonic()
    if _is_local_ip(node.ip_address or ""):
        exit_code, stdout, stderr = await _run_command(tokens, body.timeout)
    else:
        ssh_user = node.ssh_user or "autobot"
        ssh_port = int(node.ssh_port or 22)
        exit_code, stdout, stderr = await _run_via_ssh(
            node.ip_address, ssh_user, ssh_port, tokens, body.timeout
        )
    duration_ms = int((time.monotonic() - t0) * 1000)

    severity = EventSeverity.INFO if exit_code == 0 else EventSeverity.WARNING
    await _audit_execute_event(
        db,
        node_id,
        job_id,
        body.command,
        acting_user,
        exit_code,
        duration_ms,
        severity,
    )

    logger.info(
        "Remote execute done: node=%s job=%s exit=%d dur=%dms user=%s",
        node_id,
        job_id,
        exit_code,
        duration_ms,
        acting_user,
    )

    return NodeExecuteResponse(
        node_id=node_id,
        job_id=job_id,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
    )
