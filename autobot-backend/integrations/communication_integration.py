# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Communication Tools Integration (Issue #61)

Provides integration with Slack, Microsoft Teams, and Discord for
sending messages, retrieving channel history, and managing communication
workflows.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
from backend.integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)

logger = logging.getLogger(__name__)


class SlackIntegration(BaseIntegration):
    """Slack workspace integration using Bot Token authentication."""

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://slack.com/api"

    async def test_connection(self) -> IntegrationHealth:
        """Test Slack connection by calling auth.test endpoint."""
        start_time = datetime.utcnow()
        if not self.config.token:
            return self._create_health_response(
                IntegrationStatus.ERROR, 0, "Bot token not configured"
            )

        url = f"{self.base_url}/auth.test"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        result = await self._make_slack_request("POST", url, headers=headers)

        latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        if result.get("ok"):
            return self._create_health_response(
                IntegrationStatus.CONNECTED,
                latency,
                "Connected to Slack",
                {"team": result.get("team"), "user": result.get("user")},
            )
        return self._create_health_response(
            IntegrationStatus.ERROR, latency, result.get("error", "Unknown error")
        )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of supported Slack actions."""
        return [
            IntegrationAction(
                name="send_message",
                description="Send message to a Slack channel",
                method="POST",
                parameters={"channel": "str", "text": "str"},
            ),
            IntegrationAction(
                name="list_channels",
                description="List all public channels",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="get_channel_history",
                description="Get message history from a channel",
                method="GET",
                parameters={"channel": "str", "limit": "int"},
            ),
            IntegrationAction(
                name="upload_file",
                description="Upload file to a channel",
                method="POST",
                parameters={"channel": "str", "filename": "str", "content": "bytes"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a named Slack action."""
        action_map = {
            "send_message": self._send_message,
            "list_channels": self._list_channels,
            "get_channel_history": self._get_channel_history,
            "upload_file": self._upload_file,
        }
        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
        return await handler(params)

    async def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send message to Slack channel."""
        url = f"{self.base_url}/chat.postMessage"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        payload = {
            "channel": params["channel"],
            "text": params["text"],
        }
        return await self._make_slack_request("POST", url, headers, payload)

    async def _list_channels(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all public channels."""
        url = f"{self.base_url}/conversations.list"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        return await self._make_slack_request("GET", url, headers)

    async def _get_channel_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get message history from channel."""
        url = f"{self.base_url}/conversations.history"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        query_params = {
            "channel": params["channel"],
            "limit": params.get("limit", 100),
        }
        return await self._make_slack_request("GET", url, headers, query_params)

    async def _upload_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Upload file to Slack channel."""
        url = f"{self.base_url}/files.upload"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        form_data = aiohttp.FormData()
        form_data.add_field("channels", params["channel"])
        form_data.add_field("filename", params["filename"])
        form_data.add_field("file", params["content"])

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=form_data) as resp:
                return await resp.json()

    async def _make_slack_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to Slack API."""
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if method == "GET":
                    async with session.get(url, headers=headers, params=data) as resp:
                        return await resp.json()
                async with session.post(url, headers=headers, json=data) as resp:
                    return await resp.json()
        except aiohttp.ClientError as exc:
            self.logger.warning("Slack request to %s failed: %s", url, exc)
            return {"ok": False, "error": str(exc)}

    def _create_health_response(
        self,
        status: IntegrationStatus,
        latency: float,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> IntegrationHealth:
        """Create IntegrationHealth response."""
        return IntegrationHealth(
            provider="slack",
            status=status,
            latency_ms=latency,
            message=message,
            details=details or {},
        )


class TeamsIntegration(BaseIntegration):
    """Microsoft Teams integration using webhook URLs."""

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.webhook_url = config.extra.get("webhook_url")
        self.graph_url = config.base_url or "https://graph.microsoft.com/v1.0"

    async def test_connection(self) -> IntegrationHealth:
        """Test Teams connection by validating token or webhook."""
        start_time = datetime.utcnow()
        if self.webhook_url:
            result = await self._test_webhook()
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            if result.get("success"):
                return self._create_health_response(
                    IntegrationStatus.CONNECTED, latency, "Webhook configured"
                )
            return self._create_health_response(
                IntegrationStatus.ERROR, latency, "Webhook test failed"
            )

        if not self.config.token:
            return self._create_health_response(
                IntegrationStatus.ERROR, 0, "No token or webhook configured"
            )

        url = f"{self.graph_url}/me"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        result = await self._make_teams_request("GET", url, headers)
        latency = (datetime.utcnow() - start_time).total_seconds() * 1000

        if result.get("status_code") == 200:
            return self._create_health_response(
                IntegrationStatus.CONNECTED,
                latency,
                "Connected to Microsoft Teams",
            )
        return self._create_health_response(
            IntegrationStatus.ERROR, latency, "Authentication failed"
        )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of supported Teams actions."""
        return [
            IntegrationAction(
                name="send_message",
                description="Send message via webhook",
                method="POST",
                parameters={"text": "str", "title": "str"},
            ),
            IntegrationAction(
                name="list_teams",
                description="List all teams (requires Graph API token)",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="list_channels",
                description="List channels in a team",
                method="GET",
                parameters={"team_id": "str"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a named Teams action."""
        action_map = {
            "send_message": self._send_message,
            "list_teams": self._list_teams,
            "list_channels": self._list_channels,
        }
        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
        return await handler(params)

    async def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send message to Teams via webhook."""
        if not self.webhook_url:
            return {"success": False, "error": "Webhook URL not configured"}

        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": params.get("title", "AutoBot Notification"),
            "title": params.get("title", "AutoBot Notification"),
            "text": params["text"],
        }
        return await self._post_webhook(payload)

    async def _list_teams(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all teams user belongs to."""
        url = f"{self.graph_url}/me/joinedTeams"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        result = await self._make_teams_request("GET", url, headers)
        return result.get("body", {})

    async def _list_channels(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List channels in a team."""
        team_id = params["team_id"]
        url = f"{self.graph_url}/teams/{team_id}/channels"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        result = await self._make_teams_request("GET", url, headers)
        return result.get("body", {})

    async def _test_webhook(self) -> Dict[str, Any]:
        """Test webhook by sending a minimal payload."""
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "text": "AutoBot connection test",
        }
        return await self._post_webhook(payload)

    async def _post_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Post message to Teams webhook."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    status = resp.status
                    return {"success": status == 200, "status_code": status}
        except aiohttp.ClientError as exc:
            self.logger.warning("Teams webhook failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def _make_teams_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to Microsoft Graph API."""
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=headers) as resp:
                    body = await resp.json()
                    return {"status_code": resp.status, "body": body}
        except aiohttp.ClientError as exc:
            self.logger.warning("Teams Graph request to %s failed: %s", url, exc)
            return {"status_code": 0, "body": {}, "error": str(exc)}

    def _create_health_response(
        self,
        status: IntegrationStatus,
        latency: float,
        message: str,
    ) -> IntegrationHealth:
        """Create IntegrationHealth response."""
        return IntegrationHealth(
            provider="teams",
            status=status,
            latency_ms=latency,
            message=message,
        )


class DiscordIntegration(BaseIntegration):
    """Discord server integration using Bot Token authentication."""

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://discord.com/api/v10"

    async def test_connection(self) -> IntegrationHealth:
        """Test Discord connection by fetching bot user info."""
        start_time = datetime.utcnow()
        if not self.config.token:
            return self._create_health_response(
                IntegrationStatus.ERROR, 0, "Bot token not configured"
            )

        url = f"{self.base_url}/users/@me"
        headers = {"Authorization": f"Bot {self.config.token}"}
        result = await self._make_discord_request("GET", url, headers)

        latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        if result.get("status_code") == 200:
            body = result.get("body", {})
            return self._create_health_response(
                IntegrationStatus.CONNECTED,
                latency,
                "Connected to Discord",
                {"username": body.get("username"), "id": body.get("id")},
            )
        return self._create_health_response(
            IntegrationStatus.ERROR, latency, "Authentication failed"
        )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of supported Discord actions."""
        return [
            IntegrationAction(
                name="send_message",
                description="Send message to a Discord channel",
                method="POST",
                parameters={"channel_id": "str", "content": "str"},
            ),
            IntegrationAction(
                name="list_guilds",
                description="List all guilds the bot is in",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="list_channels",
                description="List channels in a guild",
                method="GET",
                parameters={"guild_id": "str"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a named Discord action."""
        action_map = {
            "send_message": self._send_message,
            "list_guilds": self._list_guilds,
            "list_channels": self._list_channels,
        }
        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
        return await handler(params)

    async def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send message to Discord channel."""
        content = self._sanitize_content(params["content"])
        url = f"{self.base_url}/channels/{params['channel_id']}/messages"
        headers = {"Authorization": f"Bot {self.config.token}"}
        payload = {"content": content}
        return await self._make_discord_request("POST", url, headers, payload)

    async def _list_guilds(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all guilds the bot is in."""
        url = f"{self.base_url}/users/@me/guilds"
        headers = {"Authorization": f"Bot {self.config.token}"}
        return await self._make_discord_request("GET", url, headers)

    async def _list_channels(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List channels in a guild."""
        url = f"{self.base_url}/guilds/{params['guild_id']}/channels"
        headers = {"Authorization": f"Bot {self.config.token}"}
        return await self._make_discord_request("GET", url, headers)

    async def _make_discord_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to Discord API."""
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method, url, headers=headers, json=data
                ) as resp:
                    body = await resp.json()
                    return {"status_code": resp.status, "body": body}
        except aiohttp.ClientError as exc:
            self.logger.warning("Discord request to %s failed: %s", url, exc)
            return {"status_code": 0, "body": {}, "error": str(exc)}

    def _sanitize_content(self, content: str) -> str:
        """Remove dangerous mentions from message content.

        Helper for _send_message (Issue #61).
        """
        sanitized = re.sub(r"@(everyone|here)", r"@\u200b\1", content)
        return sanitized

    def _create_health_response(
        self,
        status: IntegrationStatus,
        latency: float,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> IntegrationHealth:
        """Create IntegrationHealth response."""
        return IntegrationHealth(
            provider="discord",
            status=status,
            latency_ms=latency,
            message=message,
            details=details or {},
        )
