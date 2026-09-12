# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the guard_egress threading added for #11542 (outbound SSRF policy, #13625).

Split out of mcp_transport_test.py to stay under the 600-line cap.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.http_egress_guard import EgressBlockedError
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


class TestCreateTransportThreadsGuardEgress:
    def test_http_transport_receives_guard_egress(self):
        t = create_transport("http://example.com/mcp", guard_egress=False)
        assert t._guard_egress is False

    def test_streamable_http_transport_receives_guard_egress(self):
        t = create_transport("streamable-http://example.com/mcp", guard_egress=True)
        assert t._guard_egress is True

    def test_sse_transport_receives_guard_egress(self):
        t = create_transport("sse://example.com/mcp", guard_egress=False)
        assert t._guard_egress is False

    def test_default_is_none_unguarded(self):
        t = create_transport("http://example.com/mcp")
        assert t._guard_egress is None


class TestMCPClientThreadsGuardEgress:
    def test_mcp_client_passes_guard_egress_to_transport(self):
        client = MCPClient("http://example.com/mcp", guard_egress=True)
        assert client._transport._guard_egress is True

    def test_mcp_client_default_unguarded(self):
        client = MCPClient("http://example.com/mcp")
        assert client._transport._guard_egress is None


class TestHTTPTransportGuardEgress:
    @pytest.mark.anyio
    async def test_passes_guard_egress_kwarg_to_tracked_request(self):
        client = _fake_http_client(_ok_response())
        with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
            transport = HTTPTransport("http://mcp.example.com", guard_egress=False)
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        assert client.tracked_request.call_args.kwargs["guard_egress"] is False


class TestStreamableHTTPTransportGuardEgress:
    @pytest.mark.anyio
    async def test_send_passes_guard_egress_kwarg(self):
        client = _fake_http_client(_ok_response())
        with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
            transport = StreamableHTTPTransport("http://mcp.example.com/mcp", guard_egress=True)
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        assert client.tracked_request.call_args.kwargs["guard_egress"] is True

    @pytest.mark.anyio
    async def test_close_passes_guard_egress_kwarg(self):
        client = _fake_http_client(_ok_response())
        with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
            transport = StreamableHTTPTransport("http://mcp.example.com/mcp", guard_egress=False)
            transport._session_id = "sess-123"
            await transport.close()

        assert client.tracked_request.call_args.kwargs["guard_egress"] is False


class TestSSETransportGuardEgress:
    @pytest.mark.anyio
    async def test_connect_blocked_by_egress_policy(self):
        """A disallowed address raises EgressBlockedError before the session opens."""
        with patch("skills.sync.mcp_transport.is_public_url_async", AsyncMock(return_value=False)):
            transport = SSETransport("sse://internal.example.com/mcp", guard_egress=False)
            with pytest.raises(EgressBlockedError):
                await transport.connect()
        assert transport._session is None

    @pytest.mark.anyio
    async def test_connect_allowed_by_egress_policy(self):
        with patch("skills.sync.mcp_transport.is_public_url_async", AsyncMock(return_value=True)):
            transport = SSETransport("sse://public.example.com/mcp", guard_egress=False)
            await transport.connect()
        await transport.close()

    @pytest.mark.anyio
    async def test_default_guard_egress_none_skips_check(self):
        """guard_egress=None (default) never calls the egress policy at all."""
        with patch("skills.sync.mcp_transport.is_public_url_async", AsyncMock(return_value=False)) as mock_check:
            transport = SSETransport("sse://anything.example.com/mcp")
            await transport.connect()
        mock_check.assert_not_called()
        await transport.close()

    @pytest.mark.anyio
    async def test_send_blocked_by_egress_policy(self):
        with patch("skills.sync.mcp_transport.is_public_url_async", AsyncMock(return_value=True)):
            transport = SSETransport("sse://public.example.com/mcp", guard_egress=False)
            await transport.connect()

        with patch("skills.sync.mcp_transport.is_public_url_async", AsyncMock(return_value=False)):
            with pytest.raises(EgressBlockedError):
                await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        await transport.close()
