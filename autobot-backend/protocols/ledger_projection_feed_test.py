#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The user backend's live-state projection for the SLM ledger (#18632).

Publishes every tenant's presence, peer-message metadata and idle waits; never an
unresolved tenant, never a message's content; and the presence sweep survives a
publish failure (the snapshot then simply expires).
"""

from __future__ import annotations

import json

import pytest

try:
    import fakeredis
    from fakeredis import aioredis as fakeredis_async
except ImportError:  # pragma: no cover - fakeredis is a test dependency
    fakeredis_async = None

from autobot_shared.coordination import ledger_projection as lp
from protocols import idle_notice
from protocols.agent_communication import AgentIdentity
from protocols.agent_kind import AgentKind
from protocols.agent_presence import UNKNOWN_TENANT, AgentPresenceRegistry
from protocols.idle_notice import IdleSubscription
from protocols.ledger_projection_feed import publish_live_state
from protocols.peer_inbox import PeerInboxDirectory

MESSAGE_BODY = "only the recipient may read this text"


@pytest.fixture
def redis():  # noqa: ANN201
    if fakeredis_async is None:
        pytest.skip("fakeredis not installed")
    return fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)


@pytest.fixture
def world(monkeypatch):  # noqa: ANN001, ANN201
    registry = AgentPresenceRegistry(ttl_seconds=60)
    for tenant, name in (("co-a", "a-writer"), ("co-b", "b-writer"), (None, "chat"), (UNKNOWN_TENANT, "lost")):
        kind = AgentKind.AI_STACK if tenant is None else AgentKind.COMPANY_OS
        registry.report(kind=kind, tenant_id=tenant, name=name, instance_id=name, busy=False)
    registry.report(kind=AgentKind.COMPANY_OS, tenant_id="co-a", name="a-peer", instance_id="p", busy=False)
    directory = PeerInboxDirectory(registry)
    sender = AgentIdentity(
        agent_id="a-peer", agent_type="test", kind=AgentKind.COMPANY_OS, name="a-peer", tenant_id="co-a"
    )
    directory.send(kind=AgentKind.COMPANY_OS, name="a-writer", sender=sender, content=MESSAGE_BODY, message_id="m1")
    monkeypatch.setattr(
        idle_notice,
        "_ACTIVE",
        {
            1: IdleSubscription("b-waiter", AgentKind.COMPANY_OS, "co-b", "b-writer", 1.0, 9.0),
            2: IdleSubscription("ghost", AgentKind.COMPANY_OS, UNKNOWN_TENANT, "lost", 1.0, 9.0),
        },
    )
    return registry, directory


async def _rows(redis, source):  # noqa: ANN001, ANN202
    return json.loads(await redis.get(lp.projection_key(source)))["rows"]


@pytest.mark.asyncio
async def test_every_tenants_live_state_is_published_with_its_tenant_and_unknown_never(redis, world) -> None:
    registry, directory = world
    await publish_live_state(redis, registry, directory)

    presence = {(r["tenant_id"], r["name"]) for r in await _rows(redis, lp.SOURCE_PRESENCE)}
    assert presence == {("co-a", "a-writer"), ("co-b", "b-writer"), (None, "chat"), ("co-a", "a-peer")}
    assert [s["subscriber"] for s in await _rows(redis, lp.SOURCE_IDLE_SUBSCRIBERS)] == ["b-waiter"]


@pytest.mark.asyncio
async def test_peer_messages_are_counts_and_senders_and_the_content_never_reaches_redis(redis, world) -> None:
    registry, directory = world
    await publish_live_state(redis, registry, directory)

    [row] = await _rows(redis, lp.SOURCE_PEER_MESSAGES)
    assert (row["recipient_name"], row["pending"], row["senders"], row["tenant_id"]) == (
        "a-writer",
        1,
        ["a-peer"],
        "co-a",
    )
    assert set(row) == {"recipient_kind", "recipient_name", "pending", "senders", "oldest_at", "tenant_id"}
    for key in await redis.keys("autobot:ledger:projection:*"):
        assert MESSAGE_BODY not in await redis.get(key)
    assert directory.inbox_for(kind=AgentKind.COMPANY_OS, tenant_id="co-a", name="a-writer").pending()  # not drained


@pytest.mark.asyncio
async def test_a_publish_failure_is_logged_and_the_sweep_goes_on(monkeypatch) -> None:
    from initialization import agent_presence_sync

    async def _boom(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr("autobot_shared.redis_client.get_async_redis_client", _boom)
    await agent_presence_sync._publish_projection(AgentPresenceRegistry(ttl_seconds=60))  # must not raise
