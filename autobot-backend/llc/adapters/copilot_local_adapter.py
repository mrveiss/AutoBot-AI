# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""CopilotLocalAdapter — wraps a local ``gh copilot`` CLI session as an LLC heartbeat (GH#9008).

adapter_config schema::

    {
        "gh_token": "ghp_...",          # optional; falls back to ambient GH_TOKEN/GITHUB_TOKEN
        "copilot_model": "copilot-4o",  # default; exposed as GH_COPILOT_MODEL env var
        "workspace_dir": "/path/to",    # subprocess cwd; cleared on missing-dir retry
        "output_dir": "/tmp",           # where .jsonl output and state files land
        "timeout_seconds": 3600         # wall-clock limit per invocation
    }

``run_id`` is ``"<pid>/<session_id>"`` where ``session_id`` is a UUID assigned at
invoke time and used to locate the state file on disk. The state-file / status /
cancel lifecycle is shared via :class:`SubprocessLifecycleAdapter` (GH#9834).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from typing import Optional

from autobot_shared.logging_manager import get_logger

from .subprocess_base import DEFAULT_OUTPUT_DIR as _DEFAULT_OUTPUT_DIR
from .subprocess_base import SIGTERM_GRACE_SECONDS as _SIGTERM_GRACE_SECONDS
from .subprocess_base import SubprocessLifecycleAdapter
from .subprocess_base import resolve_timeout as _resolve_timeout
from .subprocess_support import inject_agent_credentials, serialize_invoke_context

logger = get_logger(__name__)

_DEFAULT_COPILOT_MODEL = "copilot-4o"

# Re-exported for the import contract (subscription adapter + tests rely on these).
__all__ = [
    "CopilotLocalAdapter",
    "_output_path",
    "_state_path",
    "_resolve_gh_cli",
    "_resolve_timeout",
    "_SIGTERM_GRACE_SECONDS",
    "_DEFAULT_OUTPUT_DIR",
]


def _resolve_gh_cli() -> str:
    path = shutil.which("gh")
    if path is None:
        raise RuntimeError("gh CLI not found on PATH. " "Install the GitHub CLI and ensure 'gh' is on PATH.")
    return path


def _output_path(output_dir: str, agent_id: str, run_id: str) -> str:
    safe_run = run_id.replace("/", "_")
    return os.path.join(output_dir, f"llc_copilot_{agent_id}_{safe_run}.jsonl")


def _state_path(output_dir: str, run_id: str) -> str:
    safe_run = run_id.replace("/", "_")
    return os.path.join(output_dir, f"llc_copilot_state_{safe_run}.json")


class CopilotLocalAdapter(SubprocessLifecycleAdapter):
    """Adapter that manages agent runs as local ``gh copilot`` CLI subprocess sessions."""

    _LOG_NAME = "CopilotLocalAdapter"
    _state_path = staticmethod(_state_path)
    _required_cli = "gh"  # GH#9793: CLI-availability gate in heartbeat dispatch

    async def _invoke(self, agent_config: dict, context: dict) -> str:
        gh_cli = _resolve_gh_cli()
        agent_id: str = agent_config.get("agent_id", "unknown")
        cfg = agent_config.get("adapter_config", {})

        output_dir: str = cfg.get("output_dir", _DEFAULT_OUTPUT_DIR)
        timeout_sec: int = _resolve_timeout(cfg)
        gh_token: Optional[str] = cfg.get("gh_token")
        copilot_model: str = cfg.get("copilot_model", _DEFAULT_COPILOT_MODEL)

        session_id = str(uuid.uuid4())
        run_id_placeholder = f"0/{session_id}"
        output_file = _output_path(output_dir, agent_id, run_id_placeholder)
        os.makedirs(output_dir, exist_ok=True)

        prompt = self._build_prompt(context)
        workspace_dir: str | None = cfg.get("workspace_dir") or context.get("workspace_dir")

        cmd: list[str] = [gh_cli, "copilot", "suggest", "--target", "bash", prompt]

        env = {**os.environ, "LLC_INVOKE_CONTEXT": serialize_invoke_context(context)}
        if gh_token:
            env["GITHUB_TOKEN"] = gh_token
            env["GH_TOKEN"] = gh_token
        env["GH_COPILOT_MODEL"] = copilot_model
        if workspace_dir:
            env["AUTOBOT_WORKSPACE_DIR"] = workspace_dir
        # GH#9623/GH#9789: forward the run-scoped LLC bearer token + API base.
        inject_agent_credentials(env, context)

        out_fh = open(output_file, "w", encoding="utf-8")
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=out_fh,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                    cwd=workspace_dir or None,
                )
            except FileNotFoundError as e:
                if workspace_dir and e.filename and os.path.abspath(str(e.filename)) == os.path.abspath(workspace_dir):
                    logger.warning("CopilotLocalAdapter: workspace_dir %r missing, retrying without cwd", workspace_dir)
                    env.pop("AUTOBOT_WORKSPACE_DIR", None)
                    workspace_dir = None
                    context.pop("workspace_dir", None)
                    env["LLC_INVOKE_CONTEXT"] = serialize_invoke_context(context)
                else:
                    raise
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=out_fh,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                )
        finally:
            out_fh.close()

        run_id = f"{proc.pid}/{session_id}"
        logger.info(
            "CopilotLocalAdapter: spawned PID %d session %s agent %s output=%s",
            proc.pid,
            session_id,
            agent_id,
            output_file,
        )

        state = {
            "pid": proc.pid,
            "session_id": session_id,
            "agent_id": agent_id,
            "output_file": output_file,
            "started_at": time.time(),
            "timeout_seconds": timeout_sec,
        }
        with open(_state_path(output_dir, run_id), "w", encoding="utf-8") as fh:
            json.dump(state, fh)

        return run_id
