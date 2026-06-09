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

The ``run_id`` is the string-encoded PID of the spawned process.
"""

import asyncio
import json
import os
import signal

from autobot_shared.logging_manager import get_logger

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus

logger = get_logger(__name__)

_SIGTERM_GRACE_SECONDS = 5


class ProcessAdapter:
    """Adapter that manages agent runs as OS subprocesses."""

    async def invoke(self, agent_config: dict, context: dict) -> str:
        cmd: str = agent_config["command"]
        env_extra: dict = agent_config.get("env", {})
        cwd: str | None = agent_config.get("cwd")

        env = {**os.environ, **env_extra}
        # Pass the invocation context as a JSON environment variable so the
        # subprocess can read it without requiring a custom IPC channel.
        env["LLC_INVOKE_CONTEXT"] = json.dumps(context, default=str)

        proc = await asyncio.create_subprocess_shell(
            cmd,
            env=env,
            cwd=cwd or None,
        )
        logger.info("ProcessAdapter: spawned PID %d for command %r", proc.pid, cmd)
        return str(proc.pid)

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        try:
            pid = int(run_id)
        except ValueError as exc:
            return AdapterRunStatus(status=LLCRunStatus.FAILED, error=str(exc))
        try:
            # Signal 0 checks existence without delivering a signal.
            os.kill(pid, 0)
            return AdapterRunStatus(status=LLCRunStatus.RUNNING)
        except ProcessLookupError:
            # PID gone — we cannot recover exit code after the fact without
            # holding a Popen handle, so report completed.
            return AdapterRunStatus(status=LLCRunStatus.COMPLETED)
        except PermissionError:
            # Process exists but we can't signal it (different uid).
            return AdapterRunStatus(status=LLCRunStatus.RUNNING)
        except OSError as exc:
            return AdapterRunStatus(status=LLCRunStatus.FAILED, error=str(exc))

    async def cancel(self, agent_config: dict, run_id: str) -> None:
        pid = int(run_id)
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("ProcessAdapter: sent SIGTERM to PID %d", pid)
        except ProcessLookupError:
            return  # already gone

        # Wait for graceful exit; escalate to SIGKILL if needed.
        for _ in range(_SIGTERM_GRACE_SECONDS * 10):
            await asyncio.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return

        try:
            os.kill(pid, signal.SIGKILL)
            logger.warning("ProcessAdapter: SIGKILL sent to PID %d (did not exit after SIGTERM)", pid)
        except ProcessLookupError:
            pass
