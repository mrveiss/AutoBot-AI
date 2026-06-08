#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Standalone demo runner for ``intelligence.streaming_executor`` (#7127).

Run with:

    python3 autobot-backend/intelligence/demos/run_streaming_executor.py

Same pattern as ``run_intelligent_agent.py`` — sys.path bootstrap before
any project import, then drive the production class with mocks.
"""

# ----- sys.path bootstrap (must run first; do NOT add project imports above) -----
import sys
from pathlib import Path

from autobot_shared.logging_manager import get_logger

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parent.parent.parent  # autobot-backend/
_REPO_ROOT = _BACKEND.parent  # AutoBot-AI/  (for autobot_shared)
for _p in (_BACKEND, _REPO_ROOT):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)
# ---------------------------------------------------------------------------

import logging  # noqa: E402

from autobot_shared.async_compat import run_or_schedule
from constants.network_constants import NetworkConstants  # noqa: E402
from intelligence.streaming_executor import (  # noqa: E402
    ChunkType,
    StreamingCommandExecutor,
)
from tests.fixtures.mocks import (  # noqa: E402
    MockCommandValidator,
    MockLLMService,
)

logger = get_logger("intelligence.demos.run_streaming_executor")


async def _demo() -> None:
    """Drive ``StreamingCommandExecutor`` through sample commands using mocks."""
    llm = MockLLMService()
    validator = MockCommandValidator()
    executor = StreamingCommandExecutor(llm, validator)

    logger.info("=== Streaming Executor Test ===")

    test_commands = [
        ("echo 'Hello, World!'", "test echo command"),
        ("ls -la", "list current directory"),
        (
            f"ping -c 3 {NetworkConstants.PUBLIC_DNS_IP}",
            "test network connectivity",
        ),
        ("sleep 5", "test long-running command"),
    ]

    for command, goal in test_commands:
        logger.info("Testing: %s", command)
        logger.info("Goal: %s", goal)
        logger.info("-" * 50)

        chunk_count = 0
        async for chunk in executor.execute_with_streaming(command, goal, timeout=10):
            timestamp = chunk.timestamp.split("T")[1][:8]
            chunk_type = chunk.chunk_type.value.upper()
            logger.info("[%s] %s: %s", timestamp, chunk_type, chunk.content)
            chunk_count += 1
            if chunk.chunk_type == ChunkType.COMPLETE:
                break
            if chunk_count > 20:
                logger.info("... (limiting output for test)")
                break


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_or_schedule(_demo())
    return 0


if __name__ == "__main__":
    sys.exit(main())
