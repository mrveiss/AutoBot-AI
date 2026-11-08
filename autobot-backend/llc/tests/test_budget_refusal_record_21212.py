# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A budget-refused dispatch leaves one visible, de-duplicated activity record (#21212)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import ActivityEventType
from llc.scheduler.dispatch_gate import BUDGET_EXHAUSTED, note_refused_wake, record_budget_refusal

_GATE = "llc.scheduler.dispatch_gate"
_COMPANY = str(uuid.uuid4())
_NODE = uuid.uuid4()
_SLUG = "ceo-acme"


class _Redis:
    def __init__(self) -> None:
        self.data: dict = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def delete(self, key):
        self.data.pop(key, None)


class _Env:
    def __init__(self) -> None:
        self.redis = _Redis()
        self.remaining = Decimal("-1")
        self.audit = AsyncMock()
        self.session = MagicMock()
        self.session.commit = AsyncMock()
        result = MagicMock()
        result.all.return_value = [(_NODE, _SLUG)]
        self.session.execute = AsyncMock(return_value=result)
        budget = MagicMock()
        budget.return_value.check_budget = AsyncMock(side_effect=lambda *a: (self.remaining, True, True))
        self.patches = [
            patch(f"{_GATE}.get_async_redis_client", AsyncMock(return_value=self.redis)),
            patch(f"{_GATE}.get_budget_service", budget),
            patch(f"{_GATE}.audit", self.audit),
        ]

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()

    async def refuse(self, reason=BUDGET_EXHAUSTED, ref=_SLUG) -> bool:
        return await record_budget_refusal(self.session, _COMPANY, ref, reason)


@pytest.mark.asyncio
async def test_a_budget_refusal_writes_one_company_scoped_record_naming_the_agent():
    with _Env() as env:
        assert await env.refuse() is True
    kwargs = env.audit.await_args.kwargs
    assert kwargs["event_type"] == ActivityEventType.BUDGET_DISPATCH_REFUSED
    assert kwargs["company_id"] == _COMPANY and kwargs["entity_id"] == str(_NODE)
    assert kwargs["metadata"] == {"agent_id": _SLUG, "reason": BUDGET_EXHAUSTED}
    env.session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_wakes_do_not_duplicate_the_record():
    with _Env() as env:
        results = [await env.refuse() for _ in range(3)]
    assert results == [True, False, False]
    assert env.audit.await_count == 1


@pytest.mark.asyncio
async def test_a_budget_change_then_another_refusal_writes_again():
    with _Env() as env:
        await env.refuse()
        env.remaining = Decimal("-7")  # limit raised, spent past it again
        assert await env.refuse() is True
        assert await env.refuse() is False
    assert env.audit.await_count == 2


@pytest.mark.asyncio
async def test_a_node_pk_reference_resolves_to_the_same_agent_and_episode():
    with _Env() as env:
        await env.refuse(ref=_SLUG)
        assert await env.refuse(ref=str(_NODE)) is False
    assert env.audit.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "agent status is paused",
        "agent is paused",
        "company is paused",
        "pause state is unreadable",
        "dispatch state could not be read",
        "agent has no company, so its budget cannot be read",
        "assigned agent was not found in this company",
    ],
)
async def test_other_refusal_reasons_stay_log_only(reason):
    with _Env() as env:
        assert await env.refuse(reason=reason) is False
    env.audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_write_is_logged_and_retried_on_the_next_wake():
    with _Env() as env:
        env.audit.side_effect = [RuntimeError("db down"), None]
        assert await env.refuse() is False
        assert await env.refuse() is True
    assert env.audit.await_count == 2


@pytest.mark.asyncio
async def test_the_scheduler_hook_logs_and_records():
    with _Env() as env:
        await note_refused_wake(env.session, _COMPANY, _SLUG, BUDGET_EXHAUSTED)
    env.audit.assert_awaited_once()
