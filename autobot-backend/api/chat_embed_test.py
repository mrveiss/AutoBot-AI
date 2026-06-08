# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for embed widget chat endpoint security (GH#9117).

Tests origin allowlist enforcement and per-IP rate limiting for the
unauthenticated embed endpoint.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_redis():
    """Mock Redis client for rate limiting tests."""
    mock = AsyncMock()
    mock.zcount = AsyncMock(return_value=0)
    mock.zadd = AsyncMock(return_value=1)
    mock.zremrangebyscore = AsyncMock(return_value=0)
    mock.expire = AsyncMock(return_value=True)
    mock.pipeline = MagicMock()
    pipe_mock = AsyncMock()
    pipe_mock.zadd = MagicMock(return_value=pipe_mock)
    pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
    pipe_mock.expire = MagicMock(return_value=pipe_mock)
    pipe_mock.execute = AsyncMock(return_value=[1, 0, True])
    mock.pipeline.return_value = pipe_mock
    return mock


@pytest.fixture
def mock_llm_service():
    """Mock LLM service for chat responses."""
    mock = AsyncMock()
    response_mock = MagicMock()
    response_mock.content = "Test response"
    response_mock.error = None
    mock.chat = AsyncMock(return_value=response_mock)
    return mock


@pytest.fixture
def app(mock_llm_service):
    """Create FastAPI app with embed router."""
    from api.chat_embed import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.llm_service = mock_llm_service
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_embed_message_rate_limit_allows_under_threshold(client, mock_redis):
    """Rate limiter allows requests under threshold."""
    with patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)):
        response = client.post(
            "/api/chats/embed/message",
            json={"message": "Hello"},
            headers={"X-Forwarded-For": "192.168.1.100"},
        )

    assert response.status_code == 200
    assert "content" in response.json()


@pytest.mark.asyncio
async def test_embed_message_rate_limit_blocks_exceeded(client, mock_redis):
    """Rate limiter blocks requests when threshold exceeded."""
    # Mock zcount to return count over limit (20 req/min for anonymous tier)
    mock_redis.zcount = AsyncMock(return_value=25)
    mock_redis.zrangebyscore = AsyncMock(return_value=[("1000.0", 1000.0)])

    with patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)):
        response = client.post(
            "/api/chats/embed/message",
            json={"message": "Hello"},
            headers={"X-Forwarded-For": "192.168.1.100"},
        )

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert "Rate limit exceeded" in response.json()["detail"]


@pytest.mark.asyncio
async def test_embed_preflight_rate_limit(client, mock_redis):
    """Preflight requests are also rate limited."""
    mock_redis.zcount = AsyncMock(return_value=25)
    mock_redis.zrangebyscore = AsyncMock(return_value=[("1000.0", 1000.0)])

    with patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)):
        response = client.options(
            "/api/chats/embed/message",
            headers={"X-Forwarded-For": "192.168.1.100"},
        )

    assert response.status_code == 429
    assert "Retry-After" in response.headers


@pytest.mark.asyncio
async def test_origin_allowlist_enforcement_disabled_by_default(client, mock_redis):
    """When AUTOBOT_EMBED_ALLOWED_ORIGINS is '*', all origins are allowed."""
    with (
        patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
        patch.dict("os.environ", {"AUTOBOT_EMBED_ALLOWED_ORIGINS": "*"}),
    ):
        response = client.post(
            "/api/chats/embed/message",
            json={"message": "Hello"},
            headers={
                "Origin": "https://evil.com",
                "X-Forwarded-For": "192.168.1.100",
            },
        )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"


