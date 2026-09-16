# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the extra_headers threading added for #11542 (credential headers).

Split out of mcp_transport_test.py to stay under the 600-line cap.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skills.sync.mcp_client import MCPClient
from skills.sync.mcp_transport import (
    HTTPTransport,
    SSETransport,
    StreamableHTTPTransport,
    create_transport,
)


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only (not trio)."""
    return "asyncio"


def _fake_http_client(response):
    client = MagicMock()
    client.tracked_request = MagicMock(return_value=response)
    return client


def _ok_response():
    resp = AsyncMock()
    resp.status = 200
    resp.headers = {"Content-Type": "application/json"}
    resp.json = AsyncMock(return_value={"jsonrpc": "2.0", "id": 1, "result": {}})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


class TestCreateTransportThreadsExtraHeaders:
    def test_http_transport_receives_extra_headers(self):
        t = create_transport("http://example.com/mcp", extra_headers={"Authorization": "Bearer x"})
        assert t._extra_headers == {"Authorization": "Bearer x"}

    def test_streamable_http_transport_receives_extra_headers(self):
        t = create_transport("streamable-http://example.com/mcp", extra_headers={"X-Api-Key": "k"})
        assert t._extra_headers == {"X-Api-Key": "k"}

    def test_sse_transport_receives_extra_headers(self):
        t = create_transport("sse://example.com/mcp", extra_headers={"Authorization": "Bearer x"})
        assert t._extra_headers == {"Authorization": "Bearer x"}


class TestMCPClientThreadsExtraHeaders:
    def test_mcp_client_passes_extra_headers_to_transport(self):
        client = MCPClient("http://example.com/mcp", extra_headers={"Authorization": "Bearer x"})
        assert client._transport._extra_headers == {"Authorization": "Bearer x"}


class TestHTTPTransportExtraHeaders:
    @pytest.mark.anyio
    async def test_merges_extra_headers_into_request(self):
        client = _fake_http_client(_ok_response())
        with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
            transport = HTTPTransport("http://mcp.example.com", extra_headers={"Authorization": "Bearer tok"})
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        assert client.tracked_request.call_args.kwargs["headers"] == {"Authorization": "Bearer tok"}


class TestStreamableHTTPTransportExtraHeaders:
    @pytest.mark.anyio
    async def test_merges_extra_headers_with_accept(self):
        client = _fake_http_client(_ok_response())
        with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
            transport = StreamableHTTPTransport(
                "http://mcp.example.com/mcp", extra_headers={"Authorization": "Bearer tok"}
            )
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        headers = client.tracked_request.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer tok"
        assert "text/event-stream" in headers["Accept"]

    @pytest.mark.anyio
    async def test_close_includes_extra_headers(self):
        client = _fake_http_client(_ok_response())
        with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
            transport = StreamableHTTPTransport(
                "http://mcp.example.com/mcp", extra_headers={"Authorization": "Bearer tok"}
            )
            transport._session_id = "sess-1"
            await transport.close()

        headers = client.tracked_request.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer tok"
        assert headers["Mcp-Session-Id"] == "sess-1"


class TestSSETransportExtraHeaders:
    @pytest.mark.anyio
    async def test_read_sse_includes_extra_headers(self):
        transport = SSETransport("sse://example.com/mcp", extra_headers={"Authorization": "Bearer tok"})

        mock_session = MagicMock()
        mock_get_cm = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.content = _empty_async_iter()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_get_cm)
        transport._session = mock_session

        await transport._read_sse()

        assert mock_session.get.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"

    @pytest.mark.anyio
    async def test_send_includes_extra_headers(self):
        transport = SSETransport("sse://example.com/mcp", extra_headers={"Authorization": "Bearer tok"})

        mock_session = MagicMock()
        mock_post_cm = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=mock_post_cm)
        transport._session = mock_session

        await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        assert mock_session.post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"


async def _empty_async_iter():
    return
    yield  # pragma: no cover - makes this an async generator with zero items
