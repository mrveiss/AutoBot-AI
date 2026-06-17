# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""CopilotSubscriptionAdapter — GitHub Copilot CLI with subscription auth (GH#9033).

Like CopilotLocalAdapter but enforces subscription-only mode:
- Uses GitHub OAuth (no separate Copilot API key required)
- Token usage parsed from CLI output
- Quota exhaustion triggers auto-pause + board notification

adapter_config schema::

    {
        "gh_token_secret": "copilot_gh_token",  # name of a secret in the company
                                                # vault — preferred (GH#10217)
        "gh_token": "ghp_...",          # plaintext fallback (discouraged)
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
from .subprocess_support import inject_agent_credentials, serialize_invoke_context

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
        # GH#10217: prefer a credential stored in the LLC secrets vault
        # (gh_token_secret = secret name) over a plaintext gh_token in config.
        gh_token: Optional[str] = await self._resolve_gh_token(agent_config, cfg)
        copilot_model: str = cfg.get("copilot_model", "copilot-4o")

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

    async def _resolve_gh_token(self, agent_config: dict, cfg: dict) -> Optional[str]:
        """Resolve the GitHub token, preferring the LLC secrets vault (GH#10217).

        ``adapter_config.gh_token_secret`` names a secret in the agent's company
        vault; when set it is decrypted at invoke time so the token is never
        stored in plaintext adapter_config. Falls back to a plaintext
        ``gh_token`` for backward compatibility.
        """
        secret_name = cfg.get("gh_token_secret")
        company_id = agent_config.get("company_id")
        if secret_name and company_id:
            try:
                from user_management.database import get_async_session_factory  # noqa: PLC0415

                from ..services.secret import SecretService  # noqa: PLC0415

                factory = get_async_session_factory()
                async with factory() as session:
                    return await SecretService().get(session, str(company_id), secret_name)
            except Exception:
                logger.warning(
                    "CopilotSubscriptionAdapter: could not resolve gh_token_secret %r — "
                    "falling back to plaintext gh_token",
                    secret_name,
                )
        return cfg.get("gh_token")

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        """Check status and parse token usage from output."""
        base_status = await super().status(agent_config, run_id)

        # On any terminal state, check the output for quota exhaustion (GH#9777).
        if base_status.status.is_terminal():
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

                # GH#10218: signal QUOTA_EXHAUSTED so the scheduler auto-pauses
                # the agent and logs a board-visible pause event (no retry).
                return AdapterRunStatus(
                    status=LLCRunStatus.QUOTA_EXHAUSTED,
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
