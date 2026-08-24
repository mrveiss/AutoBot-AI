# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
    """Mock Redis client for rate limiting tests.

    ``RateLimiter.acquire`` performs the check-and-record atomically in a Lua
    script (Issue #9610), so ``eval`` — not ``zcount``/``pipeline`` — is the
    call the endpoint's rate-limit decision hinges on. It returns 1 (allowed)
    here; tests that exercise the limit set it to 0. ``zcount`` /
    ``zrangebyscore`` still back ``get_retry_after_seconds``.
    """
    mock = AsyncMock()
    mock.eval = AsyncMock(return_value=1)
    mock.zcount = AsyncMock(return_value=0)
    mock.zrangebyscore = AsyncMock(return_value=[])
    mock.zadd = AsyncMock(return_value=1)
    mock.zremrangebyscore = AsyncMock(return_value=0)
    mock.expire = AsyncMock(return_value=True)
    return mock


@pytest.fixture(autouse=True)
def restore_chat_embed_module():
    """Reload api.chat_embed after every test in this module.

    Several tests reload the module under a patched environment to pick up its
    import-time origin/proxy allowlists. Without this teardown the reloaded
    module — with origin enforcement still switched on — leaked into every
    later test, which then got 403s from an endpoint they never configured.
    """
    yield
    import importlib

    import api.chat_embed

    importlib.reload(api.chat_embed)


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
    # Lua script reports "rate limited"; zcount/zrangebyscore feed Retry-After
    # (25 requests recorded against the 20 req/min anonymous tier).
    mock_redis.eval = AsyncMock(return_value=0)
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
    mock_redis.eval = AsyncMock(return_value=0)
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
async def test_client_ip_extraction_ignores_untrusted_x_forwarded_for(client, mock_redis):
    """No trusted proxies configured → the rate-limit key uses the peer IP.

    Honouring X-Forwarded-For from an untrusted peer would let any caller
    reset their own bucket by rotating the header, so the limiter must key on
    the direct connection instead (GH#9117).
    """
    with patch("autobot_shared.rate_limiter.get_async_redis_client", new=AsyncMock(return_value=mock_redis)):
        # X-Forwarded-For can have multiple IPs; none of them may be trusted here
        response = client.post(
            "/api/chats/embed/message",
            json={"message": "Hello"},
            headers={"X-Forwarded-For": "203.0.113.5, 198.51.100.2, 192.0.2.1"},
        )

    assert response.status_code == 200
    # The rate limiter ran, and keyed on the peer rather than the spoofable header
    mock_redis.eval.assert_called()
    rate_limit_key = mock_redis.eval.call_args.args[2]
    assert rate_limit_key.startswith("autobot:rl:embed:")
    assert "203.0.113.5" not in rate_limit_key


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
