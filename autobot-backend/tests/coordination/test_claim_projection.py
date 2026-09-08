# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The user-visible projection of work claims (#15949).

Two things are worth pinning here and neither is "the function returns a dict".

The first is the fan-out that justifies publishing ONCE. #15949 asked for a
publish to `agent:{id}` and a second to `global`; the live manager already
delivers every non-`global` channel to `global` subscribers, so the second
publish would double-deliver with mismatched event ids. Both halves of that are
asserted, because the design reads as an unimplemented requirement otherwise.

The second is that the endpoint is a genuine recovery path -- a client that
never saw the event reads the same holdings back -- rather than a differently
shaped view of the event it missed.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from starlette.websockets import WebSocketState

from autobot_shared.coordination.work_claims import Claim, ClaimConflict, ClaimMode, ScopeError, try_acquire
from services import claim_projection
from services.claim_projection import ACQUIRED, CONFLICT, RELEASED, claim_table, publish_conflict

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    from autobot_shared.coordination import work_claims as wc

    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(wc, "get_async_redis_client", _client)
    yield client
    await client.flushall()


@pytest.fixture
def published(monkeypatch):
    """Capture what reaches `events/bus.py`, without a bus behind it."""
    calls: list[tuple] = []

    async def _publish(channel, event_type, payload, **kwargs):
        calls.append((channel, event_type, payload))

    monkeypatch.setattr(claim_projection, "publish_event", _publish)
    return calls


class _FakeWS:
    """Enough WebSocket for `LiveEventManager.publish` -- state, and a sink."""

    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


@pytest.fixture
def live_manager(monkeypatch):
    """A real `LiveEventManager` with the Redis-backed id sequence stubbed."""
    import live_event_manager as lem

    class _Stream:
        def __init__(self) -> None:
            self._n = 0

        async def next_event_id(self, channel: str) -> int:
            self._n += 1
            return self._n

        async def append(self, channel: str, message: dict) -> None:
            return None

    monkeypatch.setattr(lem, "get_channel_event_stream", lambda: _Stream())
    return lem.LiveEventManager()


# ---------------------------------------------------------------------------
# The three event types, on the agent's own channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_three_event_types_publish_on_the_holder_channel(redis, published):
    outcome = await try_acquire(
        "path:autobot-backend/services/parser.py",
        agent_id="agent-1",
        task_id="t1",
        mode=ClaimMode.EXCLUSIVE,
        intent="fix the header parse",
    )
    await claim_projection.publish_acquired(outcome)
    await claim_projection.publish_released("path:autobot-backend/services/parser.py", agent_id="agent-1", task_id="t1")

    assert [c[1] for c in published] == [ACQUIRED, RELEASED]
    assert {c[0] for c in published} == {"agent:agent-1"}, "no new channel prefix"


@pytest.mark.asyncio
async def test_a_conflict_is_announced_to_the_requester_not_the_holder(redis, published):
    scope = "path:autobot-backend/services/parser.py"
    await try_acquire(scope, agent_id="agent-1", task_id="t1", mode=ClaimMode.EXCLUSIVE, intent="hold")
    refusal = await try_acquire(scope, agent_id="agent-2", task_id="t2", mode=ClaimMode.EXCLUSIVE, intent="also")

    await publish_conflict(refusal, agent_id="agent-2", task_id="t2")

    channel, event_type, payload = published[0]
    assert (channel, event_type) == ("agent:agent-2", CONFLICT), "the loser is the one who must act"
    assert payload["holder"]["agent_id"] == "agent-1"


# ---------------------------------------------------------------------------
# One publish is enough, and two would be wrong
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_global_subscriber_sees_an_agent_scoped_claim(live_manager):
    """This fan-out is the whole reason a second publish is unnecessary."""
    dashboard = _FakeWS()
    await live_manager.subscribe(dashboard, "global")

    await live_manager.publish("agent:agent-1", ACQUIRED, {"scope": "path:a/b.py"})

    assert [m["event_type"] for m in dashboard.messages] == [ACQUIRED]
    assert dashboard.messages[0]["channel"] == "agent:agent-1", "the origin channel is preserved"


@pytest.mark.asyncio
async def test_the_dashboard_is_not_told_twice(live_manager):
    """What publishing to `agent:{id}` *and* `global` would have cost.

    The two copies carry different `event_id`s -- the sequence is a per-channel
    counter -- so a client cannot dedupe them. Asserting the second publish
    produces a second, differently-numbered message is what makes the single
    publish a decision rather than an omission.
    """
    dashboard = _FakeWS()
    await live_manager.subscribe(dashboard, "global")

    await live_manager.publish("agent:agent-1", ACQUIRED, {"scope": "path:a/b.py"})
    assert len(dashboard.messages) == 1

    await live_manager.publish("global", ACQUIRED, {"scope": "path:a/b.py"})
    assert len(dashboard.messages) == 2, "a second publish is a second delivery, not a no-op"
    assert dashboard.messages[0]["event_id"] != dashboard.messages[1]["event_id"]


