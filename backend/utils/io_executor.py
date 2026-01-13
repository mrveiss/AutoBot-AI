# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backend I/O Executor - Dedicated thread pools for non-blocking file operations.

Issue #718: Provides dedicated thread pools for backend I/O operations to prevent
blocking when the main asyncio thread pool is saturated by heavy operations
like ChromaDB indexing or codebase analytics.

Thread Pools:
- _LOG_IO_EXECUTOR: For log reading/writing operations (logs.py)
- _FILE_IO_EXECUTOR: For file browser operations (files.py, filesystem_mcp.py)

These pools ensure that user-facing operations (viewing logs, browsing files)
remain responsive even during heavy background processing.
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

# Type variable for generic return type
T = TypeVar("T")

# =============================================================================
# Log I/O Thread Pool
# =============================================================================
# Dedicated thread pool for log file operations to prevent blocking during
# heavy indexing when users want to view logs.
_LOG_IO_EXECUTOR: ThreadPoolExecutor | None = None
_LOG_IO_EXECUTOR_MAX_WORKERS = 2  # Log operations are typically sequential
_LOG_IO_EXECUTOR_LOCK = threading.Lock()


def _get_log_io_executor() -> ThreadPoolExecutor:
    """Get or create the dedicated log I/O thread pool (thread-safe)."""
    global _LOG_IO_EXECUTOR
    if _LOG_IO_EXECUTOR is None:
        with _LOG_IO_EXECUTOR_LOCK:
            # Double-check after acquiring lock
            if _LOG_IO_EXECUTOR is None:
                _LOG_IO_EXECUTOR = ThreadPoolExecutor(
                    max_workers=_LOG_IO_EXECUTOR_MAX_WORKERS,
                    thread_name_prefix="log_io_"
                )
                logger.info(
                    "Created dedicated log I/O thread pool (%d workers)",
                    _LOG_IO_EXECUTOR_MAX_WORKERS
                )
    return _LOG_IO_EXECUTOR


async def run_in_log_executor(func: Callable[..., T], *args: Any) -> T:
    """Run a function in the dedicated log I/O thread pool.

    Issue #718: Uses dedicated thread pool to prevent blocking when the main
    asyncio thread pool is saturated by indexing operations.

    Args:
        func: Function to run
        *args: Arguments to pass to the function

    Returns:
        Result of the function call
    """
    loop = asyncio.get_running_loop()
    executor = _get_log_io_executor()
    return await loop.run_in_executor(executor, func, *args)


# =============================================================================
# File Browser I/O Thread Pool
# =============================================================================
# Dedicated thread pool for file browser operations (listing, reading, etc.)
# to ensure file browsing remains responsive during heavy processing.
_FILE_IO_EXECUTOR: ThreadPoolExecutor | None = None
_FILE_IO_EXECUTOR_MAX_WORKERS = 4  # Higher for parallel file operations
_FILE_IO_EXECUTOR_LOCK = threading.Lock()


def _get_file_io_executor() -> ThreadPoolExecutor:
    """Get or create the dedicated file I/O thread pool (thread-safe)."""
    global _FILE_IO_EXECUTOR
    if _FILE_IO_EXECUTOR is None:
        with _FILE_IO_EXECUTOR_LOCK:
            # Double-check after acquiring lock
            if _FILE_IO_EXECUTOR is None:
                _FILE_IO_EXECUTOR = ThreadPoolExecutor(
                    max_workers=_FILE_IO_EXECUTOR_MAX_WORKERS,
                    thread_name_prefix="file_io_"
                )
                logger.info(
                    "Created dedicated file I/O thread pool (%d workers)",
                    _FILE_IO_EXECUTOR_MAX_WORKERS
                )
    return _FILE_IO_EXECUTOR


async def run_in_file_executor(func: Callable[..., T], *args: Any) -> T:
    """Run a function in the dedicated file I/O thread pool.

    Issue #718: Uses dedicated thread pool to prevent blocking when the main
    asyncio thread pool is saturated by indexing operations.

    Args:
        func: Function to run
        *args: Arguments to pass to the function

    Returns:
        Result of the function call
    """
    loop = asyncio.get_running_loop()
    executor = _get_file_io_executor()
    return await loop.run_in_executor(executor, func, *args)


# =============================================================================
# Cleanup
# =============================================================================
def shutdown_executors():
    """Shutdown all dedicated I/O executors.

    Should be called during application shutdown to cleanly terminate threads.
    """
    global _LOG_IO_EXECUTOR, _FILE_IO_EXECUTOR

    if _LOG_IO_EXECUTOR is not None:
        _LOG_IO_EXECUTOR.shutdown(wait=False)
        logger.info("Log I/O thread pool shutdown initiated")
        _LOG_IO_EXECUTOR = None

    if _FILE_IO_EXECUTOR is not None:
        _FILE_IO_EXECUTOR.shutdown(wait=False)
        logger.info("File I/O thread pool shutdown initiated")
        _FILE_IO_EXECUTOR = None
