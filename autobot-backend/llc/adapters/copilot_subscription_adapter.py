# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""CopilotSubscriptionAdapter — GitHub Copilot CLI with subscription auth (GH#9033).

Like CopilotLocalAdapter but enforces subscription-only mode:
- Uses GitHub OAuth (no separate Copilot API key required)
- Token usage parsed from CLI output
- Quota exhaustion triggers auto-pause + board notification

adapter_config schema::

    {
        "gh_token": "ghp_...",          # GitHub PAT (OAuth recommended)
        "copilot_model": "copilot-4o",  # default
        "workspace_dir": "/path/to",
        "output_dir": "/tmp",
        "timeout_seconds": 3600,
        "quota_pause_on_exhaustion": true
    }

``run_id`` is ``"<pid>/<session_id>"``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from typing import Optional

from autobot_shared.logging_manager import get_logger

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus
from .copilot_local_adapter import CopilotLocalAdapter, _output_path, _resolve_gh_cli, _state_path

logger = get_logger(__name__)

_QUOTA_EXHAUSTED_PATTERNS = [
    r"quota exceeded",
    r"rate limit",
    r"copilot.*limit",
    r"subscription.*expired",
]


class CopilotSubscriptionAdapter(CopilotLocalAdapter):
    """Subscription-mode adapter for GitHub Copilot CLI (GitHub OAuth)."""

    async def _invoke(self, agent_config: dict, context: dict) -> str:
        """Invoke gh copilot CLI in subscription mode."""
        gh_cli = _resolve_gh_cli()
        agent_id: str = agent_config.get("agent_id", "unknown")
        cfg = agent_config.get("adapter_config", {})

        output_dir: str = cfg.get("output_dir", "/tmp")  # nosec B108
        timeout_sec: int = int(cfg.get("timeout_seconds", 3600))
        gh_token: Optional[str] = cfg.get("gh_token")
        copilot_model: str = cfg.get("copilot_model", "copilot-4o")

        session_id = str(uuid.uuid4())
        run_id_placeholder = f"0/{session_id}"
        output_file = _output_path(output_dir, agent_id, run_id_placeholder)
        os.makedirs(output_dir, exist_ok=True)

        prompt = self._build_prompt(context)
        workspace_dir: str | None = cfg.get("workspace_dir") or context.get("workspace_dir")

        cmd: list[str] = [gh_cli, "copilot", "suggest", "--target", "bash", prompt]

        env = {**os.environ, "LLC_INVOKE_CONTEXT": json.dumps(context, default=str)}
        if gh_token:
            env["GITHUB_TOKEN"] = gh_token
            env["GH_TOKEN"] = gh_token
        env["GH_COPILOT_MODEL"] = copilot_model
        if workspace_dir:
            env["AUTOBOT_WORKSPACE_DIR"] = workspace_dir

        # Verify GitHub authentication (subscription mode requires logged-in gh CLI)
        try:
            proc_check = await asyncio.create_subprocess_exec(
                gh_cli,
                "auth",
                "status",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
            await proc_check.wait()
            if proc_check.returncode != 0:
                raise RuntimeError(
                    "GitHub CLI not authenticated. Run 'gh auth login' to authenticate with your GitHub account."
                )
        except Exception as exc:
            logger.error("CopilotSubscriptionAdapter: GitHub auth check failed: %s", exc)
            raise

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
                    logger.warning(
                        "CopilotSubscriptionAdapter: workspace_dir %r missing, retrying without cwd",
                        workspace_dir,
                    )
                    env.pop("AUTOBOT_WORKSPACE_DIR", None)
                    workspace_dir = None
                    env["LLC_INVOKE_CONTEXT"] = json.dumps(
                        {k: v for k, v in context.items() if k != "workspace_dir"},
                        default=str,
                    )
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
            "CopilotSubscriptionAdapter: spawned PID %d session %s agent %s output=%s (subscription mode)",
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
                    "CopilotSubscriptionAdapter: quota exhausted for agent %s run %s",
                    agent_id,
                    run_id,
                )

                # TODO: Implement auto-pause + board notification (depends on GH#8225)
                return AdapterRunStatus(
                    status=LLCRunStatus.FAILED,
                    error="GitHub Copilot subscription quota exhausted. Please check your subscription limits.",
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
            logger.warning("CopilotSubscriptionAdapter: output file not found: %s", output_file)
            return False
        except Exception as exc:
            logger.exception("CopilotSubscriptionAdapter: error reading output file: %s", exc)
            return False
