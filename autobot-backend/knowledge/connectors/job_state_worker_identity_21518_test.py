# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The connector job state names its worker with the shared host-and-process identity (#21518)."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from knowledge.connectors.base import AbstractConnector


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["host-a-1", "host-b-22"], ids=["short", "two-digit-pid"])
async def test_the_job_state_worker_id_is_the_shared_identity(identity: str) -> None:
    redis = AsyncMock()
    fake_self = SimpleNamespace(_job_redis_key=lambda: "job:key", logger=SimpleNamespace(debug=lambda *a, **k: None))
    with (
        patch("autobot_shared.redis_client.get_async_redis_client", AsyncMock(return_value=redis)),
        patch("autobot_shared.leader_lease.worker_identity", return_value=identity),
    ):
        await AbstractConnector._write_job_state(
            fake_self,
            job_id="j1",
            status="running",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            sources_total=3,
            sources_done=1,
            sources_failed=0,
        )
    stored = json.loads(redis.set.await_args.args[1])
    assert stored["worker_id"] == identity
