# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A run key is revoked only after the run's terminal poll, exactly once (GH#20466 AC2)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters.base import AdapterRunStatus
from llc.models.enums import LLCRunStatus
from llc.scheduler.heartbeat_scheduler import _dispatch_registry_adapter
from testkit.fake_async_session import FakeAsyncSession

_HBS = "llc.scheduler.heartbeat_scheduler"
_AGENT = {"agent_id": "agent-abc", "company_id": "c-1", "adapter_type": "claude_code", "adapter_config": {"model": "m"}}
_RUNNING_POLLS = 4


def _factory() -> MagicMock:
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=FakeAsyncSession())
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.mark.asyncio
async def test_run_key_is_revoked_once_and_only_after_the_terminal_poll() -> None:
    events: list[str] = []

    async def status(*_a):
        events.append("poll")
        done = events.count("poll") > _RUNNING_POLLS
        return AdapterRunStatus(status=LLCRunStatus.COMPLETED if done else LLCRunStatus.RUNNING)

    async def revoke(*_a):
        events.append("revoke")

    adapter = MagicMock()
    adapter.invoke = AsyncMock(return_value="9/s")
    adapter.status = status
    key_record = MagicMock(id="key-1")
    with (
        patch(f"{_HBS}._ADAPTER_POLL_INTERVAL", 0),
        patch(f"{_HBS}._issue_run_key", AsyncMock(return_value=(key_record, "tok"))),
        patch(f"{_HBS}._revoke_run_key", side_effect=revoke) as revoke_mock,
        patch(f"{_HBS}.get_async_session_factory", return_value=_factory()),
    ):
        await _dispatch_registry_adapter(adapter, dict(_AGENT), {})

    assert events == ["poll"] * (_RUNNING_POLLS + 1) + ["revoke"]
    revoke_mock.assert_awaited_once()
