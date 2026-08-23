# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Durable channel sequencing and reconnect replay (#14817, #14818).

Two properties matter here and neither is covered by "the happy path returns
events":

* an id that resets on restart is worse than no id, because a consumer trusts
  it and silently skips or re-applies events (#14817);
* a replay that cannot be completed must say so.  Returning an empty list for
  both "you missed nothing" and "we cannot tell you what you missed" is exactly
  how lost events become invisible (#14818).

The fake Redis below implements only INCR/XADD/XRANGE/EXPIRE semantics, so the
tests exercise the real ``ChannelEventStream`` logic rather than a mock of it.
"""

import pytest

from events.channel_stream import ChannelEventStream


class FakeRedis:
    """Minimal INCR/XADD/XRANGE stand-in with a real trimming rule."""

    def __init__(self):
        self.counters: dict[str, int] = {}
        self.streams: dict[str, list] = {}
        self.plain: dict[str, str] = {}
        self._seq = 0

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def xadd(self, key, fields, maxlen=None, approximate=True):
        self._seq += 1
        entry_id = f"{self._seq}-0"
        self.streams.setdefault(key, []).append((entry_id, dict(fields)))
        if maxlen is not None and len(self.streams[key]) > maxlen:
            # Trim oldest first, as Redis does.
            self.streams[key] = self.streams[key][-maxlen:]
        return entry_id

    async def xrange(self, key):
        return list(self.streams.get(key, []))

    async def expire(self, key, ttl):
        return True

    async def setnx(self, key, value):
        if key in self.counters or key in self.plain:
            return False
        self.plain[key] = value
        return True

    async def get(self, key):
        return self.plain.get(key)


@pytest.fixture
def stream():
    s = ChannelEventStream()
    s._redis = FakeRedis()
    return s


async def _publish(stream: ChannelEventStream, channel: str, n: int) -> list[int]:
    ids = []
    for i in range(n):
        event_id = await stream.next_event_id(channel)
        ids.append(event_id)
        await stream.append(channel, {"event_id": event_id, "payload": {"i": i}})
    return ids


@pytest.mark.asyncio
async def test_ids_are_monotonic_per_channel(stream):
    ids = await _publish(stream, "chat:c1", 5)
    assert ids == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_ids_survive_a_restart(stream):
    """#14817: the defect was a process-local counter restarting at 1."""
    await _publish(stream, "chat:c1", 3)
    shared_redis = stream._redis

    # A "restarted" process: brand-new object, same Redis.
    restarted = ChannelEventStream()
    restarted._redis = shared_redis

    next_id = await restarted.next_event_id("chat:c1")
    assert next_id == 4, f"id restarted at {next_id} — a client's marker would now be wrong"


@pytest.mark.asyncio
async def test_two_workers_never_allocate_the_same_id(stream):
    """Independent instances sharing one Redis must not collide."""
    shared_redis = stream._redis
    worker_b = ChannelEventStream()
    worker_b._redis = shared_redis

    a_ids = [await stream.next_event_id("chat:c1") for _ in range(3)]
    b_ids = [await worker_b.next_event_id("chat:c1") for _ in range(3)]

    assert len(set(a_ids) | set(b_ids)) == 6, "workers allocated overlapping ids"


@pytest.mark.asyncio
async def test_channels_have_independent_sequences(stream):
    await _publish(stream, "chat:c1", 3)
    other = await stream.next_event_id("chat:c2")
    assert other == 1


@pytest.mark.asyncio
async def test_replay_returns_only_events_after_the_marker(stream):
    await _publish(stream, "chat:c1", 5)
    result = await stream.replay_since("chat:c1", 2)
    assert not result.resync_required
    assert [e["event_id"] for e in result.events] == [3, 4, 5]


@pytest.mark.asyncio
async def test_replay_of_a_current_client_returns_nothing_and_no_resync(stream):
    await _publish(stream, "chat:c1", 3)
    result = await stream.replay_since("chat:c1", 3)
    assert result.events == []
    assert not result.resync_required, "an up-to-date client was told to resync"


@pytest.mark.asyncio
async def test_gap_wider_than_retention_demands_resync(stream):
    """The distinguishing case: a partial history must never look complete."""
    from events import channel_stream as cs

    original = cs.CHANNEL_STREAM_MAX_ENTRIES
    cs.CHANNEL_STREAM_MAX_ENTRIES = 3
    try:
        await _publish(stream, "chat:c1", 10)
        # Retained window is ids 8,9,10. A client last saw 2 — ids 3..7 are gone.
        result = await stream.replay_since("chat:c1", 2)
    finally:
        cs.CHANNEL_STREAM_MAX_ENTRIES = original

    assert result.resync_required, "silently returned a partial history as if it were whole"
    assert result.reason == "gap_exceeds_retention"


@pytest.mark.asyncio
async def test_replay_without_redis_demands_resync():
    """No durable stream means we cannot prove completeness — say so."""
    s = ChannelEventStream()
    s._redis_unavailable = True

    result = await s.replay_since("chat:c1", 5)
    assert result.resync_required
    assert result.reason == "replay_unavailable"
    assert result.events == []


@pytest.mark.asyncio
async def test_corrupt_entry_demands_resync_rather_than_skipping(stream):
    await _publish(stream, "chat:c1", 3)
    key = stream._stream_key("chat:c1")
    stream._redis.streams[key][1] = ("2-0", {"event_id": "2", "data": "{not json"})

    result = await stream.replay_since("chat:c1", 0)
    assert result.resync_required, "an unreadable entry was skipped instead of forcing a resync"
    assert result.reason == "replay_corrupt"


@pytest.mark.asyncio
async def test_first_subscribe_is_not_treated_as_a_gap(stream):
    """last_event_id == 0 means 'never seen anything', not 'I lost events'."""
    await _publish(stream, "chat:c1", 3)
    result = await stream.replay_since("chat:c1", 0)
    assert not result.resync_required
    assert [e["event_id"] for e in result.events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_append_failure_does_not_raise(stream):
    """Losing replay-ability must never break live delivery."""

    async def boom(*_args, **_kwargs):
        raise RuntimeError("redis down")

    stream._redis.xadd = boom
    await stream.append("chat:c1", {"event_id": 1})  # must not raise


@pytest.mark.asyncio
async def test_a_lost_durable_write_forces_resync_for_earlier_clients(stream):
    """Review finding: a swallowed append failure punched an invisible hole.

    ``replay_since`` only checks the LOWER boundary of the retained range, so a
    client whose marker sits below a mid-stream hole was handed a partial
    history as if it were whole.
    """
    await _publish(stream, "chat:c1", 3)

    # Event 4's durable write fails and is swallowed, as it must be — the event
    # still reached live subscribers, only its replayability is lost.
    async def boom(*_a, **_kw):
        raise RuntimeError("redis rejected the write")

    original_xadd = stream._redis.xadd
    stream._redis.xadd = boom
    event_id = await stream.next_event_id("chat:c1")
    await stream.append("chat:c1", {"event_id": event_id, "payload": {}})
    stream._redis.xadd = original_xadd

    await _publish(stream, "chat:c1", 2)  # ids 5, 6 land normally

    result = await stream.replay_since("chat:c1", 2)

    assert result.resync_required, "partial history returned as if it were whole"
    assert result.reason == "durable_write_lost"


@pytest.mark.asyncio
async def test_a_client_past_the_hole_is_unaffected(stream):
    """The marker records the LOWEST lost id, so later clients still replay."""
    await _publish(stream, "chat:c1", 3)

    async def boom(*_a, **_kw):
        raise RuntimeError("redis rejected the write")

    original_xadd = stream._redis.xadd
    stream._redis.xadd = boom
    event_id = await stream.next_event_id("chat:c1")
    await stream.append("chat:c1", {"event_id": event_id, "payload": {}})
    stream._redis.xadd = original_xadd

    await _publish(stream, "chat:c1", 2)

    # Marker is at 4; a client that already saw 4 lost nothing.
    result = await stream.replay_since("chat:c1", 4)

    assert not result.resync_required
    assert [e["event_id"] for e in result.events] == [5, 6]


@pytest.mark.asyncio
async def test_by_design_gaps_do_not_trigger_a_resync(stream):
    """Non-durable events consume ids without being appended.

    Only PersistStrategy.REDIS publishes durably, so the stream is legitimately
    full of holes. A naive contiguity check would fire on every one of them and
    resync clients constantly for no reason.
    """
    await _publish(stream, "chat:c1", 2)
    await stream.next_event_id("chat:c1")  # id 3, never appended (non-durable)
    await _publish(stream, "chat:c1", 1)  # id 4 appended

    result = await stream.replay_since("chat:c1", 1)

    assert not result.resync_required, "a by-design gap was mistaken for data loss"
