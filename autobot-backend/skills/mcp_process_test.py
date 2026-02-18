# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for MCPProcessManager."""
import pytest
from skills.mcp_process import MCPProcessManager, get_mcp_manager

# Restrict anyio tests to asyncio backend only (trio not installed in this env)
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio backend only — trio is not installed."""
    return "asyncio"


# A minimal fake MCP server that responds to initialize and tools/list
FAKE_MCP_SERVER = """
import sys
import json

for line in sys.stdin:
    req = json.loads(line.strip())
    method = req.get("method")
    req_id = req.get("id", 0)
    if method == "initialize":
        resp = {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}
    elif method == "tools/list":
        resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": [{"name": "echo", "description": "Echo a message"}]}}
    elif method == "tools/call":
        args = req.get("params", {}).get("arguments", {})
        resp = {"jsonrpc": "2.0", "id": req_id, "result": args.get("message", "ok")}
    else:
        resp = {"jsonrpc": "2.0", "id": req_id, "error": {"message": f"unknown method {method}"}}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""


@pytest.mark.anyio
async def test_start_returns_pid():
    """MCPProcessManager.start() returns a positive PID for a valid script."""
    mgr = MCPProcessManager()
    try:
        pid = await mgr.start("test-skill", FAKE_MCP_SERVER)
        assert pid > 0
        assert mgr.is_running("test-skill")
    finally:
        await mgr.stop("test-skill")


@pytest.mark.anyio
async def test_list_tools_returns_tools():
    """list_tools() returns tool descriptors from the MCP server."""
    mgr = MCPProcessManager()
    try:
        await mgr.start("test-skill", FAKE_MCP_SERVER)
        tools = await mgr.list_tools("test-skill")
        assert len(tools) == 1
        assert tools[0]["name"] == "echo"
    finally:
        await mgr.stop("test-skill")


@pytest.mark.anyio
async def test_call_tool_returns_result():
    """call_tool() proxies arguments and returns the tool result."""
    mgr = MCPProcessManager()
    try:
        await mgr.start("test-skill", FAKE_MCP_SERVER)
        result = await mgr.call_tool("test-skill", "echo", {"message": "hello"})
        assert result == "hello"
    finally:
        await mgr.stop("test-skill")


@pytest.mark.anyio
async def test_stop_cleans_up():
    """stop() terminates the subprocess and marks it as not running."""
    mgr = MCPProcessManager()
    await mgr.start("test-skill", FAKE_MCP_SERVER)
    assert mgr.is_running("test-skill")
    await mgr.stop("test-skill")
    assert not mgr.is_running("test-skill")


@pytest.mark.anyio
async def test_invalid_script_raises():
    """A script that exits immediately causes start() to raise RuntimeError."""
    mgr = MCPProcessManager()
    bad_script = "import sys; sys.exit(1)"
    with pytest.raises(RuntimeError):
        await mgr.start("bad-skill", bad_script)


def test_get_mcp_manager_singleton():
    """get_mcp_manager() returns the same instance on repeated calls."""
    mgr1 = get_mcp_manager()
    mgr2 = get_mcp_manager()
    assert mgr1 is mgr2
