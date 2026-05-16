# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Communication Tools Integration (Issue #61)

Provides integration with Slack, Microsoft Teams, and Discord for
sending messages, retrieving channel history, and managing communication
workflows.
"""

import asyncio
import re
import time
from typing import Any, Dict, List

import aiohttp

from autobot_shared.logging_manager import get_logger
from integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)
from integrations.rate_limiter import (
    SLACK_REQUESTS_PER_HOUR,
    SLACK_REQUESTS_PER_MINUTE,
    IntegrationRateLimiter,
)
from integrations.rate_limiter import integration_rate_limiter as _shared_rate_limiter

logger = get_logger(__name__)

# In-memory limiter retained solely for apply_response_headers() (Retry-After
# header parsing on HTTP 429).  Distributed acquire() uses _shared_rate_limiter
# so quota state is shared across all backend workers (Issue #6311).
_SLACK_RATE_LIMITER = IntegrationRateLimiter(
    requests_per_minute=SLACK_REQUESTS_PER_MINUTE,
    requests_per_hour=SLACK_REQUESTS_PER_HOUR,
)


class SlackIntegration(BaseIntegration):
    """Slack workspace integration using Bot Token authentication.

    Rate limiting:
    - Local sliding-window: 50 req/min, 2 000 req/hr per token
    - Retry-After enforcement on HTTP 429 responses
    - Exponential back-off for transient network errors
    """

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://slack.com/api"
        self._rate_limiter = _SLACK_RATE_LIMITER
        self._token_key = config.token or "unauthenticated"

    async def test_connection(self) -> IntegrationHealth:
        """Test Slack connection by calling auth.test endpoint."""
        start_time = time.monotonic()
        if not self.config.token:
            return self._create_health_response(IntegrationStatus.ERROR, 0, "Bot token not configured")

        url = f"{self.base_url}/auth.test"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        result = await self._make_slack_request("POST", url, headers=headers)

        latency = (time.monotonic() - start_time) * 1000
        if result.get("ok"):
            return self._create_health_response(
                IntegrationStatus.CONNECTED,
                latency,
                "Connected to Slack",
                {"team": result.get("team"), "user": result.get("user")},
            )
        return self._create_health_response(IntegrationStatus.ERROR, latency, result.get("error", "Unknown error"))

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

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named Slack action."""
        action_map = {
            "send_message": self._send_message,
            "list_channels": self._list_channels,
            "get_channel_history": self._get_channel_history,
            "upload_file": self._upload_file,
        }
        handler = action_map.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
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

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, data=form_data) as resp:
                    result = await resp.json()
                    self._check_slack_response(url, resp.status, result)
                    return result
        except asyncio.TimeoutError:
            self.logger.warning(
                "Slack file upload to %s timed out (channel=%s)",
                url,
                params.get("channel"),
            )
            return {"ok": False, "error": "timeout"}
        except aiohttp.ClientError as exc:
            self.logger.warning(
                "Slack file upload to %s failed: %s (channel=%s)",
                url,
                exc,
                params.get("channel"),
            )
            return {"ok": False, "error": str(exc)}

    def _check_slack_response(
        self,
        url: str,
        http_status: int,
        result: Dict[str, Any],
    ) -> None:
        """Log appropriate warnings/errors for non-OK Slack API responses.

        Slack API returns HTTP 200 for most errors, encoding the error in the
        JSON body as ``{"ok": false, "error": "<code>"}``.  HTTP-level status
        codes are only used for rate limits (429) and server errors (5xx).

        Args:
            url: The API endpoint URL (used for log context only).
            http_status: The HTTP status code from the response.
            result: The parsed JSON response body.
        """
        if http_status == 429:
            retry_after = result.get("retry_after", "unknown")
            self.logger.warning(
                "Slack rate limit hit for %s (HTTP 429, retry_after=%s)",
                url,
                retry_after,
            )
            return

        if http_status >= 500:
            self.logger.warning("Slack server error for %s (HTTP %d)", url, http_status)
            return

        if result.get("ok"):
            return

        slack_error = result.get("error", "unknown")
        if slack_error in ("invalid_auth", "not_authed", "account_inactive", "token_revoked"):
            self.logger.error(
                "Slack authentication failure at %s: %s — check bot token configuration",
                url,
                slack_error,
            )
        elif slack_error in ("channel_not_found", "not_in_channel", "is_archived"):
            self.logger.warning("Slack channel error at %s: %s", url, slack_error)
        else:
            self.logger.warning("Slack API error at %s: %s", url, slack_error)

    async def _make_slack_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str] | None = None,
        data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Rate-limited HTTP request to the Slack API.

        Checks the local sliding-window quota before sending.  On HTTP 429
        (Retry-After header) the limiter is updated and the request is
        retried once after the prescribed wait.  Never raises; returns
        ``{"ok": False, "error": "<reason>"}`` on failure.
        """
        # Acquire rate-limit slot via the shared Redis-backed limiter (Issue #6311).
        # Falls back to allow-all when Redis is unavailable.
        allowed = await _shared_rate_limiter.acquire(
            self._token_key,
            requests_per_minute=SLACK_REQUESTS_PER_MINUTE,
            requests_per_hour=SLACK_REQUESTS_PER_HOUR,
        )
        if not allowed:
            self.logger.error("Slack rate limit exceeded for %s", url)
            return {"ok": False, "error": "rate_limit_exceeded"}

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if method == "GET":
                    async with session.get(url, headers=headers, params=data) as resp:
                        result = await resp.json()
                        self._check_slack_response(url, resp.status, result)
                        if resp.status == 429:
                            self._rate_limiter.apply_response_headers(self._token_key, dict(resp.headers))
                        return result
                async with session.post(url, headers=headers, json=data) as resp:
                    result = await resp.json()
                    self._check_slack_response(url, resp.status, result)
                    if resp.status == 429:
                        self._rate_limiter.apply_response_headers(self._token_key, dict(resp.headers))
                    return result
        except asyncio.TimeoutError:
            self.logger.warning("Slack request to %s timed out", url)
            return {"ok": False, "error": "timeout"}
        except aiohttp.ClientConnectionError as exc:
            self.logger.warning("Slack connection error for %s: %s", url, exc)
            return {"ok": False, "error": str(exc)}
        except aiohttp.ClientError as exc:
            self.logger.warning("Slack request to %s failed: %s", url, exc)
            return {"ok": False, "error": str(exc)}

    def _create_health_response(
        self,
        status: IntegrationStatus,
        latency: float,
        message: str,
        details: Dict[str, Any] | None = None,
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
        start_time = time.monotonic()
        if self.webhook_url:
            result = await self._test_webhook()
            latency = (time.monotonic() - start_time) * 1000
            if result.get("success"):
                return self._create_health_response(IntegrationStatus.CONNECTED, latency, "Webhook configured")
            return self._create_health_response(IntegrationStatus.ERROR, latency, "Webhook test failed")

        if not self.config.token:
            return self._create_health_response(IntegrationStatus.ERROR, 0, "No token or webhook configured")

        url = f"{self.graph_url}/me"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        result = await self._make_teams_request("GET", url, headers)
        latency = (time.monotonic() - start_time) * 1000

        if result.get("status_code") == 200:
            return self._create_health_response(
                IntegrationStatus.CONNECTED,
                latency,
                "Connected to Microsoft Teams",
            )
        return self._create_health_response(IntegrationStatus.ERROR, latency, "Authentication failed")

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

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named Teams action."""
        action_map = {
            "send_message": self._send_message,
            "list_teams": self._list_teams,
            "list_channels": self._list_channels,
        }
        handler = action_map.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
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
        headers: Dict[str, str] | None = None,
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
        start_time = time.monotonic()
        if not self.config.token:
            return self._create_health_response(IntegrationStatus.ERROR, 0, "Bot token not configured")

        url = f"{self.base_url}/users/@me"
        headers = {"Authorization": f"Bot {self.config.token}"}
        result = await self._make_discord_request("GET", url, headers)

        latency = (time.monotonic() - start_time) * 1000
        if result.get("status_code") == 200:
            body = result.get("body", {})
            return self._create_health_response(
                IntegrationStatus.CONNECTED,
                latency,
                "Connected to Discord",
                {"username": body.get("username"), "id": body.get("id")},
            )
        return self._create_health_response(IntegrationStatus.ERROR, latency, "Authentication failed")

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

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named Discord action."""
        action_map = {
            "send_message": self._send_message,
            "list_guilds": self._list_guilds,
            "list_channels": self._list_channels,
        }
        handler = action_map.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
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
        headers: Dict[str, str] | None = None,
        data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to Discord API."""
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=headers, json=data) as resp:
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
        details: Dict[str, Any] | None = None,
    ) -> IntegrationHealth:
        """Create IntegrationHealth response."""
        return IntegrationHealth(
            provider="discord",
            status=status,
            latency_ms=latency,
            message=message,
            details=details or {},
        )
