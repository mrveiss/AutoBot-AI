# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for agent_loop/slack_hook.py (Issue #4535).

Covers:
  - get_slack_hook() returns _NullSlackHook when SLACK_BOT_TOKEN absent
  - get_slack_hook() returns _SlackHook when SLACK_BOT_TOKEN is set
  - Singleton: second call returns same object without re-initialising
  - _NullSlackHook.post_agent_status is a no-op (returns None)
  - _NullSlackHook.post_task_completion is a no-op (returns None)
  - _NullSlackHook.request_approval is a no-op (returns None)
  - _SlackHook.post_agent_status delegates to integration and swallows exceptions
  - _SlackHook.post_task_completion delegates to integration and swallows exceptions
  - _SlackHook.request_approval delegates to integration and swallows exceptions
  - _SlackHook.post_agent_status passes thread_ts only when provided
  - Channel env-vars default correctly when not set
  - SLACK_APPROVALS_CHANNEL falls back to SLACK_NOTIFICATIONS_CHANNEL
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent_loop.slack_hook as slack_hook_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_singleton() -> None:
    """Reset the module-level singleton so each test starts clean."""
    slack_hook_module._hook = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_hook():
    """Ensure singleton is reset before and after every test."""
    _reset_singleton()
    yield
    _reset_singleton()


@pytest.fixture
def mock_slack_integration():
    """Return a MagicMock that stands in for SlackNotificationIntegration."""
    integration = MagicMock()
    integration.post_agent_status = AsyncMock(return_value={"ok": True})
    integration.post_task_completion = AsyncMock(return_value={"ok": True})
    integration.request_approval = AsyncMock(return_value={"ok": True})
    return integration


# ---------------------------------------------------------------------------
# _NullSlackHook tests
# ---------------------------------------------------------------------------


