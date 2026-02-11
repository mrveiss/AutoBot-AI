# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Communication Integration API Endpoints (Issue #61)

FastAPI router for managing Slack, Teams, and Discord integrations.
Provides endpoints for testing connections, sending messages, and
listing channels/guilds.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.integrations.base import IntegrationConfig, IntegrationHealth
from backend.integrations.communication_integration import (
    DiscordIntegration,
    SlackIntegration,
    TeamsIntegration,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations-communication"])


class TestConnectionRequest(BaseModel):
    """Request model for testing communication provider connections."""

    provider: str = Field(..., description="Provider name: slack, teams, or discord")
    token: Optional[str] = Field(None, description="Bot token or API token")
    webhook_url: Optional[str] = Field(None, description="Webhook URL (for Teams)")
    base_url: Optional[str] = Field(None, description="Custom base URL (optional)")


class SendMessageRequest(BaseModel):
    """Request model for sending messages."""

    channel: Optional[str] = Field(None, description="Channel ID or name (Slack)")
    channel_id: Optional[str] = Field(None, description="Channel ID (Discord)")
    text: Optional[str] = Field(None, description="Message text")
    content: Optional[str] = Field(None, description="Message content (Discord)")
    title: Optional[str] = Field(None, description="Message title (Teams)")


class ProviderInfo(BaseModel):
    """Information about a supported communication provider."""

    name: str
    description: str
    auth_type: str
    required_fields: List[str]


class WebhookMessageRequest(BaseModel):
    """Request model for webhook messages."""

    webhook_url: str = Field(..., description="Teams webhook URL")
    text: str = Field(..., description="Message text")
    title: Optional[str] = Field(None, description="Message title")


@router.post(
    "/test-connection",
    response_model=IntegrationHealth,
    summary="Test communication provider connection",
)
async def test_connection(request: TestConnectionRequest) -> IntegrationHealth:
    """Test connection to a communication provider."""
    provider = request.provider.lower()
    integration = _create_integration(provider, request)

    try:
        health = await integration.test_connection()
        return health
    except Exception as exc:
        logger.exception("Failed to test %s connection", provider)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(exc)}",
        ) from exc


@router.get(
    "/providers",
    response_model=List[ProviderInfo],
    summary="List supported communication providers",
)
async def list_providers() -> List[ProviderInfo]:
    """Return list of supported communication providers."""
    return [
        ProviderInfo(
            name="slack",
            description="Slack workspace integration",
            auth_type="bot_token",
            required_fields=["token"],
        ),
        ProviderInfo(
            name="teams",
            description="Microsoft Teams integration",
            auth_type="webhook_or_token",
            required_fields=["webhook_url or token"],
        ),
        ProviderInfo(
            name="discord",
            description="Discord server integration",
            auth_type="bot_token",
            required_fields=["token"],
        ),
    ]


@router.get(
    "/{provider}/channels",
    response_model=Dict[str, Any],
    summary="List channels for a provider",
)
async def list_channels(
    provider: str,
    token: str,
    guild_id: Optional[str] = None,
    team_id: Optional[str] = None,
) -> Dict[str, Any]:
    """List channels/teams for the specified provider."""
    provider_lower = provider.lower()
    config = _create_config(provider_lower, token)
    integration = _get_integration(provider_lower, config)

    try:
        if provider_lower == "slack":
            return await integration.execute_action("list_channels", {})
        elif provider_lower == "teams":
            if not team_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="team_id required for Teams",
                )
            return await integration.execute_action(
                "list_channels", {"team_id": team_id}
            )
        elif provider_lower == "discord":
            if not guild_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="guild_id required for Discord",
                )
            return await integration.execute_action(
                "list_channels", {"guild_id": guild_id}
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {provider}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.exception("Failed to list channels for %s", provider)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list channels: {str(exc)}",
        ) from exc


