# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ACP agent entry point (#14825).

Run as an ACP agent from any compatible client:

    python -m acp

The client spawns this as a sub-process and speaks JSON-RPC 2.0 over stdio.
Nothing may write to stdout except protocol traffic — logging goes to stderr.
"""

import asyncio
import sys

from acp.runner import autobot_turn_runner
from acp.server import AcpServer
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def _main() -> int:
    server = AcpServer(runner=autobot_turn_runner)
    logger.info("AutoBot ACP agent starting on stdio")
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("AutoBot ACP agent interrupted")
    logger.info("AutoBot ACP agent stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
