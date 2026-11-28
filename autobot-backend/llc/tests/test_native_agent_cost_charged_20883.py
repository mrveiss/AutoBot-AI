# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A native AutoBot-agent run is charged to its budget, once, and the spend is committed (#20883).

Driven through ``_dispatch_autobot_agent`` -- the scheduler's real construction site -- so a
missing factory at that site fails here. A registry run is charged by
``_ingest_adapter_usage`` and never reaches the adapter's own forwarding, so one run is
charged by exactly one of the two.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.adapters.autobot_agent_adapter import AutoBotAgentAdapter
from llc.adapters.base import AdapterRunStatus
from llc.exceptions import BudgetExhausted
from llc.models.enums import LLCRunStatus
from llc.scheduler.heartbeat_scheduler import _dispatch_autobot_agent, _ingest_adapter_usage
from testkit.fake_async_session import FakeAsyncSession

_HBS = "llc.scheduler.heartbeat_scheduler"
# A stable dotted path, as `test_adapter_budget_company_scope.py` takes from `_FAKE_AGENT_PATH`:
# `__name__` differs under `--import-mode=importlib`, and the adapter imports the class by this path.
_THIS_MODULE = "llc.tests.test_native_agent_cost_charged_20883"
_USAGE_AGENT_PATH = f"{_THIS_MODULE}.UsageAgent"
_ZERO_USAGE_AGENT_PATH = f"{_THIS_MODULE}.ZeroUsageAgent"
_COMPANY = "company-1"
_AGENT = {
    "agent_id": "agent-xyz",
    "company_id": _COMPANY,
    "adapter_config": {"agent_class": _USAGE_AGENT_PATH},
}


class _Response:
    def __init__(self, metadata: Dict[str, Any]) -> None:
        self.status = "success"
        self.metadata = metadata


class UsageAgent:
    """Reports 10 prompt and 5 completion tokens."""

    def __init__(self, **_: Any) -> None:
        pass

    async def process_request(self, request: Any) -> _Response:
        return _Response({"model": "test-model", "prompt_tokens": 10, "completion_tokens": 5})


class ZeroUsageAgent(UsageAgent):
    async def process_request(self, request: Any) -> _Response:
        return _Response({"model": "test-model", "prompt_tokens": 0, "completion_tokens": 0})


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "llc.adapters.autobot_agent_adapter.get_async_redis_client", AsyncMock(return_value=None), raising=False
    )


def _sessions() -> tuple[MagicMock, List[FakeAsyncSession]]:
    """A session maker (for the real `async_session_scope`) and the sessions it handed out.

    The fake is its own async context manager (`__aenter__` returns it, `__aexit__` closes it),
    which is the protocol the scope's ``async with session_maker() as session`` uses.
    """
    opened: List[FakeAsyncSession] = []

    def _make() -> FakeAsyncSession:
        session = FakeAsyncSession()
        opened.append(session)
        return session

    return MagicMock(side_effect=_make), opened


async def _dispatch(agent_path: str, service: MagicMock) -> List[FakeAsyncSession]:
    maker, opened = _sessions()
    agent = dict(_AGENT, adapter_config={"agent_class": agent_path})
    with (
        patch("llc.scheduler.usage_billing.get_async_session_factory", return_value=maker),
        patch("llc.services.accessors.get_budget_service", return_value=service),
    ):
        await _dispatch_autobot_agent(agent, {"title": "T"})
    return opened


@pytest.mark.asyncio
async def test_run_with_usage_produces_one_committed_cost_event_for_the_agents_budget() -> None:
    service = MagicMock(ingest_cost_event=AsyncMock())
    opened = await _dispatch(_USAGE_AGENT_PATH, service)

    service.ingest_cost_event.assert_awaited_once()
    args = service.ingest_cost_event.await_args.args
    assert args[0] is opened[0]
    assert args[1:] == ("agent-xyz", _COMPANY, 10, 5, "test-model")
    # persisted, not rolled back on exit; the scope closed it
    assert len(opened) == 1 and (opened[0].commits, opened[0].rollbacks, opened[0].closed) == (1, 0, True)


