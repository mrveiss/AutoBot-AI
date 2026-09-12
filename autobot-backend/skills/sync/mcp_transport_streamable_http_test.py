# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for StreamableHTTPTransport (#11542), split out of mcp_transport_test.py to stay under the 600-line cap."""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skills.sync.mcp_transport import StreamableHTTPTransport


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only (not trio)."""
    return "asyncio"


def _jsonrpc_ok(result: Any, req_id: int = 1) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _fake_http_client(response):
    """Build a mock pooled HTTP client whose ``tracked_request()`` returns *response*."""
    client = MagicMock()
    client.tracked_request = MagicMock(return_value=response)
    return client


def _fake_streamable_response(
    status: int, headers: Dict[str, str], json_body: Any = None, sse_lines: list | None = None
):
    """Build a mock aiohttp-style response for StreamableHTTPTransport."""
    resp = AsyncMock()
    resp.status = status
    resp.headers = headers
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    if json_body is not None:
        resp.json = AsyncMock(return_value=json_body)
    if sse_lines is not None:

        async def _content_iter():
            for line in sse_lines:
                yield line.encode("utf-8")

        resp.content = _content_iter()
    return resp


@pytest.mark.anyio
async def test_streamable_http_json_response():
    """A plain application/json response is buffered and returned as-is."""
    payload = _jsonrpc_ok({"tools": []})
    resp = _fake_streamable_response(200, {"Content-Type": "application/json"}, json_body=payload)
    client = _fake_http_client(resp)

    with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
        transport = StreamableHTTPTransport("http://mcp.example.com/mcp")
        await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        result = await transport.receive()

    assert result == payload


@pytest.mark.anyio
async def test_streamable_http_sse_response():
    """A text/event-stream response's first data: frame is parsed as the JSON-RPC result."""
    payload = _jsonrpc_ok({"tools": []})
    sse_lines = [f"data: {json.dumps(payload)}\n", "\n"]
    resp = _fake_streamable_response(200, {"Content-Type": "text/event-stream"}, sse_lines=sse_lines)
    client = _fake_http_client(resp)

    with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
        transport = StreamableHTTPTransport("http://mcp.example.com/mcp")
        await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        result = await transport.receive()

    assert result == payload


@pytest.mark.anyio
async def test_streamable_http_captures_and_echoes_session_id():
    """Mcp-Session-Id from the first response is sent as a header on the next request."""
    payload = _jsonrpc_ok({})
    resp = _fake_streamable_response(
        200, {"Content-Type": "application/json", "Mcp-Session-Id": "sess-123"}, json_body=payload
    )
    client = _fake_http_client(resp)

    with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
        transport = StreamableHTTPTransport("http://mcp.example.com/mcp")
        await transport.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        await transport.receive()

        await transport.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    assert transport._session_id == "sess-123"
    second_call_kwargs = client.tracked_request.call_args_list[1].kwargs
    assert second_call_kwargs["headers"]["Mcp-Session-Id"] == "sess-123"


@pytest.mark.anyio
async def test_streamable_http_close_deletes_session():
    """close() sends a DELETE carrying the session id when one was captured."""
    resp = _fake_streamable_response(200, {})
    client = _fake_http_client(resp)

    with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
        transport = StreamableHTTPTransport("http://mcp.example.com/mcp")
        transport._session_id = "sess-123"
        await transport.close()

    call = client.tracked_request.call_args_list[-1]
    assert call.args[0] == "DELETE"
    assert call.kwargs["headers"]["Mcp-Session-Id"] == "sess-123"
    assert transport._session_id is None


@pytest.mark.anyio
async def test_streamable_http_close_without_session_is_noop():
    """close() does nothing when no session id was ever captured."""
    client = MagicMock()
    client.tracked_request = MagicMock()

    with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
        transport = StreamableHTTPTransport("http://mcp.example.com/mcp")
        await transport.close()

    client.tracked_request.assert_not_called()


@pytest.mark.anyio
async def test_streamable_http_non_200_raises():
    """StreamableHTTPTransport raises ClientResponseError on unexpected non-200 status."""
    import aiohttp

    resp = _fake_streamable_response(500, {})
    resp.request_info = MagicMock()
    resp.history = []
    client = _fake_http_client(resp)

    with patch("skills.sync.mcp_transport.get_http_client", return_value=client):
        transport = StreamableHTTPTransport("http://mcp.example.com/mcp")
        with pytest.raises(aiohttp.ClientResponseError):
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
