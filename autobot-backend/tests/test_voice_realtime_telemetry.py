# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from autobot_shared.time_utils import utc_timestamp
from testkit.fake_redis_pipeline import FakeAsyncPipeline

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_record(**kwargs):
    """Return a RealtimeSessionRecord with sensible defaults."""
    from services.voice_realtime_telemetry import RealtimeSessionRecord

    defaults: dict[str, Any] = {
        "session_id": "test-session-1",
        "user_id": "user-42",
        "model": "gpt-realtime-2",
        "started_at": utc_timestamp(),
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


def _bare_telemetry(fake_redis, prom=None, max_seconds=1800, max_cost=5.0):
    """Construct VoiceRealtimeTelemetry via __new__ with all attrs __init__ sets.

    Mirrors __init__ including _config/_in_memory_sessions added by the
    telemetry opt-out feature (commit 50b5e13d3, Issue #9035); telemetry is
    enabled so the Redis persistence path is exercised.
    """
    from services.voice_realtime_telemetry import VoiceRealtimeTelemetry

    t = VoiceRealtimeTelemetry.__new__(VoiceRealtimeTelemetry)
    t._redis = fake_redis
    t._model = "gpt-realtime-2"
    t._max_seconds = max_seconds
    t._max_cost_usd = max_cost
    t._prom = prom if prom is not None else MagicMock()
    t._config = MagicMock()
    t._config.telemetry.enabled = True
    t._in_memory_sessions = {}
    return t


class _FakeRedis:
    """One in-memory Redis shared by every worker under test; its pipeline is the canonical fake (#18991)."""

    def __init__(self, stored: dict[str, str] | None = None):
        self.stored: dict[str, str] = stored if stored is not None else {}

    async def get(self, key):
        return self.stored.get(key)

    async def set(self, key, value, ex=None):
        self.stored[key] = value

    def pipeline(self, transaction=True):
        return FakeAsyncPipeline(self, transaction=transaction, detect_watch_conflicts=True)


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
        stored: dict[str, str] = {}

        async def fake_set(key, value, ex=None):
            stored[key] = value

        async def fake_get(key):
            return stored.get(key)

        fake_redis = AsyncMock()
        fake_redis.set = fake_set
        fake_redis.get = fake_get

        telemetry = _bare_telemetry(fake_redis)
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
        fake_redis = AsyncMock()
        fake_redis.get = AsyncMock(return_value=None)

        telemetry = _bare_telemetry(fake_redis)

        result = await telemetry._load_record("nonexistent")
        assert result is None


class TestMetricIncrements:
    """Verify Prometheus metric increments on session lifecycle calls."""

    def _make_telemetry(self, fake_redis, prom_mock):
        return _bare_telemetry(fake_redis, prom=prom_mock)

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

        fake_redis = _FakeRedis(stored)

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

        fake_redis = _FakeRedis(stored)

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

        fake_redis = _FakeRedis(stored)

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
        stored = {f"voice_realtime_session:{record.session_id}": json.dumps(record.to_dict())}
        fake_redis = AsyncMock()
        fake_redis.get = AsyncMock(side_effect=lambda k: stored.get(k))

        return _bare_telemetry(fake_redis, max_seconds=max_seconds, max_cost=max_cost)

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
        import sys

        custom_days = 7  # 7 days
        custom_ttl = custom_days * 24 * 3600
        with patch.dict(os.environ, {"AUTOBOT_VOICE_REALTIME_SESSION_TTL_DAYS": str(custom_days)}):
            # Must reload ssot_config first, then voice_realtime_telemetry
            if "autobot_shared.ssot_config" in sys.modules:
                importlib.reload(sys.modules["autobot_shared.ssot_config"])
            import services.voice_realtime_telemetry as mod

            importlib.reload(mod)
            assert mod._SESSION_TTL == custom_ttl

        # Restore defaults
        if "autobot_shared.ssot_config" in sys.modules:
            importlib.reload(sys.modules["autobot_shared.ssot_config"])
        import services.voice_realtime_telemetry as mod

        importlib.reload(mod)

    @pytest.mark.asyncio
    async def test_save_record_passes_ttl_to_redis(self):
        from services.voice_realtime_telemetry import _SESSION_TTL

        captured: list[int] = []

        async def fake_set(key, value, ex=None):
            captured.append(ex)

        fake_redis = AsyncMock()
        fake_redis.set = fake_set

        t = _bare_telemetry(fake_redis)

        rec = _make_record(session_id="ttl-test")
        await t._save_record(rec)

        assert captured == [_SESSION_TTL]


class TestConsentChangesMidSession:
    """Active session state survives an opt-out/opt-in flip; consent only governs persistence (#9035)."""

    @staticmethod
    def _consent(monkeypatch, enabled):
        monkeypatch.setattr("services.voice_realtime_telemetry.get_telemetry_settings", lambda: {"enabled": enabled})

    @pytest.mark.asyncio
    async def test_a_session_started_opted_in_is_still_capped_after_an_opt_out(self, monkeypatch):
        from services.voice_realtime_telemetry import CapBreachError

        t = _bare_telemetry(AsyncMock(), max_seconds=1800)
        self._consent(monkeypatch, True)
        record = _make_record(
            session_id="flip1",
            started_at=(datetime.now(timezone.utc) - timedelta(seconds=1810)).isoformat(),
        )
        await t._save_record(record)
        self._consent(monkeypatch, False)
        with pytest.raises(CapBreachError):
            await t.check_caps("flip1")

    @pytest.mark.asyncio
    async def test_a_session_started_opted_out_can_still_end_after_an_opt_in(self, monkeypatch):
        t = _bare_telemetry(_FakeRedis())
        t._prom = MagicMock()
        self._consent(monkeypatch, False)
        await t._save_record(_make_record(session_id="flip2"))
        self._consent(monkeypatch, True)
        ended = await t.session_end("flip2")
        assert ended is not None and ended.ended_at
        assert "flip2" not in t._in_memory_sessions  # persisted to Redis, so memory lets go

    @pytest.mark.asyncio
    async def test_nothing_reaches_redis_while_opted_out(self, monkeypatch):
        redis = AsyncMock()
        t = _bare_telemetry(redis)
        self._consent(monkeypatch, False)
        await t._save_record(_make_record(session_id="off1"))
        redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_finished_record_is_released_when_redis_is_down(self, monkeypatch):
        t = _bare_telemetry(None)
        t._get_redis = AsyncMock(return_value=None)
        self._consent(monkeypatch, True)
        await t._save_record(_make_record(session_id="r1"))
        assert "r1" in t._in_memory_sessions
        await t._save_record(_make_record(session_id="r1", ended_at=datetime.now(timezone.utc).isoformat()))
        assert "r1" not in t._in_memory_sessions

    @pytest.mark.asyncio
    async def test_a_finished_record_is_released_when_telemetry_is_off(self, monkeypatch):
        t = _bare_telemetry(AsyncMock())
        self._consent(monkeypatch, False)
        await t._save_record(_make_record(session_id="r2"))
        await t._save_record(_make_record(session_id="r2", ended_at=datetime.now(timezone.utc).isoformat()))
        assert "r2" not in t._in_memory_sessions

    @pytest.mark.asyncio
    async def test_an_abandoned_session_older_than_the_max_age_is_evicted(self, monkeypatch):
        from services import voice_realtime_telemetry as module

        t = _bare_telemetry(AsyncMock())
        self._consent(monkeypatch, False)
        threshold = module.abandoned_session_max_age_s(t._max_seconds)
        old = (datetime.now(timezone.utc) - timedelta(seconds=threshold + 60)).isoformat()
        t._in_memory_sessions["gone"] = _make_record(session_id="gone", started_at=old)
        await t._save_record(_make_record(session_id="fresh"))
        assert "gone" not in t._in_memory_sessions
        assert "fresh" in t._in_memory_sessions

    @pytest.mark.asyncio
    async def test_a_session_younger_than_the_cap_is_not_evicted_when_cap_exceeds_the_age(self, monkeypatch):
        from services import voice_realtime_telemetry as module

        cap = module._ABANDONED_SESSION_MAX_AGE_S * 2
        t = _bare_telemetry(AsyncMock(), max_seconds=cap)
        self._consent(monkeypatch, False)
        assert module.abandoned_session_max_age_s(cap) > module._ABANDONED_SESSION_MAX_AGE_S
        started = datetime.now(timezone.utc) - timedelta(seconds=module._ABANDONED_SESSION_MAX_AGE_S + 60)
        t._in_memory_sessions["live"] = _make_record(session_id="live", started_at=started.isoformat())
        await t._save_record(_make_record(session_id="fresh"))
        assert "live" in t._in_memory_sessions


class TestRedisIsSystemOfRecordAcrossWorkers:
    """Two workers share one Redis; a stale local copy must never answer a cap check or clobber usage (#21678)."""

    @staticmethod
    def _workers(monkeypatch):
        monkeypatch.setattr("services.voice_realtime_telemetry.get_telemetry_settings", lambda: {"enabled": True})
        server = _FakeRedis()
        a, b = _bare_telemetry(server), _bare_telemetry(server)
        for t in (a, b):
            t._prom = MagicMock()
        return server, a, b

    @pytest.mark.asyncio
    async def test_cap_check_on_one_worker_sees_usage_recorded_by_another(self, monkeypatch):
        from services.voice_realtime_telemetry import CapBreachError, DisconnectReason

        _, a, b = self._workers(monkeypatch)
        await a.session_start("x1")
        await b.record_audio("x1", "output", 5400.0)  # ~$18, over the $5 cap; A's local copy is still zero
        assert a._in_memory_sessions["x1"].audio_out_s == 0.0
        with pytest.raises(CapBreachError) as exc:
            await a.check_caps("x1")
        assert exc.value.reason == DisconnectReason.COST_CAP

    @pytest.mark.asyncio
    async def test_session_end_on_one_worker_keeps_usage_recorded_by_another(self, monkeypatch):
        server, a, b = self._workers(monkeypatch)
        await a.session_start("x2")
        await b.record_response_done("x2", input_tokens=700, output_tokens=300)
        await b.record_tool_call("x2", tool="search")
        ended = await a.session_end("x2")
        stored = json.loads(server.stored["voice_realtime_session:x2"])
        assert (stored["input_tokens"], stored["output_tokens"], stored["tool_calls"]) == (700, 300, 1)
        assert stored["ended_at"] and ended.input_tokens == 700
        assert "x2" not in a._in_memory_sessions

    @pytest.mark.asyncio
    async def test_a_write_between_read_and_commit_is_retried_not_overwritten(self, monkeypatch):
        server, a, b = self._workers(monkeypatch)
        await a.session_start("x3")
        key = "voice_realtime_session:x3"
        interleaved = []

        def add_forty(record):
            if not interleaved:  # worker B commits after A has read and before A commits
                interleaved.append(1)
                other = json.loads(server.stored[key])
                other["input_tokens"] = 100
                server.stored[key] = json.dumps(other)
            record.input_tokens += 40

        await a._update_record("x3", add_forty)
        assert json.loads(server.stored[key])["input_tokens"] == 140

    @pytest.mark.asyncio
    async def test_a_session_started_while_redis_was_down_is_updated_locally_then_persisted(self, monkeypatch):
        server, a, _ = self._workers(monkeypatch)
        a._redis = None
        a._get_redis = AsyncMock(return_value=None)
        await a.session_start("x4")
        await a.record_response_done("x4", input_tokens=9)
        assert a._in_memory_sessions["x4"].input_tokens == 9 and not server.stored
        a._get_redis = AsyncMock(return_value=server)
        await a.record_response_done("x4", input_tokens=1)
        assert json.loads(server.stored["voice_realtime_session:x4"])["input_tokens"] == 10
