# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #12286: stack-trace / exception-detail must never reach the HTTP client.

CodeQL py/stack-trace-exposure flagged several handlers that returned
``str(exception)`` in the response body. These tests assert the fixed handlers:

  1. Return a generic, exception-free message to the client, and
  2. Still log the full exception detail server-side (no swallowed errors).
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# A distinctive marker that must never appear in a client-facing response body,
# standing in for internal paths / exception text a raw str(exc) would leak.
INTERNAL_MARKER = "INTERNAL-DETAIL-MARKER-at-var-log-autobot-line-42"


@pytest.mark.asyncio
async def test_delete_watch_folder_hides_exception_but_logs_it(caplog):
    """knowledge.delete_watch_folder: generic client message, full detail logged."""
    from api import knowledge
    from services.kb_folder_watcher import get_kb_folder_watcher

    # Patch the singleton the handler will resolve, so remove_watch_folder raises
    # with an exception carrying an internal marker.
    watcher = get_kb_folder_watcher()
    with patch.object(watcher, "remove_watch_folder", AsyncMock(side_effect=RuntimeError(INTERNAL_MARKER))):
        with caplog.at_level(logging.ERROR):
            result = await knowledge.delete_watch_folder(folder_id="folder-123")

    assert result["success"] is False
    # Client body leaks neither the exception message nor its class name.
    assert INTERNAL_MARKER not in result["message"]
    assert "RuntimeError" not in result["message"]
    assert result["message"] == "Failed to delete watch folder due to an internal error"
    # But the server still records the real detail.
    assert INTERNAL_MARKER in caplog.text


@pytest.mark.asyncio
async def test_historical_trends_hides_redis_error_but_logs_it(caplog):
    """analytics.get_historical_trends: Redis failure is logged, not exposed."""
    from api import analytics

    redis_conn = MagicMock()
    redis_conn.lrange = AsyncMock(side_effect=RuntimeError(INTERNAL_MARKER))

    with patch.object(analytics.analytics_controller, "detect_trends", AsyncMock(return_value={})):
        with patch.object(
            analytics.analytics_controller,
            "get_redis_connection",
            AsyncMock(return_value=redis_conn),
        ):
            with caplog.at_level(logging.ERROR):
                result = await analytics.get_historical_trends(hours=24)

    body = str(result)
    assert INTERNAL_MARKER not in body
    assert "RuntimeError" not in body
    assert result["redis_error"] == "Failed to retrieve historical analytics data"
    assert INTERNAL_MARKER in caplog.text
