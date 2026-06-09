# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
    async def test_call_tool_success(self) -> None:
        """Successful JSON-RPC call returns success=True and result payload."""
        resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": 1}}) + "\n"
        fake_proc = _make_fake_proc(resp.encode("utf-8"))

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=fake_proc),
        ):
            result = await client.call_tool(
                "read_file", {"path": "/tmp/x"}  # nosec B108 - test/controlled code uses tmpdir intentionally
            )
        assert result["success"] is True
        assert result["result"] == {"ok": 1}
        assert result["bridge"] == "filesystem_mcp"

    @pytest.mark.asyncio
    async def test_call_tool_bridge_error(self) -> None:
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
    async def test_worker_restart_on_crash(self) -> None:
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
    async def test_circuit_breaker_permanent_failure(self) -> None:
        """After restart_max crashes, further calls raise."""
        policy = _make_policy()
        client = IsolatedBridgeClient("filesystem_mcp", policy)
        client._restart_count = policy.restart_max + 1
        client._permanently_failed = True
        with pytest.raises(RuntimeError, match="crash loop|restart_max"):
            await client.start()

    @pytest.mark.asyncio
    async def test_timeout_kills_worker(self) -> None:
        """A readline timeout marks the worker dead and returns failure."""
        proc = MagicMock()
        proc.returncode = None
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()

        async def _never() -> None:
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


class TestConcurrentRequestIds:
    """Concurrency tests ensuring unique JSON-RPC request IDs (#4105).

    The existing tests mock subprocess communication but run calls serially,
    so they cannot catch race conditions in `_next_id()`.  These tests run
    N >= 100 concurrent coroutines via ``asyncio.gather`` and assert that
    every assigned request ID is unique.
    """

    _N = 100  # stress level — must be at least 100 per issue spec

    # ------------------------------------------------------------------
    # Helper: build a fake proc whose readline captures the request line
    # written by _raw_request so we can inspect the JSON-RPC id field.
    # ------------------------------------------------------------------

    def _make_capturing_proc(self, captured_ids: list) -> MagicMock:
        """Return a fake proc that records the JSON-RPC id from each write.

        ``stdin.write`` receives the encoded JSON line; we decode it and
        store the ``id`` field in *captured_ids* so the test can assert
        uniqueness after all coroutines complete.

        ``stdout.readline`` returns a generic success response each call.
        """
        proc = MagicMock()
        proc.returncode = None
        proc.stdin = MagicMock()
        proc.stdin.drain = AsyncMock()

        def _capture_write(data: bytes) -> None:
            msg = json.loads(data.decode("utf-8").strip())
            captured_ids.append(msg["id"])

        proc.stdin.write = MagicMock(side_effect=_capture_write)

        # readline returns a unique success payload on every call so
        # _raw_request can parse it without crashing.
        async def _readline():
            return (json.dumps({"jsonrpc": "2.0", "id": 0, "result": {"pong": True}}) + "\n").encode("utf-8")

        proc.stdout = MagicMock()
        proc.stdout.readline = AsyncMock(side_effect=_readline)
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        return proc

    # ------------------------------------------------------------------
    # Test 1 — _next_id() called concurrently without the outer lock
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_next_id_uniqueness_direct(self) -> None:
        """N concurrent _next_id() calls each return a distinct integer.

        ``_next_id`` does a simple ``self._req_id += 1`` with no explicit
        mutex.  Under CPython the GIL makes the increment atomic for pure
        integer add, but this test documents and enforces the guarantee so
        future refactors (e.g. moving to a non-GIL build) cannot regress.
        """
        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        ids = await asyncio.gather(*[client._next_id() for _ in range(self._N)])
        assert len(ids) == self._N
        assert len(set(ids)) == self._N, (
            f"Collision detected: {self._N} calls produced only " f"{len(set(ids))} unique IDs"
        )

    # ------------------------------------------------------------------
    # Test 2 — concurrent call_tool() calls embed unique ids in requests
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_call_tool_unique_request_ids(self) -> None:
        """N concurrent call_tool() invocations send N unique JSON-RPC ids.

        The asyncio.Lock inside IsolatedBridgeClient serialises access to
        the subprocess, so calls queue up naturally.  This test verifies
        that each queued request receives a distinct ``id`` in the JSON-RPC
        message actually written to stdin — i.e. no two requests share an id
        that would cause response routing to fail.
        """
        captured_ids: list = []
        fake_proc = self._make_capturing_proc(captured_ids)

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=fake_proc),
        ):
            await asyncio.gather(
                *[
                    client.call_tool("read_file", {"path": f"/tmp/f{i}"}) for i in range(self._N)
                ]  # nosec B108 - test/controlled code uses tmpdir intentionally
            )

        # Filter out the "shutdown" or "ping" requests emitted by _ensure_alive
        # (those also get ids but belong to internal housekeeping, not tool calls).
        # We only need to verify the tool call ids — captured_ids contains ALL
        # requests; uniqueness must still hold across the entire set.
        assert len(captured_ids) >= self._N, f"Expected at least {self._N} captured ids, got {len(captured_ids)}"
        assert len(captured_ids) == len(set(captured_ids)), (
            f"Request ID collision detected in {len(captured_ids)} requests: "
            f"duplicates = {[x for x in captured_ids if captured_ids.count(x) > 1]}"
        )

    # ------------------------------------------------------------------
    # Test 3 — mixed concurrent call_tool + health_check unique ids
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_mixed_concurrent_call_tool_and_health_check(self) -> None:
        """Concurrent call_tool() and health_check() share the same id counter.

        Both methods acquire the same asyncio.Lock and call _raw_request,
        which invokes _next_id().  This test ensures the counter advances
        monotonically across both call paths so ids never collide even when
        the two call types are interleaved under concurrent load.
        """
        captured_ids: list = []
        fake_proc = self._make_capturing_proc(captured_ids)

        half = self._N // 2
        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=fake_proc),
        ):
            tool_coros = [
                client.call_tool("list_dir", {"path": f"/tmp/{i}"})
                for i in range(half)  # nosec B108 - test/controlled code uses tmpdir intentionally
            ]
            health_coros = [client.health_check() for _ in range(half)]
            await asyncio.gather(*tool_coros, *health_coros)

        assert len(captured_ids) >= self._N, f"Expected at least {self._N} captured ids, got {len(captured_ids)}"
        assert len(captured_ids) == len(set(captured_ids)), (
            f"Request ID collision between call_tool and health_check: "
            f"duplicates = {[x for x in captured_ids if captured_ids.count(x) > 1]}"
        )


class TestIsolatedBridgeRegistry:
    """Registry mode routing."""

    @pytest.mark.asyncio
    async def test_inprocess_bridge_returns_none(self) -> None:
        """Registry returns None for bridges with INPROCESS mode."""
        reg = IsolatedBridgeRegistry()
        with patch.dict(os.environ, {}, clear=True):
            client = await reg.get_or_create("knowledge_mcp")
        assert client is None

    @pytest.mark.asyncio
    async def test_subprocess_bridge_creates_client(self) -> None:
        """Registry creates a cached client for SUBPROCESS bridges."""
        reg = IsolatedBridgeRegistry()
        with patch.dict(os.environ, {}, clear=True):
            c1 = await reg.get_or_create("filesystem_mcp")
            c2 = await reg.get_or_create("filesystem_mcp")
        assert c1 is not None
        assert c1 is c2

    def test_singleton_instance(self) -> None:
        """get_isolated_registry returns the same object."""
        assert get_isolated_registry() is get_isolated_registry()
