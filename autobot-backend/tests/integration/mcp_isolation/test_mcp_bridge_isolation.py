# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for MCP bridge isolation (#4106).

Covers the five lifecycle concerns noted in the #4089 PR:
1. Worker process spawning and cleanup
2. Resource limit enforcement (CPU, memory, file descriptors)
3. Worker restart on crash
4. Circuit breaker behaviour on persistent failures
5. Graceful shutdown lifecycle

All tests mock ``asyncio.create_subprocess_exec`` so no real processes are
spawned, keeping every test well under the 2-second budget.
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
)
from services.mcp_isolation_config import BridgePolicy, IsolationMode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy(
    bridge: str = "filesystem_mcp",
    restart_max: int = 3,
    cpu_seconds: int = 10,
    memory_mb: int = 128,
    nofile: int = 64,
) -> BridgePolicy:
    """Return a fully-specified BridgePolicy for tests."""
    return BridgePolicy(
        bridge=bridge,
        mode=IsolationMode.SUBPROCESS,
        cpu_seconds=cpu_seconds,
        memory_mb=memory_mb,
        nofile=nofile,
        restart_max=restart_max,
    )


def _make_fake_proc(response_lines=None, returncode=None):
    """Return a mock asyncio subprocess.

    *response_lines* is a list of raw bytes to return from successive
    ``stdout.readline()`` calls.  When the list is exhausted the mock
    returns ``b""`` (simulating EOF).

    *returncode* sets the initial returncode; ``None`` means still alive.
    """
    if response_lines is None:
        ok = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"pong": True}}) + "\n"
        response_lines = [ok.encode("utf-8")]

    lines_iter = iter(response_lines)

    async def _readline():
        try:
            return next(lines_iter)
        except StopIteration:
            return b""

    proc = MagicMock()
    proc.returncode = returncode
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(side_effect=_readline)
    proc.wait = AsyncMock(return_value=0)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


def _success_line(req_id: int = 1, result=None) -> bytes:
    payload = {"jsonrpc": "2.0", "id": req_id, "result": result or {}}
    return (json.dumps(payload) + "\n").encode("utf-8")


def _error_line(req_id: int = 1, message: str = "bridge error") -> bytes:
    payload = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": message}}
    return (json.dumps(payload) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# 1. Worker process spawning and cleanup
# ---------------------------------------------------------------------------


class TestWorkerSpawnAndCleanup:
    """Integration: spawning a worker and cleaning it up."""

    @pytest.mark.asyncio
    async def test_start_spawns_subprocess_once(self):
        """start() calls create_subprocess_exec exactly once."""
        fake_proc = _make_fake_proc()
        spawn = AsyncMock(return_value=fake_proc)

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch("asyncio.create_subprocess_exec", new=spawn):
            await client.start()
            await client.start()  # second call must be a no-op

        spawn.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_passes_resource_env_vars(self):
        """start() injects CPU/mem/nofile limits into the worker environment."""
        policy = _make_policy(cpu_seconds=42, memory_mb=256, nofile=128)
        fake_proc = _make_fake_proc()
        spawn = AsyncMock(return_value=fake_proc)

        client = IsolatedBridgeClient("filesystem_mcp", policy)
        with patch("asyncio.create_subprocess_exec", new=spawn):
            await client.start()

        _args, kwargs = spawn.call_args
        env = kwargs.get("env", {})
        assert env.get("MCP_WORKER_CPU_SECONDS") == "42"
        assert env.get("MCP_WORKER_MEM_MB") == "256"
        assert env.get("MCP_WORKER_NOFILE") == "128"

    @pytest.mark.asyncio
    async def test_start_scrubs_env_to_allowlist(self):
        """start() strips env vars not on the _WORKER_ENV_ALLOW whitelist."""
        fake_proc = _make_fake_proc()
        spawn = AsyncMock(return_value=fake_proc)

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch.dict(os.environ, {"SECRET_KEY": "topsecret", "DB_PASSWORD": "hunter2"}):
            with patch("asyncio.create_subprocess_exec", new=spawn):
                await client.start()

        _args, kwargs = spawn.call_args
        env = kwargs.get("env", {})
        assert "SECRET_KEY" not in env
        assert "DB_PASSWORD" not in env

    @pytest.mark.asyncio
    async def test_stop_terminates_process(self):
        """stop() sends shutdown then terminates the worker process."""
        shutdown_resp = (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n").encode("utf-8")
        fake_proc = _make_fake_proc(response_lines=[shutdown_resp])

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)):
            await client.start()

        await client.stop()

        assert client._proc is None, "stop() must set _proc to None"
        fake_proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_kills_when_terminate_times_out(self):
        """stop() falls back to kill() when graceful shutdown stalls."""
        shutdown_resp = (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n").encode("utf-8")
        fake_proc = _make_fake_proc(response_lines=[shutdown_resp])

        # Simulate process that never exits after terminate
        async def _hang():
            await asyncio.sleep(60)

        fake_proc.wait = AsyncMock(side_effect=_hang)

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)):
            await client.start()

        # Patch asyncio.wait_for so the terminate timeout fires immediately
        orig_wait_for = asyncio.wait_for

        async def _mock_wait_for(coro, timeout=None):
            if timeout is not None and timeout <= 5.0:
                coro.close()
                raise asyncio.TimeoutError()
            return await orig_wait_for(coro, timeout=timeout)

        with patch("asyncio.wait_for", side_effect=_mock_wait_for):
            await client.stop()

        fake_proc.kill.assert_called_once()
        assert client._proc is None


