# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cached result older than the source's last sync is served flagged ``stale`` (#17982).

Owner decision (2026-11-12): flag, do not suppress. The stored result is returned either way;
``stale`` says whether the source was synced after the result completed.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.codebase_analytics.source_storage import RegistryUnavailable
from api.source_scope import cached_task_result

COMPLETED = "2026-11-06T10:00:00+00:00"


async def _cached(last_synced, completed_at=COMPLETED, source="registered", registry_error=None):
    """``cached_task_result`` over a stored result and a registry holding one source."""
    stored = {"result": {"duplicates": []}, "completed_at": completed_at}
    if registry_error is not None:
        get_source = AsyncMock(side_effect=registry_error)
    else:
        get_source = AsyncMock(return_value=SimpleNamespace(last_synced=last_synced) if source else None)
    with (
        patch("utils.celery_task_status.get_latest_task_result", AsyncMock(return_value=stored)),
        patch("api.codebase_analytics.source_storage.get_source", get_source),
    ):
        return await cached_task_result("dup_task:", "src-a"), get_source


@pytest.mark.asyncio
async def test_a_sync_after_the_result_flags_it_stale_and_still_serves_it():
    body, _ = await _cached("2026-11-06T10:00:01+00:00")
    assert body["stale"] is True
    assert (body["status"], body["from_cache"], body["duplicates"]) == ("success", True, [])


@pytest.mark.asyncio
@pytest.mark.parametrize("synced", ["2026-11-06T09:59:59+00:00", COMPLETED])
async def test_a_sync_before_or_at_the_result_is_not_stale(synced):
    body, _ = await _cached(synced)
    assert body["stale"] is False


@pytest.mark.asyncio
async def test_a_naive_sync_time_is_read_as_utc_against_an_aware_completion_time():
    assert (await _cached("2026-11-06T10:00:01"))[0]["stale"] is True
    assert (await _cached("2026-11-06T09:00:00"))[0]["stale"] is False


@pytest.mark.asyncio
async def test_a_source_never_synced_is_not_stale():
    body, _ = await _cached(None)
    assert body["stale"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("completed_at", [None, ""])
async def test_a_result_without_a_completion_time_is_not_stale_and_asks_no_registry(completed_at):
    body, get_source = await _cached("2030-01-01T00:00:00+00:00", completed_at=completed_at)
    assert body["stale"] is False
    get_source.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unknown_source_an_unreadable_registry_or_an_unparsable_time_is_not_stale():
    assert (await _cached(None, source=None))[0]["stale"] is False
    assert (await _cached(None, registry_error=RegistryUnavailable("down")))[0]["stale"] is False
    assert (await _cached("not a time"))[0]["stale"] is False
    assert (await _cached("2030-01-01T00:00:00+00:00", completed_at="not a time"))[0]["stale"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ConnectionError("redis down"), ValueError("record does not validate")])
async def test_a_registry_failure_does_not_fail_a_cached_route_that_worked_before(error):
    """Fails on a bare registry read: ``get_source_or_none_if_unreadable`` only absorbs ``RegistryUnavailable``."""
    body, _ = await _cached(None, registry_error=error)
    assert (body["status"], body["from_cache"], body["stale"]) == ("success", True, False)


@pytest.mark.asyncio
async def test_stale_overrides_a_same_named_key_in_the_stored_result():
    stored = {"result": {"stale": "from the payload"}, "completed_at": COMPLETED}
    with (
        patch("utils.celery_task_status.get_latest_task_result", AsyncMock(return_value=stored)),
        patch(
            "api.codebase_analytics.source_storage.get_source",
            AsyncMock(return_value=SimpleNamespace(last_synced="2026-11-06T09:00:00+00:00")),
        ),
    ):
        assert (await cached_task_result("dup_task:", "src-a"))["stale"] is False
