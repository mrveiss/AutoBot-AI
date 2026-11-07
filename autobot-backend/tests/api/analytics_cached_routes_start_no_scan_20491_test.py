# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The cached analytics GET routes read stored results and start no scan (#20491).

Page-open calls these routes, so a GET that enqueued a task would start work on every visit.
Each test replaces the scan entry point with a mock; a control proves the mock is the one the
route module would call, so "not called" is a statement about the route and not about the mock.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SOURCE = "atlas"


@pytest.mark.asyncio
async def test_cached_security_score_starts_no_scan():
    from api import code_intelligence as mod

    stored = {"result": {"security_score": 90}, "completed_at": "2026-11-06T10:00:00+00:00"}
    with (
        patch.object(mod, "get_latest_task_result", AsyncMock(return_value=stored)) as read,
        patch.object(mod, "store_latest_task_id", AsyncMock()) as store,
        patch.object(mod.run_security_analysis, "delay", MagicMock()) as delay,
    ):
        body = await mod.get_cached_security_score(source_id=SOURCE)

    # control + scoping: the read answered, and it read this source's prefix
    read.assert_awaited_once_with(f"sec_task:source_id:{SOURCE}:")
    assert body["status"] == "success" and body["from_cache"] is True
    assert body["completed_at"] == "2026-11-06T10:00:00+00:00"
    delay.assert_not_called()
    store.assert_not_called()


@pytest.mark.asyncio
async def test_cached_security_score_without_a_result_still_starts_no_scan():
    from api import code_intelligence as mod

    with (
        patch.object(mod, "get_latest_task_result", AsyncMock(return_value=None)),
        patch.object(mod.run_security_analysis, "delay", MagicMock()) as delay,
    ):
        body = await mod.get_cached_security_score(source_id=SOURCE)

    assert body == {"status": "no_data"}
    delay.assert_not_called()


@pytest.mark.asyncio
async def test_the_explicit_start_route_does_reach_the_scan_entry_point():
    """Control: the mocked entry point is the one the explicit route calls."""
    from api import code_intelligence as mod

    task = MagicMock(id="task-1")
    with (
        patch.object(mod.os.path, "exists", return_value=True),
        patch.object(mod, "store_latest_task_id", AsyncMock()),
        patch.object(mod.run_security_analysis, "delay", MagicMock(return_value=task)) as delay,
    ):
        body = await mod.start_security_analysis(path=".", source_id=SOURCE, admin_check=True)

    delay.assert_called_once()
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_cached_bug_prediction_starts_no_scan():
    from api import analytics_bug_prediction as mod

    stored = {"result": {"files": [], "summary": {}}, "completed_at": "2026-11-06T10:00:00+00:00"}
    with (
        patch.object(mod, "get_latest_task_result", AsyncMock(return_value=stored)) as read,
        patch.object(mod, "store_latest_task_id", AsyncMock()) as store,
        patch.object(mod.run_bug_prediction_analysis, "delay", MagicMock()) as delay,
    ):
        body = await mod.get_cached_bug_prediction()

    assert read.await_count == 1
    assert body["from_cache"] is True and body["completed_at"]
    delay.assert_not_called()
    store.assert_not_called()


@pytest.mark.asyncio
async def test_the_explicit_bug_prediction_start_route_does_reach_the_scan_entry_point():
    """Control: the mocked ``.delay`` is the one the explicit POST route calls."""
    from api import analytics_bug_prediction as mod

    task = MagicMock(id="task-2")
    with (
        patch.object(mod, "store_latest_task_id", AsyncMock()),
        patch.object(mod.run_bug_prediction_analysis, "delay", MagicMock(return_value=task)) as delay,
    ):
        body = await mod.start_bug_analysis(admin_check=True, path=".", include_pattern="*.py", limit=10)

    delay.assert_called_once_with(".", "*.py", 10)
    assert body == {"task_id": "task-2", "status": "pending"}
