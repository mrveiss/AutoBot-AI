# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for MCP transport layer and MCPClient (Issue #2133)."""

import asyncio
import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skills.sync.mcp_client import MCPClient, MCPError, ResourceSubscription
from skills.sync.mcp_transport import (
    HTTPTransport,
    MCPTransport,
    SSETransport,
    StdioTransport,
    create_transport,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only (not trio)."""
    return "asyncio"


def _jsonrpc_ok(result: Any, req_id: int = 1) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_err(code: int, message: str, req_id: int = 1) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# create_transport factory
# ---------------------------------------------------------------------------


def test_create_transport_stdio():
    t = create_transport("stdio://npx server")
    assert isinstance(t, StdioTransport)


def test_create_transport_sse():
    t = create_transport("sse://example.com/mcp")
    assert isinstance(t, SSETransport)


def test_create_transport_http():
    t = create_transport("http://example.com/mcp")
    assert isinstance(t, HTTPTransport)


def test_create_transport_https():
    t = create_transport("https://example.com/mcp")
    assert isinstance(t, HTTPTransport)


# ---------------------------------------------------------------------------
# HTTPTransport
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_http_transport_send_receive():
    """HTTPTransport POSTs to /rpc and returns buffered JSON response."""
    payload = _jsonrpc_ok({"tools": []})

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=payload)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        transport = HTTPTransport("http://mcp.example.com")
        await transport.connect()
        await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        result = await transport.receive()

    assert result == payload


@pytest.mark.anyio
async def test_http_transport_receive_without_send_raises():
    """HTTPTransport.receive() before send() raises RuntimeError."""
    transport = HTTPTransport("http://mcp.example.com")
    with pytest.raises(RuntimeError, match="receive\\(\\) called before send\\(\\)"):
        await transport.receive()


@pytest.mark.anyio
async def test_http_transport_non_200_raises():
    """HTTPTransport raises ClientResponseError on non-200 responses."""
    import aiohttp

    mock_resp = MagicMock()
    mock_resp.status = 500
    mock_resp.request_info = MagicMock()
    mock_resp.history = []
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        transport = HTTPTransport("http://mcp.example.com")
        with pytest.raises(aiohttp.ClientResponseError):
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})


# ---------------------------------------------------------------------------
# StdioTransport
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stdio_transport_send_receive():
    """StdioTransport writes JSON to stdin and reads JSON from stdout."""
    response = json.dumps(_jsonrpc_ok({"tools": []})) + "\n"

    mock_proc = MagicMock()
    mock_proc.pid = 12345
    mock_proc.stdin = AsyncMock()
    mock_proc.stdin.write = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.readline = AsyncMock(return_value=response.encode("utf-8"))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        transport = StdioTransport("npx fake-mcp-server")
        await transport.connect()
        await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        result = await transport.receive()

    assert result["result"]["tools"] == []


@pytest.mark.anyio
async def test_stdio_transport_send_without_connect_raises():
    """StdioTransport.send() without connect() raises RuntimeError."""
    transport = StdioTransport("npx fake-server")
    with pytest.raises(RuntimeError, match="not connected"):
        await transport.send({"method": "tools/list"})


@pytest.mark.anyio
async def test_stdio_transport_receive_timeout():
    """StdioTransport.receive() raises TimeoutError when subprocess is slow."""
    mock_proc = MagicMock()
    mock_proc.pid = 99
    mock_proc.stdin = AsyncMock()
    mock_proc.stdout = AsyncMock()

    async def _slow_readline():
        await asyncio.sleep(10)
        return b""

    mock_proc.stdout.readline = _slow_readline

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        transport = StdioTransport("npx fake-server", timeout=0.05)
        await transport.connect()
        await transport.send({"method": "tools/list"})
        with pytest.raises(TimeoutError):
            await transport.receive()


@pytest.mark.anyio
async def test_stdio_transport_eof_raises():
    """StdioTransport.receive() raises EOFError when subprocess closes stdout."""
    mock_proc = MagicMock()
    mock_proc.pid = 99
    mock_proc.stdin = AsyncMock()
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.readline = AsyncMock(return_value=b"")

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        transport = StdioTransport("npx fake-server")
        await transport.connect()
        await transport.send({"method": "tools/list"})
        with pytest.raises(EOFError):
            await transport.receive()


# ---------------------------------------------------------------------------
# SSETransport
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sse_transport_url_rewrite():
    """SSETransport rewrites sse:// scheme to https://."""
    t = SSETransport("sse://example.com/mcp")
    assert t._base_url == "https://example.com/mcp"


@pytest.mark.anyio
async def test_sse_transport_receive_queued_event():
    """SSETransport delivers SSE data events via the internal queue."""
    notification = _jsonrpc_ok({"tools": []})
    sse_line = f"data: {json.dumps(notification)}\n\n".encode("utf-8")

    # Fake SSE stream that yields one event then stops
    async def _fake_iter():
        yield sse_line.decode()

    transport = SSETransport("sse://example.com/mcp", timeout=1.0)
    # Directly push to queue instead of mocking the full HTTP stack
    await transport._queue.put(notification)

    result = await transport.receive()
    assert result == notification


@pytest.mark.anyio
async def test_sse_transport_receive_timeout():
    """SSETransport.receive() raises TimeoutError when queue is empty."""
    transport = SSETransport("sse://example.com/mcp", timeout=0.05)
    with pytest.raises(TimeoutError):
        await transport.receive()


# ---------------------------------------------------------------------------
# MCPClient — tool operations
# ---------------------------------------------------------------------------


def _make_http_client(response_data: Dict[str, Any]) -> MCPClient:
    """Return an MCPClient whose HTTPTransport returns a fixed response."""
    client = MCPClient("http://mcp.example.com")
    transport = client._transport
    transport._pending = response_data
    return client


@pytest.mark.anyio
async def test_mcp_client_discover_tools():
    """MCPClient.discover_tools() parses MCPToolDefinition objects."""
    raw_tool = {
        "name": "read_file",
        "description": "Read a file",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    }
    resp = _jsonrpc_ok({"tools": [raw_tool]})

    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.send = AsyncMock()
    mock_transport.receive = AsyncMock(return_value=resp)

    client = MCPClient("http://mcp.example.com")
    client._transport = mock_transport

    tools = await client.discover_tools()
    assert len(tools) == 1
    assert tools[0].name == "read_file"


@pytest.mark.anyio
async def test_mcp_client_call_tool():
    """MCPClient.call_tool() sends tools/call and returns result."""
    resp = _jsonrpc_ok({"content": [{"type": "text", "text": "hello"}]})

    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.send = AsyncMock()
    mock_transport.receive = AsyncMock(return_value=resp)

    client = MCPClient("http://mcp.example.com")
    client._transport = mock_transport

    result = await client.call_tool("echo", {"message": "hello"})
    assert result["content"][0]["text"] == "hello"

    call_args = mock_transport.send.call_args[0][0]
    assert call_args["method"] == "tools/call"
    assert call_args["params"]["name"] == "echo"


@pytest.mark.anyio
async def test_mcp_client_raises_on_error_response():
    """MCPClient raises MCPError when the server returns a JSON-RPC error."""
    resp = _jsonrpc_err(code=-32601, message="Method not found")

    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.send = AsyncMock()
    mock_transport.receive = AsyncMock(return_value=resp)

    client = MCPClient("http://mcp.example.com")
    client._transport = mock_transport

    with pytest.raises(MCPError) as exc_info:
        await client.discover_tools()
    assert exc_info.value.code == -32601


# ---------------------------------------------------------------------------
# MCPClient — resource operations
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mcp_client_list_resources():
    """MCPClient.list_resources() parses MCPResourceDefinition objects."""
    raw_res = {
        "uri": "file:///tmp/data.json",
        "name": "data",
        "mimeType": "application/json",
    }
    resp = _jsonrpc_ok({"resources": [raw_res]})

    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.send = AsyncMock()
    mock_transport.receive = AsyncMock(return_value=resp)

    client = MCPClient("http://mcp.example.com")
    client._transport = mock_transport

    resources = await client.list_resources()
    assert len(resources) == 1
    assert resources[0].uri == "file:///tmp/data.json"


@pytest.mark.anyio
async def test_mcp_client_subscribe_resource():
    """MCPClient.subscribe_resource() sends subscribe and returns ResourceSubscription."""
    resp = _jsonrpc_ok(None)

    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.send = AsyncMock()
    mock_transport.receive = AsyncMock(return_value=resp)

    client = MCPClient("http://mcp.example.com")
    client._transport = mock_transport

    sub = await client.subscribe_resource("file:///tmp/data.json")
    assert isinstance(sub, ResourceSubscription)
    assert sub._uri == "file:///tmp/data.json"

    call_args = mock_transport.send.call_args[0][0]
    assert call_args["method"] == "resources/subscribe"
    assert call_args["params"]["uri"] == "file:///tmp/data.json"


@pytest.mark.anyio
async def test_resource_subscription_yields_notifications():
    """ResourceSubscription yields resource-update notifications from transport."""
    update = {
        "jsonrpc": "2.0",
        "method": "notifications/resources/updated",
        "params": {"uri": "file:///tmp/data.json"},
    }
    # First call yields the update; second call raises EOFError to stop iteration
    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.receive = AsyncMock(side_effect=[update, EOFError("closed")])

    sub = ResourceSubscription(uri="file:///tmp/data.json", transport=mock_transport, timeout=1.0)
    received = []
    async with sub as active_sub:
        async for notification in active_sub:
            received.append(notification)

    assert len(received) == 1
    assert received[0]["method"] == "notifications/resources/updated"


@pytest.mark.anyio
async def test_resource_subscription_ignores_unrelated_messages():
    """ResourceSubscription skips messages that are not resource updates."""
    unrelated = {"jsonrpc": "2.0", "method": "tools/list_changed", "params": {}}
    update = {
        "jsonrpc": "2.0",
        "method": "notifications/resources/updated",
        "params": {},
    }

    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.receive = AsyncMock(side_effect=[unrelated, update, EOFError("closed")])

    sub = ResourceSubscription(uri="file:///tmp/x", transport=mock_transport, timeout=1.0)
    received = []
    async with sub as active_sub:
        async for notification in active_sub:
            received.append(notification)

    assert len(received) == 1
    assert received[0]["method"] == "notifications/resources/updated"


# ---------------------------------------------------------------------------
# MCPClient — prompt operations
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mcp_client_list_prompts():
    """MCPClient.list_prompts() parses MCPPromptDefinition objects."""
    raw_prompt = {"name": "code_review", "description": "Review code", "arguments": []}
    resp = _jsonrpc_ok({"prompts": [raw_prompt]})

    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.send = AsyncMock()
    mock_transport.receive = AsyncMock(return_value=resp)

    client = MCPClient("http://mcp.example.com")
    client._transport = mock_transport

    prompts = await client.list_prompts()
    assert len(prompts) == 1
    assert prompts[0].name == "code_review"


@pytest.mark.anyio
async def test_mcp_client_get_prompt():
    """MCPClient.get_prompt() sends prompts/get with correct params."""
    resp = _jsonrpc_ok({"messages": []})

    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.send = AsyncMock()
    mock_transport.receive = AsyncMock(return_value=resp)

    client = MCPClient("http://mcp.example.com")
    client._transport = mock_transport

    await client.get_prompt("code_review", {"language": "python"})

    call_args = mock_transport.send.call_args[0][0]
    assert call_args["method"] == "prompts/get"
    assert call_args["params"]["name"] == "code_review"
    assert call_args["params"]["arguments"]["language"] == "python"


# ---------------------------------------------------------------------------
# MCPClient — context manager
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mcp_client_context_manager_calls_connect_close():
    """MCPClient async context manager calls connect() and close() on transport."""
    mock_transport = AsyncMock(spec=MCPTransport)
    mock_transport.connect = AsyncMock()
    mock_transport.close = AsyncMock()

    client = MCPClient("http://mcp.example.com")
    client._transport = mock_transport

    async with client:
        pass

    mock_transport.connect.assert_awaited_once()
    mock_transport.close.assert_awaited_once()
