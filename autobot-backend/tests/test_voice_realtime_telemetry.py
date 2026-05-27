# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pytest suite for VoiceRealtimeTelemetry.

Issue #7421 — covers:
- Metric counter increments on session start/end
- Cost calculation (audio + token rates)
- Cap-breach disconnect path (duration and cost)
- Redis persistence shape (keys and field presence)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_record(**kwargs):
    """Return a RealtimeSessionRecord with sensible defaults."""
    from services.voice_realtime_telemetry import RealtimeSessionRecord

    defaults: dict[str, Any] = {
        "session_id": "test-session-1",
        "user_id": "user-42",
        "model": "gpt-realtime-2",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "duration_s": 0.0,
        "audio_in_s": 0.0,
        "audio_out_s": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "tool_calls": 0,
        "estimated_cost_usd": 0.0,
        "disconnect_reason": "normal",
        "metadata": {},
    }
    defaults.update(kwargs)
    return RealtimeSessionRecord(**defaults)


def _fake_prom():
    """Return a MagicMock that mimics PrometheusMetricsManager._voice_realtime."""
    m = MagicMock()
    # All label calls return mock objects with .inc() / .observe()
    for attr in (
        "sessions_total",
        "sessions_active",
        "session_seconds_total",
        "session_duration",
        "audio_seconds_total",
        "tokens_total",
        "tool_calls_total",
        "tool_call_duration",
        "estimated_cost_usd",
        "cap_breaches_total",
    ):
        child = MagicMock()
        child.labels.return_value = child
        setattr(m, attr, child)
    return m


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCostCalculation:
    """Unit tests for _estimate_cost — pure function, no I/O."""

    def test_audio_only_cost(self):
        from services.voice_realtime_telemetry import _AUDIO_COST_PER_SEC, _estimate_cost

        rec = _make_record(audio_in_s=60.0, audio_out_s=30.0)
        expected = 60.0 * _AUDIO_COST_PER_SEC["input"] + 30.0 * _AUDIO_COST_PER_SEC["output"]
        assert abs(_estimate_cost(rec) - expected) < 1e-9

    def test_token_only_cost(self):
        from services.voice_realtime_telemetry import _TOKEN_COST_PER_1M, _estimate_cost

        rec = _make_record(input_tokens=1_000_000, output_tokens=500_000, cached_input_tokens=200_000)
        expected = (
            1_000_000 * _TOKEN_COST_PER_1M["input"] / 1_000_000
            + 500_000 * _TOKEN_COST_PER_1M["output"] / 1_000_000
            + 200_000 * _TOKEN_COST_PER_1M["cached_input"] / 1_000_000
        )
        assert abs(_estimate_cost(rec) - expected) < 1e-9

    def test_combined_cost(self):
        from services.voice_realtime_telemetry import _estimate_cost

        rec = _make_record(
            audio_in_s=10.0,
            audio_out_s=20.0,
            input_tokens=100,
            output_tokens=200,
        )
        cost = _estimate_cost(rec)
        assert cost > 0.0

    def test_zero_cost_for_empty_record(self):
        from services.voice_realtime_telemetry import _estimate_cost

        rec = _make_record()
        assert _estimate_cost(rec) == 0.0


class TestRedisShape:
    """Verify persistence key format and round-trip serialisation."""

    @pytest.mark.asyncio
    async def test_save_and_load_round_trip(self):
        from services.voice_realtime_telemetry import VoiceRealtimeTelemetry

        stored: dict[str, str] = {}

        async def fake_set(key, value, ex=None):
            stored[key] = value

        async def fake_get(key):
            return stored.get(key)

        fake_redis = AsyncMock()
        fake_redis.set = fake_set
        fake_redis.get = fake_get

        telemetry = VoiceRealtimeTelemetry.__new__(VoiceRealtimeTelemetry)
        telemetry._redis = fake_redis
        telemetry._model = "gpt-realtime-2"
        telemetry._max_seconds = 1800
        telemetry._max_cost_usd = 5.0
        telemetry._prom = MagicMock()
        telemetry._prom._voice_realtime = _fake_prom()

        rec = _make_record(session_id="abc-123", user_id="u1")
        await telemetry._save_record(rec)

        assert "voice_realtime_session:abc-123" in stored
        loaded = await telemetry._load_record("abc-123")
        assert loaded is not None
        assert loaded.session_id == "abc-123"
        assert loaded.user_id == "u1"

    @pytest.mark.asyncio
    async def test_load_returns_none_for_missing_key(self):
        from services.voice_realtime_telemetry import VoiceRealtimeTelemetry

        fake_redis = AsyncMock()
        fake_redis.get = AsyncMock(return_value=None)

        telemetry = VoiceRealtimeTelemetry.__new__(VoiceRealtimeTelemetry)
        telemetry._redis = fake_redis
        telemetry._prom = MagicMock()

        result = await telemetry._load_record("nonexistent")
        assert result is None


