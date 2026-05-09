# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import os
import resource
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("mcp_worker")

_JSONRPC = "2.0"


def _apply_rlimits() -> None:
    """Apply RLIMIT_CPU, RLIMIT_AS, RLIMIT_NOFILE from env (#3229)."""
    cpu = int(os.environ.get("MCP_WORKER_CPU_SECONDS", "0") or 0)
    if cpu > 0:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    mem_mb = int(os.environ.get("MCP_WORKER_MEM_MB", "0") or 0)
    if mem_mb > 0:
        mem_bytes = mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    nofile = int(os.environ.get("MCP_WORKER_NOFILE", "0") or 0)
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
        level=os.environ.get("MCP_WORKER_LOG_LEVEL", "INFO"),
        format="%(asctime)s mcp_worker[%(process)d] %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    if len(sys.argv) != 2:
        print("usage: worker_entrypoint.py <bridge_module>", file=sys.stderr)
        sys.exit(2)
    _apply_rlimits()
    asyncio.run(_serve(sys.argv[1]))


if __name__ == "__main__":
    main()
