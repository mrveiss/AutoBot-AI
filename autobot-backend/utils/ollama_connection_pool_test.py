# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for OllamaConnectionPool session tracking (#12119).

acquire_connection() borrows the shared HTTPClientManager session via
tracked_session(), so an in-flight pooled request keeps the active-request
counter above zero and a concurrent pool resize defers recreation instead of
closing the session mid-request.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from autobot_shared.http_client import get_http_client
from utils.ollama_connection_pool import OllamaConnectionPool


class TestAcquireConnectionSessionTracking:
    async def test_acquire_connection_delegates_to_tracked_session(self):
        """acquire_connection() yields the shared session through tracked_session()
        so the active-request counter is incremented for the borrow's duration and
        restored afterwards (real singleton, only ``get_session`` patched)."""
        pool = OllamaConnectionPool()
        manager = get_http_client()
        sentinel = MagicMock(closed=False)
        baseline = manager._active_requests

        with patch.object(manager, "get_session", new=AsyncMock(return_value=sentinel)):
            async with pool.acquire_connection() as session:
                assert session is sentinel
                assert manager._active_requests == baseline + 1

        assert manager._active_requests == baseline, "counter must return to baseline after release"
