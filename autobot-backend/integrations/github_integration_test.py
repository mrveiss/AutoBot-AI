# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests — GitHubIntegration rate limiting (Issues #4097, #4162)

All HTTP calls are patched; no real network traffic.
Covers:
- Successful requests record quota
- HTTP 429 triggers Retry-After enforcement and returns structured response
- HTTP 403 secondary rate limit is handled gracefully
- Local window exhaustion returns rate_limit_timeout error
- X-RateLimit-Remaining=0 blocks subsequent requests
- Connection errors return structured error dict
"""

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

import integrations.github_integration as _gh_mod
from integrations.base import IntegrationConfig, IntegrationStatus
from integrations.github_integration import GitHubIntegration
from integrations.rate_limiter import IntegrationRateLimiter


@pytest.fixture(autouse=True)
def _reset_module_rate_limiter():
    """Reset the module-level GitHub rate limiter before each test.

    The singleton accumulates state across tests (e.g. Retry-After from a 403
    test will cause a subsequent test's acquire() to time out).  Resetting the
    states dict and the lock reference is sufficient.
    """
    limiter = _gh_mod._GITHUB_RATE_LIMITER
    limiter._states.clear()
    limiter._lock = None
    yield
    limiter._states.clear()
    limiter._lock = None


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_config(**kwargs) -> IntegrationConfig:
    defaults = dict(
        name="Test GitHub",
        provider="github",
        api_key="ghp_test_token_abc",
        base_url="https://api.github.com",
    )
    defaults.update(kwargs)
    return IntegrationConfig(**defaults)


def _build_response_mock(status: int, body: Any, headers: Dict[str, str] | None = None):
    """Return a nested async context-manager mock for aiohttp.ClientSession.request."""
    resp = AsyncMock()
    resp.status = status
    resp.headers = headers or {}
    resp.json = AsyncMock(return_value=body)

    inner_cm = AsyncMock()
    inner_cm.__aenter__ = AsyncMock(return_value=resp)
    inner_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.request = MagicMock(return_value=inner_cm)

    outer_cm = AsyncMock()
    outer_cm.__aenter__ = AsyncMock(return_value=session)
    outer_cm.__aexit__ = AsyncMock(return_value=False)
    return outer_cm


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_connection_success():
    gh = GitHubIntegration(_make_config())
    body = {"login": "testuser", "type": "User"}
    with patch("aiohttp.ClientSession", return_value=_build_response_mock(200, body)):
        health = await gh.test_connection()
    assert health.status == IntegrationStatus.CONNECTED
    assert "testuser" in health.message


@pytest.mark.asyncio
async def test_test_connection_unauthorized():
    gh = GitHubIntegration(_make_config())
    body = {"message": "Bad credentials"}
    with patch("aiohttp.ClientSession", return_value=_build_response_mock(401, body)):
        health = await gh.test_connection()
    assert health.status == IntegrationStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_test_connection_timeout():
    gh = GitHubIntegration(_make_config())
    # Patch acquire to pass through, then simulate network timeout
    with patch.object(gh._rate_limiter, "acquire", new=AsyncMock()):
        with patch("aiohttp.ClientSession", side_effect=asyncio.TimeoutError):
            health = await gh.test_connection()
    assert health.status == IntegrationStatus.ERROR
    assert "timed out" in health.message.lower()


# ---------------------------------------------------------------------------
# HTTP 429: rate limited response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_request_429_returns_error_and_sets_retry_after():
    gh = GitHubIntegration(_make_config())
    body = {"message": "API rate limit exceeded"}
    headers = {"Retry-After": "60"}
    with patch("asyncio.sleep", new=AsyncMock()):
        with patch(
            "aiohttp.ClientSession",
            return_value=_build_response_mock(429, body, headers),
        ):
            result = await gh._github_request("GET", "/repos/owner/repo")

    assert result["status_code"] == 429
    # The retry_after_until on the limiter state should now be set
    state = gh._rate_limiter._get_state(gh._token_key)
    assert state.retry_after_until > 0.0


# ---------------------------------------------------------------------------
# HTTP 403: secondary rate limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_request_403_secondary_rate_limit():
    gh = GitHubIntegration(_make_config())
    body = {"message": "You have exceeded a secondary rate limit."}
    headers = {"Retry-After": "30"}
    with patch(
        "aiohttp.ClientSession",
        return_value=_build_response_mock(403, body, headers),
    ):
        result = await gh._github_request("GET", "/repos/owner/repo")

    assert result["status_code"] == 403
    state = gh._rate_limiter._get_state(gh._token_key)
    assert state.retry_after_until > 0.0


# ---------------------------------------------------------------------------
# X-RateLimit-Remaining=0 blocks next acquire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_x_ratelimit_remaining_zero_blocks_next_request():
    import time

    gh = GitHubIntegration(_make_config())
    body = {"login": "testuser", "type": "User"}
    # Simulate response where quota is exhausted, reset in 60 s
    reset_time = int(time.time()) + 60
    headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset_time)}
    with patch(
        "aiohttp.ClientSession",
        return_value=_build_response_mock(200, body, headers),
    ):
        await gh._github_request("GET", "/user")

    # Next check should be blocked
    can, wait = gh._rate_limiter.check(gh._token_key)
    assert can is False
    assert wait > 0.0


# ---------------------------------------------------------------------------
# Local rate limit exhaustion → rate_limit_timeout error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_timeout_returns_structured_error():
    gh = GitHubIntegration(_make_config())
    # Replace rate limiter with one that always raises TimeoutError on acquire
    mock_limiter = MagicMock()
    mock_limiter.acquire = AsyncMock(side_effect=asyncio.TimeoutError)
    gh._rate_limiter = mock_limiter

    result = await gh._github_request("GET", "/repos/owner/repo")
    assert result["status_code"] == 429
    assert result["error"] == "rate_limit_timeout"


# ---------------------------------------------------------------------------
# Connection error → structured error dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_request_connection_error():
    gh = GitHubIntegration(_make_config())
    with patch.object(gh._rate_limiter, "acquire", new=AsyncMock()):
        with patch(
            "aiohttp.ClientSession",
            side_effect=aiohttp.ClientConnectionError("refused"),
        ):
            result = await gh._github_request("GET", "/repos/owner/repo")

    assert result["status_code"] == 0
    assert result["error"] == "connection_error"
    assert "refused" in result["body"]["message"]


# ---------------------------------------------------------------------------
# 5xx transient error retries and eventually returns last result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_request_5xx_returns_after_max_retries(caplog):
    gh = GitHubIntegration(_make_config())
    body = {"message": "Service Unavailable"}

    with patch("asyncio.sleep", new=AsyncMock()):
        with patch(
            "aiohttp.ClientSession",
            return_value=_build_response_mock(503, body),
        ):
            result = await gh._github_request("GET", "/repos/owner/repo")

    # Should return after _MAX_RETRIES attempts with the 503 response
    assert result["status_code"] == 503


# ---------------------------------------------------------------------------
# execute_action: get_repository maps correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_action_get_repository():
    gh = GitHubIntegration(_make_config())
    repo_body = {"id": 1, "full_name": "owner/repo", "private": False}
    with patch(
        "aiohttp.ClientSession",
        return_value=_build_response_mock(200, repo_body),
    ):
        result = await gh.execute_action("get_repository", {"owner": "owner", "repo": "repo"})
    assert result["full_name"] == "owner/repo"


# ---------------------------------------------------------------------------
# execute_action: unknown action returns error dict (#6658)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_action_unknown_returns_error_dict():
    """#6658: BaseIntegration.execute_action contract returns Dict[str, Any];
    unknown actions must surface as {"error": ...} — not raise ValueError."""
    gh = GitHubIntegration(_make_config())
    result = await gh.execute_action("invalid_action", {})
    assert isinstance(result, dict)
    assert "error" in result
    assert "Unknown action" in result["error"]


# ---------------------------------------------------------------------------
# Rate limiting: quota records after each request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_records_after_successful_request():
    gh = GitHubIntegration(_make_config())
    # Give fresh limiter so history is clean
    fresh_limiter = IntegrationRateLimiter(requests_per_minute=100, requests_per_hour=5000)
    gh._rate_limiter = fresh_limiter

    body = {"login": "u", "type": "User"}
    with patch(
        "aiohttp.ClientSession",
        return_value=_build_response_mock(200, body),
    ):
        await gh._github_request("GET", "/user")

    state = fresh_limiter._get_state(gh._token_key)
    assert len(state.history) == 1


# ---------------------------------------------------------------------------
# Slack rate limiting: _make_slack_request applies Retry-After on 429
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_make_request_429_applies_retry_after():
    """Slack _make_slack_request should update rate limiter state on HTTP 429."""
    from integrations.communication_integration import SlackIntegration

    def _slack_config(**kw):
        from integrations.base import IntegrationConfig

        defaults = dict(
            name="Test Slack",
            provider="slack",
            token="xoxb-test",
            base_url="https://slack.com/api",
        )
        defaults.update(kw)
        return IntegrationConfig(**defaults)

    slack = SlackIntegration(_slack_config())
    fresh_limiter = IntegrationRateLimiter(requests_per_minute=100, requests_per_hour=5000)
    slack._rate_limiter = fresh_limiter

    body = {"ok": False, "error": "ratelimited", "retry_after": 30}

    resp = AsyncMock()
    resp.status = 429
    resp.headers = {"Retry-After": "30"}
    resp.json = AsyncMock(return_value=body)

    inner_cm = AsyncMock()
    inner_cm.__aenter__ = AsyncMock(return_value=resp)
    inner_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=inner_cm)

    outer_cm = AsyncMock()
    outer_cm.__aenter__ = AsyncMock(return_value=session)
    outer_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=outer_cm):
        result = await slack._make_slack_request(
            "POST",
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": "Bearer xoxb-test"},
            data={"channel": "C123", "text": "hi"},
        )

    assert result["ok"] is False
    state = fresh_limiter._get_state(slack._token_key)
    assert state.retry_after_until > 0.0
