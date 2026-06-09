# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Entrypoint for an isolated MCP bridge worker subprocess (#3229).

Spawned by :mod:`services.mcp_isolated_runtime` with one positional argument:
the bridge module name (e.g. ``filesystem_mcp``).  Applies rlimits and then
serves a line-delimited JSON-RPC loop on stdin/stdout.

Protocol (one JSON object per line):

    -> {"jsonrpc": "2.0", "id": 1, "method": "call",
        "params": {"tool": "<name>", "arguments": {...}}}
    <- {"jsonrpc": "2.0", "id": 1, "result": {...}}
    <- {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "..."}}

Method ``ping`` returns ``{"pong": true}`` and is used for health checks.
Method ``shutdown`` closes the worker cleanly.

Bridge resolution strategy:
    The worker imports ``api.<bridge_module>`` and looks for a function named
    ``mcp_call_tool`` or, failing that, iterates FastAPI routes on the
    module-level ``router`` and calls the matching handler directly.  This
    keeps the existing in-process bridge code reusable without rewrites.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import resource
import sys
from typing import Any, Dict

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger("mcp_worker")

# When set to "1" the worker enforces run-scoped JWT on every ``call`` request.
# Workers spawned without JWT support can opt out by leaving this unset.
_JWT_ENFORCE = config.mcp_run_jwt_enforce == "1"

_JSONRPC = "2.0"


def _apply_rlimits() -> None:
    """Apply RLIMIT_CPU, RLIMIT_AS, RLIMIT_NOFILE from env (#3229)."""
    cpu = int(config.mcp_worker_cpu_seconds or 0)
    if cpu > 0:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    mem_mb = int(config.mcp_worker_mem_mb or 0)
    if mem_mb > 0:
        mem_bytes = mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    nofile = int(config.mcp_worker_nofile or 0)
    if nofile > 0:
        resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))
    # Prevent fork bombs — cap total user processes
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except (ValueError, OSError):
        pass


def _load_bridge(bridge_module: str) -> Any:
    """Import and return the bridge module object."""
    mod_path = f"api.{bridge_module}"
    logger.info("worker: importing %s", mod_path)
    return importlib.import_module(mod_path)


async def _invoke_tool(bridge: Any, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch *tool_name* on *bridge* module.

    Prefers a module-level ``mcp_call_tool(name, arguments)`` coroutine.
    Falls back to scanning ``bridge.router.routes`` for a POST route whose
    path ends in ``/mcp/<tool_name>`` and calling its endpoint directly.
    """
    if hasattr(bridge, "mcp_call_tool"):
        return await bridge.mcp_call_tool(tool_name, arguments)

    router = getattr(bridge, "router", None)
    if router is None:
        raise RuntimeError(f"bridge {bridge.__name__} exposes no router or mcp_call_tool")

    target_suffix = f"/mcp/{tool_name}"
    for route in router.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if "POST" in methods and path.endswith(target_suffix):
            endpoint = route.endpoint
            result = endpoint(arguments) if not asyncio.iscoroutinefunction(endpoint) else await endpoint(arguments)
            return result
    raise RuntimeError(f"tool {tool_name} not found on bridge {bridge.__name__}")


async def _validate_run_jwt_param(params: Dict[str, Any]) -> Dict[str, Any] | None:
    """Validate the ``run_jwt`` field in RPC params, returning claims or None.

    Returns ``None`` when JWT enforcement is disabled (``MCP_RUN_JWT_ENFORCE``
    is not ``"1"``).  Raises ``PermissionError`` with a descriptive message
    when enforcement is on but the token is absent, expired, or revoked.
    """
    if not _JWT_ENFORCE:
        return None

    token = params.get("run_jwt") or config.mcp_run_jwt
    if not token:
        raise PermissionError("run_jwt: no token provided and MCP_RUN_JWT is unset")

    # Import lazily — keeps the module importable even when the service layer
    # is not on PYTHONPATH (e.g. unit tests that mock validate_run_jwt).
    from services.run_jwt import validate_run_jwt

    try:
        return await validate_run_jwt(token)
    except JWTExpiredError as exc:
        raise PermissionError(f"run_jwt: token expired — {exc}") from exc
    except JWTDecodeError as exc:
        raise PermissionError(f"run_jwt: invalid token — {exc}") from exc


async def _handle_request(bridge: Any, req: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single JSON-RPC request object."""
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    if method == "ping":
        return {"jsonrpc": _JSONRPC, "id": req_id, "result": {"pong": True}}
    if method == "shutdown":
        return {"jsonrpc": _JSONRPC, "id": req_id, "result": {"shutdown": True}}
    if method != "call":
        return {
            "jsonrpc": _JSONRPC,
            "id": req_id,
            "error": {"code": -32601, "message": f"unknown method {method}"},
        }

    try:
        await _validate_run_jwt_param(params)
    except PermissionError as exc:
        logger.warning("worker: JWT auth rejected: %s", exc)
        return {
            "jsonrpc": _JSONRPC,
            "id": req_id,
            "error": {"code": -32001, "message": str(exc)},
        }

    tool = params.get("tool")
    args = params.get("arguments") or {}
    try:
        result = await _invoke_tool(bridge, tool, args)
        return {"jsonrpc": _JSONRPC, "id": req_id, "result": result}
    except Exception as exc:  # surface to parent via RPC error
        logger.exception("worker: tool %s raised", tool)
        return {
            "jsonrpc": _JSONRPC,
            "id": req_id,
            "error": {"code": -32000, "message": str(exc)[:500]},
        }


async def _serve(bridge_module: str) -> None:
    """Stdio serve loop: read one JSON line, dispatch, write one JSON line."""
    bridge = _load_bridge(bridge_module)
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    try:
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    except Exception as exc:
        logger.error("worker: failed to connect stdin: %s", exc)
        raise

    try:
        writer_transport, writer_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
    except Exception as exc:
        logger.error("worker: failed to connect stdout: %s", exc)
        raise
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, loop)

    while True:
        line = await reader.readline()
        if not line:
            logger.info("worker: stdin closed, exiting")
            return
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            err = {
                "jsonrpc": _JSONRPC,
                "id": None,
                "error": {"code": -32700, "message": f"parse error: {exc}"},
            }
            writer.write((json.dumps(err) + "\n").encode("utf-8"))
            await writer.drain()
            continue

        resp = await _handle_request(bridge, req)
        writer.write((json.dumps(resp) + "\n").encode("utf-8"))
        await writer.drain()

        if req.get("method") == "shutdown":
            logger.info("worker: shutdown requested")
            return


def main() -> None:
    """CLI entrypoint: worker_entrypoint.py <bridge_module>."""
    logging.basicConfig(
        level=config.mcp_worker_log_level,
        format="%(asctime)s mcp_worker[%(process)d] %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    if len(sys.argv) != 2:
        print("usage: worker_entrypoint.py <bridge_module>", file=sys.stderr)
        sys.exit(2)
    _apply_rlimits()
    run_or_schedule(_serve(sys.argv[1]))


if __name__ == "__main__":
    main()
