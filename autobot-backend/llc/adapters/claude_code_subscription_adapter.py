# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ClaudeCodeSubscriptionAdapter — runs Claude Code CLI with subscription auth (GH#9033).

Like ClaudeCodeAdapter but enforces subscription-only mode:
- No API key in environment — the Claude Code CLI authenticates via its own
  one-time browser login (``claude login``, stored in ~/.claude), so there is
  no token to inject from secrets here (GH#10217); this adapter only strips the
  API-key env vars so the CLI falls back to that subscription session.
- Token usage parsed from CLI output (GH#10220)
- Quota exhaustion triggers auto-pause + board notification (GH#10218)

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
from .subprocess_support import inject_agent_credentials, serialize_invoke_context

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
                    env["LLC_INVOKE_CONTEXT"] = serialize_invoke_context(context)
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

        # Add standard context (provider keys stripped above; the LLC platform
        # bearer token is a separate credential and IS forwarded — GH#9789).
        env["LLC_INVOKE_CONTEXT"] = serialize_invoke_context(context)
        if workspace_dir:
            env["AUTOBOT_WORKSPACE_DIR"] = workspace_dir
        inject_agent_credentials(env, context)

        logger.info("ClaudeCodeSubscriptionAdapter: subscription mode enforced (provider API keys stripped)")
        return env

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        """Check status and parse token usage from output.

        Quota-exhaustion (subscription limit) takes precedence over RATE_LIMITED
        (per-minute API rate limit) when both could apply.  ``_check_quota_exhaustion``
        is evaluated first on any terminal state so that a subscription-limit hit
        always returns FAILED (no retry loop) rather than RATE_LIMITED (backoff loop).
        """
        base_status = await super().status(agent_config, run_id)

        # On any terminal state, check the output for quota exhaustion (GH#9777).
        # This check runs BEFORE honoring an inherited RATE_LIMITED so that a
        # subscription-quota hit (→ FAILED, no retry) beats a transient rate-limit
        # (→ RATE_LIMITED, exponential backoff) when both patterns match (M2).
        if base_status.status.is_terminal():
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

                # GH#10218: signal QUOTA_EXHAUSTED so the scheduler auto-pauses
                # the agent and logs a board-visible pause event (no retry).
                return AdapterRunStatus(
                    status=LLCRunStatus.QUOTA_EXHAUSTED,
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