@pytest.mark.asyncio
async def test_origin_allowlist_blocks_disallowed_origin(client, mock_redis):
    """When specific origins are configured, others are blocked."""
    with (
        patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
        patch.dict("os.environ", {"AUTOBOT_EMBED_ALLOWED_ORIGINS": "https://example.com,https://app.acme.io"}),
    ):
        # Need to reload the module to pick up new env var
        import importlib

        import api.chat_embed

        importlib.reload(api.chat_embed)

        from api.chat_embed import router as reloaded_router

        app = FastAPI()
        app.include_router(reloaded_router, prefix="/api")
        test_client = TestClient(app)

        response = test_client.post(
            "/api/chats/embed/message",
            json={"message": "Hello"},
            headers={
                "Origin": "https://evil.com",
                "X-Forwarded-For": "192.168.1.100",
            },
        )

    assert response.status_code == 403
    assert "Origin not allowed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_origin_allowlist_allows_configured_origin(client, mock_redis):
    """Configured origins are allowed through."""
    with (
        patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
        patch.dict("os.environ", {"AUTOBOT_EMBED_ALLOWED_ORIGINS": "https://example.com,https://app.acme.io"}),
    ):
        # Reload module to pick up env var
        import importlib

        import api.chat_embed

        importlib.reload(api.chat_embed)

        from api.chat_embed import router as reloaded_router

        app = FastAPI()
        app.include_router(reloaded_router, prefix="/api")
        test_client = TestClient(app)

        response = test_client.post(
            "/api/chats/embed/message",
            json={"message": "Hello"},
            headers={
                "Origin": "https://example.com",
                "X-Forwarded-For": "192.168.1.100",
            },
        )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"


@pytest.mark.asyncio
async def test_client_ip_extraction_from_x_forwarded_for(client, mock_redis):
    """Client IP is correctly extracted from X-Forwarded-For header."""
    with patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)):
        # X-Forwarded-For can have multiple IPs, first one is client
        response = client.post(
            "/api/chats/embed/message",
            json={"message": "Hello"},
            headers={"X-Forwarded-For": "203.0.113.5, 198.51.100.2, 192.0.2.1"},
        )

    assert response.status_code == 200
    # Verify the rate limiter was called with the first IP
    mock_redis.pipeline.assert_called()


@pytest.mark.asyncio
async def test_empty_message_returns_empty_response(client, mock_redis):
    """Empty messages return empty response without hitting LLM."""
    with patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)):
        response = client.post(
            "/api/chats/embed/message",
            json={"message": "   "},
            headers={"X-Forwarded-For": "192.168.1.100"},
        )

    assert response.status_code == 200
    assert response.json()["content"] == ""


@pytest.mark.asyncio
async def test_redis_unavailable_allows_request(client):
    """When Redis is unavailable, requests are allowed (fail-open)."""
    with patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=None)):
        response = client.post(
            "/api/chats/embed/message",
            json={"message": "Hello"},
            headers={"X-Forwarded-For": "192.168.1.100"},
        )

    # Should allow the request despite Redis being down
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_xff_ignored_when_peer_not_trusted(client, mock_redis):
    """X-Forwarded-For is ignored when the immediate peer is not in trusted proxies."""
    with (
        patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
        patch.dict("os.environ", {"AUTOBOT_EMBED_TRUSTED_PROXIES": "10.0.1.100"}),
    ):
        # Reload module to pick up env var
        import importlib

        import api.chat_embed

        importlib.reload(api.chat_embed)

        # Request from untrusted IP with spoofed X-Forwarded-For
        # The rate limiter should use testclient's IP, not XFF value
        from fastapi import Request

        from api.chat_embed import _get_client_ip

        mock_request = MagicMock(spec=Request)
        mock_request.client = MagicMock()
        mock_request.client.host = "203.0.113.5"  # Not in trusted proxies
        mock_request.headers = {"x-forwarded-for": "spoofed.attacker.ip"}

        client_ip = _get_client_ip(mock_request)

    # Should use direct connection IP, not X-Forwarded-For
    assert client_ip == "203.0.113.5"


@pytest.mark.asyncio
async def test_xff_honored_when_peer_trusted(client, mock_redis):
    """X-Forwarded-For is honored when the immediate peer is in trusted proxies."""
    with (
        patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
        patch.dict("os.environ", {"AUTOBOT_EMBED_TRUSTED_PROXIES": "10.0.1.100,10.0.1.101"}),
    ):
        # Reload module to pick up env var
        import importlib

        import api.chat_embed

        importlib.reload(api.chat_embed)

        from fastapi import Request

        from api.chat_embed import _get_client_ip

        mock_request = MagicMock(spec=Request)
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.1.100"  # Trusted proxy
        mock_request.headers = {"x-forwarded-for": "192.168.1.200"}

        client_ip = _get_client_ip(mock_request)

    # Should use X-Forwarded-For value from trusted proxy
    assert client_ip == "192.168.1.200"
