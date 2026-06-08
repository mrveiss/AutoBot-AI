# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""ClaudeCodeSubscriptionAdapter — runs Claude Code CLI with subscription auth (GH#9033).

Like ClaudeCodeAdapter but enforces subscription-only mode:
- No API key in environment (uses browser OAuth)
- Token usage parsed from CLI output
- Quota exhaustion triggers auto-pause + board notification

adapter_config schema::

    {
        "model": "claude-sonnet-4-6",
        "max_turns": 10,
        "allowed_tools": ["Bash", "Read"],
        "output_dir": "/tmp",
        "timeout_seconds": 3600,
        "workspace_dir": "/path/to/worktree",
        "quota_pause_on_exhaustion": true
    }

``run_id`` is ``"<pid>/<session_id>"``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Optional

from autobot_shared.logging_manager import get_logger

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus
from .claude_code_adapter import ClaudeCodeAdapter, _output_path, _resolve_claude_cli, _state_path

logger = get_logger(__name__)

_QUOTA_EXHAUSTED_PATTERNS = [
    r"quota exceeded",
    r"rate limit",
    r"subscription limit",
    r"out of tokens",
]


class ClaudeCodeSubscriptionAdapter(ClaudeCodeAdapter):
    """Subscription-mode adapter for Claude Code CLI (no API key required)."""

    async def _invoke(self, agent_config: dict, context: dict) -> str:
        """Invoke Claude Code CLI in subscription mode (no API key)."""
        import time
        import uuid

        cli = _resolve_claude_cli()
        agent_id: str = agent_config.get("agent_id", "unknown")
        cfg = agent_config.get("adapter_config", {})

        output_dir: str = cfg.get("output_dir", "/tmp")  # nosec B108
        timeout_sec: int = int(cfg.get("timeout_seconds", 3600))
        model: Optional[str] = cfg.get("model")
        max_turns: Optional[int] = cfg.get("max_turns")
        allowed_tools: Optional[list] = cfg.get("allowed_tools")

        session_id = str(uuid.uuid4())
        run_id_placeholder = f"0/{session_id}"
        output_file = _output_path(output_dir, agent_id, run_id_placeholder)
        os.makedirs(output_dir, exist_ok=True)

        prompt = self._build_prompt(context)
        resume_session_id = await self._get_resumable_session(agent_id)

        cmd: list[str] = [cli, "--output-format", "stream-json", "--print"]

        if resume_session_id:
            cmd += ["--resume", resume_session_id]
            session_id = resume_session_id
            logger.info(
                "ClaudeCodeSubscriptionAdapter: resuming session %s for agent %s",
                session_id,
                agent_id,
            )
        else:
            if model:
                cmd += ["--model", model]
            if max_turns is not None:
                cmd += ["--max-turns", str(max_turns)]
            if allowed_tools:
                cmd += ["--allowedTools", ",".join(allowed_tools)]

        cmd.append(prompt)

        workspace_dir: str | None = context.get("workspace_dir")

        # Build env with API keys explicitly stripped (subscription mode)
        env = self._build_subscription_env(context, workspace_dir)

        out_fh = open(output_file, "w", encoding="utf-8")
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=out_fh,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=workspace_dir or None,
                )
            except FileNotFoundError as e:
                if workspace_dir and e.filename and os.path.abspath(str(e.filename)) == os.path.abspath(workspace_dir):
                    logger.warning(
                        "ClaudeCodeSubscriptionAdapter: workspace_dir %r missing, retrying without cwd",
                        workspace_dir,
                    )
                    context.pop("workspace_dir", None)
                    env.pop("AUTOBOT_WORKSPACE_DIR", None)
                    env["LLC_INVOKE_CONTEXT"] = json.dumps(context, default=str)
                    workspace_dir = None
                else:
                    raise
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=out_fh,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
        finally:
            out_fh.close()

        run_id = f"{proc.pid}/{session_id}"
        logger.info(
            "ClaudeCodeSubscriptionAdapter: spawned PID %d session %s agent %s output=%s (subscription mode)",
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

        await self._store_session(agent_id, session_id)
        return run_id

    def _build_subscription_env(self, context: dict, workspace_dir: Optional[str]) -> dict:
        """Build environment with API keys explicitly removed (subscription mode)."""
        env = {**os.environ}

        # Strip any API key env vars to enforce subscription mode
        keys_to_remove = [
            "ANTHROPIC_API_KEY",
            "CLAUDE_API_KEY",
            "API_KEY",
        ]
        for key in keys_to_remove:
            if key in env:
                logger.debug("ClaudeCodeSubscriptionAdapter: removing %s from environment", key)
                env.pop(key)

        # Add standard context
        env["LLC_INVOKE_CONTEXT"] = json.dumps(context, default=str)
        if workspace_dir:
            env["AUTOBOT_WORKSPACE_DIR"] = workspace_dir

        logger.info("ClaudeCodeSubscriptionAdapter: subscription mode enforced (API keys stripped)")
        return env

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        """Check status and parse token usage from output."""
        base_status = await super().status(agent_config, run_id)

        # If run completed, check for quota exhaustion in output
        if base_status.status in (LLCRunStatus.COMPLETED, LLCRunStatus.FAILED):
            cfg = agent_config.get("adapter_config", {})
            output_dir: str = cfg.get("output_dir", "/tmp")  # nosec B108
            agent_id: str = agent_config.get("agent_id", "unknown")
            output_file = _output_path(output_dir, agent_id, run_id)

            quota_exhausted = self._check_quota_exhaustion(output_file)
            if quota_exhausted:
                logger.warning(
                    "ClaudeCodeSubscriptionAdapter: quota exhausted for agent %s run %s",
                    agent_id,
                    run_id,
                )

                # TODO: Implement auto-pause + board notification (depends on GH#8225)
                # For now, just return FAILED status with clear error
                return AdapterRunStatus(
                    status=LLCRunStatus.FAILED,
                    error="Subscription quota exhausted. Please check your Claude Max subscription limits.",
                )

        return base_status

    def _check_quota_exhaustion(self, output_file: str) -> bool:
        """Parse CLI output for quota exhaustion indicators."""
        try:
            with open(output_file, encoding="utf-8") as fh:
                content = fh.read()

            for pattern in _QUOTA_EXHAUSTED_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    return True

            return False
        except FileNotFoundError:
            logger.warning("ClaudeCodeSubscriptionAdapter: output file not found: %s", output_file)
            return False
        except Exception as exc:
            logger.exception("ClaudeCodeSubscriptionAdapter: error reading output file: %s", exc)
            return False
