# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A run whose key cannot be issued fails visibly instead of dispatching keyless (#20149 AC2)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters.base import AdapterRunStatus
from llc.exceptions import RunKeyIssueFailed
from llc.models.enums import LLCRunStatus
from llc.scheduler import run_key
from llc.scheduler.heartbeat_scheduler import LLCHeartbeatScheduler
from testkit.fake_async_session import FakeAsyncSession

_HBS = "llc.scheduler.heartbeat_scheduler"
_CAUSE_TEXT = "connection to db-internal-host refused"
_AGENT = {
    "agent_id": "agent-abc",
    "company_id": "c-1",
    "adapter_type": "claude_code",
    "adapter_config": {},
    "context_mode": "slim",
}


def _factory() -> MagicMock:
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=FakeAsyncSession())
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


def _adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.invoke = AsyncMock(return_value="ext-1")
    adapter.status = AsyncMock(return_value=AdapterRunStatus(status=LLCRunStatus.COMPLETED))
    return adapter


async def _run(adapter: MagicMock, issue: AsyncMock) -> AsyncMock:
    """Drive `_run_adapter` for one agent with the real `issue_run_key`'s collaborator replaced."""
    scheduler, finish = LLCHeartbeatScheduler(), AsyncMock()
    with (
        patch.object(scheduler, "_finish_run", finish),
        patch(f"{_HBS}.mark_running", AsyncMock(return_value=0)),
        patch(f"{_HBS}.adapter_block_reason", return_value=None),
        patch(f"{_HBS}.get_adapter", return_value=adapter),
        patch(f"{_HBS}._record_run_for_replay", AsyncMock()),
        patch(f"{_HBS}.pause_after_auth_failure", AsyncMock()),
        patch(f"{_HBS}._revoke_run_key", AsyncMock()),
        patch(f"{_HBS}.get_async_session_factory", return_value=_factory()),
        patch("llc.scheduler.run_key.get_async_session_factory", return_value=_factory()),
        patch("llc.scheduler.run_key.ApiKeyService.issue_key", issue),
    ):
        await scheduler._run_adapter(dict(_AGENT), uuid.uuid4(), {})
        for task in list(scheduler._tasks):
            await task
    return finish


@pytest.mark.asyncio
async def test_failed_key_issue_fails_the_run_and_never_starts_the_adapter() -> None:
    adapter = _adapter()
    finish = await _run(adapter, AsyncMock(side_effect=RuntimeError(_CAUSE_TEXT)))

    adapter.invoke.assert_not_awaited()
    args = finish.await_args.args
    assert args[3] == LLCRunStatus.FAILED.value
    assert "run key issue" in args[4] and _CAUSE_TEXT not in args[4]


@pytest.mark.asyncio
async def test_issue_run_key_raises_typed_error_with_cause_chained_not_in_text() -> None:
    with (
        patch("llc.scheduler.run_key.get_async_session_factory", return_value=_factory()),
        patch("llc.scheduler.run_key.ApiKeyService.issue_key", AsyncMock(side_effect=RuntimeError(_CAUSE_TEXT))),
    ):
        with pytest.raises(RunKeyIssueFailed) as caught:
            await run_key.issue_run_key("agent-abc", "c-1")
    assert _CAUSE_TEXT not in str(caught.value)
    assert isinstance(caught.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_issued_key_reaches_the_dispatched_run_and_is_not_a_failure() -> None:
    adapter = _adapter()
    record = MagicMock(id=uuid.uuid4())
    finish = await _run(adapter, AsyncMock(return_value=(record, "issued-value")))

    assert adapter.invoke.await_args.args[1]["agent_api_key"] == "issued-value"  # pragma: allowlist secret
    assert finish.await_args.args[3] == LLCRunStatus.COMPLETED.value