# ---------------------------------------------------------------------------
# The combined entry point enforcement will use
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_and_publish_projects_both_outcomes(redis, published):
    scope = "path:autobot-backend/services/parser.py"
    first = await claim_projection.acquire_and_publish(scope, agent_id="agent-1", task_id="t1", intent="fix parse")
    second = await claim_projection.acquire_and_publish(scope, agent_id="agent-2", task_id="t2", intent="rename")

    assert isinstance(first, Claim) and isinstance(second, ClaimConflict)
    assert [c[1] for c in published] == [ACQUIRED, CONFLICT]


@pytest.mark.asyncio
async def test_a_broken_projection_never_breaks_the_claim(redis, monkeypatch):
    """Losing the dashboard must not stop the work."""

    async def _explode(*args, **kwargs):
        raise RuntimeError("bus down")

    monkeypatch.setattr(claim_projection, "publish_event", _explode)

    outcome = await claim_projection.acquire_and_publish(
        "path:a/b.py", agent_id="agent-1", task_id="t1", intent="x"
    )

    assert isinstance(outcome, Claim), "the claim is the coordination fact; the event is only a view"
    assert [c["scope"] for c in await claim_table()] == ["path:a/b.py"]


@pytest.mark.asyncio
async def test_release_and_publish_is_silent_when_nothing_was_held(redis, published):
    """No claim went, so there is nothing to announce."""
    assert await claim_projection.release_and_publish("path:a/b.py", agent_id="agent-1", task_id="t1") is False
    assert published == []


# ---------------------------------------------------------------------------
# State over notification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_client_that_missed_the_event_recovers_the_same_holdings(redis, published):
    """The acquire is published to nobody; the table still knows."""
    scope = "path:autobot-backend/services/parser.py"
    claim = await try_acquire(scope, agent_id="agent-1", task_id="t1", mode=ClaimMode.EXCLUSIVE, intent="fix parse")
    await claim_projection.publish_acquired(claim)
    event_payload = published[0][2]

    recovered = await claim_table()

    assert recovered == [event_payload], "the endpoint must answer with what the event said"


@pytest.mark.asyncio
async def test_the_table_filters_by_agent_and_by_kind(redis):
    await try_acquire("path:a/b.py", agent_id="agent-1", task_id="t1", mode=ClaimMode.EXCLUSIVE, intent="x")
    await try_acquire("kb:topic/redis", agent_id="agent-2", task_id="t2", mode=ClaimMode.EXCLUSIVE, intent="y")

    assert [c["agent_id"] for c in await claim_table(agent_id="agent-1")] == ["agent-1"]
    assert [c["scope"] for c in await claim_table(kind="kb")] == ["kb:topic/redis"]


@pytest.mark.asyncio
async def test_the_scope_filter_is_segment_aligned_like_the_claim_rule(redis):
    """`path:a/bc` is not under `path:a/b`, and a `startswith` filter would say it is.

    A filter that disagreed with `Scope.overlaps` would show an operator a table
    that does not match what the registry enforces.
    """
    await try_acquire("path:a/bc", agent_id="agent-1", task_id="t1", mode=ClaimMode.EXCLUSIVE, intent="x")
    await try_acquire("path:a/b/inner.py", agent_id="agent-2", task_id="t2", mode=ClaimMode.EXCLUSIVE, intent="y")

    assert [c["scope"] for c in await claim_table(scope_prefix="path:a/b")] == ["path:a/b/inner.py"]


@pytest.mark.asyncio
async def test_an_unusable_scope_filter_is_an_error_not_an_empty_table(redis):
    """Failing open would answer "nothing holds this" for a question not understood."""
    with pytest.raises(ScopeError):
        await claim_table(scope_prefix="path:a/../b")


# ---------------------------------------------------------------------------
# Nothing internal reaches a payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_absolute_filesystem_path_cannot_become_a_scope(redis):
    """The "no internal paths" requirement holds by construction, not by scrubbing.

    An absolute path's leading `/` makes an empty first segment, which
    `Scope.parse` rejects -- so there is no payload-scrubbing step here that
    could be forgotten at a new publish site.
    """
    with pytest.raises(ScopeError):
        await try_acquire(
            "path:/opt/autobot/secret.py", agent_id="agent-1", task_id="t1", mode=ClaimMode.EXCLUSIVE, intent="x"
        )


def test_the_router_is_authenticated_and_mounted():
    """An unmounted router is a dead endpoint, and an open one leaks who is working where."""
    from api.coordination import router
    from initialization.router_registry.core_routers import load_core_routers

    assert router.dependencies, "the claim table must not be readable unauthenticated"
    mounted = {name: prefix for _, prefix, _, name in load_core_routers()}
    assert mounted.get("coordination") == "/coordination"
    assert [r.path for r in router.routes] == ["/claims"]
