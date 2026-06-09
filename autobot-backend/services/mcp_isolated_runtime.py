# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Isolated MCP bridge runtime (#3229)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager
from autobot_shared.ssot_config import config
from services.mcp_isolation_config import BridgePolicy, IsolationMode, policy_for

logger = get_logger(__name__)

_JSONRPC = "2.0"
_WORKER_SCRIPT = str(Path(__file__).parent / "mcp_bridge_workers" / "worker_entrypoint.py")

_WORKER_ENV_ALLOW = frozenset(
    {
        "PATH",
        "PYTHONPATH",
        "AUTOBOT_BASE_DIR",
        "LANG",
        "LC_ALL",
        "HOME",
        "USER",
        "TMPDIR",
    }
)


class IsolatedBridgeClient:
    """Client for a single bridge running as a subprocess worker."""

    def __init__(self, bridge: str, policy: BridgePolicy) -> None:
        """Initialise with bridge module name and policy."""
        self._bridge = bridge
        self._policy = policy
        self._proc = None
        self._lock = asyncio.Lock()
        self._req_id = 0
        self._restart_count = 0
        self._last_restart_ts = 0.0
        self._permanently_failed = False

    async def start(self) -> None:
        """Spawn the worker subprocess with scrubbed env."""
        if self._proc is not None and self._proc.returncode is None:
            return
        if self._permanently_failed:
            raise RuntimeError("bridge " + self._bridge + " exceeded restart_max")

        env = {k: v for k, v in os.environ.items() if k in _WORKER_ENV_ALLOW}
        env["MCP_WORKER_CPU_SECONDS"] = str(self._policy.cpu_seconds)
        env["MCP_WORKER_MEM_MB"] = str(self._policy.memory_mb)
        env["MCP_WORKER_NOFILE"] = str(self._policy.nofile)
        env["MCP_WORKER_LOG_LEVEL"] = config.log_level

        logger.info(
            "mcp_isolation: spawning worker bridge=%s cpu=%ss mem=%sMB nofile=%s",
            self._bridge,
            self._policy.cpu_seconds,
            self._policy.memory_mb,
            self._policy.nofile,
        )
        self._proc = await asyncio.create_subprocess_exec(
            sys.executable,
            _WORKER_SCRIPT,
            self._bridge,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        self._last_restart_ts = time.monotonic()
        metrics = get_metrics_manager()
        metrics.set_mcp_worker_uptime(self._bridge, 0.0)
        metrics.set_mcp_worker_permanently_failed(self._bridge, False)

    async def stop(self) -> None:
        """Send shutdown RPC then terminate if still alive."""
        if self._proc is None:
            return
        try:
            await self._raw_request({"method": "shutdown"}, timeout=2.0)
        except Exception:
            pass
        if self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None

    async def _ensure_alive(self) -> None:
        """Restart worker if it died; honour circuit breaker."""
        if self._proc is None or self._proc.returncode is not None:
            if self._proc is not None:
                logger.warning(
                    "mcp_isolation: bridge %s worker exited rc=%s, restarting",
                    self._bridge,
                    self._proc.returncode,
                )
                self._restart_count += 1
                metrics = get_metrics_manager()
                metrics.record_mcp_worker_restart(self._bridge, self._restart_count)

                # Record crash interval if we had a previous restart
                if self._last_restart_ts > 0:
                    crash_interval = time.monotonic() - self._last_restart_ts
                    metrics.record_mcp_worker_crash_interval(self._bridge, crash_interval)

                if self._restart_count > self._policy.restart_max:
                    self._permanently_failed = True
                    metrics.record_mcp_restart_budget_exhaustion(self._bridge)
                    metrics.set_mcp_worker_permanently_failed(self._bridge, True)
                    logger.error(
                        "mcp_isolation: bridge %s exceeded restart_max (%s), entering permanent failure",
                        self._bridge,
                        self._policy.restart_max,
                    )
                    raise RuntimeError("bridge " + self._bridge + " crash loop")
            await self.start()

    async def _next_id(self):
        """Return next monotonic request id (must be called with lock held)."""
        self._req_id += 1
        return self._req_id

    async def _raw_request(self, req, timeout=30.0):
        """Send one JSON-RPC request and await its response line."""
        assert self._proc is not None and self._proc.stdin is not None
        assert self._proc.stdout is not None
        req_full = {"jsonrpc": _JSONRPC, "id": await self._next_id(), **req}
        line = (json.dumps(req_full) + "\n").encode("utf-8")
        self._proc.stdin.write(line)
        await self._proc.stdin.drain()
        try:
            raw = await asyncio.wait_for(self._proc.stdout.readline(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError("bridge " + self._bridge + " did not respond within " + str(timeout) + "s")
        if not raw:
            raise EOFError("bridge " + self._bridge + " closed stdout")
        return json.loads(raw.decode("utf-8"))

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float = 30.0,
        run_jwt: str | None = None,
    ) -> Dict[str, Any]:
        """Invoke a tool on the isolated bridge.

        Args:
            tool_name: MCP tool to invoke.
            arguments: Tool arguments dict.
            timeout: Per-request timeout in seconds.
            run_jwt: Optional run-scoped JWT (minted by ``services.run_jwt``).
                When provided, it is forwarded in the RPC params so the worker
                can validate it before dispatching the tool.  Workers that have
                JWT enforcement enabled will reject calls with an invalid or
                missing token.
        """
        async with self._lock:
            await self._ensure_alive()
            params: Dict[str, Any] = {"tool": tool_name, "arguments": arguments}
            if run_jwt:
                params["run_jwt"] = run_jwt
            try:
                resp = await self._raw_request(
                    {"method": "call", "params": params},
                    timeout=timeout,
                )
            except (TimeoutError, EOFError) as exc:
                logger.error(
                    "mcp_isolation: bridge %s transport error: %s",
                    self._bridge,
                    exc,
                )
                metrics = get_metrics_manager()
                metrics.set_mcp_circuit_breaker_activated(self._bridge, True)
                if self._proc is not None and self._proc.returncode is None:
                    self._proc.kill()
                return {"success": False, "result": str(exc), "bridge": self._bridge}

            if "error" in resp:
                metrics = get_metrics_manager()
                metrics.set_mcp_circuit_breaker_activated(self._bridge, True)
                return {
                    "success": False,
                    "result": resp["error"].get("message", "bridge error"),
                    "bridge": self._bridge,
                }
            return {
                "success": True,
                "result": resp.get("result"),
                "bridge": self._bridge,
            }

    async def health_check(self) -> bool:
        """Return True if worker responds to a ping RPC within 2 seconds."""
        async with self._lock:
            try:
                await self._ensure_alive()
                resp = await self._raw_request({"method": "ping"}, timeout=2.0)
                return bool(resp.get("result", {}).get("pong"))
            except Exception as exc:
                logger.warning(
                    "mcp_isolation: bridge %s health check failed: %s",
                    self._bridge,
                    exc,
                )
                return False


class IsolatedBridgeRegistry:
    """Singleton registry of IsolatedBridgeClient per bridge name."""

    def __init__(self) -> None:
        """Initialise empty registry."""
        self._clients = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, bridge):
        """Return an isolated client if the bridge policy requires isolation."""
        policy = policy_for(bridge)
        if policy.mode == IsolationMode.INPROCESS:
            return None
        async with self._lock:
            client = self._clients.get(bridge)
            if client is None:
                client = IsolatedBridgeClient(bridge, policy)
                self._clients[bridge] = client
            return client

    async def shutdown_all(self) -> None:
        """Stop every managed worker; used on backend graceful shutdown."""
        async with self._lock:
            for client in self._clients.values():
                try:
                    await client.stop()
                except Exception as exc:
                    logger.warning("mcp_isolation: stop failed: %s", exc)
            self._clients.clear()


_registry = None


def get_isolated_registry():
    """Return the module-level IsolatedBridgeRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = IsolatedBridgeRegistry()
    return _registry
