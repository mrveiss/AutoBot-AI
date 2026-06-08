#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Standalone demo runner for ``intelligence.intelligent_agent`` (#7127).

Run with:

    python3 autobot-backend/intelligence/demos/run_intelligent_agent.py

The bootstrap below MUST happen before any project import — that's the whole
point of moving the demo here. Replaces the broken ``__main__`` block in
``intelligent_agent.py`` whose sys.path setup ran after top-level imports
already failed.
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
from intelligence.intelligent_agent import IntelligentAgent  # noqa: E402
from intelligence.streaming_executor import ChunkType  # noqa: E402
from tests.fixtures.mocks import (  # noqa: E402
    MockCommandValidator,
    MockKnowledgeBase,
    MockLLMService,
    MockWorkerNode,
)

logger = get_logger("intelligence.demos.run_intelligent_agent")


async def _demo() -> None:
    """Drive ``IntelligentAgent`` through three sample goals using mocks."""
    llm = MockLLMService()
    kb = MockKnowledgeBase()
    wn = MockWorkerNode()
    cv = MockCommandValidator()

    agent = IntelligentAgent(llm, kb, wn, cv)
    init_result = await agent.initialize()

    logger.info("=== Initialization Result ===")
    logger.info("Status: %s", init_result.get("status", "unknown"))
    os_info = init_result.get("os_info") or {}
    logger.info("OS: %s", os_info.get("os_type", "unknown"))
    capabilities = init_result.get("capabilities") or {}
    logger.info("Capabilities: %s", capabilities.get("total_count", 0))

    test_goals = [
        "what is my ip address?",
        "list the files in current directory",
        "show system information",
    ]

    for goal in test_goals:
        logger.info("=== Testing Goal: %s ===", goal)
        async for chunk in agent.process_natural_language_goal(goal):
            timestamp = chunk.timestamp.split("T")[1][:8]
            chunk_type = chunk.chunk_type.value.upper()
            logger.info("[%s] %s: %s", timestamp, chunk_type, chunk.content)
            if chunk.chunk_type == ChunkType.COMPLETE:
                break


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_or_schedule(_demo())
    return 0


if __name__ == "__main__":
    sys.exit(main())
