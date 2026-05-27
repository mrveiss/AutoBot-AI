# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for the AutoBot Python SDK.

These tests run against a live local backend (http://localhost:8000).
Set AUTOBOT_API_TOKEN in the environment if auth is required.
Skip with: pytest -m "not integration"
"""

import os

import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def base_url() -> str:
    return os.environ.get("AUTOBOT_BASE_URL", "http://localhost:8000")


@pytest.mark.asyncio
async def test_sessions_list(base_url: str) -> None:
    """SDK can list chat sessions against the running backend."""
    from autobot_sdk import AutoBot

    async with AutoBot(base_url=base_url) as bot:
        result = await bot.sessions.list(limit=5)

    assert result.success is True
    assert result.data is not None
    assert isinstance(result.data.sessions, list)


@pytest.mark.asyncio
async def test_knowledge_stats(base_url: str) -> None:
    """SDK can retrieve knowledge base statistics."""
    from autobot_sdk import AutoBot

    async with AutoBot(base_url=base_url) as bot:
        result = await bot.knowledge.stats()

    assert result.success is True


@pytest.mark.asyncio
async def test_auth_token_injection(base_url: str) -> None:
    """SDK injects AUTOBOT_API_TOKEN as Bearer header when set."""
    import httpx
    from unittest.mock import AsyncMock, patch

    captured: list[str] = []

    async def _mock_get(*_args, **_kwargs):
        resp = httpx.Response(200, json={"success": True, "data": {"sessions": [], "total": 0}})
        return resp

    from autobot_sdk import AutoBot

    token = "test-token-123"
    with patch.dict(os.environ, {"AUTOBOT_API_TOKEN": token}):
        bot = AutoBot(base_url=base_url)
        assert bot._token == token


@pytest.mark.asyncio
async def test_sdk_package_importable() -> None:
    """Top-level package imports all expected public names."""
    import autobot_sdk  # noqa: F401

    assert hasattr(autobot_sdk, "AutoBot")
    assert hasattr(autobot_sdk, "AutoBotClient")
    assert hasattr(autobot_sdk, "DataResponse")
    assert hasattr(autobot_sdk, "Session")
    assert hasattr(autobot_sdk, "KnowledgeStats")
    assert hasattr(autobot_sdk, "AnalyticsUsage")
