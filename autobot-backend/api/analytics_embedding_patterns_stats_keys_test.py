# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Embedding analytics must report the figures the writer actually stored (#13278).

``EmbeddingPatternAnalyzer._update_stats`` writes every counter with
``pipe.hincrby(daily_key, "total_operations", 1)`` and
``pipe.hincrbyfloat(daily_key, "total_cost", cost)`` — ``str`` field names. Its
client comes from ``AsyncRedisClientLockedMixin`` →
``get_async_redis_client(database=RedisDatabase.ANALYTICS)``, and the shared
async pool is ``decode_responses=True``
(``redis_management/connection_manager.py:500`` reading
``config.decode_responses``, which defaults ``True`` at
``redis_management/config.py:61,153`` with no per-database override). So
``hgetall`` hands back a ``str``-keyed dict.

Both readers probed it with bytes literals::

    ops  += int(stats.get(b"total_operations", 0))
    cost += float(stats.get(b"total_cost", 0))

Every lookup missed, every default was returned, and ``int(0)``/``float(0)``
succeeded — so ``GET .../stats`` and ``GET .../model-comparison`` reported zero
operations, zero tokens and $0.00 cost forever, no matter how much
vectorization had run. No exception, no log line.

The round-trip tests below drive the real ``record_usage`` → ``_update_stats``
writer into the real ``get_stats``/``get_model_comparison`` readers over one
shared hash, so any future writer/reader key drift breaks the suite rather than
silently zeroing the endpoint again.
"""

import pytest

from api.analytics_embedding_patterns import EmbeddingPatternAnalyzer
from api.schemas_analytics import EmbeddingUsageRequest

# text-embedding-3-small bills 0.02 USD / 1M tokens with no compute cost, so
# 1500 tokens is a small but strictly non-zero figure — exactly the kind of
# value the bug replaced with 0.0.
MODEL = "text-embedding-3-small"
TOKENS = 1500
EXPECTED_COST_PER_OP = TOKENS / 1_000_000 * 0.02


class _FakePipeline:
    """Buffered pipeline with redis-py asyncio's awaitable-command shape."""

    def __init__(self, store):
        self._store = store
        self._queued = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def hincrby(self, key, field, amount=1):
        self._queued.append(lambda: self._store.raw_hincrby(key, field, amount))

    async def hincrbyfloat(self, key, field, amount):
        self._queued.append(lambda: self._store.raw_hincrbyfloat(key, field, amount))

    async def hgetall(self, key):
        self._queued.append(lambda: self._store.raw_hgetall(key))

    async def expire(self, key, ttl):
        self._queued.append(lambda: True)

    async def execute(self):
        results = [op() for op in self._queued]
        self._queued.clear()
        return results


class _FakeAsyncRedis:
    """Dict-backed stand-in that stores hash fields the way Redis does.

    HINCRBY and HINCRBYFLOAT both persist their result as a decimal *string*
    under a ``str`` field name; ``decoded`` selects whether the client hands
    those values back as ``str`` (the live ``decode_responses=True`` shape) or
    as ``bytes`` (a client configured without it).
    """

    def __init__(self, decoded=True):
        self._hashes = {}
        self._decoded = decoded

    # -- raw storage ---------------------------------------------------
    def raw_hincrby(self, key, field, amount):
        bucket = self._hashes.setdefault(key, {})
        bucket[field] = str(int(bucket.get(field, "0")) + amount)
        return int(bucket[field])

    def raw_hincrbyfloat(self, key, field, amount):
        bucket = self._hashes.setdefault(key, {})
        bucket[field] = repr(float(bucket.get(field, "0")) + amount)
        return float(bucket[field])

    def raw_hgetall(self, key):
        bucket = self._hashes.get(key, {})
        if self._decoded:
            return dict(bucket)
        # Field names stay str; only the values arrive as bytes.
        return {k: v.encode() for k, v in bucket.items()}

    # -- client surface ------------------------------------------------
    def pipeline(self):
        return _FakePipeline(self)

    async def setex(self, key, ttl, value):
        return True

    async def scan(self, cursor, match=None, count=None):
        prefix = match[:-1] if match and match.endswith("*") else match
        keys = [k for k in self._hashes if prefix is None or k.startswith(prefix)]
        if not self._decoded:
            keys = [k.encode() for k in keys]
        return 0, keys


