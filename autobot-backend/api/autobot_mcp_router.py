# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
FastAPI router for the AutoBot MCP Server HTTP transport (Issue #5072).

Exposes ``POST /api/mcp/tool`` so that HTTP MCP clients can reach the
AutoBotMCPServer without running a separate aiohttp process.

The router delegates every request to AutoBotMCPServer.handle_request(),
which handles auth, rate limiting, and tool dispatch internally.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from autobot_shared.logging_manager import get_logger
from mcp.autobot_server import AutoBotMCPServer

logger = get_logger(__name__)

router = APIRouter(tags=["mcp", "autobot-mcp"])

# Module-level server singleton (lazy-initialised on first request)
_server: AutoBotMCPServer | None = None


def _get_server() -> AutoBotMCPServer:
    global _server
    if _server is None:
        _server = AutoBotMCPServer()
    return _server


@router.post("/mcp/tool")
async def mcp_tool_call(request: Request) -> JSONResponse:
    """Dispatch an MCP tool call from an HTTP client.

    Expects a JSON-RPC 2.0 body::

        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "kb.search", "arguments": {"query": "..."}}
        }

    Auth: ``Authorization: Bearer <token>`` header required.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
        )

    method = body.get("method", "")
    params = body.get("params") or {}
    req_id = body.get("id")

    server = _get_server()
    response = await server.handle_request(method, params, token, req_id)

    status = 200
    if "error" in response:
        code = response["error"].get("code", -32000)
        if code == -32001:
            status = 401
        elif code == -32003:
            status = 403
        elif code == -32029:
            status = 429

    return JSONResponse(status_code=status, content=response)
