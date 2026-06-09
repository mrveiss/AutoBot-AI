# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
- The endpoint requires admin.system permission (require_permission dependency).
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

from autobot_shared.auth.permissions import Permission
from models.database import EventSeverity, EventType, Node, NodeEvent, NodeStatus
from services.auth import require_permission
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
        # File inspection (read-only; find destructive flags blocked by _validate_find_args)
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

# find flags that perform writes or arbitrary execution.  Any argument token
# that equals one of these is rejected to preserve the read-only intent of the
# "find" allowlist entry.  The check is case-sensitive (find flag names are
# always lowercase on Linux).
_FIND_BLOCKED_FLAGS: frozenset[str] = frozenset(
    {
        "-delete",  # deletes matched files/dirs in-place
        "-fprint",  # writes matched paths to a named file
        "-fprint0",  # same as -fprint but NUL-separated
        "-fprintf",  # formatted write to a named file
        "-exec",  # executes an arbitrary command per match
        "-execdir",  # like -exec but changes directory first
        "-ok",  # interactive -exec (still executes commands)
        "-okdir",  # interactive -execdir
    }
)


def _validate_find_args(tokens: list[str]) -> None:
    """Reject ``find`` invocations that carry write or execution flags.

    ``find`` is in ``ALLOWED_EXECUTABLES`` for read-only path enumeration
    (e.g. ``find /var/log -name "*.log"``).  Several ``find`` primaries
    cause side effects: ``-delete`` removes matched files, ``-fprint``/
    ``-fprint0``/``-fprintf`` write paths to an arbitrary file, and
    ``-exec``/``-execdir``/``-ok``/``-okdir`` run arbitrary commands.
    All of these are blocked here (#3474).

    Args:
        tokens: The full token list from shlex.split(), with tokens[0] == "find".

    Raises:
        HTTPException: HTTP 400 if any blocked flag is present in the argument
            list.
    """
    blocked = [t for t in tokens[1:] if t in _FIND_BLOCKED_FLAGS]
    if blocked:
        bad = ", ".join(sorted(blocked))
        logger.warning("Command rejected — find contains destructive/exec flag(s): %s", bad)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Command rejected: find flag(s) {bad} are not permitted "
                "(only read-only find operations are allowed)"
            ),
        )


# ---------------------------------------------------------------------------
# Security: path restrictions for file-read commands
# ---------------------------------------------------------------------------

# Executables that read arbitrary file paths — require additional argument
# validation to prevent exposure of secrets, credentials, and system files.
_FILE_READ_EXECUTABLES: frozenset[str] = frozenset({"cat", "head", "tail"})

# Path prefixes that cat/head/tail must never be allowed to read.
# Any argument that resolves to (or starts with) one of these prefixes is
# rejected.  The list is intentionally broad: omission is the safe default.
_SENSITIVE_PATH_PREFIXES: tuple[str, ...] = (
    "/etc/",
    "/etc",  # block bare "/etc" as a directory reference too
    "/root/",
    "/root",
    "/home/",  # home directories contain .ssh, .env, etc.
    "/proc/",
    "/sys/",
    "/run/secrets",
    "/var/lib/",  # databases, docker volumes, snapd state, etc.
    "/var/log/auth",  # auth.log / auth.log.* — keep general /var/log/ readable
    "/boot/",
    "/snap/",
)

# Filename patterns (basename only) that are always blocked regardless of
# directory, because they commonly hold secrets or credentials.
_SENSITIVE_FILENAME_SUFFIXES: tuple[str, ...] = (
    ".env",
    ".key",
    ".pem",
    ".crt",
    ".cert",
    ".pfx",
    ".p12",
    ".secret",
    ".passwd",
    ".password",
    ".credentials",
    ".token",
    ".htpasswd",
    ".netrc",
    "id_rsa",
    "id_ecdsa",
    "id_ed25519",
    "id_dsa",
    "authorized_keys",
    "known_hosts",
)


def _check_sensitive_path(executable: str, tokens: list[str]) -> None:
    """Validate that file-read commands do not target sensitive paths.

    Applies only to executables in *_FILE_READ_EXECUTABLES*.  Each argument
    that looks like a file path (does not start with '-') is normalised with
    os.path.normpath and then checked against *_SENSITIVE_PATH_PREFIXES* and
    *_SENSITIVE_FILENAME_SUFFIXES*.

    Raises HTTPException 400 if any argument references a sensitive path.
    """
    if executable not in _FILE_READ_EXECUTABLES:
        return

    for arg in tokens[1:]:
        # Skip option flags (e.g. -n, --lines=10) and non-path tokens such as
        # numeric option values (100 in "tail -n 100") or bare words produced
        # by shlex splitting metachar sequences.  Tokens without any '/' cannot
        # be file paths, so the absolute-path guard below does not apply.
        if arg.startswith("-") or "/" not in arg:
            continue  # skip flags and non-path tokens (option values, metachar-split words)

        # Require absolute paths — relative paths bypass the prefix denylist
        # because the working directory on the remote host is unpredictable.
        if not os.path.isabs(arg):
            logger.warning(
                "Command rejected — %r argument %r is not an absolute path",
                executable,
                arg,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(f"Command rejected: file-read commands must use absolute " f"paths, got {arg!r}"),
            )

        # Normalise to collapse ../ traversal attempts
        normalised = os.path.normpath(arg)

        # Check prefix denylist
        for prefix in _SENSITIVE_PATH_PREFIXES:
            if normalised == prefix.rstrip("/") or normalised.startswith(
                prefix if prefix.endswith("/") else prefix + "/"
            ):
                logger.warning(
                    "Command rejected — %r targets sensitive path %r (prefix %r)",
                    executable,
                    normalised,
                    prefix,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Command rejected: {executable!r} is not permitted to " f"read {arg!r} — path is restricted."
                    ),
                )

        # Check filename denylist (basename match)
        basename = os.path.basename(normalised).lower()
        for suffix in _SENSITIVE_FILENAME_SUFFIXES:
            if basename == suffix or basename.endswith(suffix):
                logger.warning(
                    "Command rejected — %r targets sensitive filename %r (rule %r)",
                    executable,
                    normalised,
                    suffix,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Command rejected: {executable!r} is not permitted to "
                        f"read {arg!r} — filename matches a restricted pattern."
                    ),
                )


