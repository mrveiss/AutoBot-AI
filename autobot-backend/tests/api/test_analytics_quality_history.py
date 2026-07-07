# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for real quality-trend history and remediation delta surfacing.

Issue #11203: verifies:
  1. _persist_health_snapshot writes and caps the Redis sorted set.
  2. _build_quality_trends returns REAL history when available; falls back
     to the flat synthetic line when Redis is empty or unreachable.
  3. _read_remediation_deltas reads remediation:delta:history; returns []
     when there is no history or Redis is unavailable.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.analytics_quality import (
    QUALITY_HISTORY_MAX_POINTS,
    _DELTA_HISTORY_KEY,
    _HEALTH_HISTORY_KEY,
    _QUALITY_WEIGHTS,
    _build_quality_trends,
    _persist_health_snapshot,
    _read_remediation_deltas,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_METRICS: dict[str, float] = {
    "maintainability": 80.0,
    "reliability": 75.0,
    "security": 90.0,
    "performance": 70.0,
    "testability": 60.0,
    "documentation": 65.0,
    "runtime_risk": 100.0,
}

_PATCH_TARGET = "autobot_shared.redis_client.get_async_redis_client"


def _flat_score(metrics: dict) -> float:
    return sum(metrics.get(c, 0) * w for c, w in _QUALITY_WEIGHTS.items())


def _make_redis_mock(*, zrange_entries: list[str] | None = None) -> AsyncMock:
    """Return a minimal async Redis stub."""
    redis = AsyncMock()
    redis.zadd = AsyncMock(return_value=1)
    redis.zremrangebyrank = AsyncMock(return_value=0)
    redis.zrangebyscore = AsyncMock(return_value=zrange_entries or [])
    redis.zrevrange = AsyncMock(return_value=[])
    return redis


# ---------------------------------------------------------------------------
# _persist_health_snapshot
# ---------------------------------------------------------------------------


class TestPersistHealthSnapshot:
    @pytest.mark.asyncio
    async def test_writes_one_entry_to_sorted_set(self):
        redis = _make_redis_mock()
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            await _persist_health_snapshot(78.5, _SAMPLE_METRICS)

        redis.zadd.assert_awaited_once()
        call_args = redis.zadd.call_args
        key = call_args.args[0]
        assert key == _HEALTH_HISTORY_KEY
        payload_map: dict = call_args.args[1]
        assert len(payload_map) == 1
        raw_payload = list(payload_map.keys())[0]
        rec = json.loads(raw_payload)
        assert rec["score"] == pytest.approx(78.5, abs=0.01)
        assert "ts" in rec
        assert "metrics" in rec

    @pytest.mark.asyncio
    async def test_caps_sorted_set_with_zremrangebyrank(self):
        redis = _make_redis_mock()
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            await _persist_health_snapshot(78.5, _SAMPLE_METRICS)

        redis.zremrangebyrank.assert_awaited_once()
        args = redis.zremrangebyrank.call_args.args
        assert args[0] == _HEALTH_HISTORY_KEY
        assert args[1] == 0
        assert args[2] == -(QUALITY_HISTORY_MAX_POINTS + 1)

    @pytest.mark.asyncio
    async def test_degrades_gracefully_on_redis_error(self):
        """Redis failure must not raise — metric computation continues."""
        with patch(
            _PATCH_TARGET,
            new=AsyncMock(side_effect=RuntimeError("connection refused")),
        ):
            # Should not raise
            await _persist_health_snapshot(78.5, _SAMPLE_METRICS)


# ---------------------------------------------------------------------------
# _build_quality_trends
# ---------------------------------------------------------------------------


class TestBuildQualityTrends:
    @pytest.mark.asyncio
    async def test_returns_real_history_when_available(self):
        entries = [
            json.dumps({"ts": "2026-01-01T00:00:00+00:00", "score": 72.0}),
            json.dumps({"ts": "2026-01-02T00:00:00+00:00", "score": 74.5}),
        ]
        redis = _make_redis_mock(zrange_entries=entries)
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            result = await _build_quality_trends(_SAMPLE_METRICS, days=30)

        assert len(result) == 2
        assert result[0]["score"] == pytest.approx(72.0)
        assert result[1]["score"] == pytest.approx(74.5)
        assert result[0]["date"] == "2026-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_falls_back_to_flat_when_history_empty(self):
        redis = _make_redis_mock(zrange_entries=[])
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            result = await _build_quality_trends(_SAMPLE_METRICS, days=7)

        expected_score = _flat_score(_SAMPLE_METRICS)
        assert len(result) == 8  # days=7 → range(7, -1, -1) → 8 points
        for point in result:
            assert point["score"] == pytest.approx(expected_score, rel=1e-6)

    @pytest.mark.asyncio
    async def test_falls_back_to_flat_on_redis_error(self):
        with patch(
            _PATCH_TARGET,
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            result = await _build_quality_trends(_SAMPLE_METRICS, days=7)

        assert len(result) == 8
        expected_score = _flat_score(_SAMPLE_METRICS)
        for point in result:
            assert point["score"] == pytest.approx(expected_score, rel=1e-6)

    @pytest.mark.asyncio
    async def test_returns_dict_with_date_and_score_keys(self):
        redis = _make_redis_mock(zrange_entries=[])
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            result = await _build_quality_trends(_SAMPLE_METRICS)

        for point in result:
            assert "date" in point
            assert "score" in point

    @pytest.mark.asyncio
    async def test_skips_malformed_json_entries(self):
        entries = [
            "not-valid-json",
            json.dumps({"ts": "2026-01-01T00:00:00+00:00", "score": 80.0}),
        ]
        redis = _make_redis_mock(zrange_entries=entries)
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            result = await _build_quality_trends(_SAMPLE_METRICS, days=30)

        # Only the valid entry should survive; malformed one is skipped
        assert len(result) == 1
        assert result[0]["score"] == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# _read_remediation_deltas
# ---------------------------------------------------------------------------


class TestReadRemediationDeltas:
    @pytest.mark.asyncio
    async def test_returns_deltas_when_history_exists(self):
        delta_record = {
            "timestamp": "2026-06-01T12:00:00+00:00",
            "health_delta": 3.5,
            "findings_delta": -2,
            "before_health": 70.0,
            "after_health": 73.5,
            "source": "remediation_delta",
        }
        redis = AsyncMock()
        redis.zrevrange = AsyncMock(return_value=[json.dumps(delta_record)])
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            result = await _read_remediation_deltas(50)

        assert len(result) == 1
        assert result[0]["health_delta"] == pytest.approx(3.5)
        assert result[0]["findings_delta"] == -2
        assert result[0]["before_health"] == pytest.approx(70.0)
        assert result[0]["after_health"] == pytest.approx(73.5)
        assert result[0]["ts"] == "2026-06-01T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_history(self):
        redis = AsyncMock()
        redis.zrevrange = AsyncMock(return_value=[])
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            result = await _read_remediation_deltas(50)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_redis_error(self):
        with patch(
            _PATCH_TARGET,
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            result = await _read_remediation_deltas(50)

        assert result == []

    @pytest.mark.asyncio
    async def test_reads_from_correct_key(self):
        redis = AsyncMock()
        redis.zrevrange = AsyncMock(return_value=[])
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            await _read_remediation_deltas(10)

        redis.zrevrange.assert_awaited_once()
        key_arg = redis.zrevrange.call_args.args[0]
        assert key_arg == _DELTA_HISTORY_KEY

    @pytest.mark.asyncio
    async def test_limit_is_passed_to_zrevrange(self):
        redis = AsyncMock()
        redis.zrevrange = AsyncMock(return_value=[])
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            await _read_remediation_deltas(25)

        args = redis.zrevrange.call_args.args
        # zrevrange(key, 0, limit-1)
        assert args[2] == 24

    @pytest.mark.asyncio
    async def test_skips_malformed_json_entries(self):
        redis = AsyncMock()
        redis.zrevrange = AsyncMock(
            return_value=[
                "bad-json",
                json.dumps({"timestamp": "2026-01-01T00:00:00+00:00", "health_delta": 1.0, "findings_delta": -1}),
            ]
        )
        with patch(_PATCH_TARGET, new=AsyncMock(return_value=redis)):
            result = await _read_remediation_deltas(50)

        assert len(result) == 1
        assert result[0]["health_delta"] == pytest.approx(1.0)