# ---------------------------------------------------------------------------
# 2. Resource limit enforcement (CPU, memory, file descriptors)
# ---------------------------------------------------------------------------


class TestResourceLimitEnforcement:
    """Integration: resource limits passed through policy."""

    @pytest.mark.asyncio
    async def test_cpu_limit_propagated_to_env(self):
        """CPU seconds limit is written to MCP_WORKER_CPU_SECONDS in env."""
        policy = _make_policy(cpu_seconds=99)
        fake_proc = _make_fake_proc()
        spawn = AsyncMock(return_value=fake_proc)

        client = IsolatedBridgeClient("filesystem_mcp", policy)
        with patch("asyncio.create_subprocess_exec", new=spawn):
            await client.start()

        _, kwargs = spawn.call_args
        assert kwargs["env"]["MCP_WORKER_CPU_SECONDS"] == "99"

    @pytest.mark.asyncio
    async def test_memory_limit_propagated_to_env(self):
        """Memory MB limit is written to MCP_WORKER_MEM_MB in env."""
        policy = _make_policy(memory_mb=512)
        fake_proc = _make_fake_proc()
        spawn = AsyncMock(return_value=fake_proc)

        client = IsolatedBridgeClient("filesystem_mcp", policy)
        with patch("asyncio.create_subprocess_exec", new=spawn):
            await client.start()

        _, kwargs = spawn.call_args
        assert kwargs["env"]["MCP_WORKER_MEM_MB"] == "512"

    @pytest.mark.asyncio
    async def test_nofile_limit_propagated_to_env(self):
        """File descriptor limit is written to MCP_WORKER_NOFILE in env."""
        policy = _make_policy(nofile=32)
        fake_proc = _make_fake_proc()
        spawn = AsyncMock(return_value=fake_proc)

        client = IsolatedBridgeClient("filesystem_mcp", policy)
        with patch("asyncio.create_subprocess_exec", new=spawn):
            await client.start()

        _, kwargs = spawn.call_args
        assert kwargs["env"]["MCP_WORKER_NOFILE"] == "32"

    @pytest.mark.asyncio
    async def test_worker_spawned_in_new_session(self):
        """Worker is spawned with start_new_session=True for process isolation."""
        fake_proc = _make_fake_proc()
        spawn = AsyncMock(return_value=fake_proc)

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch("asyncio.create_subprocess_exec", new=spawn):
            await client.start()

        _, kwargs = spawn.call_args
        assert kwargs.get("start_new_session") is True


