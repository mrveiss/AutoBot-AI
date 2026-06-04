# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for subscription-mode adapters (GH#9033)."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters.base import LLCAdapter
from llc.adapters.claude_code_subscription_adapter import ClaudeCodeSubscriptionAdapter
from llc.adapters.codex_subscription_adapter import CodexSubscriptionAdapter
from llc.adapters.copilot_subscription_adapter import CopilotSubscriptionAdapter
from llc.models.enums import LLCRunStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_cfg(agent_id: str = "agent-1", output_dir: str | None = None, **kwargs) -> dict:
    cfg: dict = {"agent_id": agent_id, "adapter_config": {**kwargs}}
    if output_dir:
        cfg["adapter_config"]["output_dir"] = output_dir
    return cfg


# ---------------------------------------------------------------------------
# ClaudeCodeSubscriptionAdapter
# ---------------------------------------------------------------------------


class TestClaudeCodeSubscriptionAdapter:
    def test_satisfies_llc_adapter_protocol(self) -> None:
        assert isinstance(ClaudeCodeSubscriptionAdapter(), LLCAdapter)

    def test_build_subscription_env_strips_api_keys(self) -> None:
        """Verify API keys are stripped from environment in subscription mode."""
        adapter = ClaudeCodeSubscriptionAdapter()

        # Set API keys in os.environ
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-key"
        os.environ["CLAUDE_API_KEY"] = "sk-another-key"
        os.environ["API_KEY"] = "generic-key"

        try:
            context = {"workspace_dir": "/tmp/test"}
            env = adapter._build_subscription_env(context, "/tmp/test")

            # Verify API keys are NOT in the built environment
            assert "ANTHROPIC_API_KEY" not in env
            assert "CLAUDE_API_KEY" not in env
            assert "API_KEY" not in env

            # Verify standard context is present
            assert "LLC_INVOKE_CONTEXT" in env
            assert "AUTOBOT_WORKSPACE_DIR" in env
        finally:
            # Clean up
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("CLAUDE_API_KEY", None)
            os.environ.pop("API_KEY", None)

    def test_check_quota_exhaustion_detects_patterns(self) -> None:
        """Verify quota exhaustion detection from CLI output."""
        adapter = ClaudeCodeSubscriptionAdapter()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            f.write('{"type": "error", "message": "quota exceeded for this session"}\n')
            output_file = f.name

        try:
            assert adapter._check_quota_exhaustion(output_file) is True
        finally:
            os.unlink(output_file)

    def test_check_quota_exhaustion_returns_false_on_clean_output(self) -> None:
        """Verify quota exhaustion returns False for clean output."""
        adapter = ClaudeCodeSubscriptionAdapter()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            f.write('{"type": "success", "message": "completed successfully"}\n')
            output_file = f.name

        try:
            assert adapter._check_quota_exhaustion(output_file) is False
        finally:
            os.unlink(output_file)

    def test_check_quota_exhaustion_handles_missing_file(self) -> None:
        """Verify quota exhaustion check handles missing output file gracefully."""
        adapter = ClaudeCodeSubscriptionAdapter()
        assert adapter._check_quota_exhaustion("/nonexistent/file.jsonl") is False


# ---------------------------------------------------------------------------
# CopilotSubscriptionAdapter
# ---------------------------------------------------------------------------


class TestCopilotSubscriptionAdapter:
    def test_satisfies_llc_adapter_protocol(self) -> None:
        assert isinstance(CopilotSubscriptionAdapter(), LLCAdapter)

    def test_check_quota_exhaustion_detects_copilot_patterns(self) -> None:
        """Verify Copilot quota exhaustion detection."""
        adapter = CopilotSubscriptionAdapter()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("Error: Copilot subscription limit reached for this billing period\n")
            output_file = f.name

        try:
            assert adapter._check_quota_exhaustion(output_file) is True
        finally:
            os.unlink(output_file)


# ---------------------------------------------------------------------------
# CodexSubscriptionAdapter
# ---------------------------------------------------------------------------


class TestCodexSubscriptionAdapter:
    def test_satisfies_llc_adapter_protocol(self) -> None:
        """Codex adapter is a stub but should still satisfy protocol."""
        assert isinstance(CodexSubscriptionAdapter(), LLCAdapter)

    @pytest.mark.asyncio
    async def test_invoke_raises_not_implemented(self) -> None:
        """Codex adapter should raise NotImplementedError since CLI doesn't exist."""
        adapter = CodexSubscriptionAdapter()
        cfg = _agent_cfg(agent_id="test-agent")

        with pytest.raises(NotImplementedError, match="does not exist"):
            await adapter.invoke(cfg, {})

    @pytest.mark.asyncio
    async def test_status_returns_failed(self) -> None:
        """Codex adapter status should return FAILED with clear error."""
        adapter = CodexSubscriptionAdapter()
        cfg = _agent_cfg(agent_id="test-agent")

        status = await adapter.status(cfg, "fake-run-id")
        assert status.status == LLCRunStatus.FAILED
        assert "does not exist" in status.error.lower()
