# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SlackNotificationIntegration (Issue #4098)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from integrations.base import IntegrationConfig
from integrations.slack_integration import (
    SlackChannelMapping,
    SlackNotificationIntegration,
    _APPROVAL_THREAD_KEY_PREFIX,
    _CHANNEL_MAPPING_KEY_PREFIX,
)


@pytest.fixture()
def config() -> IntegrationConfig:
    return IntegrationConfig(
        name="test-slack",
        provider="slack",
        token="xoxb-test-token",
    )


@pytest.fixture()
def integration(config: IntegrationConfig) -> SlackNotificationIntegration:
    return SlackNotificationIntegration(config)


@pytest.fixture()
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    return redis


class TestSlackChannelMapping:
    def test_round_trip(self) -> None:
        mapping = SlackChannelMapping(
            project_id="proj-1",
            default_channel="#general",
            notifications_channel="#notifications",
            approvals_channel="#approvals",
            status_channel="#status",
        )
        restored = SlackChannelMapping.from_dict(mapping.to_dict())
        assert restored.project_id == "proj-1"
        assert restored.default_channel == "#general"
        assert restored.approvals_channel == "#approvals"

    def test_defaults_fallback_to_default_channel(self) -> None:
        mapping = SlackChannelMapping(project_id="p", default_channel="#ch")
        assert mapping.notifications_channel == "#ch"
        assert mapping.approvals_channel == "#ch"
        assert mapping.status_channel == "#ch"


class TestGetAvailableActions:
    def test_includes_notification_actions(
        self, integration: SlackNotificationIntegration
    ) -> None:
        action_names = {a.name for a in integration.get_available_actions()}
        assert "post_task_completion" in action_names
        assert "request_approval" in action_names
        assert "post_agent_status" in action_names
        assert "reply_in_thread" in action_names
        assert "check_approval_response" in action_names

    def test_includes_base_actions(
        self, integration: SlackNotificationIntegration
    ) -> None:
        action_names = {a.name for a in integration.get_available_actions()}
        assert "send_message" in action_names
        assert "list_channels" in action_names


class TestPostTaskCompletion:
    @pytest.mark.asyncio
    async def test_success(self, integration: SlackNotificationIntegration) -> None:
        slack_response = {"ok": True, "ts": "1234.5678", "channel": "C123"}
        integration._make_slack_request = AsyncMock(return_value=slack_response)

        result = await integration.post_task_completion(
            {
                "channel": "#eng",
                "task_id": "task-42",
                "task_title": "Deploy service",
                "agent_name": "DeployBot",
                "summary": "Deployment succeeded.",
                "status": "completed",
                "duration_seconds": 45.3,
            }
        )

        assert result["ok"] is True
        call_args = integration._make_slack_request.call_args
        payload = call_args[0][3]
        assert payload["channel"] == "#eng"
        assert "blocks" in payload
        # Header block contains the task title
        header_text = payload["blocks"][0]["text"]["text"]
        assert "Deploy service" in header_text
        assert ":white_check_mark:" in header_text

    @pytest.mark.asyncio
    async def test_failed_status_uses_x_emoji(
        self, integration: SlackNotificationIntegration
    ) -> None:
        integration._make_slack_request = AsyncMock(return_value={"ok": True, "ts": "1"})
        await integration.post_task_completion(
            {
                "channel": "#eng",
                "task_id": "t1",
                "task_title": "Deploy",
                "agent_name": "Bot",
                "summary": "Failed.",
                "status": "failed",
                "duration_seconds": 10,
            }
        )
        payload = integration._make_slack_request.call_args[0][3]
        assert ":x:" in payload["blocks"][0]["text"]["text"]


