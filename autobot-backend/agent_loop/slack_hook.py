# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Slack Notification Hook for AgentLoop (Issue #4308)

Thin wrapper around SlackNotificationIntegration that:
- Loads configuration from environment variables at first use (lazy)
- Provides a no-op singleton when SLACK_BOT_TOKEN is absent
- Exposes fire-and-forget helpers used by AgentLoop

Environment variables:
    SLACK_BOT_TOKEN           — Slack bot token (xoxb-…); required to enable
    SLACK_NOTIFICATIONS_CHANNEL — Channel for task completion & status updates
                                  (default: #agent-notifications)
    SLACK_APPROVALS_CHANNEL   — Channel for approval request messages
                                  (default: same as SLACK_NOTIFICATIONS_CHANNEL)
"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

_SLACK_NOTIFICATIONS_CHANNEL_DEFAULT = "#agent-notifications"


class _NullSlackHook:
    """No-op hook returned when Slack is not configured."""

    async def post_agent_status(self, agent_name: str, status: str, message: str, thread_ts: str | None = None) -> None:
        pass

    async def post_task_completion(
        self,
        task_id: str,
        task_title: str,
        agent_name: str,
        summary: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        pass

    async def request_approval(
        self,
        approval_id: str,
        title: str,
        description: str,
        approval_type: str = "tool",
        requested_by: str = "AutoBot",
    ) -> None:
        pass

    async def ask_human(
        self,
        question_id: str,
        question: str,
        choices: list[str] | None = None,
        task_id: str | None = None,
    ) -> None:
        pass


class _SlackHook:
    """Active hook backed by SlackNotificationIntegration."""

    def __init__(self, token: str, notifications_channel: str, approvals_channel: str) -> None:
        from integrations.base import IntegrationConfig
        from integrations.slack_integration import SlackNotificationIntegration

        config = IntegrationConfig(
            name="agent-loop-slack",
            provider="slack",
            token=token,
        )
        self._integration = SlackNotificationIntegration(config)
        self._notifications_channel = notifications_channel
        self._approvals_channel = approvals_channel

    async def post_agent_status(self, agent_name: str, status: str, message: str, thread_ts: str | None = None) -> None:
        params: Dict[str, Any] = {
            "channel": self._notifications_channel,
            "agent_name": agent_name,
            "status": status,
            "message": message,
        }
        if thread_ts:
            params["thread_ts"] = thread_ts
        try:
            await self._integration.post_agent_status(params)
        except Exception as exc:
            logger.debug("SlackHook.post_agent_status failed (non-critical): %s", exc)

    async def post_task_completion(
        self,
        task_id: str,
        task_title: str,
        agent_name: str,
        summary: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        params: Dict[str, Any] = {
            "channel": self._notifications_channel,
            "task_id": task_id,
            "task_title": task_title,
            "agent_name": agent_name,
            "summary": summary,
            "status": status,
            "duration_seconds": duration_seconds,
        }
        try:
            await self._integration.post_task_completion(params)
        except Exception as exc:
            logger.debug("SlackHook.post_task_completion failed (non-critical): %s", exc)

    async def request_approval(
        self,
        approval_id: str,
        title: str,
        description: str,
        approval_type: str = "tool",
        requested_by: str = "AutoBot",
    ) -> None:
        params: Dict[str, Any] = {
            "channel": self._approvals_channel,
            "approval_id": approval_id,
            "title": title,
            "description": description,
            "approval_type": approval_type,
            "requested_by": requested_by,
        }
        try:
            await self._integration.request_approval(params)
        except Exception as exc:
            logger.debug("SlackHook.request_approval failed (non-critical): %s", exc)

    async def ask_human(
        self,
        question_id: str,
        question: str,
        choices: list[str] | None = None,
        task_id: str | None = None,
    ) -> None:
        """Notify the Slack approvals channel that the agent needs a human answer (#10553).

        Human can reply via the /tasks/{task_id}/answer endpoint; the reply
        body must include the question_id to be routed correctly.
        """
        choices_text = " | ".join(choices) if choices else "free-form text"
        description = (
            f"Agent is waiting for your answer (question_id={question_id}).\n"
            f"Choices: {choices_text}\n"
            f"Reply via POST /api/agent-terminal/tasks/{task_id}/answer"
        )
        params: Dict[str, Any] = {
            "channel": self._approvals_channel,
            "approval_id": question_id,
            "title": f"Agent question: {question[:80]}",
            "description": description,
            "approval_type": "human_question",
            "requested_by": "AgentLoop",
        }
        try:
            await self._integration.request_approval(params)
        except Exception as exc:
            logger.debug("SlackHook.ask_human failed (non-critical): %s", exc)


# Module-level singleton; resolved lazily on first call to get_slack_hook().
_hook: Any | None = None


def get_slack_hook() -> Any:
    """Return the module-level Slack hook singleton.

    Reads SLACK_BOT_TOKEN from the environment.  Returns a _NullSlackHook
    (all no-ops) when the token is absent so callers need no guard.
    """
    global _hook
    if _hook is not None:
        return _hook

    token = config.slack_bot_token.strip()
    if not token:
        logger.debug("SLACK_BOT_TOKEN not set — Slack notifications disabled")
        _hook = _NullSlackHook()
        return _hook

    notifications_channel = config.slack_notifications_channel.strip()
    approvals_channel = config.slack_approvals_channel.strip()

    logger.info(
        "Slack notifications enabled (channel=%s, approvals=%s)",
        notifications_channel,
        approvals_channel,
    )
    _hook = _SlackHook(token, notifications_channel, approvals_channel)
    return _hook
