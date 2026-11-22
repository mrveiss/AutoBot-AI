# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The reconcile loop's first pass waits one interval (#20232, from #20117).

It starts before the schedulers seed the set, so a first pass at once found every member
absent and logged each as "restored" at WARNING.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from llc.scheduler import schedule_reconcile as rec


@pytest.mark.asyncio
async def test_no_pass_runs_before_the_first_interval_has_elapsed():
    events = []

    async def fake_sleep(seconds):
        events.append(("sleep", seconds))
        if len(events) > 2:
            raise asyncio.CancelledError

    async def fake_restore(redis):
        events.append(("restore",))
        return []

    with (
        patch.object(rec.asyncio, "sleep", fake_sleep),
        patch.object(rec, "get_async_redis_client", AsyncMock(return_value=object())),
        patch.object(rec, "restore_lost_schedule_members", fake_restore),
    ):
        with pytest.raises(asyncio.CancelledError):
            await rec.reconcile_loop(interval=7.0)

    assert events[0] == ("sleep", 7.0)
    assert events[1] == ("restore",)
