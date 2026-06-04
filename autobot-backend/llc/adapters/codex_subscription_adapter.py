# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""CodexSubscriptionAdapter — STUB for OpenAI Codex CLI subscription mode (GH#9033).

NOTE: As of 2025, OpenAI does not provide a Codex CLI with ChatGPT Plus subscription auth.
This adapter is a placeholder for when/if such a CLI becomes available.

If you need to run OpenAI agents today, use API key based adapters instead.

adapter_config schema (future)::

    {
        "model": "gpt-4",
        "max_tokens": 4000,
        "output_dir": "/tmp",
        "timeout_seconds": 3600,
        "workspace_dir": "/path/to/worktree",
        "quota_pause_on_exhaustion": true
    }
"""

from __future__ import annotations


from autobot_shared.logging_manager import get_logger

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus

logger = get_logger(__name__)


class CodexSubscriptionAdapter:
    """STUB: OpenAI Codex CLI subscription adapter (CLI does not exist yet)."""

    async def invoke(self, agent_config: dict, context: dict) -> str:
        """Invoke OpenAI Codex CLI (NOT IMPLEMENTED - CLI does not exist)."""
        logger.error(
            "CodexSubscriptionAdapter.invoke called but OpenAI does not provide a Codex CLI. "
            "Use API-key based OpenAI adapters instead."
        )
        raise NotImplementedError(
            "OpenAI Codex CLI with ChatGPT Plus subscription auth does not exist. "
            "This adapter is a placeholder for future OpenAI CLI releases. "
            "Use API key based adapters for OpenAI models."
        )

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        """Return status (NOT IMPLEMENTED - CLI does not exist)."""
        return AdapterRunStatus(
            status=LLCRunStatus.FAILED,
            error="OpenAI Codex CLI does not exist. Use API-key based adapters.",
        )

    async def cancel(self, agent_config: dict, run_id: str) -> None:
        """Cancel run (NOT IMPLEMENTED - CLI does not exist)."""
        logger.warning("CodexSubscriptionAdapter.cancel called but adapter is not implemented")
        return
