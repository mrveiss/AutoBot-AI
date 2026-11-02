# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Issue #1341: Subprocess timeout and watchdog configuration
# ---------------------------------------------------------------------------


def _bounded_seconds(name: str, raw: str, default: int, low: int, high: int) -> int:
    """Read a watchdog limit, clamping and logging rather than failing at import (#18057)."""
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid %s %r, using default %d", name, raw, default)
        return default
    bounded = max(low, min(value, high))
    if bounded != value:
        logger.warning("%s=%d is outside %d-%d, using %d", name, value, low, high, bounded)
    return bounded


# Issue #18057: env-backed, so a run reaching a limit is a config change, not a release.
# Read through ``config.misc``: top-level access raises on an empty ``*_timeout`` value.
_SUBPROCESS_HARD_TIMEOUT = _bounded_seconds(
    "AUTOBOT_INDEXING_HARD_TIMEOUT", config.misc.indexing_hard_timeout, 1800, 60, 86400
)
_SUBPROCESS_PROGRESS_TIMEOUT = _bounded_seconds(
    "AUTOBOT_INDEXING_PROGRESS_TIMEOUT", config.misc.indexing_progress_timeout, 300, 30, 14400
)
# An interval above the progress limit would check too rarely to enforce that limit.
_SUBPROCESS_WATCHDOG_INTERVAL = _bounded_seconds(
    "AUTOBOT_INDEXING_WATCHDOG_INTERVAL",
    config.misc.indexing_watchdog_interval,
    30,
    1,
    min(300, _SUBPROCESS_PROGRESS_TIMEOUT),
)

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
