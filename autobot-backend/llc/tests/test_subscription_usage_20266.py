# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A finished subscription run is never failed over dollars; API-billed runs keep the stop (#20266)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters.base import BILLING_API, BILLING_SUBSCRIPTION, AdapterRunStatus
from llc.exceptions import AdapterRunFailed, BudgetExhausted
from llc.models.enums import LLCRunStatus
from llc.scheduler.heartbeat_scheduler import _dispatch_registry_adapter
from testkit.fake_async_session import FakeAsyncSession

_HBS = "llc.scheduler.heartbeat_scheduler"
_AGENT = {"agent_id": "agent-abc", "company_id": "c-1", "adapter_type": "claude_code", "adapter_config": {"model": "m"}}


async def _dispatch(status: LLCRunStatus, billing, session: FakeAsyncSession, ingest: AsyncMock) -> None:
    result = AdapterRunStatus(status=status, tokens_in=1000, tokens_out=200, billing=billing)
    adapter = MagicMock()
    adapter.invoke = AsyncMock(return_value="9/s")
    adapter.status = AsyncMock(return_value=result)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    with (
        patch(f"{_HBS}._issue_run_key", AsyncMock(return_value=(None, None))),
        patch(f"{_HBS}._revoke_run_key", AsyncMock()),
        patch(f"{_HBS}.get_async_session_factory", return_value=factory),
        patch(f"{_HBS}.BudgetService.ingest_cost_event", new=ingest),
    ):
        await _dispatch_registry_adapter(adapter, dict(_AGENT), {})


@pytest.mark.asyncio
async def test_finished_subscription_run_over_budget_is_not_failed_and_usage_is_recorded() -> None:
    session, ingest = FakeAsyncSession(), AsyncMock(side_effect=BudgetExhausted("agent-abc", 12.0, 10.0))
    await _dispatch(LLCRunStatus.COMPLETED, BILLING_SUBSCRIPTION, session, ingest)  # must not raise
    assert ingest.await_args.args[3:6] == (1000, 200, "m")
    assert session.commits == 1


@pytest.mark.asyncio
async def test_finished_api_run_over_budget_still_raises_budget_exhausted() -> None:
    for billing in (BILLING_API, None):
        session, ingest = FakeAsyncSession(), AsyncMock(side_effect=BudgetExhausted("agent-abc", 12.0, 10.0))
        with pytest.raises(BudgetExhausted):
            await _dispatch(LLCRunStatus.COMPLETED, billing, session, ingest)
        assert session.commits == 0


@pytest.mark.asyncio
async def test_failed_subscription_run_still_fails_and_records_usage() -> None:
    session, ingest = FakeAsyncSession(), AsyncMock(side_effect=BudgetExhausted("agent-abc", 12.0, 10.0))
    with pytest.raises(AdapterRunFailed):
        await _dispatch(LLCRunStatus.FAILED, BILLING_SUBSCRIPTION, session, ingest)
    ingest.assert_awaited_once()
    assert session.commits == 1


@pytest.mark.asyncio
async def test_subscription_run_under_budget_records_normally() -> None:
    session, ingest = FakeAsyncSession(), AsyncMock(return_value=0)
    await _dispatch(LLCRunStatus.COMPLETED, BILLING_SUBSCRIPTION, session, ingest)
    assert session.commits == 1