def _validate_command(script: str) -> str:
    """Parse *script* and enforce the executable allowlist and path restrictions.

    For git commands, additionally enforces:
    - An explicit subcommand must be provided (bare ``git`` alone is rejected).
    - The subcommand must be in ``_GIT_ALLOWED_SUBCOMMANDS``.
    - For ``git stash``, an explicit operation (e.g. ``list`` or ``show``) must
      be provided — bare ``git stash`` with no operation is rejected (#3478).

    Returns the normalised first token for logging.
    Raises HTTPException 400 if the command is empty, the executable is not in
    ALLOWED_EXECUTABLES, git-specific subcommand rules are violated, or a
    file-read command targets a sensitive path.
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
        logger.warning("Command rejected — executable %r not in allowlist", executable)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Command rejected: executable {executable!r} is not permitted. "
                "Contact an administrator to extend the allowlist."
            ),
        )

    if executable == "git":
        _validate_git_subcommand(tokens)

    if executable == "find":
        _validate_find_args(tokens)

    # Additional path-level validation for file-read commands (#3475)
    _check_sensitive_path(executable, tokens)

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
        logger.warning("Command rejected — git subcommand %r not in allowlist", subcommand)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Command rejected: git subcommand {subcommand!r} is not permitted"),
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
        message=(f"Remote execution job {job_id} by {acting_user!r}: " f"exit_code={exit_code} cmd={short_cmd!r}"),
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
_SSH_KNOWN_HOSTS_PATH = os.environ.get("SLM_SSH_KNOWN_HOSTS", "/home/autobot/.ssh/known_hosts")  # noqa: ssot-path
# System-wide known_hosts populated by Ansible — used as fallback when the
# per-user file is absent.  Defined at module level so tests can patch it.
_SSH_SYSTEM_KNOWN_HOSTS_PATH = "/etc/ssh/ssh_known_hosts"

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
        raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
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
    per-user or system-wide known_hosts file exists.  Falls back to the
    system-wide /etc/ssh/ssh_known_hosts (populated by Ansible) if the
    per-user file is absent.  Refuses the connection if neither file exists
    rather than falling back to accept-new+/dev/null, which provides no TOFU
    protection (every connection would accept whatever key is presented #3469).
    """
    known_hosts_path = Path(_SSH_KNOWN_HOSTS_PATH)
    if known_hosts_path.exists():
        host_key_checking = "yes"
        known_hosts_file = str(known_hosts_path)
    elif Path(_SSH_SYSTEM_KNOWN_HOSTS_PATH).exists():
        host_key_checking = "yes"
        known_hosts_file = _SSH_SYSTEM_KNOWN_HOSTS_PATH
        logger.warning(
            "Per-user known_hosts not found at %s — falling back to system " "known_hosts %s for %s",
            _SSH_KNOWN_HOSTS_PATH,
            _SSH_SYSTEM_KNOWN_HOSTS_PATH,
            ip,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"SSH connection to {ip} refused: no known_hosts file found at "
                f"{_SSH_KNOWN_HOSTS_PATH} or {_SSH_SYSTEM_KNOWN_HOSTS_PATH}. "
                "Run the Ansible provisioning playbook to populate known_hosts "
                "before executing remote commands."
            ),
        )

    cmd = [
        "ssh",
        "-p",
        str(ssh_port),
        "-o",
        f"StrictHostKeyChecking={host_key_checking}",
        "-o",
        f"UserKnownHostsFile={known_hosts_file}",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={min(timeout, 30)}",
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
        raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
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
    current_user: dict = Depends(require_permission(Permission.ADMIN_SYSTEM)),
) -> NodeExecuteResponse:
    """Run *body.command* on the node identified by *node_id*.

    The node must be ONLINE.  *body.command* is tokenised with shlex.split()
    and the first token (executable name) must be present in
    ALLOWED_EXECUTABLES — any other command is rejected with HTTP 400.

    Permission admin.system is required (require_permission dependency).

    Local nodes (manager host) execute via subprocess with shell=False;
    remote nodes execute via SSH using the SLM key (SLM_SSH_KEY env var)
    and known_hosts verification (SLM_SSH_KNOWN_HOSTS env var). Default
    paths are documented at the module-level constants ``_SSH_KEY_PATH``
    and ``_SSH_KNOWN_HOSTS_PATH``.

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
        exit_code, stdout, stderr = await _run_via_ssh(node.ip_address, ssh_user, ssh_port, tokens, body.timeout)
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
