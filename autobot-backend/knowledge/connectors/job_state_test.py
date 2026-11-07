# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20755: the job a poller sees follows the sync's lease, not only the stored job state."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from knowledge.connectors import job_state, sync_lease
from knowledge.connectors.sync_lease_test import redis  # noqa: F401  (the shared fake-Redis fixture)


def _store(fake, status: str) -> None:
    fake.keys[job_state.job_key("c")] = json.dumps({"job_id": "j", "status": status, "sources_total": 7})


@pytest.mark.asyncio
async def test_a_claimed_sync_with_no_job_state_yet_reads_as_starting(redis) -> None:  # noqa: F811
    """The Sync button claims the lease before answering; detection may run for minutes."""
    await sync_lease.claim_connector_sync("c")
    assert (await job_state.read_job_state(redis, "c"))["status"] == "starting"


@pytest.mark.asyncio
async def test_the_previous_runs_result_does_not_end_a_new_claimed_sync(redis) -> None:  # noqa: F811
    _store(redis, "success")
    await sync_lease.claim_connector_sync("c")
    assert (await job_state.read_job_state(redis, "c"))["status"] == "starting"


@pytest.mark.asyncio
async def test_a_running_sync_shows_its_own_progress(redis) -> None:  # noqa: F811
    _store(redis, "running")
    await sync_lease.claim_connector_sync("c")
    state = await job_state.read_job_state(redis, "c")
    assert state["status"] == "running" and state["sources_total"] == 7


@pytest.mark.asyncio
async def test_a_finished_sync_shows_its_result_once_the_lease_is_free(redis) -> None:  # noqa: F811
    _store(redis, "partial")
    assert (await job_state.read_job_state(redis, "c"))["status"] == "partial"


@pytest.mark.asyncio
async def test_a_running_state_left_by_a_crashed_run_reads_as_no_job(redis) -> None:  # noqa: F811
    _store(redis, "running")  # nobody holds the lease: the run that wrote this is gone
    assert await job_state.read_job_state(redis, "c") is None


@pytest.mark.asyncio
async def test_no_sync_and_no_state_is_no_job(redis) -> None:  # noqa: F811
    assert await job_state.read_job_state(redis, "c") is None


@pytest.mark.asyncio
async def test_another_connectors_lease_does_not_count(redis) -> None:  # noqa: F811
    """The control: only this connector's own lease means its sync is in flight."""
    await sync_lease.claim_connector_sync("other")
    assert await job_state.read_job_state(redis, "c") is None


@pytest.mark.asyncio
async def test_a_lease_that_cannot_be_checked_is_unavailable_not_no_job() -> None:
    redis_down = AsyncMock(side_effect=ConnectionError("down"))
    with patch.object(sync_lease, "get_async_redis_client", redis_down):
        with pytest.raises(sync_lease.ConnectorSyncUnavailable):
            await sync_lease.sync_lease_held("c")