# ---------------------------------------------------------------------------
# 3. Worker restart on crash
# ---------------------------------------------------------------------------


class TestWorkerRestartOnCrash:
    """Integration: automatic restart when worker exits unexpectedly."""

    @pytest.mark.asyncio
    async def test_dead_worker_is_respawned_on_call(self):
        """call_tool() detects a dead worker and respawns before the RPC."""
        ok_resp = _success_line(result={"data": "hi"})
        fresh_proc = _make_fake_proc(response_lines=[ok_resp])
        spawn = AsyncMock(return_value=fresh_proc)

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        # Inject a dead (exited) process as the current worker
        dead_proc = MagicMock()
        dead_proc.returncode = 1
        client._proc = dead_proc

        with patch("asyncio.create_subprocess_exec", new=spawn):
            result = await client.call_tool(
                "read_file", {"path": "/tmp/x"}  # nosec B108 - test/controlled code uses tmpdir intentionally
            )

        assert spawn.await_count == 1, "Should have spawned exactly one new worker"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_restart_count_increments_on_crash(self):
        """_restart_count increments each time a dead worker is detected."""
        ok_resp = _success_line()
        fake_proc = _make_fake_proc(response_lines=[ok_resp])
        spawn = AsyncMock(return_value=fake_proc)

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy(restart_max=10))

        for _ in range(3):
            dead_proc = MagicMock()
            dead_proc.returncode = 1
            client._proc = dead_proc
            fresh = _make_fake_proc(response_lines=[_success_line()])
            with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fresh)):
                await client.call_tool("noop", {})

        assert client._restart_count == 3

    @pytest.mark.asyncio
    async def test_worker_bridge_name_consistent_after_restart(self):
        """After restart the bridge name in responses is unchanged."""
        fresh_proc = _make_fake_proc(response_lines=[_success_line(result={"val": 42})])
        client = IsolatedBridgeClient("browser_mcp", _make_policy(bridge="browser_mcp", restart_max=5))

        dead_proc = MagicMock()
        dead_proc.returncode = 2
        client._proc = dead_proc

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fresh_proc)):
            result = await client.call_tool("screenshot", {})

        assert result["bridge"] == "browser_mcp"


# ---------------------------------------------------------------------------
# 4. Circuit breaker on persistent failures
# ---------------------------------------------------------------------------


class TestCircuitBreakerOnPersistentFailures:
    """Integration: permanent failure after restart budget exhausted."""

    @pytest.mark.asyncio
    async def test_permanently_failed_flag_blocks_start(self):
        """start() raises RuntimeError immediately when permanently_failed=True."""
        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        client._permanently_failed = True

        with pytest.raises(RuntimeError, match="restart_max|exceeded"):
            await client.start()

    @pytest.mark.asyncio
    async def test_restart_budget_exhaustion_sets_permanently_failed(self):
        """Crashing beyond restart_max triggers permanent failure."""
        policy = _make_policy(restart_max=2)
        client = IsolatedBridgeClient("filesystem_mcp", policy)

        # Drive _ensure_alive() to exhaustion via dead workers
        for _ in range(policy.restart_max + 1):
            dead_proc = MagicMock()
            dead_proc.returncode = 1
            client._proc = dead_proc
            if client._restart_count <= policy.restart_max:
                fresh = _make_fake_proc(response_lines=[_success_line()])
                try:
                    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fresh)):
                        await client.call_tool("noop", {})
                except RuntimeError:
                    break  # budget exhausted — expected
            else:
                break

        assert client._permanently_failed is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_activated_on_timeout(self):
        """A worker timeout returns success=False (circuit breaker path)."""
        proc = MagicMock()
        proc.returncode = None
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()
        proc.kill = MagicMock()

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            with patch("asyncio.wait_for", new=AsyncMock(side_effect=asyncio.TimeoutError())):
                result = await client.call_tool("slow_tool", {}, timeout=0.01)

        assert result["success"] is False
        assert result["bridge"] == "filesystem_mcp"
        proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_circuit_breaker_activated_on_eof(self):
        """An EOF from the worker pipe returns success=False."""
        eof_proc = _make_fake_proc(response_lines=[b""])  # EOF immediately

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=eof_proc)):
            result = await client.call_tool(
                "read_file", {"path": "/tmp/z"}  # nosec B108 - test/controlled code uses tmpdir intentionally
            )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_jsonrpc_error_returns_failure(self):
        """A JSON-RPC error response activates the failure path."""
        err_proc = _make_fake_proc(response_lines=[_error_line(message="permission denied")])

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=err_proc)):
            result = await client.call_tool("restricted", {})

        assert result["success"] is False
        assert "permission denied" in result["result"]


