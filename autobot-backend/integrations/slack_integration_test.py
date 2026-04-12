# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests — SlackIntegration error handling (Issue #4161)

Tests are isolated: all aiohttp calls are patched so no real network traffic occurs.
Covers network timeout, HTTP 429 rate limit, HTTP 401 auth failure, and
invalid-channel errors.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from integrations.base import IntegrationConfig, IntegrationStatus
from integrations.communication_integration import SlackIntegration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**kwargs) -> IntegrationConfig:
    defaults = dict(
        name="Test Slack",
        provider="slack",
        token="xoxb-test-token",
        base_url="https://slack.com/api",
    )
    defaults.update(kwargs)
    return IntegrationConfig(**defaults)


def _mock_session_get(status: int, body: dict):
    """Build nested mock for aiohttp.ClientSession.get()."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=body)

    cm_inner = AsyncMock()
    cm_inner.__aenter__ = AsyncMock(return_value=resp)
    cm_inner.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=cm_inner)
    mock_session.post = MagicMock(return_value=cm_inner)

    cm_outer = MagicMock()
    cm_outer.__enter__ = MagicMock(return_value=mock_session)
    cm_outer.__exit__ = MagicMock(return_value=False)
    cm_outer.__aenter__ = AsyncMock(return_value=mock_session)
    cm_outer.__aexit__ = AsyncMock(return_value=False)
    return cm_outer


def _mock_session_post(status: int, body: dict):
    """Build nested mock for aiohttp.ClientSession.post()."""
    return _mock_session_get(status, body)


# ---------------------------------------------------------------------------
# _make_slack_request: successful path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_slack_request_success():
    slack = SlackIntegration(_make_config())
    body = {"ok": True, "channel": "C123", "ts": "12345.678"}
    with patch("aiohttp.ClientSession", return_value=_mock_session_post(200, body)):
        result = await slack._make_slack_request(
            "POST",
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": "Bearer xoxb-test"},
            data={"channel": "C123", "text": "hi"},
        )
    assert result["ok"] is True
    assert result["channel"] == "C123"


# ---------------------------------------------------------------------------
# _make_slack_request: asyncio.TimeoutError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_slack_request_timeout(caplog):
    slack = SlackIntegration(_make_config())
    with patch(
        "aiohttp.ClientSession",
        side_effect=asyncio.TimeoutError,
    ):
        result = await slack._make_slack_request(
            "POST", "https://slack.com/api/chat.postMessage"
        )
    assert result["ok"] is False
    assert result["error"] == "timeout"
    assert "timed out" in caplog.text


# ---------------------------------------------------------------------------
# _make_slack_request: aiohttp.ClientConnectionError (network error)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_slack_request_connection_error(caplog):
    slack = SlackIntegration(_make_config())
    with patch(
        "aiohttp.ClientSession",
        side_effect=aiohttp.ClientConnectionError("connection refused"),
    ):
        result = await slack._make_slack_request(
            "POST", "https://slack.com/api/chat.postMessage"
        )
    assert result["ok"] is False
    assert "connection refused" in result["error"]
    assert "connection error" in caplog.text.lower()


# ---------------------------------------------------------------------------
# _make_slack_request: HTTP 429 rate limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_slack_request_rate_limit(caplog):
    slack = SlackIntegration(_make_config())
    body = {"ok": False, "error": "ratelimited", "retry_after": 30}
    with patch("aiohttp.ClientSession", return_value=_mock_session_post(429, body)):
        result = await slack._make_slack_request(
            "POST", "https://slack.com/api/chat.postMessage"
        )
    assert result["ok"] is False
    assert "429" in caplog.text or "rate limit" in caplog.text.lower()


# ---------------------------------------------------------------------------
# _check_slack_response: auth failure → ERROR log
# ---------------------------------------------------------------------------


def test_check_slack_response_auth_failure(caplog):
    import logging

    slack = SlackIntegration(_make_config())
    with caplog.at_level(logging.ERROR):
        slack._check_slack_response(
            "https://slack.com/api/chat.postMessage",
            200,
            {"ok": False, "error": "invalid_auth"},
        )
    assert "invalid_auth" in caplog.text
    assert "authentication failure" in caplog.text.lower()


def test_check_slack_response_token_revoked(caplog):
    import logging

    slack = SlackIntegration(_make_config())
    with caplog.at_level(logging.ERROR):
        slack._check_slack_response(
            "https://slack.com/api/chat.postMessage",
            200,
            {"ok": False, "error": "token_revoked"},
        )
    assert "token_revoked" in caplog.text


# ---------------------------------------------------------------------------
# _check_slack_response: channel_not_found → WARNING (not ERROR)
# ---------------------------------------------------------------------------


def test_check_slack_response_channel_not_found(caplog):
    import logging

    slack = SlackIntegration(_make_config())
    with caplog.at_level(logging.WARNING):
        slack._check_slack_response(
            "https://slack.com/api/chat.postMessage",
            200,
            {"ok": False, "error": "channel_not_found"},
        )
    # Must log at WARNING, not ERROR
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert not error_records, "channel_not_found must not trigger ERROR-level log"
    assert "channel_not_found" in caplog.text


# ---------------------------------------------------------------------------
# _check_slack_response: ok=True is silent (no log)
# ---------------------------------------------------------------------------


def test_check_slack_response_ok_is_silent(caplog):
    slack = SlackIntegration(_make_config())
    slack._check_slack_response(
        "https://slack.com/api/chat.postMessage",
        200,
        {"ok": True, "ts": "123.456"},
    )
    assert caplog.records == []


# ---------------------------------------------------------------------------
# _check_slack_response: HTTP 5xx server error
# ---------------------------------------------------------------------------


def test_check_slack_response_server_error(caplog):
    import logging

    slack = SlackIntegration(_make_config())
    with caplog.at_level(logging.WARNING):
        slack._check_slack_response(
            "https://slack.com/api/chat.postMessage",
            503,
            {},
        )
    assert "503" in caplog.text


# ---------------------------------------------------------------------------
# _upload_file: timeout is handled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_timeout(caplog):
    slack = SlackIntegration(_make_config())
    with patch(
        "aiohttp.ClientSession",
        side_effect=asyncio.TimeoutError,
    ):
        result = await slack._upload_file(
            {"channel": "C123", "filename": "test.txt", "content": b"data"}
        )
    assert result["ok"] is False
    assert result["error"] == "timeout"
    assert "timed out" in caplog.text


# ---------------------------------------------------------------------------
# _upload_file: network error is handled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_connection_error(caplog):
    slack = SlackIntegration(_make_config())
    with patch(
        "aiohttp.ClientSession",
        side_effect=aiohttp.ClientError("upload failed"),
    ):
        result = await slack._upload_file(
            {"channel": "C123", "filename": "test.txt", "content": b"data"}
        )
    assert result["ok"] is False
    assert "upload failed" in result["error"]


# ---------------------------------------------------------------------------
# test_connection: propagates auth error via health response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_connection_auth_failure():
    slack = SlackIntegration(_make_config())
    body = {"ok": False, "error": "invalid_auth"}
    with patch("aiohttp.ClientSession", return_value=_mock_session_post(200, body)):
        health = await slack.test_connection()
    assert health.status == IntegrationStatus.ERROR
    assert "invalid_auth" in health.message


# ---------------------------------------------------------------------------
# test_connection: no token configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_connection_no_token():
    slack = SlackIntegration(_make_config(token=None))
    health = await slack.test_connection()
    assert health.status == IntegrationStatus.ERROR
    assert "token" in health.message.lower()
