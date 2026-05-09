# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
AsyncSyncBridge — invoke async code from sync host contexts.

Singleton owning a daemon-thread event loop running forever. Sync callers
submit coroutines via run_coro(); the call blocks until the coroutine
completes (or raises). The daemon thread is auto-killed at process exit.

Plugin authors never touch this — only host runtimes (e.g., Celery
signal handlers) do.

Issue #6970 — extension-point hook dispatch sites.
"""

import asyncio
import logging
import threading
from collections.abc import Coroutine
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AsyncSyncBridge:
    """Singleton bridge for invoking async code from sync host contexts."""

    _instance: Optional["AsyncSyncBridge"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self) -> None:
        """Initialize the daemon-thread event loop.

        Invoked exactly once from __new__ while holding _lock. Do NOT add
        an __init__ method — it would re-run on every AsyncSyncBridge()
        call and reset _loop/_thread, breaking the singleton contract.
        """
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="AsyncSyncBridge",
        )
        self._thread.start()
        logger.debug("AsyncSyncBridge initialized — daemon loop thread started")

    def run_coro(
        self,
        coro: "Coroutine[Any, Any, Any]",
        timeout: Optional[float] = None,
    ) -> Any:
        """Submit coro to the bridge loop and block until it completes.

        Args:
            coro: A coroutine object (NOT a coroutine function — call it first).
            timeout: Optional seconds to wait. None blocks indefinitely.

        Returns:
            The coroutine's return value.

        Raises:
            Whatever the coroutine raises propagates synchronously.
            concurrent.futures.TimeoutError if timeout elapses.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    @classmethod
    def reset_for_tests(cls) -> None:
        """Test-only — tear down the singleton + thread for clean test state."""
        with cls._lock:
            if cls._instance is not None:
                inst = cls._instance
                # Use thread liveness, NOT loop.is_running(), because the latter
                # races during startup window between Thread.start() and the loop
                # entering run_forever's frame.
                if inst._thread.is_alive():
                    inst._loop.call_soon_threadsafe(inst._loop.stop)
                    inst._thread.join(timeout=2.0)
                # Close the loop to release selector file descriptors. Without
                # this, GC of the unclosed loop emits PytestUnraisableExceptionWarning
                # ("invalid file descriptor -1") from the kqueue/epoll cleanup.
                inst._loop.close()
            cls._instance = None
