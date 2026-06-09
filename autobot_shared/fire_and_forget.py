# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fire-and-forget async task utilities.

For observability/analytics writes that must never block the hot path.
Errors are swallowed at DEBUG level.
"""

import asyncio
import logging
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


def run_redis_write(coro: Coroutine[Any, Any, None], *, label: str) -> None:
    """Schedule *coro* as a fire-and-forget asyncio task.

    Swallows all exceptions from the coroutine at DEBUG level so observability
    writes never propagate to the caller.

    Args:
        coro: Coroutine to run (typically a Redis write).
        label: Identifies the call site in debug logs.
    """

    async def _wrapper() -> None:
        try:
            await coro
        except Exception as exc:
            logger.debug("%s: background write failed: %s", label, exc)

    try:
        asyncio.get_running_loop().create_task(_wrapper())
    except RuntimeError:
        logger.warning("%s: no running event loop — background write skipped", label)
        coro.close()  # Prevent "coroutine never awaited" warning
