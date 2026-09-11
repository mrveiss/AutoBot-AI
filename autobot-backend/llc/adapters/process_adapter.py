# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ProcessAdapter — spawns a subprocess to run an agent (GH#8226).

adapter_config schema::

    {
        "command": "python run_agent.py",
        "env": {"KEY": "VALUE"},
        "cwd": "/path/to/workdir"
    }

The ``run_id`` is ``"<pid>"``, or ``"<pid>:<create_time>"`` when psutil could
record the child's start time at spawn (PR#16284 review) — the PID-reuse
guard ``status``/``cancel`` verify before ever trusting that PID again.

Security (GH#11059): ``command`` is tenant-writable, so this adapter runs
host commands from untrusted config. It is therefore hardened three ways:

* **Disabled by default** — an operator must set ``LLC_PROCESS_ADAPTER_ENABLED``
  on the backend host; it can never be turned on from tenant configuration.
* **No shell** — the command runs via ``create_subprocess_exec`` after
  ``shlex.split`` (never ``create_subprocess_shell``), so shell metacharacters
  in tenant config can't chain arbitrary commands.
* **Minimal env** — the subprocess receives only an allowlist of non-secret
  system vars plus the agent's declared extras and injected LLC token; the
  backend's DB/LLC credentials are never inherited.
"""

import json
import os
import shlex

from autobot_shared.logging_manager import get_logger

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus
from .subprocess_support import (
    inject_agent_credentials,
    probe_pid_identity,
    spawn_create_time,
    spawn_detached,
    terminate_pid,
)

logger = get_logger(__name__)

_LOG_NAME = "ProcessAdapter"
_SIGTERM_GRACE_SECONDS = 5

# GH#11059 (P0 RCE): ProcessAdapter executes a tenant-writable command on the
# backend host. It is DISABLED unless an operator explicitly enables it via this
# server-side env flag — never runnable from tenant config alone.
_ENABLE_FLAG = "LLC_PROCESS_ADAPTER_ENABLED"
_TRUTHY = {"1", "true", "yes", "on"}

# Non-secret environment variables forwarded to the spawned subprocess. The full
# backend environment (DB/LLC creds, API keys) is NEVER inherited — only these,
# plus the agent's declared ``env`` extras and the injected LLC bearer token.
_SAFE_ENV_PASSTHROUGH = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR")


def _process_adapter_enabled() -> bool:
    """True only when an operator has explicitly enabled ProcessAdapter (GH#11059)."""
    return os.environ.get(_ENABLE_FLAG, "").strip().lower() in _TRUTHY


def _encode_run_id(pid: int, create_time: float | None) -> str:
    """Pack pid + psutil create_time into the run_id (PR#16284 review).

    A bare pid (``create_time`` unrecordable — psutil raced the child's own
    exit) falls back to the old ``"<pid>"`` shape, so :func:`_decode_run_id`
    still parses runs from before this field existed.
    """
    return f"{pid}:{create_time}" if create_time is not None else str(pid)


def _decode_run_id(run_id: str) -> tuple[int, float | None]:
    """Unpack a run_id built by :func:`_encode_run_id`."""
    pid_str, sep, create_time_str = run_id.partition(":")
    return int(pid_str), (float(create_time_str) if sep else None)


def _build_minimal_env(env_extra: dict, context: dict) -> dict:
    """Build a minimal, secret-free environment for the spawned agent (GH#11059).

    Starts from an allowlist of safe system vars (never the full ``os.environ``),
    layers the agent's declared ``env`` extras, injects the LLC bearer token, and
    attaches the invocation context as ``LLC_INVOKE_CONTEXT`` so the subprocess
    can read it without a custom IPC channel.
    """
    env: dict = {k: os.environ[k] for k in _SAFE_ENV_PASSTHROUGH if k in os.environ}
    env.update(env_extra or {})
    inject_agent_credentials(env, context)
    env["LLC_INVOKE_CONTEXT"] = json.dumps(context, default=str)
    return env


class ProcessAdapter:
    """Adapter that manages agent runs as OS subprocesses."""

    async def invoke(self, agent_config: dict, context: dict) -> str:
        if not _process_adapter_enabled():
            raise PermissionError(
                "ProcessAdapter is disabled by policy (GH#11059). Set "
                f"{_ENABLE_FLAG}=1 on the backend host to allow host command "
                "execution; it must never be enabled from tenant configuration."
            )

        cmd: str = agent_config["command"]
        cwd: str | None = agent_config.get("cwd")
        env = _build_minimal_env(agent_config.get("env", {}), context)

        argv = shlex.split(cmd)
        if not argv:
            raise ValueError("ProcessAdapter: empty command")

        proc = await spawn_detached(
            *argv,
            env=env,
            cwd=cwd or None,
        )
        create_time = spawn_create_time(proc.pid)  # PR#16284 review: PID-reuse guard
        logger.info("ProcessAdapter: spawned PID %d for executable %r", proc.pid, argv[0])
        return _encode_run_id(proc.pid, create_time)

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        try:
            pid, create_time = _decode_run_id(run_id)
        except ValueError as exc:
            return AdapterRunStatus(status=LLCRunStatus.FAILED, error=str(exc))
        return probe_pid_identity(pid, create_time)

    async def cancel(self, agent_config: dict, run_id: str) -> None:
        pid, create_time = _decode_run_id(run_id)
        # terminate_pid verifies pid still owns create_time before signalling
        # anything (PR#16284 review) and returns True when no signal was sent
        # (already gone, or unverifiable) — match the original early-return
        # behavior: no further action needed either way.
        already_gone = await terminate_pid(pid, _SIGTERM_GRACE_SECONDS, _LOG_NAME, create_time)
        if already_gone:
            return
