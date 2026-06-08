# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dedicated thread pool for indexing operations.

Issue #2364: Extracted from scanner.py to isolate executor management.

The indexing task needs its own thread pool to avoid being starved by
concurrent analytics requests (duplicates, hardcodes, etc.) that also use
the default executor.  With 175k+ files, the default pool can be exhausted.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Issue #1341: Subprocess timeout and watchdog configuration
# ---------------------------------------------------------------------------
_SUBPROCESS_HARD_TIMEOUT = 1800  # 30 minutes max for entire subprocess
_SUBPROCESS_PROGRESS_TIMEOUT = 300  # 5 min without progress = stale
_SUBPROCESS_WATCHDOG_INTERVAL = 30  # Check progress every 30 seconds

# ---------------------------------------------------------------------------
# Dedicated Indexing Thread Pool (#2364: Prevent thread starvation on large repos)
# ---------------------------------------------------------------------------
_INDEXING_EXECUTOR: ThreadPoolExecutor | None = None
_INDEXING_EXECUTOR_MAX_WORKERS = 4  # Dedicated threads for indexing operations
_INDEXING_EXECUTOR_LOCK = threading.Lock()  # Issue #662: Thread-safe initialisation


def _get_indexing_executor() -> ThreadPoolExecutor:
    """Get or create the dedicated indexing thread pool (thread-safe)."""
    global _INDEXING_EXECUTOR
    if _INDEXING_EXECUTOR is None:
        with _INDEXING_EXECUTOR_LOCK:
            if _INDEXING_EXECUTOR is None:
                _INDEXING_EXECUTOR = ThreadPoolExecutor(
                    max_workers=_INDEXING_EXECUTOR_MAX_WORKERS,
                    thread_name_prefix="indexing_worker",
                )
                logger.info(
                    "Created dedicated indexing thread pool (%d workers)",
                    _INDEXING_EXECUTOR_MAX_WORKERS,
                )
    return _INDEXING_EXECUTOR


async def _run_in_indexing_thread(func, *args):
    """Run a function in the dedicated indexing thread pool.

    If no args are provided (e.g., when using a lambda), calls func directly.
    Otherwise, calls func(*args).
    """
    loop = asyncio.get_running_loop()
    executor = _get_indexing_executor()
    if args:
        return await loop.run_in_executor(executor, func, *args)
    else:
        return await loop.run_in_executor(executor, func)
