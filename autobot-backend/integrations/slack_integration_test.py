# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Slack Integration with Error Handling (Issue #4161)

Verifies that all Slack API operations properly handle:
- Network failures (timeouts, connection errors)
- API errors (auth failures, rate limits, invalid channels)
- Payload validation errors
- Redis storage errors
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from integrations.base import IntegrationConfig
from integrations.slack_integration import (
    SlackChannelMapping,
    SlackNotificationIntegration,
)


@pytest.fixture
def slack_config():
    """Create a test Slack integration config."""
    return IntegrationConfig(
        name="slack",
        type="communication",
        token="xoxb-test-token",
        base_url="https://slack.com/api",
    )


@pytest.fixture
def slack_integration(slack_config):
    """Create a test Slack integration instance."""
    return SlackNotificationIntegration(slack_config)


@pytest.fixture
def channel_mapping():
    """Create a test channel mapping."""
    return SlackChannelMapping(
        project_id="proj-123",
        default_channel="C12345",
        notifications_channel="C12345",
        approvals_channel="C67890",
        status_channel="C11111",
    )


class TestPostTaskCompletion:
    """Test task completion posting with error handling."""

    @pytest.mark.asyncio
    async def test_post_task_completion_success(self, slack_integration):
        """Task completion posts successfully to Slack."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": True, "ts": "1234567890.0"})

        params = {
            "channel": "C12345",
            "task_id": "task-123",
            "task_title": "Deploy Services",
            "agent_name": "DeployBot",
            "summary": "Deployment completed successfully",
            "status": "completed",
            "duration_seconds": 45.5,
        }

        result = await slack_integration.post_task_completion(params)

        assert result["ok"] is True
        assert result["ts"] == "1234567890.0"

    @pytest.mark.asyncio
    async def test_post_task_completion_network_error(self, slack_integration):
        """Task completion gracefully handles network errors."""
        slack_integration._make_slack_request = AsyncMock(side_effect=ConnectionError("Network unreachable"))

        params = {
            "channel": "C12345",
            "task_id": "task-123",
            "task_title": "Deploy Services",
            "agent_name": "DeployBot",
            "summary": "Deployment attempted",
            "status": "failed",
            "duration_seconds": 10.0,
        }

        result = await slack_integration.post_task_completion(params)

        assert result["ok"] is False
        assert "error" in result
        assert "Network unreachable" in result["error"]
        assert result["task_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_post_task_completion_api_error(self, slack_integration):
        """Task completion handles Slack API errors."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": False, "error": "channel_not_found"})

        params = {
            "channel": "C_INVALID",
            "task_id": "task-456",
            "task_title": "Invalid Channel",
            "agent_name": "Bot",
            "summary": "Test",
            "status": "completed",
            "duration_seconds": 1.0,
        }

        result = await slack_integration.post_task_completion(params)

        assert result["ok"] is False
        assert result["error"] == "channel_not_found"


class TestRequestApproval:
    """Test approval request posting with error handling."""

    @pytest.mark.asyncio
    async def test_request_approval_success(self, slack_integration):
        """Approval request posts successfully and stores thread."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": True, "ts": "1234567890.0"})
        slack_integration._store_approval_thread = AsyncMock(return_value=True)

        params = {
            "channel": "C67890",
            "approval_id": "approval-123",
            "title": "Deploy to Production",
            "description": "Request to deploy version 2.0 to production",
            "approval_type": "deployment",
            "requested_by": "alice@example.com",
        }

        result = await slack_integration.request_approval(params)

        assert result["ok"] is True
        slack_integration._store_approval_thread.assert_awaited_once_with("approval-123", "C67890", "1234567890.0")

    @pytest.mark.asyncio
    async def test_request_approval_network_timeout(self, slack_integration):
        """Approval request handles timeout errors."""
        import asyncio

        slack_integration._make_slack_request = AsyncMock(side_effect=asyncio.TimeoutError("Request timed out"))

        params = {
            "channel": "C67890",
            "approval_id": "approval-456",
            "title": "Database Migration",
            "description": "Run migration script",
            "approval_type": "database",
            "requested_by": "bob@example.com",
        }

        result = await slack_integration.request_approval(params)

        assert result["ok"] is False
        assert "error" in result
        assert result["approval_id"] == "approval-456"

    @pytest.mark.asyncio
    async def test_request_approval_auth_error(self, slack_integration):
        """Approval request handles auth failures."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": False, "error": "invalid_auth"})

        params = {
            "channel": "C67890",
            "approval_id": "approval-789",
            "title": "Test Approval",
            "description": "Test",
            "approval_type": "test",
            "requested_by": "test@example.com",
        }

        result = await slack_integration.request_approval(params)

        assert result["ok"] is False
        assert result["error"] == "invalid_auth"