class TestMetricIncrements:
    """Verify Prometheus metric increments on session lifecycle calls."""

    def _make_telemetry(self, fake_redis, prom_mock):
        from services.voice_realtime_telemetry import VoiceRealtimeTelemetry

        t = VoiceRealtimeTelemetry.__new__(VoiceRealtimeTelemetry)
        t._redis = fake_redis
        t._model = "gpt-realtime-2"
        t._max_seconds = 1800
        t._max_cost_usd = 5.0
        t._prom = prom_mock
        return t

    @pytest.mark.asyncio
    async def test_session_start_increments_counter(self):
        stored: dict[str, str] = {}
        fake_redis = AsyncMock()
        fake_redis.set = AsyncMock(side_effect=lambda k, v, ex=None: stored.update({k: v}))
        fake_redis.get = AsyncMock(side_effect=lambda k: stored.get(k))

        prom = MagicMock()
        vr = _fake_prom()
        prom._voice_realtime = vr

        t = self._make_telemetry(fake_redis, prom)
        await t.session_start("s1", user_id="u1")

        vr.sessions_total.labels.assert_called_once_with(model="gpt-realtime-2")
        vr.sessions_total.inc.assert_called_once()
        vr.sessions_active.labels.assert_called_once_with(model="gpt-realtime-2")
        vr.sessions_active.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_end_emits_duration_counter(self):
        from services.voice_realtime_telemetry import DisconnectReason

        record = _make_record(
            session_id="s2",
            started_at=(datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat(),
        )
        stored = {"voice_realtime_session:s2": json.dumps(record.to_dict())}

        fake_redis = AsyncMock()
        fake_redis.set = AsyncMock(side_effect=lambda k, v, ex=None: stored.update({k: v}))
        fake_redis.get = AsyncMock(side_effect=lambda k: stored.get(k))

        prom = MagicMock()
        vr = _fake_prom()
        prom._voice_realtime = vr

        t = self._make_telemetry(fake_redis, prom)
        result = await t.session_end("s2", reason=DisconnectReason.NORMAL)

        assert result is not None
        assert result.duration_s >= 90.0
        vr.session_seconds_total.labels.assert_called()
        vr.session_seconds_total.inc.assert_called()
        vr.session_duration.labels.assert_called()

    @pytest.mark.asyncio
    async def test_response_done_increments_tokens(self):
        record = _make_record(session_id="s3")
        stored = {"voice_realtime_session:s3": json.dumps(record.to_dict())}

        fake_redis = AsyncMock()
        fake_redis.set = AsyncMock(side_effect=lambda k, v, ex=None: stored.update({k: v}))
        fake_redis.get = AsyncMock(side_effect=lambda k: stored.get(k))

        prom = MagicMock()
        vr = _fake_prom()
        prom._voice_realtime = vr

        t = self._make_telemetry(fake_redis, prom)
        await t.record_response_done("s3", input_tokens=500, output_tokens=250)

        vr.tokens_total.labels.assert_any_call(type="input")
        vr.tokens_total.inc.assert_any_call(500)

        loaded = await t._load_record("s3")
        assert loaded.input_tokens == 500
        assert loaded.output_tokens == 250

    @pytest.mark.asyncio
    async def test_tool_call_increments_counter(self):
        record = _make_record(session_id="s4")
        stored = {"voice_realtime_session:s4": json.dumps(record.to_dict())}

        fake_redis = AsyncMock()
        fake_redis.set = AsyncMock(side_effect=lambda k, v, ex=None: stored.update({k: v}))
        fake_redis.get = AsyncMock(side_effect=lambda k: stored.get(k))

        prom = MagicMock()
        vr = _fake_prom()
        prom._voice_realtime = vr

        t = self._make_telemetry(fake_redis, prom)
        await t.record_tool_call("s4", tool="search", latency_s=0.3, outcome="success")

        # tool_calls_total incremented in record_tool_call
        vr.tool_calls_total.labels.assert_called_with(tool="search", outcome="success")


class TestCapBreachDisconnect:
    """Verify CapBreachError is raised on threshold breach."""

    def _make_telemetry_with_record(self, record, max_seconds=1800, max_cost=5.0):
        from services.voice_realtime_telemetry import VoiceRealtimeTelemetry

        stored = {f"voice_realtime_session:{record.session_id}": json.dumps(record.to_dict())}
        fake_redis = AsyncMock()
        fake_redis.get = AsyncMock(side_effect=lambda k: stored.get(k))

        t = VoiceRealtimeTelemetry.__new__(VoiceRealtimeTelemetry)
        t._redis = fake_redis
        t._model = "gpt-realtime-2"
        t._max_seconds = max_seconds
        t._max_cost_usd = max_cost
        t._prom = MagicMock()
        return t

    @pytest.mark.asyncio
    async def test_duration_cap_raises(self):
        from services.voice_realtime_telemetry import CapBreachError, DisconnectReason

        record = _make_record(
            session_id="cap1",
            started_at=(datetime.now(timezone.utc) - timedelta(seconds=1810)).isoformat(),
        )
        t = self._make_telemetry_with_record(record, max_seconds=1800)

        with pytest.raises(CapBreachError) as exc_info:
            await t.check_caps("cap1")

        assert exc_info.value.reason == DisconnectReason.DURATION_CAP
        assert "minute limit" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cost_cap_raises(self):
        from services.voice_realtime_telemetry import CapBreachError, DisconnectReason

        record = _make_record(
            session_id="cap2",
            # 90 min of output audio at $0.004/s ≈ $21.6 — well over $5 cap
            audio_out_s=5400.0,
        )
        t = self._make_telemetry_with_record(record, max_cost=5.0)

        with pytest.raises(CapBreachError) as exc_info:
            await t.check_caps("cap2")

        assert exc_info.value.reason == DisconnectReason.COST_CAP
        assert "cost limit" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_breach_within_limits(self):
        pass

        record = _make_record(
            session_id="cap3",
            started_at=(datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(),
            audio_out_s=10.0,
        )
        t = self._make_telemetry_with_record(record, max_seconds=1800, max_cost=5.0)

        # Should not raise
        await t.check_caps("cap3")


class TestSessionTTL:
    """Verify _SESSION_TTL is read from env var with correct default."""

    def test_default_ttl_is_90_days(self):
        import services.voice_realtime_telemetry as mod

        assert mod._SESSION_TTL == 90 * 24 * 3600

    def test_env_var_overrides_ttl(self):
        import importlib

        import services.voice_realtime_telemetry as mod

        custom_ttl = 7 * 24 * 3600  # 7 days
        with patch.dict(os.environ, {"AUTOBOT_VOICE_REALTIME_SESSION_TTL": str(custom_ttl)}):
            importlib.reload(mod)
            assert mod._SESSION_TTL == custom_ttl
        importlib.reload(mod)  # restore default for subsequent tests

    @pytest.mark.asyncio
    async def test_save_record_passes_ttl_to_redis(self):
        from services.voice_realtime_telemetry import VoiceRealtimeTelemetry, _SESSION_TTL

        captured: list[int] = []

        async def fake_set(key, value, ex=None):
            captured.append(ex)

        fake_redis = AsyncMock()
        fake_redis.set = fake_set

        t = VoiceRealtimeTelemetry.__new__(VoiceRealtimeTelemetry)
        t._redis = fake_redis

        rec = _make_record(session_id="ttl-test")
        await t._save_record(rec)

        assert captured == [_SESSION_TTL]
