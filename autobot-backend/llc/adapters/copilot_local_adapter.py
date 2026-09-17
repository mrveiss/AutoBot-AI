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

import json
import os
import shutil
import time
import uuid
from typing import Optional

from autobot_shared.logging_manager import get_logger

from .subprocess_base import DEFAULT_OUTPUT_DIR as _DEFAULT_OUTPUT_DIR
from .subprocess_base import SIGTERM_GRACE_SECONDS as _SIGTERM_GRACE_SECONDS
from .subprocess_base import SubprocessLifecycleAdapter, placeholder_run_id
from .subprocess_base import resolve_first_output_deadline as _resolve_first_output_deadline
from .subprocess_base import resolve_stall_deadline as _resolve_stall_deadline
from .subprocess_base import resolve_timeout as _resolve_timeout
from .subprocess_support import (
    inject_agent_credentials,
    serialize_invoke_context,
    spawn_create_time,
    spawn_with_workspace_retry,
)

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
    "build_copilot_state",
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


def build_copilot_state(
    proc,
    session_id: str,
    agent_id: str,
    output_file: str,
    stderr_file: str | None,
    timeout_sec: int,
    first_output_sec: int,
    stall_sec: int,
) -> dict:
    """Assemble a Copilot-family run's persisted state, incl. its psutil
    create_time (PR#16284 review) — shared by :class:`CopilotLocalAdapter`
    and :class:`CopilotSubscriptionAdapter` so the two stay in lock-step.
    ``stderr_file=None`` (subscription mode discards stderr to DEVNULL)
    omits that key instead of recording a nonexistent sidecar file.
    """
    state = {
        "pid": proc.pid,
        "session_id": session_id,
        "agent_id": agent_id,
        "output_file": output_file,
        "started_at": time.time(),
        "create_time": spawn_create_time(proc.pid),  # PR#16284 review
        "timeout_seconds": timeout_sec,
        "first_output_deadline_seconds": first_output_sec,  # GH#13099
        "stall_deadline_seconds": stall_sec,  # GH#13099
    }
    if stderr_file is not None:
        state["stderr_file"] = stderr_file  # GH#9992
    return state


class CopilotLocalAdapter(SubprocessLifecycleAdapter):
    """Adapter that manages agent runs as local ``gh copilot`` CLI subprocess sessions."""

    _LOG_NAME = "CopilotLocalAdapter"
    _state_path = staticmethod(_state_path)
    _output_path = staticmethod(_output_path)
    _required_cli = "gh"  # GH#9793: CLI-availability gate in heartbeat dispatch

    async def _invoke(self, agent_config: dict, context: dict) -> str:
        gh_cli = _resolve_gh_cli()
        agent_id: str = agent_config.get("agent_id", "unknown")
        cfg = agent_config.get("adapter_config", {})

        output_dir: str = cfg.get("output_dir", _DEFAULT_OUTPUT_DIR)
        timeout_sec: int = _resolve_timeout(cfg)
        # GH#13099 AC4 / PR#16284 review: `gh copilot suggest`'s output
        # buffering is UNVERIFIED, not assumed streaming. The command carries
        # no --stream/--output-format flag (unlike claude_code_adapter's
        # stream-json), the classic gh-copilot-extension UX prints one
        # suggestion after a "thinking" spinner rather than incrementally,
        # and gh 2.98.0 (2026-08-20, installed in dev) no longer even
        # recognises a "suggest" subcommand (`gh copilot suggest --help`
        # just reprints the top-level `gh copilot` help) -- so on a current
        # gh install "--target bash" may be silently ignored by the
        # downloaded interactive Copilot CLI. Given a CLI that buffers to
        # exit would be killed by the streaming-CLI 120s/600s defaults on
        # every legitimate run, this adapter's own default is the run's
        # overall timeout: the watchdog can then never fire before the
        # timeout would have anyway, costing nothing on a genuinely slow
        # suggestion while adding no new risk.
        first_output_sec: int = _resolve_first_output_deadline(cfg, default=timeout_sec)
        stall_sec: int = _resolve_stall_deadline(cfg, default=timeout_sec)
        gh_token: Optional[str] = cfg.get("gh_token")
        copilot_model: str = cfg.get("copilot_model", _DEFAULT_COPILOT_MODEL)

        session_id = str(uuid.uuid4())
        run_id_placeholder = placeholder_run_id(session_id)
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

        # GH#9992: capture stderr to a sidecar file instead of discarding it to
        # DEVNULL, so CLI errors on a failed/killed run are diagnosable.
        stderr_file = f"{output_file}.stderr.log"
        out_fh = open(output_file, "w", encoding="utf-8")
        err_fh = open(stderr_file, "w", encoding="utf-8")
        try:
            proc, workspace_dir = await spawn_with_workspace_retry(
                cmd,
                context=context,
                env=env,
                workspace_dir=workspace_dir,
                stdout=out_fh,
                stderr=err_fh,
                log_name="CopilotLocalAdapter",
            )
        finally:
            out_fh.close()
            err_fh.close()

        run_id = f"{proc.pid}/{session_id}"
        logger.info(
            "CopilotLocalAdapter: spawned PID %d session %s agent %s output=%s",
            proc.pid,
            session_id,
            agent_id,
            output_file,
        )

        state = build_copilot_state(
            proc, session_id, agent_id, output_file, stderr_file, timeout_sec, first_output_sec, stall_sec
        )
        with open(_state_path(output_dir, run_id), "w", encoding="utf-8") as fh:
            json.dump(state, fh)

        return run_id