class TestPostAgentStatus:
    """Test agent status posting with error handling."""

    @pytest.mark.asyncio
    async def test_post_agent_status_success(self, slack_integration):
        """Agent status posts successfully."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": True, "ts": "1234567890.0"})

        params = {
            "channel": "C12345",
            "agent_name": "ScanBot",
            "status": "running",
            "message": "Scanning 150 files",
            "thread_ts": None,
        }

        result = await slack_integration.post_agent_status(params)

        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_post_agent_status_with_thread(self, slack_integration):
        """Agent status posts to thread when specified."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": True, "ts": "1234567890.1"})

        params = {
            "channel": "C12345",
            "agent_name": "ScanBot",
            "status": "completed",
            "message": "Scanning complete, 150 files processed",
            "thread_ts": "1234567890.0",
        }

        result = await slack_integration.post_agent_status(params)

        assert result["ok"] is True
        call_args = slack_integration._make_slack_request.call_args
        assert call_args[0][2]["thread_ts"] == "1234567890.0"

    @pytest.mark.asyncio
    async def test_post_agent_status_rate_limit(self, slack_integration):
        """Agent status handles rate limiting."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": False, "error": "rate_limited"})

        params = {
            "channel": "C12345",
            "agent_name": "Bot",
            "status": "running",
            "message": "Processing",
            "thread_ts": None,
        }

        result = await slack_integration.post_agent_status(params)

        assert result["ok"] is False
        assert result["error"] == "rate_limited"


class TestReplyInThread:
    """Test thread reply posting with error handling."""

    @pytest.mark.asyncio
    async def test_reply_in_thread_success(self, slack_integration):
        """Thread reply posts successfully."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": True, "ts": "1234567890.1"})

        params = {
            "channel": "C12345",
            "thread_ts": "1234567890.0",
            "text": "This is a thread reply",
        }

        result = await slack_integration.reply_in_thread(params)

        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_reply_in_thread_invalid_thread(self, slack_integration):
        """Thread reply handles invalid thread timestamps."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": False, "error": "thread_not_found"})

        params = {
            "channel": "C12345",
            "thread_ts": "9999999999.0",
            "text": "Reply to non-existent thread",
        }

        result = await slack_integration.reply_in_thread(params)

        assert result["ok"] is False
        assert result["error"] == "thread_not_found"

    @pytest.mark.asyncio
    async def test_reply_in_thread_permission_error(self, slack_integration):
        """Thread reply handles permission errors."""
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": False, "error": "no_permission"})

        params = {
            "channel": "C12345",
            "thread_ts": "1234567890.0",
            "text": "Reply without permission",
        }

        result = await slack_integration.reply_in_thread(params)

        assert result["ok"] is False
        assert result["error"] == "no_permission"


class TestCheckApprovalResponse:
    """Test approval response checking with error handling."""

    @pytest.mark.asyncio
    async def test_check_approval_response_approved(self, slack_integration):
        """Approval check detects approve response."""
        slack_integration._load_approval_thread = AsyncMock(
            return_value={"channel": "C67890", "thread_ts": "1234567890.0"}
        )
        slack_integration._make_slack_request = AsyncMock(
            return_value={
                "ok": True,
                "messages": [
                    {"text": "Approval Required: Deploy"},
                    {"text": "approve", "user": "U12345"},
                ],
            }
        )

        params = {"approval_id": "approval-123"}
        result = await slack_integration.check_approval_response(params)

        assert result["found"] is True
        assert result["decision"] == "approved"
        assert result["decided_by"] == "U12345"

    @pytest.mark.asyncio
    async def test_check_approval_response_rejected(self, slack_integration):
        """Approval check detects reject response."""
        slack_integration._load_approval_thread = AsyncMock(
            return_value={"channel": "C67890", "thread_ts": "1234567890.0"}
        )
        slack_integration._make_slack_request = AsyncMock(
            return_value={
                "ok": True,
                "messages": [
                    {"text": "Approval Required: Deploy"},
                    {"text": "rejected", "user": "U67890"},
                ],
            }
        )

        params = {"approval_id": "approval-456"}
        result = await slack_integration.check_approval_response(params)

        assert result["found"] is True
        assert result["decision"] == "rejected"
        assert result["decided_by"] == "U67890"

    @pytest.mark.asyncio
    async def test_check_approval_response_not_found_in_redis(self, slack_integration):
        """Approval check handles missing Redis entry."""
        slack_integration._load_approval_thread = AsyncMock(return_value=None)

        params = {"approval_id": "approval-999"}
        result = await slack_integration.check_approval_response(params)

        assert result["found"] is False
        assert result["decision"] is None

    @pytest.mark.asyncio
    async def test_check_approval_response_api_error(self, slack_integration):
        """Approval check handles Slack API errors."""
        slack_integration._load_approval_thread = AsyncMock(
            return_value={"channel": "C67890", "thread_ts": "1234567890.0"}
        )
        slack_integration._make_slack_request = AsyncMock(return_value={"ok": False, "error": "channel_not_found"})

        params = {"approval_id": "approval-888"}
        result = await slack_integration.check_approval_response(params)

        assert result["found"] is False
        assert result["decision"] is None

    @pytest.mark.asyncio
    async def test_check_approval_response_exception(self, slack_integration):
        """Approval check handles unexpected exceptions."""
        slack_integration._load_approval_thread = AsyncMock(side_effect=RuntimeError("Unexpected error"))

        params = {"approval_id": "approval-777"}
        result = await slack_integration.check_approval_response(params)

        assert result["found"] is False
        assert result["decision"] is None
        assert "error" in result


class TestChannelMapping:
    """Test channel mapping storage and retrieval."""

    @pytest.mark.asyncio
    async def test_save_channel_mapping_success(self, slack_integration, channel_mapping):
        """Channel mapping saves successfully to Redis."""
        mock_redis = AsyncMock()
        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration.save_channel_mapping(channel_mapping)

            assert result is True
            mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_channel_mapping_redis_unavailable(self, slack_integration, channel_mapping):
        """Channel mapping gracefully handles Redis unavailability."""
        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=None,
        ):
            result = await slack_integration.save_channel_mapping(channel_mapping)

            assert result is False

    @pytest.mark.asyncio
    async def test_save_channel_mapping_redis_error(self, slack_integration, channel_mapping):
        """Channel mapping handles Redis errors."""
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = Exception("Redis connection failed")

        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration.save_channel_mapping(channel_mapping)

            assert result is False

    @pytest.mark.asyncio
    async def test_load_channel_mapping_success(self, slack_integration, channel_mapping):
        """Channel mapping loads successfully from Redis."""
        mapping_data = json.dumps(channel_mapping.to_dict())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = mapping_data

        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration.load_channel_mapping("proj-123")

            assert result is not None
            assert result.project_id == "proj-123"
            assert result.default_channel == "C12345"

    @pytest.mark.asyncio
    async def test_load_channel_mapping_not_found(self, slack_integration):
        """Channel mapping returns None when not found."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration.load_channel_mapping("proj-nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_load_channel_mapping_corrupted_json(self, slack_integration):
        """Channel mapping handles corrupted JSON gracefully."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "{invalid json"

        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration.load_channel_mapping("proj-123")

            assert result is None

    @pytest.mark.asyncio
    async def test_load_channel_mapping_redis_error(self, slack_integration):
        """Channel mapping handles Redis errors during load."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis connection failed")

        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration.load_channel_mapping("proj-123")

            assert result is None


