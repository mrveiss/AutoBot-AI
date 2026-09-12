# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for QuotaHeadroomStore (Issue #15026).

Coverage:
- record -> get round-trips a reading (Redis-backed via fakeredis).
- Two store instances sharing a FakeServer simulate two workers sharing state
  (mirrors test_provider_degradation.py's cross-worker verification style).
- Absent entry (no record() call) returns None — distinguishable from a real
  zero-remaining entry.
- Expiry (simulated by deleting the key) restores the absent state.
- No-Redis fallback (mocked _get_redis raises): in-process dict round-trips
  and expires correctly.
- utilization derives correctly from limit/remaining, and is None when
  either is unknown.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:
    fakeredis_async = None  # type: ignore[assignment]

from redis.exceptions import ConnectionError as RedisConnectionError

from llm_shared.quota_headroom import QuotaHeadroomEntry, QuotaHeadroomStore

# ---------------------------------------------------------------------------
# Local fixtures — deliberately not shared with provider_degradation's
# conftest.py fixtures, which are hardcoded to ProviderDegradationStore
# (see that conftest's own docstring on why fixtures here stay narrow).
# ---------------------------------------------------------------------------


@pytest.fixture
def _require_fakeredis():
    pytest.importorskip("fakeredis.aioredis")


@pytest.fixture
def _make_store_with_fake_server():
    fakeredis_mod = pytest.importorskip("fakeredis.aioredis")

    def _factory(server):
        store = QuotaHeadroomStore()

        async def _fake_redis(*_args, **_kwargs):
            return fakeredis_mod.FakeRedis(server=server, decode_responses=True)

        store._get_redis = _fake_redis  # type: ignore[method-assign]
        return store

    return _factory


# ---------------------------------------------------------------------------
# Redis-backed tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_then_get_redis(_require_fakeredis, _make_store_with_fake_server):
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.record(
        "openai", "rpm", limit=500, remaining=42, resets_at=time.time() + 60, source="x-ratelimit-remaining-requests"
    )

    entry = await store.get("openai", "rpm")
    assert entry is not None
    assert entry.provider == "openai"
    assert entry.window == "rpm"
    assert entry.account_id == "default"
    assert entry.remaining == 42
    assert entry.limit == 500
    assert entry.source == "x-ratelimit-remaining-requests"


@pytest.mark.asyncio
async def test_absent_entry_returns_none_redis(_require_fakeredis, _make_store_with_fake_server):
    """No record() call ever made for this key -> None, not a fabricated zero."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    assert await store.get("anthropic", "5h_output_tokens") is None


@pytest.mark.asyncio
async def test_cross_worker_visibility(_require_fakeredis, _make_store_with_fake_server):
    """Two stores sharing a FakeServer (simulating two uvicorn workers) share state."""
    server = fakeredis_async.FakeServer()
    worker_a = _make_store_with_fake_server(server)
    worker_b = _make_store_with_fake_server(server)

    await worker_a.record("openai", "tpm", limit=100000, remaining=5000)

    entry = await worker_b.get("openai", "tpm")
    assert entry is not None
    assert entry.remaining == 5000


@pytest.mark.asyncio
async def test_expiry_restores_absent_state(_require_fakeredis, _make_store_with_fake_server):
    """After TTL expiry (simulated by deleting the key), get() returns None again."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.record("openai", "rpm", limit=500, remaining=10)
    assert await store.get("openai", "rpm") is not None

    redis = await store._get_redis()
    await redis.delete("autobot:llm:headroom:openai:default:rpm")

    assert await store.get("openai", "rpm") is None


@pytest.mark.asyncio
async def test_all_entries_filters_by_provider(_require_fakeredis, _make_store_with_fake_server):
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.record("openai", "rpm", limit=500, remaining=10)
    await store.record("openai", "tpm", limit=100000, remaining=5000)
    await store.record("anthropic", "5h_output_tokens", remaining=1000)

    openai_entries = await store.all_entries(provider="openai")
    assert {e.window for e in openai_entries} == {"rpm", "tpm"}

    all_entries = await store.all_entries()
    assert {e.provider for e in all_entries} == {"openai", "anthropic"}


@pytest.mark.asyncio
async def test_account_id_scopes_entries_independently(_require_fakeredis, _make_store_with_fake_server):
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.record("openai", "rpm", account_id="acct-a", remaining=10)
    await store.record("openai", "rpm", account_id="acct-b", remaining=99)

    assert (await store.get("openai", "rpm", account_id="acct-a")).remaining == 10
    assert (await store.get("openai", "rpm", account_id="acct-b")).remaining == 99
    assert await store.get("openai", "rpm") is None  # default account never written here


# ---------------------------------------------------------------------------
# In-process fallback (no Redis)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_redis_fallback_record_and_get():
    store = QuotaHeadroomStore()

    async def _raise(*_args, **_kwargs):
        raise RedisConnectionError("Redis unavailable")

    store._get_redis = _raise  # type: ignore[method-assign]

    await store.record("openai", "rpm", limit=500, remaining=10)
    entry = await store.get("openai", "rpm")
    assert entry is not None
    assert entry.remaining == 10


@pytest.mark.asyncio
async def test_no_redis_fallback_expiry():
    """In-process fallback respects expiry (time-travel via monotonic patch)."""
    store = QuotaHeadroomStore()

    async def _raise(*_args, **_kwargs):
        raise RedisConnectionError("Redis unavailable")

    store._get_redis = _raise  # type: ignore[method-assign]

    await store.record("openai", "rpm", limit=500, remaining=10)
    assert await store.get("openai", "rpm") is not None

    with patch("time.monotonic", return_value=time.monotonic() + 999999):
        assert await store.get("openai", "rpm") is None


@pytest.mark.asyncio
async def test_no_redis_fallback_all_entries():
    store = QuotaHeadroomStore()

    async def _raise(*_args, **_kwargs):
        raise RedisConnectionError("Redis unavailable")

    store._get_redis = _raise  # type: ignore[method-assign]

    await store.record("openai", "rpm", remaining=10)
    await store.record("anthropic", "5h_output_tokens", remaining=1000)

    assert {e.provider for e in await store.all_entries()} == {"openai", "anthropic"}
    assert {e.provider for e in await store.all_entries(provider="openai")} == {"openai"}


# ---------------------------------------------------------------------------
# Redis client unavailable (disabled, or its circuit breaker open) --
# get_async_redis_client() returns None in this case rather than raising, and
# _get_redis() must turn that into the same fallback the connection/timeout
# errors above use, not an AttributeError from calling a method on None.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_falls_back_when_redis_client_is_none():
    store = QuotaHeadroomStore()

    with patch("autobot_shared.redis_client.get_async_redis_client", AsyncMock(return_value=None)):
        await store.record("openai", "rpm", limit=500, remaining=10)

    entry = await store.get("openai", "rpm")
    assert entry is not None
    assert entry.remaining == 10


@pytest.mark.asyncio
async def test_get_falls_back_when_redis_client_is_none():
    store = QuotaHeadroomStore()

    with patch("autobot_shared.redis_client.get_async_redis_client", AsyncMock(return_value=None)):
        await store.record("openai", "rpm", limit=500, remaining=10)
        entry = await store.get("openai", "rpm")

    assert entry is not None
    assert entry.remaining == 10


@pytest.mark.asyncio
async def test_all_entries_falls_back_when_redis_client_is_none():
    store = QuotaHeadroomStore()

    with patch("autobot_shared.redis_client.get_async_redis_client", AsyncMock(return_value=None)):
        await store.record("openai", "rpm", remaining=10)
        await store.record("anthropic", "5h_output_tokens", remaining=1000)
        entries = await store.all_entries()

    assert {e.provider for e in entries} == {"openai", "anthropic"}


# ---------------------------------------------------------------------------
# Corrupt entries — one bad payload must not sink the whole store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_none_for_a_corrupt_entry(_require_fakeredis, _make_store_with_fake_server, caplog):
    """A payload that doesn't parse must not raise into the caller -- treated as absent, not fabricated."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)
    redis = await store._get_redis()
    await redis.set("autobot:llm:headroom:openai:default:rpm", "not valid json")

    with caplog.at_level("WARNING", logger="llm_shared.quota_headroom"):
        assert await store.get("openai", "rpm") is None

    assert "corrupt entry" in caplog.text


@pytest.mark.asyncio
async def test_all_entries_skips_a_corrupt_entry_but_keeps_the_rest(
    _require_fakeredis, _make_store_with_fake_server, caplog
):
    """One bad row must not make every other Redis-held entry vanish."""
    server = fakeredis_async.FakeServer()
    store = _make_store_with_fake_server(server)

    await store.record("openai", "rpm", limit=500, remaining=10)
    redis = await store._get_redis()
    await redis.set("autobot:llm:headroom:anthropic:default:5h_output_tokens", "not valid json")

    with caplog.at_level("WARNING", logger="llm_shared.quota_headroom"):
        entries = await store.all_entries()

    assert {e.provider for e in entries} == {"openai"}
    assert "corrupt entry" in caplog.text


# ---------------------------------------------------------------------------
# QuotaHeadroomEntry.utilization
# ---------------------------------------------------------------------------


class TestUtilization:
    def _entry(self, **overrides) -> QuotaHeadroomEntry:
        base = dict(
            provider="openai",
            window="rpm",
            account_id="default",
            limit=100.0,
            remaining=25.0,
            resets_at=None,
            observed_at=time.time(),
            source="test",
        )
        base.update(overrides)
        return QuotaHeadroomEntry(**base)

    def test_computes_fraction_consumed(self):
        assert self._entry(limit=100.0, remaining=25.0).utilization == 0.75

    def test_none_when_limit_unknown(self):
        assert self._entry(limit=None).utilization is None

    def test_none_when_remaining_unknown(self):
        assert self._entry(remaining=None).utilization is None

    def test_none_when_limit_is_zero(self):
        assert self._entry(limit=0.0).utilization is None

    def test_clamped_to_one_when_remaining_negative(self):
        assert self._entry(limit=100.0, remaining=-5.0).utilization == 1.0