class TestNullSlackHook:
    """_NullSlackHook is returned when SLACK_BOT_TOKEN is absent."""

    def test_returns_null_hook_when_token_missing(self):
        with patch.dict("os.environ", {}, clear=False):
            # Ensure token absent
            import os

            os.environ.pop("SLACK_BOT_TOKEN", None)
            hook = slack_hook_module.get_slack_hook()
        assert isinstance(hook, slack_hook_module._NullSlackHook)

    def test_singleton_returned_on_second_call(self):
        import os

        os.environ.pop("SLACK_BOT_TOKEN", None)
        hook1 = slack_hook_module.get_slack_hook()
        hook2 = slack_hook_module.get_slack_hook()
        assert hook1 is hook2

    @pytest.mark.asyncio
    async def test_post_agent_status_is_noop(self):
        import os

        os.environ.pop("SLACK_BOT_TOKEN", None)
        hook = slack_hook_module.get_slack_hook()
        result = await hook.post_agent_status("BotA", "running", "Working…")
        assert result is None

    @pytest.mark.asyncio
    async def test_post_task_completion_is_noop(self):
        import os

        os.environ.pop("SLACK_BOT_TOKEN", None)
        hook = slack_hook_module.get_slack_hook()
        result = await hook.post_task_completion("t-1", "Deploy", "BotA", "done", "completed", 10.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_request_approval_is_noop(self):
        import os

        os.environ.pop("SLACK_BOT_TOKEN", None)
        hook = slack_hook_module.get_slack_hook()
        result = await hook.request_approval("a-1", "Gate", "Need approval")
        assert result is None


# ---------------------------------------------------------------------------
# get_slack_hook lazy-init with token
# ---------------------------------------------------------------------------


class TestGetSlackHookWithToken:
    """get_slack_hook() builds a _SlackHook when SLACK_BOT_TOKEN is present."""

    def _env(self, extra: dict | None = None) -> dict:
        base = {"SLACK_BOT_TOKEN": "xoxb-test-token"}
        if extra:
            base.update(extra)
        return base

    def test_returns_slack_hook_when_token_present(self):
        env = self._env()
        fake_config_cls = MagicMock()
        fake_integration = MagicMock()
        fake_integration_cls = MagicMock(return_value=fake_integration)
        with (
            patch.dict("os.environ", env, clear=False),
            patch("integrations.base.IntegrationConfig", fake_config_cls),
            patch("integrations.slack_integration.SlackNotificationIntegration", fake_integration_cls),
        ):
            hook = slack_hook_module.get_slack_hook()
        assert isinstance(hook, slack_hook_module._SlackHook)

    def test_singleton_reused_after_init(self):
        env = self._env()
        fake_integration_cls = MagicMock(return_value=MagicMock())
        fake_config_cls = MagicMock()
        with (
            patch.dict("os.environ", env, clear=False),
            patch("integrations.base.IntegrationConfig", fake_config_cls),
            patch("integrations.slack_integration.SlackNotificationIntegration", fake_integration_cls),
        ):
            h1 = slack_hook_module.get_slack_hook()
            h2 = slack_hook_module.get_slack_hook()
            # SlackNotificationIntegration must be called exactly once
            assert fake_integration_cls.call_count == 1
        assert h1 is h2

    def test_notifications_channel_defaults(self):
        env = self._env()
        env.pop("SLACK_NOTIFICATIONS_CHANNEL", None)
        fake_integration_cls = MagicMock(return_value=MagicMock())
        fake_config_cls = MagicMock()
        with (
            patch.dict("os.environ", env, clear=False),
            patch("integrations.base.IntegrationConfig", fake_config_cls),
            patch("integrations.slack_integration.SlackNotificationIntegration", fake_integration_cls),
        ):
            import os

            os.environ.pop("SLACK_NOTIFICATIONS_CHANNEL", None)
            os.environ.pop("SLACK_APPROVALS_CHANNEL", None)
            hook = slack_hook_module.get_slack_hook()
        assert hook._notifications_channel == "#agent-notifications"

    def test_approvals_channel_falls_back_to_notifications_channel(self):
        env = self._env({"SLACK_NOTIFICATIONS_CHANNEL": "#notifs"})
        env.pop("SLACK_APPROVALS_CHANNEL", None)
        fake_integration_cls = MagicMock(return_value=MagicMock())
        fake_config_cls = MagicMock()
        with (
            patch.dict("os.environ", env, clear=False),
            patch("integrations.base.IntegrationConfig", fake_config_cls),
            patch("integrations.slack_integration.SlackNotificationIntegration", fake_integration_cls),
        ):
            import os

            os.environ.pop("SLACK_APPROVALS_CHANNEL", None)
            hook = slack_hook_module.get_slack_hook()
        assert hook._approvals_channel == "#notifs"

    def test_approvals_channel_overridden(self):
        env = self._env(
            {
                "SLACK_NOTIFICATIONS_CHANNEL": "#notifs",
                "SLACK_APPROVALS_CHANNEL": "#approvals",
            }
        )
        fake_integration_cls = MagicMock(return_value=MagicMock())
        fake_config_cls = MagicMock()
        with (
            patch.dict("os.environ", env, clear=False),
            patch("integrations.base.IntegrationConfig", fake_config_cls),
            patch("integrations.slack_integration.SlackNotificationIntegration", fake_integration_cls),
        ):
            hook = slack_hook_module.get_slack_hook()
        assert hook._approvals_channel == "#approvals"


# ---------------------------------------------------------------------------
# _SlackHook delegation and error-swallowing
# ---------------------------------------------------------------------------


class TestSlackHookDelegation:
    """_SlackHook delegates to the integration and swallows exceptions."""

    def _make_hook(self, integration: Any) -> slack_hook_module._SlackHook:
        """Build a _SlackHook with a pre-supplied integration (no real imports)."""
        hook = slack_hook_module._SlackHook.__new__(slack_hook_module._SlackHook)
        hook._integration = integration
        hook._notifications_channel = "#notifs"
        hook._approvals_channel = "#approvals"
        return hook

    @pytest.mark.asyncio
    async def test_post_agent_status_delegates(self, mock_slack_integration):
        hook = self._make_hook(mock_slack_integration)
        await hook.post_agent_status("BotA", "running", "Scanning…")
        mock_slack_integration.post_agent_status.assert_awaited_once()
        params = mock_slack_integration.post_agent_status.call_args[0][0]
        assert params["agent_name"] == "BotA"
        assert params["status"] == "running"
        assert params["channel"] == "#notifs"

    @pytest.mark.asyncio
    async def test_post_agent_status_includes_thread_ts_when_provided(self, mock_slack_integration):
        hook = self._make_hook(mock_slack_integration)
        await hook.post_agent_status("BotA", "done", "Finished", thread_ts="123.456")
        params = mock_slack_integration.post_agent_status.call_args[0][0]
        assert params["thread_ts"] == "123.456"

    @pytest.mark.asyncio
    async def test_post_agent_status_omits_thread_ts_when_absent(self, mock_slack_integration):
        hook = self._make_hook(mock_slack_integration)
        await hook.post_agent_status("BotA", "running", "Working")
        params = mock_slack_integration.post_agent_status.call_args[0][0]
        assert "thread_ts" not in params

    @pytest.mark.asyncio
    async def test_post_agent_status_swallows_exception(self, mock_slack_integration):
        mock_slack_integration.post_agent_status = AsyncMock(side_effect=RuntimeError("network down"))
        hook = self._make_hook(mock_slack_integration)
        # Must not raise
        await hook.post_agent_status("BotA", "running", "msg")

    @pytest.mark.asyncio
    async def test_post_task_completion_delegates(self, mock_slack_integration):
        hook = self._make_hook(mock_slack_integration)
        await hook.post_task_completion("t-1", "Deploy", "BotA", "All done", "completed", 42.5)
        mock_slack_integration.post_task_completion.assert_awaited_once()
        params = mock_slack_integration.post_task_completion.call_args[0][0]
        assert params["task_id"] == "t-1"
        assert params["duration_seconds"] == 42.5
        assert params["channel"] == "#notifs"

    @pytest.mark.asyncio
    async def test_post_task_completion_swallows_exception(self, mock_slack_integration):
        mock_slack_integration.post_task_completion = AsyncMock(side_effect=ConnectionError("timeout"))
        hook = self._make_hook(mock_slack_integration)
        await hook.post_task_completion("t-2", "Deploy", "BotA", "summary", "failed", 5.0)

    @pytest.mark.asyncio
    async def test_request_approval_delegates(self, mock_slack_integration):
        hook = self._make_hook(mock_slack_integration)
        await hook.request_approval("a-1", "Gate", "Need approval", "deployment")
        mock_slack_integration.request_approval.assert_awaited_once()
        params = mock_slack_integration.request_approval.call_args[0][0]
        assert params["approval_id"] == "a-1"
        assert params["approval_type"] == "deployment"
        assert params["channel"] == "#approvals"

    @pytest.mark.asyncio
    async def test_request_approval_swallows_exception(self, mock_slack_integration):
        mock_slack_integration.request_approval = AsyncMock(side_effect=Exception("Slack down"))
        hook = self._make_hook(mock_slack_integration)
        await hook.request_approval("a-2", "Gate", "Needs sign-off")
