# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for TracedHttpClient (Issue #3827).

Verifies that TracedHttpClient delegates all HTTP calls to HTTPClientManager
instead of creating its own raw httpx.AsyncClient.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from utils.traced_http_client import (
    TracedHttpClient,
    traced_delete,
    traced_get,
    traced_http_client,
    traced_post,
    traced_put,
)


def _make_mock_response(status: int = 200) -> MagicMock:
    """Return a MagicMock that passes as an aiohttp.ClientResponse."""
    response = MagicMock(spec=aiohttp.ClientResponse)
    response.status = status
    return response


def _make_mock_http_client(response: MagicMock | None = None) -> MagicMock:
    """Return a mock HTTPClientManager whose request() is an AsyncMock."""
    mock = MagicMock()
    mock.request = AsyncMock(return_value=response or _make_mock_response())
    return mock


class TestTracedHttpClientUsesSharedPool:
    """TracedHttpClient must delegate requests to HTTPClientManager, not httpx."""

    @pytest.mark.asyncio
    async def test_get_calls_http_client_manager(self):
        mock_response = _make_mock_response(200)
        mock_pool = _make_mock_http_client(mock_response)

        client = TracedHttpClient(http_client=mock_pool)
        result = await client.get("http://10.0.0.1/api/status")

        mock_pool.request.assert_awaited_once()
        call_args = mock_pool.request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "http://10.0.0.1/api/status"
        assert result is mock_response

    @pytest.mark.asyncio
    async def test_post_calls_http_client_manager(self):
        mock_pool = _make_mock_http_client()

        client = TracedHttpClient(http_client=mock_pool)
        await client.post("http://10.0.0.2/api/infer", json={"prompt": "hello"})

        mock_pool.request.assert_awaited_once()
        call_args = mock_pool.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "http://10.0.0.2/api/infer"
        assert call_args[1].get("json") == {"prompt": "hello"}

    @pytest.mark.asyncio
    async def test_put_calls_http_client_manager(self):
        mock_pool = _make_mock_http_client()

        client = TracedHttpClient(http_client=mock_pool)
        await client.put("http://10.0.0.3/resource/1", json={"key": "val"})

        mock_pool.request.assert_awaited_once()
        assert mock_pool.request.call_args[0][0] == "PUT"

    @pytest.mark.asyncio
    async def test_patch_calls_http_client_manager(self):
        mock_pool = _make_mock_http_client()

        client = TracedHttpClient(http_client=mock_pool)
        await client.patch("http://10.0.0.3/resource/1", json={"key": "updated"})

        mock_pool.request.assert_awaited_once()
        assert mock_pool.request.call_args[0][0] == "PATCH"

    @pytest.mark.asyncio
    async def test_delete_calls_http_client_manager(self):
        mock_pool = _make_mock_http_client()

        client = TracedHttpClient(http_client=mock_pool)
        await client.delete("http://10.0.0.4/resource/1")

        mock_pool.request.assert_awaited_once()
        assert mock_pool.request.call_args[0][0] == "DELETE"

    @pytest.mark.asyncio
    async def test_no_httpx_client_created(self):
        """Confirm httpx.AsyncClient is never instantiated during a request."""
        mock_pool = _make_mock_http_client()

        with patch("httpx.AsyncClient") as mock_httpx:
            client = TracedHttpClient(http_client=mock_pool)
            await client.get("http://10.0.0.1/api/status")

        mock_httpx.assert_not_called()

    @pytest.mark.asyncio
    async def test_context_manager_returns_self(self):
        mock_pool = _make_mock_http_client()
        client = TracedHttpClient(http_client=mock_pool)
        async with client as c:
            assert c is client

    @pytest.mark.asyncio
    async def test_default_timeout_injected_when_absent(self):
        """When caller supplies no timeout, the default is forwarded to the pool."""
        mock_pool = _make_mock_http_client()
        client = TracedHttpClient(timeout=15.0, http_client=mock_pool)
        await client.get("http://10.0.0.1/api/status")

        kwargs = mock_pool.request.call_args[1]
        assert "timeout" in kwargs
        assert isinstance(kwargs["timeout"], aiohttp.ClientTimeout)
        assert kwargs["timeout"].total == 15.0

    @pytest.mark.asyncio
    async def test_caller_provided_timeout_is_not_overridden(self):
        """When caller supplies a timeout, it must be forwarded unchanged."""
        mock_pool = _make_mock_http_client()
        custom_timeout = aiohttp.ClientTimeout(total=99)
        client = TracedHttpClient(http_client=mock_pool)
        await client.get("http://10.0.0.1/api/status", timeout=custom_timeout)

        kwargs = mock_pool.request.call_args[1]
        assert kwargs["timeout"] is custom_timeout

    @pytest.mark.asyncio
    async def test_exception_from_pool_propagates(self):
        mock_pool = MagicMock()
        mock_pool.request = AsyncMock(side_effect=aiohttp.ClientConnectionError("down"))

        client = TracedHttpClient(http_client=mock_pool)
        with pytest.raises(aiohttp.ClientConnectionError):
            await client.get("http://10.0.0.1/api/status")


class TestTracedHttpClientServiceMapping:
    """_get_target_service maps known IPs to service names."""

    @pytest.mark.asyncio
    async def test_unknown_ip_returns_unknown_service(self):
        mock_pool = _make_mock_http_client()
        client = TracedHttpClient(http_client=mock_pool)
        assert client._get_target_service("http://192.168.99.99/x") == "unknown-service"


class TestConvenienceFunctions:
    """Module-level traced_get / traced_post / traced_put / traced_delete helpers."""

    @pytest.mark.asyncio
    async def test_traced_get_delegates_to_pool(self):
        mock_pool = _make_mock_http_client()
        with patch("utils.traced_http_client.get_http_client", return_value=mock_pool):
            await traced_get("http://10.0.0.1/api/x")
        mock_pool.request.assert_awaited_once()
        assert mock_pool.request.call_args[0][0] == "GET"

    @pytest.mark.asyncio
    async def test_traced_post_delegates_to_pool(self):
        mock_pool = _make_mock_http_client()
        with patch("utils.traced_http_client.get_http_client", return_value=mock_pool):
            await traced_post("http://10.0.0.1/api/x", json={"a": 1})
        mock_pool.request.assert_awaited_once()
        assert mock_pool.request.call_args[0][0] == "POST"

    @pytest.mark.asyncio
    async def test_traced_put_delegates_to_pool(self):
        mock_pool = _make_mock_http_client()
        with patch("utils.traced_http_client.get_http_client", return_value=mock_pool):
            await traced_put("http://10.0.0.1/api/x")
        mock_pool.request.assert_awaited_once()
        assert mock_pool.request.call_args[0][0] == "PUT"

    @pytest.mark.asyncio
    async def test_traced_delete_delegates_to_pool(self):
        mock_pool = _make_mock_http_client()
        with patch("utils.traced_http_client.get_http_client", return_value=mock_pool):
            await traced_delete("http://10.0.0.1/api/x")
        mock_pool.request.assert_awaited_once()
        assert mock_pool.request.call_args[0][0] == "DELETE"

    @pytest.mark.asyncio
    async def test_traced_http_client_context_manager(self):
        mock_pool = _make_mock_http_client()
        with patch("utils.traced_http_client.get_http_client", return_value=mock_pool):
            async with traced_http_client() as client:
                assert isinstance(client, TracedHttpClient)
                await client.get("http://10.0.0.1/api/x")
        mock_pool.request.assert_awaited_once()