@pytest.mark.asyncio
async def test_run_with_zero_usage_charges_nothing_and_opens_no_session() -> None:
    service = MagicMock(ingest_cost_event=AsyncMock())
    opened = await _dispatch(_ZERO_USAGE_AGENT_PATH, service)

    service.ingest_cost_event.assert_not_awaited()
    assert opened == []


@pytest.mark.asyncio
async def test_hard_stop_still_stops_the_run() -> None:
    service = MagicMock(ingest_cost_event=AsyncMock(side_effect=BudgetExhausted("agent-xyz", 12.0, 10.0)))
    maker, opened = _sessions()
    with (
        patch("llc.scheduler.usage_billing.get_async_session_factory", return_value=maker),
        patch("llc.services.accessors.get_budget_service", return_value=service),
    ):
        with pytest.raises(BudgetExhausted):
            await _dispatch_autobot_agent(dict(_AGENT), {"title": "T"})
    service.ingest_cost_event.assert_awaited_once()
    # The scope rolled back and closed; the service itself commits the hard-stop spend (#20202).
    assert len(opened) == 1 and (opened[0].commits, opened[0].rollbacks, opened[0].closed) == (0, 1, True)


@pytest.mark.asyncio
async def test_scheduler_construction_site_passes_a_budget_session_factory() -> None:
    """The guard AC3 asks for: the adapter is never built without a factory in production wiring."""
    with patch(f"{_HBS}.AutoBotAgentAdapter", wraps=AutoBotAgentAdapter) as built:
        with (
            patch("llc.scheduler.usage_billing.get_async_session_factory", return_value=_sessions()[0]),
            patch("llc.services.accessors.get_budget_service", return_value=MagicMock(ingest_cost_event=AsyncMock())),
        ):
            await _dispatch_autobot_agent(dict(_AGENT), {"title": "T"})
    assert callable(built.call_args.kwargs["budget_session_factory"])


@pytest.mark.asyncio
async def test_a_lost_charge_is_logged_at_error_with_traceback_and_does_not_fail_the_run(caplog: Any) -> None:
    """Any failure but `BudgetExhausted` leaves the finished run alone, but never silently."""
    service = MagicMock(ingest_cost_event=AsyncMock(side_effect=RuntimeError("db down")))
    with caplog.at_level(logging.ERROR, logger="llc.adapters.autobot_agent_adapter"):
        opened = await _dispatch(_USAGE_AGENT_PATH, service)

    lost = [r for r in caplog.records if "charge is lost" in r.getMessage()]
    assert len(lost) == 1 and lost[0].levelno == logging.ERROR and lost[0].exc_info is not None
    assert (opened[0].commits, opened[0].rollbacks) == (0, 1)  # nothing half-written


@pytest.mark.asyncio
async def test_a_registry_run_lost_charge_is_logged_the_same_way(caplog: Any) -> None:
    result = AdapterRunStatus(status=LLCRunStatus.COMPLETED, tokens_in=3, tokens_out=2)
    factory = MagicMock(return_value=FakeAsyncSession())
    service = MagicMock(ingest_cost_event=AsyncMock(side_effect=RuntimeError("db down")))
    with (
        patch(f"{_HBS}.get_async_session_factory", return_value=factory),
        patch(f"{_HBS}.get_budget_service", return_value=service),
        caplog.at_level(logging.ERROR, logger=_HBS),
    ):
        await _ingest_adapter_usage(dict(_AGENT, model="test-model"), result)

    lost = [r for r in caplog.records if "charge is lost" in r.getMessage()]
    assert len(lost) == 1 and lost[0].levelno == logging.ERROR and lost[0].exc_info is not None
