# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Slack Integration for Notifications and Approvals (Issue #4098)

Extends the base SlackIntegration from communication_integration with:
- Task completion summaries posted to channels with Block Kit formatting
- Approval request messages with approve/reject interactive actions
- Approval response detection via thread reply polling
- Real-time agent status update messages
- Thread-based conversation support

Channel mappings are stored in Redis (main database) keyed by project/workspace.

Error Handling (Issue #4161):
- Network errors (aiohttp.ClientError, timeouts) are caught and logged
- Slack API errors (auth failures, rate limits, server errors) are logged
- Redis errors gracefully degrade with circuit breaker pattern
- All methods return error dicts instead of raising exceptions
"""

import json
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from integrations.base import IntegrationAction
from integrations.communication_integration import SlackIntegration

logger = get_logger(__name__)

_CHANNEL_MAPPING_KEY_PREFIX = "slack:channel_mapping:"
_APPROVAL_THREAD_KEY_PREFIX = "slack:approval_thread:"
_APPROVAL_THREAD_TTL = 86400  # 24 hours


class SlackChannelMapping:
    """Channel mapping for a project/workspace stored in Redis."""

    def __init__(
        self,
        project_id: str,
        default_channel: str,
        notifications_channel: str | None = None,
        approvals_channel: str | None = None,
        status_channel: str | None = None,
    ) -> None:
        self.project_id = project_id
        self.default_channel = default_channel
        self.notifications_channel = notifications_channel or default_channel
        self.approvals_channel = approvals_channel or default_channel
        self.status_channel = status_channel or default_channel

    def to_dict(self) -> Dict[str, str]:
        return {
            "project_id": self.project_id,
            "default_channel": self.default_channel,
            "notifications_channel": self.notifications_channel,
            "approvals_channel": self.approvals_channel,
            "status_channel": self.status_channel,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "SlackChannelMapping":
        return cls(
            project_id=data["project_id"],
            default_channel=data["default_channel"],
            notifications_channel=data.get("notifications_channel"),
            approvals_channel=data.get("approvals_channel"),
            status_channel=data.get("status_channel"),
        )


class SlackNotificationIntegration(SlackIntegration):
    """Slack integration for agent notifications and approval workflows.

    Adds task completion summaries, approval request/response handling,
    real-time status updates, and thread-based conversations on top of
    the base SlackIntegration.

    All Slack API operations are wrapped with comprehensive error handling:
    - Network errors (timeouts, DNS failures, connection resets)
    - API errors (auth failures, rate limits, invalid channels)
    - Rate limiting (429 responses) are logged with backoff guidance
    - Transient failures are logged with context for debugging
    """

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return all supported Slack actions including notification-specific ones."""
        base_actions = super().get_available_actions()
        return base_actions + [
            IntegrationAction(
                name="post_task_completion",
                description="Post agent task completion summary to a channel",
                method="POST",
                parameters={
                    "channel": "str",
                    "task_id": "str",
                    "task_title": "str",
                    "agent_name": "str",
                    "summary": "str",
                    "status": "str",
                    "duration_seconds": "float",
                },
            ),
            IntegrationAction(
                name="request_approval",
                description="Post an approval request message with approve/reject actions",
                method="POST",
                parameters={
                    "channel": "str",
                    "approval_id": "str",
                    "title": "str",
                    "description": "str",
                    "approval_type": "str",
                    "requested_by": "str",
                },
            ),
            IntegrationAction(
                name="post_agent_status",
                description="Post real-time agent status update to a channel",
                method="POST",
                parameters={
                    "channel": "str",
                    "agent_name": "str",
                    "status": "str",
                    "message": "str",
                    "thread_ts": "str",
                },
            ),
            IntegrationAction(
                name="reply_in_thread",
                description="Post a reply in an existing Slack thread",
                method="POST",
                parameters={
                    "channel": "str",
                    "thread_ts": "str",
                    "text": "str",
                },
            ),
            IntegrationAction(
                name="check_approval_response",
                description="Poll a thread for approval/rejection response",
                method="GET",
                parameters={"approval_id": "str"},
            ),
        ]

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named Slack action, including notification-specific actions."""
        notification_map = {
            "post_task_completion": self.post_task_completion,
            "request_approval": self.request_approval,
            "post_agent_status": self.post_agent_status,
            "reply_in_thread": self.reply_in_thread,
            "check_approval_response": self.check_approval_response,
        }
        if action in notification_map:
            return await notification_map[action](params)
        return await super().execute_action(action, params)

    async def post_task_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post a task completion summary using Block Kit formatting.

        Wraps the Slack API call with error handling for network failures,
        auth errors, and invalid channels.

        Args:
            params: channel, task_id, task_title, agent_name, summary,
                    status, duration_seconds
        Returns:
            Slack API response with message ts, or error dict on failure.
            Never raises; logs and returns error response instead.
        """
        try:
            status = params.get("status", "completed")
            status_emoji = ":white_check_mark:" if status == "completed" else ":x:"
            duration = params.get("duration_seconds", 0)
            duration_str = f"{duration:.1f}s" if duration < 60 else f"{duration / 60:.1f}m"

            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{status_emoji} Task {status.capitalize()}: {params['task_title']}",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Agent:*\n{params['agent_name']}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Task ID:*\n`{params['task_id']}`",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Status:*\n{status.capitalize()}",
                        },
                        {"type": "mrkdwn", "text": f"*Duration:*\n{duration_str}"},
                    ],
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Summary:*\n{params['summary']}",
                    },
                },
            ]

            url = f"{self.base_url}/chat.postMessage"
            headers = {"Authorization": f"Bearer {self.config.token}"}
            payload = {
                "channel": params["channel"],
                "text": f"Task {status}: {params['task_title']}",
                "blocks": blocks,
            }
            result = await self._make_slack_request("POST", url, headers, payload)
            logger.info(
                "Posted task completion for task_id=%s to channel=%s",
                params.get("task_id"),
                params.get("channel"),
            )
            return result
        except Exception as exc:
            logger.error(
                "Failed to post task completion (task_id=%s, channel=%s): %s",
                params.get("task_id"),
                params.get("channel"),
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "task_id": params.get("task_id"),
            }

    async def request_approval(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post an approval request with approve/reject action buttons.

        Wraps Slack API call and Redis storage with error handling.
        Stores the resulting thread ts in Redis keyed by approval_id so
        check_approval_response can poll for replies.

        Args:
            params: channel, approval_id, title, description, approval_type,
                    requested_by
        Returns:
            Slack API response with message ts, or error dict on failure.
            Never raises; logs and returns error response instead.
        """
        try:
            approval_id = params["approval_id"]
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f":rotating_light: Approval Required: {params['title']}",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Type:*\n{params.get('approval_type', 'action')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Requested by:*\n{params.get('requested_by', 'AutoBot')}",
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Description:*\n{params['description']}",
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ("Reply *approve* or *reject* in this thread, " "or use the buttons below."),
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Approve",
                                "emoji": True,
                            },
                            "style": "primary",
                            "value": f"approve:{approval_id}",
                            "action_id": f"approval_approve_{approval_id}",
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Reject",
                                "emoji": True,
                            },
                            "style": "danger",
                            "value": f"reject:{approval_id}",
                            "action_id": f"approval_reject_{approval_id}",
                        },
                    ],
                },
            ]

            url = f"{self.base_url}/chat.postMessage"
            headers = {"Authorization": f"Bearer {self.config.token}"}
            payload = {
                "channel": params["channel"],
                "text": f"Approval Required: {params['title']}",
                "blocks": blocks,
            }
            result = await self._make_slack_request("POST", url, headers, payload)

            if result.get("ok") and result.get("ts"):
                await self._store_approval_thread(approval_id, params["channel"], result["ts"])
            return result
        except Exception as exc:
            logger.error(
                "Failed to request approval (approval_id=%s, channel=%s): %s",
                params.get("approval_id"),
                params.get("channel"),
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "approval_id": params.get("approval_id"),
            }

    async def post_agent_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post a real-time agent status update.

        Wraps Slack API call with error handling for network failures,
        invalid channels, and rate limiting.

        If thread_ts is provided, posts as a thread reply to keep
        related updates grouped.

        Args:
            params: channel, agent_name, status, message, thread_ts (optional)
        Returns:
            Slack API response, or error dict on failure.
            Never raises; logs and returns error response instead.
        """
        try:
            status_emoji_map = {
                "running": ":hourglass_flowing_sand:",
                "completed": ":white_check_mark:",
                "failed": ":x:",
                "waiting": ":pause_button:",
                "started": ":rocket:",
            }
            emoji = status_emoji_map.get(params.get("status", ""), ":information_source:")
            text = (
                f"{emoji} *{params['agent_name']}* — "
                f"{params.get('status', 'update').capitalize()}: {params['message']}"
            )

            url = f"{self.base_url}/chat.postMessage"
            headers = {"Authorization": f"Bearer {self.config.token}"}
            payload: Dict[str, Any] = {
                "channel": params["channel"],
                "text": text,
                "mrkdwn": True,
            }
            if params.get("thread_ts"):
                payload["thread_ts"] = params["thread_ts"]

            result = await self._make_slack_request("POST", url, headers, payload)
            logger.debug(
                "Posted agent status for agent=%s (status=%s) to channel=%s",
                params.get("agent_name"),
                params.get("status"),
                params.get("channel"),
            )
            return result
        except Exception as exc:
            logger.error(
                "Failed to post agent status (agent=%s, channel=%s): %s",
                params.get("agent_name"),
                params.get("channel"),
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "agent_name": params.get("agent_name"),
            }

    async def reply_in_thread(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post a reply in an existing Slack thread.

        Wraps Slack API call with error handling for network failures,
        invalid channels, and invalid thread timestamps.

        Args:
            params: channel, thread_ts, text
        Returns:
            Slack API response, or error dict on failure.
            Never raises; logs and returns error response instead.
        """
        try:
            url = f"{self.base_url}/chat.postMessage"
            headers = {"Authorization": f"Bearer {self.config.token}"}
            payload = {
                "channel": params["channel"],
                "thread_ts": params["thread_ts"],
                "text": params["text"],
            }
            result = await self._make_slack_request("POST", url, headers, payload)
            logger.debug(
                "Posted reply to thread %s in channel=%s",
                params.get("thread_ts"),
                params.get("channel"),
            )
            return result
        except Exception as exc:
            logger.error(
                "Failed to reply in thread (channel=%s, thread_ts=%s): %s",
                params.get("channel"),
                params.get("thread_ts"),
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "thread_ts": params.get("thread_ts"),
            }

    async def check_approval_response(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Poll a Slack thread for an approve/reject response.

        Wraps Slack API call and Redis lookup with error handling.
        Reads thread replies for the stored approval thread and looks for
        messages containing 'approve' or 'reject' (case-insensitive).

        Args:
            params: approval_id
        Returns:
            dict with keys: found (bool), decision (str|None), decided_by (str|None).
            On error, returns found=False with error key.
            Never raises; logs and returns error response instead.
        """
        try:
            approval_id = params["approval_id"]
            thread_info = await self._load_approval_thread(approval_id)
            if not thread_info:
                logger.warning(
                    "No stored approval thread found for approval_id=%s",
                    approval_id,
                )
                return {
                    "found": False,
                    "decision": None,
                    "decided_by": None,
                }

            channel = thread_info["channel"]
            thread_ts = thread_info["thread_ts"]

            url = f"{self.base_url}/conversations.replies"
            headers = {"Authorization": f"Bearer {self.config.token}"}
            query = {"channel": channel, "ts": thread_ts}
            result = await self._make_slack_request("GET", url, headers, query)

            if not result.get("ok"):
                logger.warning(
                    "Failed to fetch thread replies for approval_id=%s: %s",
                    approval_id,
                    result.get("error", "unknown error"),
                )
                return {
                    "found": False,
                    "decision": None,
                    "decided_by": None,
                }

            messages = result.get("messages", [])
            # Skip the first message (the original approval request)
            for msg in messages[1:]:
                text = (msg.get("text") or "").lower().strip()
                if text in {"approve", "approved"}:
                    logger.info(
                        "Approval response found for approval_id=%s: approved",
                        approval_id,
                    )
                    return {
                        "found": True,
                        "decision": "approved",
                        "decided_by": msg.get("user"),
                    }
                if text in {"reject", "rejected"}:
                    logger.info(
                        "Approval response found for approval_id=%s: rejected",
                        approval_id,
                    )
                    return {
                        "found": True,
                        "decision": "rejected",
                        "decided_by": msg.get("user"),
                    }

            logger.debug(
                "No approval response found yet for approval_id=%s",
                approval_id,
            )
            return {"found": False, "decision": None, "decided_by": None}
        except Exception as exc:
            logger.error(
                "Failed to check approval response (approval_id=%s): %s",
                params.get("approval_id"),
                exc,
            )
            return {
                "found": False,
                "decision": None,
                "decided_by": None,
                "error": str(exc),
            }

    async def save_channel_mapping(self, mapping: SlackChannelMapping) -> bool:
        """Persist a channel mapping to Redis.

        Wraps Redis set operation with error handling.

        Args:
            mapping: SlackChannelMapping instance to store

        Returns:
            True on success, False on failure.
            Never raises; logs error and returns False instead.
        """
        try:
            client = await get_async_redis_client(database="main")
            if client is None:
                logger.warning(
                    "Redis client unavailable for saving channel mapping (project_id=%s)",
                    mapping.project_id,
                )
                return False

            key = f"{_CHANNEL_MAPPING_KEY_PREFIX}{mapping.project_id}"
            await client.set(key, json.dumps(mapping.to_dict(), ensure_ascii=False))
            logger.debug(
                "Saved channel mapping for project_id=%s",
                mapping.project_id,
            )
            return True
        except json.JSONDecodeError as exc:
            logger.error(
                "JSON encoding error saving channel mapping (project_id=%s): %s",
                mapping.project_id,
                exc,
            )
            return False
        except Exception as exc:
            logger.error(
                "Failed to save channel mapping (project_id=%s): %s",
                mapping.project_id,
                exc,
            )
            return False

    async def load_channel_mapping(self, project_id: str) -> SlackChannelMapping | None:
        """Load a channel mapping from Redis.

        Wraps Redis get operation with error handling.

        Args:
            project_id: project or workspace identifier

        Returns:
            SlackChannelMapping or None if not found or on error.
            Never raises; logs error and returns None instead.
        """
        try:
            client = await get_async_redis_client(database="main")
            if client is None:
                logger.warning(
                    "Redis client unavailable for loading channel mapping (project_id=%s)",
                    project_id,
                )
                return None

            key = f"{_CHANNEL_MAPPING_KEY_PREFIX}{project_id}"
            raw = await client.get(key)
            if not raw:
                logger.debug(
                    "No channel mapping found in Redis for project_id=%s",
                    project_id,
                )
                return None

            data = json.loads(raw)
            logger.debug(
                "Loaded channel mapping for project_id=%s",
                project_id,
            )
            return SlackChannelMapping.from_dict(data)
        except json.JSONDecodeError as exc:
            logger.error(
                "Malformed JSON in channel mapping (project_id=%s): %s",
                project_id,
                exc,
            )
            return None
        except Exception as exc:
            logger.error(
                "Failed to load channel mapping (project_id=%s): %s",
                project_id,
                exc,
            )
            return None

    async def _store_approval_thread(self, approval_id: str, channel: str, thread_ts: str) -> bool:
        """Store channel + thread_ts for an approval in Redis.

        Wraps Redis set operation with error handling.

        Args:
            approval_id: approval identifier
            channel: Slack channel ID
            thread_ts: Slack thread timestamp

        Returns:
            True on success, False on failure.
            Never raises; logs error and returns False instead.
        """
        try:
            client = await get_async_redis_client(database="main")
            if client is None:
                logger.warning(
                    "Redis client unavailable for storing approval thread (approval_id=%s)",
                    approval_id,
                )
                return False

            key = f"{_APPROVAL_THREAD_KEY_PREFIX}{approval_id}"
            value = json.dumps(
                {"channel": channel, "thread_ts": thread_ts},
                ensure_ascii=False,
            )
            await client.set(key, value, ex=_APPROVAL_THREAD_TTL)
            logger.debug(
                "Stored approval thread (approval_id=%s, channel=%s, thread_ts=%s)",
                approval_id,
                channel,
                thread_ts,
            )
            return True
        except json.JSONDecodeError as exc:
            logger.error(
                "JSON encoding error storing approval thread (approval_id=%s): %s",
                approval_id,
                exc,
            )
            return False
        except Exception as exc:
            logger.error(
                "Failed to store approval thread (approval_id=%s): %s",
                approval_id,
                exc,
            )
            return False

    async def _load_approval_thread(self, approval_id: str) -> Dict[str, str] | None:
        """Load stored channel + thread_ts for an approval from Redis.

        Wraps Redis get operation with error handling.

        Args:
            approval_id: approval identifier

        Returns:
            dict with "channel" and "thread_ts" keys, or None on failure.
            Never raises; logs error and returns None instead.
        """
        try:
            client = await get_async_redis_client(database="main")
            if client is None:
                logger.warning(
                    "Redis client unavailable for loading approval thread (approval_id=%s)",
                    approval_id,
                )
                return None

            key = f"{_APPROVAL_THREAD_KEY_PREFIX}{approval_id}"
            raw = await client.get(key)
            if not raw:
                logger.debug(
                    "No approval thread found in Redis (approval_id=%s)",
                    approval_id,
                )
                return None

            data = json.loads(raw)
            logger.debug(
                "Loaded approval thread (approval_id=%s)",
                approval_id,
            )
            return data
        except json.JSONDecodeError as exc:
            logger.error(
                "Malformed JSON in approval thread (approval_id=%s): %s",
                approval_id,
                exc,
            )
            return None
        except Exception as exc:
            logger.error(
                "Failed to load approval thread (approval_id=%s): %s",
                approval_id,
                exc,
            )
            return None
