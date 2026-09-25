# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The dev loop's per-action record (#17091 AC 2/3).

The distinction under test throughout: *nothing was attempted* and *the store
could not be read* must not produce the same answer, and *not recorded* must
not look like *recorded fine*.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from autobot_shared.coordination import dev_loop_actions
from autobot_shared.coordination.dev_loop_actions import (
    ACTION_LOG_MAX,
    OUTCOME_RAN,
    OUTCOME_REFUSED_BUDGET,
    OUTCOME_SKIPPED_CLAIMED,
    DevLoopAction,
    action_payload,
    build_action,
    last_refusal,
    recent,
    record,
)

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover - environment without the extra
    fakeredis_async = None


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis not installed")
    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(dev_loop_actions, "get_async_redis_client", _client)
    yield client
    await client.flushall()


class TestBuildAction:
    def test_it_stamps_the_entry_with_a_time(self):
        action = build_action(17091, intent="verify", outcome=OUTCOME_RAN, estimated_tokens=5)

        assert action.issue == 17091
        assert action.at, "an entry with no timestamp cannot be ordered or aged out"

    def test_an_unknown_outcome_raises_rather_than_being_recorded(self):
        """A typo'd outcome drops out of every count that filters on one, silently."""
        with pytest.raises(ValueError, match="unknown dev-loop outcome"):
            build_action(17091, intent="verify", outcome="finished", estimated_tokens=5)

    def test_the_payload_round_trips(self):
        action = build_action(17091, intent="verify", outcome=OUTCOME_RAN, estimated_tokens=5)

        assert DevLoopAction(**json.loads(json.dumps(action_payload(action)))) == action


class TestRecordAndRead:
    @pytest.mark.asyncio
    async def test_a_recorded_action_reads_back(self, redis):
        assert await record(build_action(17091, intent="verify", outcome=OUTCOME_RAN, estimated_tokens=5)) is True

        entries = await recent(17091)
        assert [(e.issue, e.outcome, e.estimated_tokens) for e in entries] == [(17091, OUTCOME_RAN, 5)]

    @pytest.mark.asyncio
    async def test_an_issue_with_no_history_reads_empty_from_a_healthy_store(self, redis):
        assert await recent(4242) == []

    @pytest.mark.asyncio
    async def test_an_unreadable_store_raises_instead_of_reading_empty(self, monkeypatch):
        """The other half of the same distinction: an outage must not report
        "this issue was never touched"."""

        async def _none(database: str = "main"):
            return None

        monkeypatch.setattr(dev_loop_actions, "get_async_redis_client", _none)

        with pytest.raises(RuntimeError, match="cannot be read"):
            await recent(17091)

    @pytest.mark.asyncio
    async def test_a_failed_write_reports_false_rather_than_pretending(self, monkeypatch):
        async def _none(database: str = "main"):
            return None

        monkeypatch.setattr(dev_loop_actions, "get_async_redis_client", _none)

        assert await record(build_action(17091, intent="v", outcome=OUTCOME_RAN, estimated_tokens=1)) is False

    @pytest.mark.asyncio
    async def test_a_broken_client_does_not_raise_into_the_action(self, monkeypatch, redis):
        """An audit write must never fail the work it describes."""

        class _Broken:
            async def lpush(self, *args, **kwargs):
                raise ConnectionError("redis went away mid-write")

        async def _broken(database: str = "main"):
            return _Broken()

        monkeypatch.setattr(dev_loop_actions, "get_async_redis_client", _broken)

        assert await record(build_action(17091, intent="v", outcome=OUTCOME_RAN, estimated_tokens=1)) is False

    @pytest.mark.asyncio
    async def test_the_newest_entry_comes_first(self, redis):
        await record(build_action(17091, intent="first", outcome=OUTCOME_RAN, estimated_tokens=1))
        await record(build_action(17091, intent="second", outcome=OUTCOME_RAN, estimated_tokens=2))

        assert [e.intent for e in await recent(17091)] == ["second", "first"]

    @pytest.mark.asyncio
    async def test_the_history_is_trimmed_to_its_ceiling(self, redis):
        for n in range(ACTION_LOG_MAX + 5):
            await record(build_action(17091, intent=f"a{n}", outcome=OUTCOME_RAN, estimated_tokens=1))

        assert await redis.llen("work_claims:actions:issue:17091") == ACTION_LOG_MAX

    @pytest.mark.asyncio
    async def test_the_history_carries_a_ttl_so_it_cannot_accumulate_forever(self, redis):
        await record(build_action(17091, intent="v", outcome=OUTCOME_RAN, estimated_tokens=1))

        assert await redis.ttl("work_claims:actions:issue:17091") > 0

    @pytest.mark.asyncio
    async def test_each_issue_keeps_its_own_history(self, redis):
        await record(build_action(17091, intent="a", outcome=OUTCOME_RAN, estimated_tokens=1))
        await record(build_action(17092, intent="b", outcome=OUTCOME_RAN, estimated_tokens=1))

        assert [e.intent for e in await recent(17091)] == ["a"]
        assert [e.intent for e in await recent(17092)] == ["b"]


