# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for IsolatedBridgeClient / IsolatedBridgeRegistry (#3229).

These tests exercise the JSON-RPC framing, circuit breaker, and policy
routing using mocked asyncio subprocesses.  End-to-end worker spawn is
verified via the integration test in tests/integration/mcp_isolation/.
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.mcp_isolated_runtime import (
    IsolatedBridgeClient,
    IsolatedBridgeRegistry,
    get_isolated_registry,
)
from services.mcp_isolation_config import BridgePolicy, IsolationMode


def _make_policy(bridge="filesystem_mcp"):
    """Return a minimal subprocess BridgePolicy."""
    return BridgePolicy(
        bridge=bridge,
        mode=IsolationMode.SUBPROCESS,
        cpu_seconds=10,
        memory_mb=128,
        nofile=64,
        restart_max=3,
    )


def _make_fake_proc(response_line):
    """Build a fake asyncio subprocess that replies with *response_line*."""
    proc = MagicMock()
    proc.returncode = None
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(return_value=response_line)
    proc.wait = AsyncMock(return_value=0)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


class TestIsolatedBridgeClient:
    """IsolatedBridgeClient behaviour with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """Successful JSON-RPC call returns success=True and result payload."""
        resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": 1}}) + "\n"
        fake_proc = _make_fake_proc(resp.encode("utf-8"))

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=fake_proc),
        ):
            result = await client.call_tool("read_file", {"path": "/tmp/x"})
        assert result["success"] is True
        assert result["result"] == {"ok": 1}
        assert result["bridge"] == "filesystem_mcp"

    @pytest.mark.asyncio
    async def test_call_tool_bridge_error(self):
        """JSON-RPC error response surfaces as success=False."""
        resp = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32000, "message": "boom"},
                }
            )
            + "\n"
        )
        fake_proc = _make_fake_proc(resp.encode("utf-8"))

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=fake_proc),
        ):
            result = await client.call_tool("bad", {})
        assert result["success"] is False
        assert "boom" in result["result"]

    @pytest.mark.asyncio
    async def test_worker_restart_on_crash(self):
        """If the worker exited, next call respawns it."""
        resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
        fake_proc = _make_fake_proc(resp.encode("utf-8"))
        spawn = AsyncMock(return_value=fake_proc)

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        # Simulate existing dead worker
        dead = MagicMock()
        dead.returncode = 1
        client._proc = dead

        with patch("asyncio.create_subprocess_exec", new=spawn):
            await client.call_tool("noop", {})
        assert spawn.await_count == 1
        assert client._restart_count == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_permanent_failure(self):
        """After restart_max crashes, further calls raise."""
        policy = _make_policy()
        client = IsolatedBridgeClient("filesystem_mcp", policy)
        client._restart_count = policy.restart_max + 1
        client._permanently_failed = True
        with pytest.raises(RuntimeError, match="crash loop|restart_max"):
            await client.start()

    @pytest.mark.asyncio
    async def test_timeout_kills_worker(self):
        """A readline timeout marks the worker dead and returns failure."""
        proc = MagicMock()
        proc.returncode = None
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()

        async def _never():
            await asyncio.sleep(10)

        proc.stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError())
        proc.kill = MagicMock()

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ):
            # Make wait_for raise TimeoutError directly
            with patch("asyncio.wait_for", new=AsyncMock(side_effect=asyncio.TimeoutError())):
                result = await client.call_tool("slow", {}, timeout=0.01)
        assert result["success"] is False
        proc.kill.assert_called_once()


class TestIsolatedBridgeRegistry:
    """Registry mode routing."""

    @pytest.mark.asyncio
    async def test_inprocess_bridge_returns_none(self):
        """Registry returns None for bridges with INPROCESS mode."""
        reg = IsolatedBridgeRegistry()
        with patch.dict(os.environ, {}, clear=True):
            client = await reg.get_or_create("knowledge_mcp")
        assert client is None

    @pytest.mark.asyncio
    async def test_subprocess_bridge_creates_client(self):
        """Registry creates a cached client for SUBPROCESS bridges."""
        reg = IsolatedBridgeRegistry()
        with patch.dict(os.environ, {}, clear=True):
            c1 = await reg.get_or_create("filesystem_mcp")
            c2 = await reg.get_or_create("filesystem_mcp")
        assert c1 is not None
        assert c1 is c2

    def test_singleton_instance(self):
        """get_isolated_registry returns the same object."""
        assert get_isolated_registry() is get_isolated_registry()
