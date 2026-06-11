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

from autobot_shared.logging_manager import get_logger

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus
from .subprocess_support import probe_pid, terminate_pid

logger = get_logger(__name__)

_LOG_NAME = "ProcessAdapter"
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
        return probe_pid(pid)

    async def cancel(self, agent_config: dict, run_id: str) -> None:
        pid = int(run_id)
        # terminate_pid returns True when the process was already gone
        # (SIGTERM raised ProcessLookupError) — match the original early-return
        # behavior: no further action needed when the process is already dead.
        already_gone = await terminate_pid(pid, _SIGTERM_GRACE_SECONDS, _LOG_NAME)
        if already_gone:
            return
