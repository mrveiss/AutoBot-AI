# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot MCP Server entry point (Issue #5072).

Usage:
    # stdio transport (default — used by Claude Code / Cline):
    python -m mcp.autobot_mcp_main

    # HTTP transport (port 8200):
    python -m mcp.autobot_mcp_main --http

    # HTTP on custom host/port:
    python -m mcp.autobot_mcp_main --http --host 127.0.0.1 --port 9200
"""

import sys

from autobot_shared.async_compat import run_or_schedule
from mcp.autobot_server import AutoBotMCPServer


async def main() -> None:
    server = AutoBotMCPServer()
    if "--http" in sys.argv:
        host = "0.0.0.0"  # nosec B104 - intentional bind to all interfaces for service/test
        port = 8200
        args = sys.argv[1:]
        if "--host" in args:
            host = args[args.index("--host") + 1]
        if "--port" in args:
            port = int(args[args.index("--port") + 1])
        await server.serve_http(host, port)
    else:
        await server.serve_stdio()


if __name__ == "__main__":
    run_or_schedule(main())