# ---------------------------------------------------------------------------
# 5. Graceful shutdown lifecycle
# ---------------------------------------------------------------------------


class TestGracefulShutdownLifecycle:
    """Integration: registry-level shutdown of all managed workers."""

    @pytest.mark.asyncio
    async def test_registry_shutdown_all_stops_clients(self):
        """shutdown_all() calls stop() on every registered client."""
        reg = IsolatedBridgeRegistry()

        shutdown_resp = (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n").encode("utf-8")

        procs = [
            _make_fake_proc(response_lines=[shutdown_resp]),
            _make_fake_proc(response_lines=[shutdown_resp]),
        ]
        proc_iter = iter(procs)

        async def _spawn(*_args, **_kwargs):
            return next(proc_iter)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=_spawn)):
            c1 = await reg.get_or_create("filesystem_mcp")
            c2 = await reg.get_or_create("browser_mcp")
            await c1.start()
            await c2.start()

        await reg.shutdown_all()

        assert len(reg._clients) == 0, "shutdown_all() must clear the client registry"

    @pytest.mark.asyncio
    async def test_registry_shutdown_clears_client_map(self):
        """After shutdown_all() the registry returns new clients on next get_or_create."""
        reg = IsolatedBridgeRegistry()
        shutdown_resp = (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n").encode("utf-8")

        fake = _make_fake_proc(response_lines=[shutdown_resp])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake)):
            original = await reg.get_or_create("filesystem_mcp")
            await original.start()

        await reg.shutdown_all()

        fresh_fake = _make_fake_proc()
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fresh_fake)):
            second = await reg.get_or_create("filesystem_mcp")

        assert second is not original, "After shutdown, registry must create a fresh client"

    @pytest.mark.asyncio
    async def test_stop_on_already_stopped_client_is_noop(self):
        """Calling stop() on a client that was never started does not raise."""
        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        # _proc is None — must be safe to call stop()
        await client.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_health_check_returns_true_for_alive_worker(self):
        """health_check() returns True when worker responds with pong."""
        pong = (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"pong": True}}) + "\n").encode("utf-8")
        fake_proc = _make_fake_proc(response_lines=[pong])

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)):
            alive = await client.health_check()

        assert alive is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_for_dead_worker(self):
        """health_check() returns False when no pong field in response."""
        no_pong = (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n").encode("utf-8")
        fake_proc = _make_fake_proc(response_lines=[no_pong])

        client = IsolatedBridgeClient("filesystem_mcp", _make_policy())
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)):
            alive = await client.health_check()

        assert alive is False

    @pytest.mark.asyncio
    async def test_shutdown_tolerates_stop_exception(self):
        """shutdown_all() continues stopping remaining clients even if one raises."""
        reg = IsolatedBridgeRegistry()

        # Manually inject two clients, one of which will raise on stop()
        bad_client = MagicMock()
        bad_client.stop = AsyncMock(side_effect=RuntimeError("stop failed"))
        good_client = MagicMock()
        good_client.stop = AsyncMock()

        reg._clients = {"bad_bridge": bad_client, "good_bridge": good_client}

        # Should not propagate the exception
        await reg.shutdown_all()

        good_client.stop.assert_awaited_once()
        assert len(reg._clients) == 0