def _analyzer(decoded=True):
    analyzer = EmbeddingPatternAnalyzer()
    analyzer._redis = _FakeAsyncRedis(decoded=decoded)
    return analyzer


def _request(success=True):
    return EmbeddingUsageRequest(
        model=MODEL,
        token_count=TOKENS,
        document_count=3,
        batch_size=10,
        processing_time=0.5,
        success=success,
    )


async def _record(analyzer, times=2):
    for _ in range(times):
        result = await analyzer.record_usage(_request())
        assert result["status"] == "recorded", result
    return analyzer


@pytest.mark.asyncio
async def test_daily_stats_round_trip_through_the_real_writer():
    """Pre-fix every one of these read back 0 / 0.0."""
    analyzer = await _record(_analyzer())

    result = await analyzer.get_stats(days=2)

    assert result["status"] == "success", result
    stats = result["stats"]
    assert stats["total_operations"] == 2, "hincrby wrote str fields the reader could not see"
    assert stats["total_tokens"] == 2 * TOKENS
    assert stats["total_documents"] == 6
    assert stats["total_cost"] == pytest.approx(2 * EXPECTED_COST_PER_OP, rel=1e-6)
    assert stats["total_cost"] > 0.0, "a billed embedding run must never report $0.00"
    assert stats["avg_processing_time"] == pytest.approx(0.5, rel=1e-6)
    assert stats["avg_batch_size"] == pytest.approx(10.0, rel=1e-6)
    assert stats["success_rate"] == pytest.approx(1.0, rel=1e-6)
    assert stats["tokens_per_second"] == pytest.approx(2 * TOKENS / 1.0, rel=1e-6)


@pytest.mark.asyncio
async def test_failed_operations_lower_the_success_rate():
    """successful_operations is a distinct hincrby field; it too was invisible."""
    analyzer = _analyzer()
    await analyzer.record_usage(_request(success=True))
    await analyzer.record_usage(_request(success=False))

    stats = (await analyzer.get_stats(days=2))["stats"]

    assert stats["total_operations"] == 2
    assert stats["success_rate"] == pytest.approx(0.5, rel=1e-6), "a 50% failure rate was reported as 100% success"


@pytest.mark.asyncio
async def test_model_comparison_round_trip_through_the_real_writer():
    """The per-model breakdown had the same bytes probes at _parse_model_stats."""
    analyzer = await _record(_analyzer())

    result = await analyzer.get_model_comparison()

    assert result["status"] == "success", result
    assert len(result["models"]) == 1, result["models"]
    model = result["models"][0]
    assert model["model"] == MODEL
    assert model["total_operations"] == 2
    assert model["total_tokens"] == 2 * TOKENS
    assert model["total_cost"] == pytest.approx(2 * EXPECTED_COST_PER_OP, rel=1e-6)
    assert model["total_cost"] > 0.0
    assert model["tokens_per_operation"] == pytest.approx(float(TOKENS), rel=1e-6)


@pytest.mark.asyncio
async def test_bytes_values_still_work():
    """decode_redis_value keeps a client without decode_responses working."""
    analyzer = await _record(_analyzer(decoded=False))

    stats = (await analyzer.get_stats(days=2))["stats"]
    models = (await analyzer.get_model_comparison())["models"]

    assert stats["total_operations"] == 2
    assert stats["total_cost"] == pytest.approx(2 * EXPECTED_COST_PER_OP, rel=1e-6)
    assert models[0]["model"] == MODEL, "a bytes scan key must still parse to the model name"
    assert models[0]["total_tokens"] == 2 * TOKENS


@pytest.mark.asyncio
async def test_no_usage_reports_zeros():
    """The one case that looked correct before the fix must still work."""
    analyzer = _analyzer()

    stats = (await analyzer.get_stats(days=2))["stats"]

    assert stats["total_operations"] == 0
    assert stats["total_cost"] == 0.0
    assert stats["success_rate"] == 1.0
    assert (await analyzer.get_model_comparison())["models"] == []
