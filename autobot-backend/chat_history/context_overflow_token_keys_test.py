# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Session token counters must read back what add_message_tokens wrote (#13274).

``SessionTokenTracker`` writes with ``hincrby(key, "total_tokens", n)`` — ``str``
field names — and reads with the shared async client, which is
``decode_responses=True``. ``hgetall`` therefore returns a ``str``-keyed dict.

``get_session_usage`` probed it with bytes literals::

    "total_tokens": int(data.get(b"total_tokens", 0)),

Every lookup missed, ``int(0)`` returned 0, and nothing raised. The tracker
reported zero usage for every session no matter how many tokens were recorded,
so any consumer of these counters saw a permanently empty session.
"""

import pytest

from chat_history.context_overflow import _TOKEN_TRACKER_KEY_PREFIX, SessionTokenTracker

SESSION = "session-abc"
SESSION_KEY = f"{_TOKEN_TRACKER_KEY_PREFIX}{SESSION}"


class _FakePipeline:
    """Captures hincrby/expire the way redis-py's pipeline does."""

    def __init__(self, store):
        self._store = store
        self.expire_calls = []

    def hincrby(self, key, field, amount):
        self._store.setdefault(key, {})
        self._store[key][field] = int(self._store[key].get(field, 0)) + amount

    def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))

    async def execute(self):
        return []


class _FakeAsyncRedis:
    """Dict-backed stand-in returning decoded (str) hash field names."""

    def __init__(self, hashes=None, decoded=True):
        self._hashes = dict(hashes or {})
        self._decoded = decoded

    def pipeline(self):
        return _FakePipeline(self._hashes)

    async def hgetall(self, key):
        raw = self._hashes.get(key, {})
        if self._decoded:
            return {str(k): str(v) for k, v in raw.items()}
        # Field names stay str; only the values arrive as bytes.
        return {str(k): str(v).encode() for k, v in raw.items()}


def _tracker(redis):
    tracker = SessionTokenTracker()
    tracker.redis = redis
    return tracker


@pytest.mark.asyncio
async def test_stored_counters_are_returned():
    """The live configuration. Pre-fix every counter read back 0."""
    tracker = _tracker(
        _FakeAsyncRedis(
            {
                SESSION_KEY: {
                    "total_tokens": 1500,
                    "prompt_tokens": 900,
                    "completion_tokens": 600,
                    "message_count": 7,
                }
            }
        )
    )

    usage = await tracker.get_session_usage(SESSION)

    assert usage == {
        "total_tokens": 1500,
        "prompt_tokens": 900,
        "completion_tokens": 600,
        "message_count": 7,
    }


@pytest.mark.asyncio
async def test_write_then_read_round_trips():
    """Drive the real writer, then the real reader, over one shared hash."""
    redis = _FakeAsyncRedis()
    tracker = _tracker(redis)

    await tracker.add_message_tokens(SESSION, prompt_tokens=120, completion_tokens=80)
    await tracker.add_message_tokens(SESSION, prompt_tokens=30, completion_tokens=20)

    usage = await tracker.get_session_usage(SESSION)

    assert usage["total_tokens"] == 250, "hincrby wrote str fields the reader could not see"
    assert usage["prompt_tokens"] == 150
    assert usage["completion_tokens"] == 100
    assert usage["message_count"] == 2


@pytest.mark.asyncio
async def test_bytes_values_still_work():
    """``decode_redis_value`` keeps handling a bytes counter value."""
    redis = _FakeAsyncRedis(decoded=False)
    tracker = _tracker(redis)

    await tracker.add_message_tokens(SESSION, prompt_tokens=10, completion_tokens=5)

    usage = await tracker.get_session_usage(SESSION)

    assert usage["total_tokens"] == 15
    assert usage["message_count"] == 1


@pytest.mark.asyncio
async def test_unknown_session_returns_zeros():
    """The one case that looked correct before the fix must still work."""
    tracker = _tracker(_FakeAsyncRedis())

    usage = await tracker.get_session_usage("never-seen")

    assert usage == {
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "message_count": 0,
    }