class TestLastRefusal:
    def test_it_finds_the_most_recent_stopping_entry(self):
        ran = build_action(17091, intent="v", outcome=OUTCOME_RAN, estimated_tokens=1)
        refused = build_action(17091, intent="v", outcome=OUTCOME_REFUSED_BUDGET, estimated_tokens=1, reason="spent")
        skipped = build_action(17091, intent="v", outcome=OUTCOME_SKIPPED_CLAIMED, estimated_tokens=0, reason="held")

        assert last_refusal([ran, refused, skipped]) is refused

    def test_a_history_that_never_stopped_has_no_refusal(self):
        ran = build_action(17091, intent="v", outcome=OUTCOME_RAN, estimated_tokens=1)

        assert last_refusal([ran]) is None

    def test_an_empty_history_has_no_refusal(self):
        assert last_refusal([]) is None


class TestTheHistoryWriteIsAtomic:
    """`LPUSH`, `LTRIM` and `EXPIRE` go in one transaction (#17380 review).

    Sent separately, a failure after `LPUSH` succeeded left the history key with
    no TTL -- bounded only by the next `LTRIM` that happens to run. `record`
    returns `False` and `_record` logs it, but neither caller repairs the
    partial write, so the bounded-history contract broke quietly.

    Same shape and same fix as `token_budget._increment` on this PR. Asserting
    the TTL rather than the command list, because `record` goes through the real
    client here: an immortal key is the property that matters, and it stays the
    property to assert if this ever moves to a Lua script.
    """

    @pytest.mark.asyncio
    async def test_the_history_key_always_carries_a_ttl(self, redis):
        assert await record(build_action(17380, intent="verify", outcome=OUTCOME_RAN, estimated_tokens=1)) is True

        keys = [k for k in await redis.keys("*") if "17380" in k]
        assert keys, "nothing was written, so this asserts nothing"
        for key in keys:
            assert await redis.ttl(key) > 0, f"{key} has no expiry and will outlive the history window"

    @pytest.mark.asyncio
    async def test_a_second_write_keeps_the_expiry(self, redis):
        """Redis preserves an existing TTL across LPUSH, so the exposed write is
        the FIRST one -- the one that creates the key. This pins that the
        transaction covers it and that a later append does not clear it."""
        for _ in range(2):
            await record(build_action(17381, intent="verify", outcome=OUTCOME_RAN, estimated_tokens=1))

        keys = [k for k in await redis.keys("*") if "17381" in k]
        assert keys
        # A loop, not `all(await ... for ...)`: an await inside a generator
        # expression makes it an ASYNC generator, which `all()` cannot consume
        # -- it raises TypeError rather than evaluating to False, so the
        # assertion never runs.
        for key in keys:
            assert await redis.ttl(key) > 0
