# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bounds on the chat budget gate's store reads, and the once-only default seed (#16845)."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock

import fakeredis
import fakeredis.aioredis as fakeredis_async
import pytest
import pytest_asyncio

import services.budget_policy as bp_mod
import services.chat_budget_bounds as guard
import services.chat_budget_gate as gate
from autobot_shared.time_utils import now_utc
from llm_shared.run_credentials import llm_principal_scope
from services.budget_policy import (
    ACTION_ALERT_THEN_PAUSE,
    PERIOD_DAY,
    SCOPE_TENANT,
    SCOPE_USER,
    BudgetPolicy,
    create_policy,
    delete_policy,
    list_policies_for_scope,
    patch_policy,
    seed_default_policies,
)

USER, ORG = "alice", "acme"


@pytest_asyncio.fixture
async def redis(monkeypatch):
    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)

    async def _client(*_a, **_k):
        return client

    monkeypatch.setattr(bp_mod, "get_async_redis_client", _client)
    monkeypatch.setattr(gate, "get_async_redis_client", _client)
    monkeypatch.setattr("services.audit.audit.record", AsyncMock())
    guard.reset_state()
    yield client
    guard.reset_state()
    await client.aclose()


async def _user_policy_and_spend(redis, limit=1.0, spent=5.0):
    await create_policy(
        BudgetPolicy(
            scope=SCOPE_USER, scope_id=USER, period=PERIOD_DAY, threshold_usd=limit, action=ACTION_ALERT_THEN_PAUSE
        )
    )
    await redis.incrbyfloat(f"{gate.USER_SPEND_NS}:{USER}:daily:{now_utc().strftime('%Y-%m-%d')}", spent)


class TestSeedOnce:
    @pytest.mark.asyncio
    async def test_a_disabled_default_stays_disabled_across_a_restart(self, redis):
        await seed_default_policies()
        (policy,) = await list_policies_for_scope(SCOPE_TENANT, "default")
        await patch_policy(policy.id, {"enabled": False})
        await seed_default_policies()  # the next start
        assert await list_policies_for_scope(SCOPE_TENANT, "default") == []
        assert len(await list_policies_for_scope(SCOPE_TENANT, "default", include_disabled=True)) == 1

    @pytest.mark.asyncio
    async def test_a_deleted_default_does_not_come_back(self, redis):
        await seed_default_policies()
        (policy,) = await list_policies_for_scope(SCOPE_TENANT, "default")
        await delete_policy(policy.id)
        await seed_default_policies()
        assert await list_policies_for_scope(SCOPE_TENANT, "default", include_disabled=True) == []

    @pytest.mark.asyncio
    async def test_an_install_with_a_disabled_policy_is_not_seeded(self, redis):
        await create_policy(
            BudgetPolicy(scope=SCOPE_TENANT, scope_id="default", period=PERIOD_DAY, threshold_usd=9.0, enabled=False)
        )
        await seed_default_policies()
        (only,) = await list_policies_for_scope(SCOPE_TENANT, "default", include_disabled=True)
        assert only.threshold_usd == 9.0

    @pytest.mark.asyncio
    async def test_a_fresh_install_is_seeded_exactly_once(self, redis):
        await seed_default_policies()
        await seed_default_policies()
        assert len(await list_policies_for_scope(SCOPE_TENANT, "default")) == 1


class TestStoreBounds:
    @pytest.mark.asyncio
    async def test_a_hung_store_times_out_and_lets_the_request_through(self, redis, monkeypatch, caplog):
        async def _hang(*_a, **_k):
            await asyncio.sleep(30)

        monkeypatch.setattr(gate, "list_policies_for_scope", _hang)
        monkeypatch.setattr(guard, "CHECK_TIMEOUT_SECONDS", 0.05)
        with llm_principal_scope(USER, ORG), caplog.at_level(logging.ERROR):
            await asyncio.wait_for(gate.enforce_chat_budget(), 5)
        assert "Chat budget store failure" in caplog.text

    @pytest.mark.asyncio
    async def test_flipping_the_outage_decision_refuses_instead(self, redis, monkeypatch):
        monkeypatch.setattr(gate, "list_policies_for_scope", AsyncMock(side_effect=ConnectionError("down")))
        monkeypatch.setattr(guard, "STORE_OUTAGE_ALLOWS_REQUEST", False)
        with llm_principal_scope(USER, ORG), pytest.raises(gate.ChatBudgetUnavailable) as caught:
            await gate.enforce_chat_budget()
        assert caught.value.status_code == 503

    @pytest.mark.asyncio
    async def test_an_outage_logs_once_per_interval(self, redis, monkeypatch, caplog):
        monkeypatch.setattr(gate, "list_policies_for_scope", AsyncMock(side_effect=ConnectionError("down")))
        with llm_principal_scope(USER, ORG), caplog.at_level(logging.ERROR):
            for _ in range(5):
                await gate.enforce_chat_budget()
        assert caplog.text.count("Chat budget store failure") == 1

    @pytest.mark.asyncio
    async def test_spend_is_read_once_per_ttl(self, redis, monkeypatch):
        await _user_policy_and_spend(redis, limit=100.0, spent=1.0)
        reads = AsyncMock(return_value=1.0)
        monkeypatch.setattr(guard, "get_namespace_period_spend", reads)
        monkeypatch.setattr(guard, "SPEND_CACHE_TTL_SECONDS", 60.0)
        with llm_principal_scope(USER, ORG):
            for _ in range(4):  # a tool loop
                await gate.enforce_chat_budget()
        assert reads.await_count == 1

    @pytest.mark.asyncio
    async def test_an_expired_cache_entry_is_read_again_and_sees_the_new_spend(self, redis, monkeypatch):
        await _user_policy_and_spend(redis, limit=3.0, spent=1.0)
        monkeypatch.setattr(guard, "SPEND_CACHE_TTL_SECONDS", 0.05)
        with llm_principal_scope(USER, ORG):
            await gate.enforce_chat_budget()
            await redis.incrbyfloat(f"{gate.USER_SPEND_NS}:{USER}:daily:{now_utc().strftime('%Y-%m-%d')}", 5.0)
            await gate.enforce_chat_budget()  # still inside the TTL: the old reading
            await asyncio.sleep(0.1)
            with pytest.raises(gate.ChatBudgetExceeded):
                await gate.enforce_chat_budget()
