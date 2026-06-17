# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for subscription-mode adapters (GH#9033)."""

import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from llc.adapters.base import LLCAdapter
from llc.adapters.claude_code_subscription_adapter import ClaudeCodeSubscriptionAdapter
from llc.adapters.codex_subscription_adapter import CodexSubscriptionAdapter
from llc.adapters.copilot_subscription_adapter import CopilotSubscriptionAdapter
from llc.models.enums import LLCRunStatus

from .conftest import agent_cfg as _agent_cfg

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

    @pytest.mark.asyncio
    async def test_quota_exhausted_wins_over_rate_limited(self) -> None:
        """M2: quota-exhaustion (→ FAILED, no retry) must beat RATE_LIMITED (→ backoff loop).

        When both quota-exhaustion patterns AND rate-limit keywords are present in the
        output, ``status()`` must return FAILED (not RATE_LIMITED), because a subscription
        quota hit should never enter the exponential-backoff retry loop.
        """
        import json
        import time as _time

        from llc.adapters.claude_code_adapter import _state_path

        adapter = ClaudeCodeSubscriptionAdapter()

        with tempfile.TemporaryDirectory() as td:
            run_id = "3001/session-quota-rl"
            # output_file must match the _output_path convention used by the adapter
            from llc.adapters.claude_code_adapter import _output_path

            output_file = _output_path(td, "agent-quota", run_id)

            with open(output_file, "w", encoding="utf-8") as fh:
                # Contains BOTH a quota-exhaustion marker AND a rate-limit keyword so
                # both _check_quota_exhaustion and _status's keyword scan would fire.
                # Also: NO success result event, so C1 gate does not suppress the scan.
                fh.write('{"type": "error", "message": "quota exceeded — rate_limit_error on subscription"}\n')

            state = {
                "pid": 3001,
                "session_id": "session-quota-rl",
                "agent_id": "agent-quota",
                "output_file": output_file,
                "started_at": _time.time(),
                "timeout_seconds": 3600,
            }
            with open(_state_path(td, run_id), "w", encoding="utf-8") as fh:
                json.dump(state, fh)

            cfg = {"agent_id": "agent-quota", "adapter_config": {"output_dir": td}}

            with (
                patch("os.kill", side_effect=ProcessLookupError()),
                patch(
                    "llc.adapters.claude_code_adapter.get_async_redis_client",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
            ):
                result = await adapter.status(cfg, run_id)

        assert result.status == LLCRunStatus.QUOTA_EXHAUSTED, (
            "Quota exhaustion must return QUOTA_EXHAUSTED (no retry → auto-pause), " "not RATE_LIMITED (backoff loop)."
        )
        assert result.error is not None
        assert "quota" in result.error.lower()


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


@pytest.mark.asyncio
class TestResolveGhToken:
    """GH#10217: copilot subscription resolves gh_token from the LLC secrets vault."""

    async def test_resolves_from_secret(self) -> None:
        from unittest.mock import MagicMock

        adapter = CopilotSubscriptionAdapter()
        session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        with (
            patch("user_management.database.get_async_session_factory", return_value=factory),
            patch("llc.services.secret.SecretService.get", new=AsyncMock(return_value="resolved-token")),
        ):
            token = await adapter._resolve_gh_token({"company_id": "c1"}, {"gh_token_secret": "gh_pat"})
        assert token == "resolved-token"

    async def test_falls_back_to_plaintext_when_no_secret(self) -> None:
        adapter = CopilotSubscriptionAdapter()
        token = await adapter._resolve_gh_token({"company_id": "c1"}, {"gh_token": "plain"})
        assert token == "plain"

    async def test_falls_back_on_secret_error(self) -> None:
        adapter = CopilotSubscriptionAdapter()
        with patch(
            "user_management.database.get_async_session_factory",
            side_effect=RuntimeError("no db"),
        ):
            token = await adapter._resolve_gh_token(
                {"company_id": "c1"}, {"gh_token_secret": "x", "gh_token": "fallback"}
            )
        assert token == "fallback"

    async def test_no_company_uses_plaintext(self) -> None:
        adapter = CopilotSubscriptionAdapter()
        token = await adapter._resolve_gh_token({}, {"gh_token_secret": "x", "gh_token": "plain"})
        assert token == "plain"