class TestApprovalThreadStorage:
    """Test approval thread metadata storage and retrieval."""

    @pytest.mark.asyncio
    async def test_store_approval_thread_success(self, slack_integration):
        """Approval thread stores successfully."""
        mock_redis = AsyncMock()
        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration._store_approval_thread("approval-123", "C12345", "1234567890.0")

            assert result is True
            mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_store_approval_thread_redis_error(self, slack_integration):
        """Approval thread handles storage errors."""
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = Exception("Redis write failed")

        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration._store_approval_thread("approval-123", "C12345", "1234567890.0")

            assert result is False

    @pytest.mark.asyncio
    async def test_load_approval_thread_success(self, slack_integration):
        """Approval thread loads successfully."""
        thread_data = json.dumps({"channel": "C12345", "thread_ts": "1234567890.0"})
        mock_redis = AsyncMock()
        mock_redis.get.return_value = thread_data

        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration._load_approval_thread("approval-123")

            assert result is not None
            assert result["channel"] == "C12345"
            assert result["thread_ts"] == "1234567890.0"

    @pytest.mark.asyncio
    async def test_load_approval_thread_not_found(self, slack_integration):
        """Approval thread returns None when not found."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration._load_approval_thread("approval-nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_load_approval_thread_corrupted_json(self, slack_integration):
        """Approval thread handles corrupted JSON."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "{corrupted"

        with patch(
            "integrations.slack_integration.get_redis_client",
            return_value=mock_redis,
        ):
            result = await slack_integration._load_approval_thread("approval-123")

            assert result is None
