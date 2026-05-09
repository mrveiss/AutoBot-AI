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
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="AsyncSyncBridge",
        )
        self._thread.start()
        logger.debug("AsyncSyncBridge initialized — daemon loop thread started")

    def run_coro(self, coro) -> Any:
        """Submit coro to the bridge loop and block until it completes.

        Exceptions raised in the coro propagate to the caller.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    @classmethod
    def reset_for_tests(cls) -> None:
        """Test-only — tear down the singleton + thread for clean test state."""
        with cls._lock:
            if cls._instance is not None and cls._instance._loop.is_running():
                cls._instance._loop.call_soon_threadsafe(cls._instance._loop.stop)
                cls._instance._thread.join(timeout=2.0)
            cls._instance = None