@router.post(
    "/{provider}/messages",
    response_model=Dict[str, Any],
    summary="Send message to a channel",
)
async def send_message(
    provider: str,
    token: str,
    message: SendMessageRequest,
) -> Dict[str, Any]:
    """Send a message to the specified provider channel."""
    provider_lower = provider.lower()
    config = _create_config(provider_lower, token)
    integration = _get_integration(provider_lower, config)

    try:
        params = _build_message_params(provider_lower, message)
        result = await integration.execute_action("send_message", params)
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.exception("Failed to send message via %s", provider)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send message: {str(exc)}",
        ) from exc


@router.get(
    "/{provider}/channels/{channel_id}/history",
    response_model=Dict[str, Any],
    summary="Get channel message history",
)
async def get_channel_history(
    provider: str,
    channel_id: str,
    token: str,
    limit: int = 100,
) -> Dict[str, Any]:
    """Get message history from a channel (Slack only)."""
    provider_lower = provider.lower()
    if provider_lower != "slack":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="History only supported for Slack",
        )

    config = _create_config(provider_lower, token)
    integration = _get_integration(provider_lower, config)

    try:
        result = await integration.execute_action(
            "get_channel_history", {"channel": channel_id, "limit": limit}
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.exception("Failed to get history for %s", channel_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get history: {str(exc)}",
        ) from exc


@router.post(
    "/{provider}/webhooks",
    response_model=Dict[str, Any],
    summary="Send webhook message (Teams)",
)
async def send_webhook_message(
    provider: str,
    webhook: WebhookMessageRequest,
) -> Dict[str, Any]:
    """Send a message via Teams webhook."""
    provider_lower = provider.lower()
    if provider_lower != "teams":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhooks only supported for Teams",
        )

    config = IntegrationConfig(
        name="teams_webhook",
        provider="teams",
        extra={"webhook_url": webhook.webhook_url},
    )
    integration = TeamsIntegration(config)

    try:
        params = {"text": webhook.text}
        if webhook.title:
            params["title"] = webhook.title
        result = await integration.execute_action("send_message", params)
        return result
    except Exception as exc:
        logger.exception("Failed to send webhook message")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send webhook: {str(exc)}",
        ) from exc


def _create_integration(
    provider: str,
    request: TestConnectionRequest,
) -> Any:
    """Create integration instance from test request.

    Helper for test_connection (Issue #61).
    """
    config = IntegrationConfig(
        name=f"{provider}_test",
        provider=provider,
        token=request.token,
        base_url=request.base_url,
        extra={"webhook_url": request.webhook_url} if request.webhook_url else {},
    )
    return _get_integration(provider, config)


def _create_config(provider: str, token: str) -> IntegrationConfig:
    """Create IntegrationConfig from provider and token.

    Helper for list_channels and send_message (Issue #61).
    """
    return IntegrationConfig(
        name=f"{provider}_api",
        provider=provider,
        token=token,
    )


def _get_integration(provider: str, config: IntegrationConfig) -> Any:
    """Get integration class instance for provider.

    Helper for multiple endpoints (Issue #61).
    """
    if provider == "slack":
        return SlackIntegration(config)
    elif provider == "teams":
        return TeamsIntegration(config)
    elif provider == "discord":
        return DiscordIntegration(config)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported provider: {provider}",
    )


def _build_message_params(
    provider: str,
    message: SendMessageRequest,
) -> Dict[str, Any]:
    """Build message parameters for provider.

    Helper for send_message (Issue #61).
    """
    if provider == "slack":
        if not message.channel or not message.text:
            raise ValueError("Slack requires 'channel' and 'text'")
        return {"channel": message.channel, "text": message.text}
    elif provider == "teams":
        if not message.text:
            raise ValueError("Teams requires 'text'")
        params = {"text": message.text}
        if message.title:
            params["title"] = message.title
        return params
    elif provider == "discord":
        if not message.channel_id or not message.content:
            raise ValueError("Discord requires 'channel_id' and 'content'")
        return {"channel_id": message.channel_id, "content": message.content}
    raise ValueError(f"Unsupported provider: {provider}")