class TestRequestApproval:
    @pytest.mark.asyncio
    async def test_stores_thread_on_success(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        slack_response = {"ok": True, "ts": "9999.0001"}
        integration._make_slack_request = AsyncMock(return_value=slack_response)

        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await integration.request_approval(
                {
                    "channel": "#approvals",
                    "approval_id": "appr-abc",
                    "title": "Drop production table",
                    "description": "Required for migration.",
                    "approval_type": "destructive_action",
                    "requested_by": "MigrationAgent",
                }
            )

        assert result["ok"] is True
        mock_redis.set.assert_awaited_once()
        key_used = mock_redis.set.call_args[0][0]
        assert key_used == f"{_APPROVAL_THREAD_KEY_PREFIX}appr-abc"

    @pytest.mark.asyncio
    async def test_blocks_contain_approve_reject_buttons(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        integration._make_slack_request = AsyncMock(return_value={"ok": True, "ts": "1"})
        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            await integration.request_approval(
                {
                    "channel": "#approvals",
                    "approval_id": "appr-xyz",
                    "title": "Action",
                    "description": "Desc",
                    "approval_type": "workflow_gate",
                    "requested_by": "Bot",
                }
            )
        payload = integration._make_slack_request.call_args[0][3]
        actions_block = next(b for b in payload["blocks"] if b["type"] == "actions")
        action_values = [el["value"] for el in actions_block["elements"]]
        assert "approve:appr-xyz" in action_values
        assert "reject:appr-xyz" in action_values

    @pytest.mark.asyncio
    async def test_no_store_when_slack_fails(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        integration._make_slack_request = AsyncMock(
            return_value={"ok": False, "error": "channel_not_found"}
        )
        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await integration.request_approval(
                {
                    "channel": "#bad",
                    "approval_id": "appr-fail",
                    "title": "X",
                    "description": "Y",
                    "approval_type": "workflow_gate",
                    "requested_by": "Bot",
                }
            )
        assert result["ok"] is False
        mock_redis.set.assert_not_awaited()


class TestPostAgentStatus:
    @pytest.mark.asyncio
    async def test_posts_to_channel(
        self, integration: SlackNotificationIntegration
    ) -> None:
        integration._make_slack_request = AsyncMock(return_value={"ok": True, "ts": "1"})
        await integration.post_agent_status(
            {
                "channel": "#status",
                "agent_name": "DataBot",
                "status": "running",
                "message": "Processing records",
            }
        )
        payload = integration._make_slack_request.call_args[0][3]
        assert payload["channel"] == "#status"
        assert "DataBot" in payload["text"]
        assert ":hourglass_flowing_sand:" in payload["text"]

    @pytest.mark.asyncio
    async def test_thread_reply_when_thread_ts_given(
        self, integration: SlackNotificationIntegration
    ) -> None:
        integration._make_slack_request = AsyncMock(return_value={"ok": True, "ts": "2"})
        await integration.post_agent_status(
            {
                "channel": "#status",
                "agent_name": "Bot",
                "status": "completed",
                "message": "Done",
                "thread_ts": "1234.5678",
            }
        )
        payload = integration._make_slack_request.call_args[0][3]
        assert payload.get("thread_ts") == "1234.5678"


class TestReplyInThread:
    @pytest.mark.asyncio
    async def test_includes_thread_ts(
        self, integration: SlackNotificationIntegration
    ) -> None:
        integration._make_slack_request = AsyncMock(return_value={"ok": True})
        await integration.reply_in_thread(
            {"channel": "#general", "thread_ts": "111.222", "text": "Hello thread"}
        )
        payload = integration._make_slack_request.call_args[0][3]
        assert payload["thread_ts"] == "111.222"
        assert payload["text"] == "Hello thread"


class TestCheckApprovalResponse:
    @pytest.mark.asyncio
    async def test_returns_not_found_when_no_thread(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        mock_redis.get = AsyncMock(return_value=None)
        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await integration.check_approval_response(
                {"approval_id": "appr-missing"}
            )
        assert result["found"] is False
        assert result["decision"] is None

    @pytest.mark.asyncio
    async def test_detects_approve_reply(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        stored = json.dumps({"channel": "C1", "thread_ts": "123.456"})
        mock_redis.get = AsyncMock(return_value=stored)
        replies_response = {
            "ok": True,
            "messages": [
                {"text": "Approval Required: ...", "user": "bot"},
                {"text": "approve", "user": "U9999"},
            ],
        }
        integration._make_slack_request = AsyncMock(return_value=replies_response)
        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await integration.check_approval_response(
                {"approval_id": "appr-1"}
            )
        assert result["found"] is True
        assert result["decision"] == "approved"
        assert result["decided_by"] == "U9999"

    @pytest.mark.asyncio
    async def test_detects_reject_reply(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        stored = json.dumps({"channel": "C1", "thread_ts": "123.456"})
        mock_redis.get = AsyncMock(return_value=stored)
        replies_response = {
            "ok": True,
            "messages": [
                {"text": "Approval Required", "user": "bot"},
                {"text": "reject", "user": "U8888"},
            ],
        }
        integration._make_slack_request = AsyncMock(return_value=replies_response)
        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await integration.check_approval_response(
                {"approval_id": "appr-2"}
            )
        assert result["found"] is True
        assert result["decision"] == "rejected"

    @pytest.mark.asyncio
    async def test_no_response_yet(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        stored = json.dumps({"channel": "C1", "thread_ts": "123.456"})
        mock_redis.get = AsyncMock(return_value=stored)
        replies_response = {
            "ok": True,
            "messages": [{"text": "Approval Required", "user": "bot"}],
        }
        integration._make_slack_request = AsyncMock(return_value=replies_response)
        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await integration.check_approval_response(
                {"approval_id": "appr-3"}
            )
        assert result["found"] is False


class TestSaveLoadChannelMapping:
    @pytest.mark.asyncio
    async def test_save_calls_redis_set(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            mapping = SlackChannelMapping(
                project_id="proj-10", default_channel="#gen"
            )
            await integration.save_channel_mapping(mapping)

        mock_redis.set.assert_awaited_once()
        key = mock_redis.set.call_args[0][0]
        assert key == f"{_CHANNEL_MAPPING_KEY_PREFIX}proj-10"

    @pytest.mark.asyncio
    async def test_load_returns_none_when_missing(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        mock_redis.get = AsyncMock(return_value=None)
        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await integration.load_channel_mapping("proj-missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_returns_mapping_when_present(
        self, integration: SlackNotificationIntegration, mock_redis
    ) -> None:
        stored = json.dumps(
            {
                "project_id": "proj-20",
                "default_channel": "#all",
                "notifications_channel": "#notifs",
                "approvals_channel": "#approv",
                "status_channel": "#status",
            }
        )
        mock_redis.get = AsyncMock(return_value=stored)
        with patch(
            "integrations.slack_integration.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await integration.load_channel_mapping("proj-20")
        assert result is not None
        assert result.project_id == "proj-20"
        assert result.approvals_channel == "#approv"
