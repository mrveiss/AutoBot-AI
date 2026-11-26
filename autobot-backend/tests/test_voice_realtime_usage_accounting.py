# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cross-worker and delta accounting tests for VoiceRealtimeTelemetry (#21678)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.voice_realtime_usage import EndedSession, UsageDelta
from tests.helpers._voice_realtime_fakes import FakeRedis as _FakeRedis
from tests.helpers._voice_realtime_fakes import bare_telemetry as _bare_telemetry
from tests.helpers._voice_realtime_fakes import make_record as _make_record


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
        from services import voice_realtime_telemetry as module

        server, a, _ = self._workers(monkeypatch)
        await a.session_start("x3")
        key = "voice_realtime_session:x3"
        interleaved = []
        real_apply = module.UsageDelta.apply_to

        def apply_with_a_write_in_between(delta, record):
            if not interleaved:  # worker B commits after A has read and before A commits
                interleaved.append(1)
                other = json.loads(server.stored[key])
                other["input_tokens"] = 100
                server.stored[key] = json.dumps(other)
            real_apply(delta, record)

        monkeypatch.setattr(module.UsageDelta, "apply_to", apply_with_a_write_in_between)
        await a.record_response_done("x3", input_tokens=40)
        assert json.loads(server.stored[key])["input_tokens"] == 140

    @pytest.mark.asyncio
    async def test_a_session_started_while_redis_was_down_keeps_its_usage_pending_then_flushes_it(self, monkeypatch):
        server, a, _ = self._workers(monkeypatch)
        a._get_redis = AsyncMock(return_value=None)
        await a.session_start("x4")
        await a.record_response_done("x4", input_tokens=9)
        assert (await a.get_session("x4")).input_tokens == 9 and not server.stored
        a._get_redis = AsyncMock(return_value=server)
        await a.record_response_done("x4", input_tokens=1)
        assert json.loads(server.stored["voice_realtime_session:x4"])["input_tokens"] == 10
        assert a._pending == {}


class TestDeltaAccounting:
    """Usage is added as deltas: no write failure, consent flip or missing-key race replaces a larger total (#21678)."""

    @staticmethod
    def _setup(monkeypatch, enabled=True, max_cost=5.0):
        state = {"enabled": enabled}
        monkeypatch.setattr("services.voice_realtime_telemetry.get_telemetry_settings", lambda: state)
        server = _FakeRedis()
        t = _bare_telemetry(server, max_cost=max_cost)
        t._prom = MagicMock()
        return state, server, t

    @pytest.mark.asyncio
    async def test_a_consent_flip_counts_opted_out_usage_for_the_cap_but_never_persists_it(self, monkeypatch):
        from services.voice_realtime_telemetry import CapBreachError

        state, server, t = self._setup(monkeypatch)
        await t.session_start("c1")
        writes = []
        real_set = server.set

        async def recording_set(key, value, ex=None):
            writes.append((state["enabled"], key))
            await real_set(key, value, ex=ex)

        server.set = recording_set
        state["enabled"] = False
        await t.record_audio("c1", "output", 1200.0)  # ~ $4 collected while opted out
        assert not [w for w in writes if not w[0]]  # no voice_realtime_session:* write while opted out
        state["enabled"] = True
        await t.check_caps("c1")  # $4 is under the $5 cap, and already counted
        await t.record_audio("c1", "output", 600.0)  # ~ $2 more opted in: the real total is ~ $6
        with pytest.raises(CapBreachError):
            await t.check_caps("c1")
        assert json.loads(server.stored["voice_realtime_session:c1"])["audio_out_s"] == 600.0  # never the 1200 s

    @pytest.mark.asyncio
    async def test_a_session_ended_while_opted_out_is_never_persisted_after_an_opt_in(self, monkeypatch):
        state, server, t = self._setup(monkeypatch)
        await t.session_start("c5")
        before = dict(server.stored)
        state["enabled"] = False
        await t.record_audio("c5", "output", 100.0)
        ended = await t.session_end("c5")
        assert ended.ended_at and "c5" not in t._in_memory_sessions
        assert t._ended_unflushed == {} and t._cap_only == {} and t._pending == {}
        state["enabled"] = True
        await t.session_start("other")  # any operation reaches Redis again
        await t.record_audio("other", "input", 1.0)
        assert server.stored["voice_realtime_session:c5"] == before["voice_realtime_session:c5"]

    @pytest.mark.asyncio
    async def test_a_retried_end_that_already_landed_adds_no_usage_twice(self, monkeypatch):
        _, server, t = self._setup(monkeypatch)
        await t.session_start("c6")
        await t.record_response_done("c6", input_tokens=100)
        local = t._in_memory_sessions["c6"]
        ended = await t.session_end("c6")  # committed
        t._ended_unflushed["c6"] = EndedSession(local, UsageDelta(input_tokens=100), ended)  # queued again
        await t.session_start("other")
        assert json.loads(server.stored["voice_realtime_session:c6"])["input_tokens"] == 100

    @pytest.mark.asyncio
    async def test_the_opted_out_usage_counts_toward_the_cap_before_any_flush(self, monkeypatch):
        from services.voice_realtime_telemetry import CapBreachError

        state, _, t = self._setup(monkeypatch)
        await t.session_start("c2")
        state["enabled"] = False
        await t.record_audio("c2", "output", 1800.0)  # ~ $6
        state["enabled"] = True
        with pytest.raises(CapBreachError):
            await t.check_caps("c2")

    @pytest.mark.asyncio
    async def test_a_failed_commit_is_kept_pending_and_counted_once_when_a_later_commit_succeeds(self, monkeypatch):
        from services import voice_realtime_telemetry as module

        _, server, t = self._setup(monkeypatch)
        await t.session_start("c3")
        real = module.update_in_redis
        monkeypatch.setattr(module, "update_in_redis", AsyncMock(side_effect=ConnectionError("down")))
        await t.record_response_done("c3", input_tokens=500)
        assert (await t.get_session("c3")).input_tokens == 500  # the cap sees it although Redis never did
        assert json.loads(server.stored["voice_realtime_session:c3"])["input_tokens"] == 0
        monkeypatch.setattr(module, "update_in_redis", real)
        await t.record_response_done("c3", input_tokens=20)
        assert json.loads(server.stored["voice_realtime_session:c3"])["input_tokens"] == 520
        assert (await t.get_session("c3")).input_tokens == 520 and t._pending == {}

    @pytest.mark.asyncio
    async def test_concurrent_updates_on_a_missing_key_are_both_counted(self, monkeypatch):
        import asyncio

        _, server, t = self._setup(monkeypatch)
        await t.session_start("c4")
        server.stored.clear()  # the key expired; this worker still holds the started record

        real_get = server.get

        async def yielding_get(key):
            await asyncio.sleep(0)  # lets the other update interleave between read and commit
            return await real_get(key)

        server.get = yielding_get
        await asyncio.gather(t.record_response_done("c4", input_tokens=3), t.record_response_done("c4", input_tokens=4))
        assert json.loads(server.stored["voice_realtime_session:c4"])["input_tokens"] == 7


class TestUnreadableRedis:
    """An unreadable Redis falls back to the local record, so the cost cap still runs (#21678)."""

    @pytest.mark.asyncio
    async def test_cap_check_uses_the_local_record_when_the_redis_read_fails(self, monkeypatch):
        from services.voice_realtime_telemetry import CapBreachError

        monkeypatch.setattr("services.voice_realtime_telemetry.get_telemetry_settings", lambda: {"enabled": True})
        redis = _FakeRedis()
        redis.get = AsyncMock(side_effect=ConnectionError("redis down"))
        t = _bare_telemetry(redis)
        t._in_memory_sessions["d1"] = _make_record(session_id="d1", audio_out_s=5400.0)
        with pytest.raises(CapBreachError):
            await t.check_caps("d1")

    @pytest.mark.asyncio
    async def test_a_session_nobody_can_read_is_not_capped(self, monkeypatch):
        monkeypatch.setattr("services.voice_realtime_telemetry.get_telemetry_settings", lambda: {"enabled": True})
        redis = _FakeRedis()
        redis.get = AsyncMock(side_effect=ConnectionError("redis down"))
        await _bare_telemetry(redis).check_caps("unknown")  # existing behaviour: no record, no breach


class TestSessionEndedDuringAnOutage:
    """A session that ends while Redis is unreachable is flushed when Redis returns, once (#21678)."""

    @staticmethod
    async def _ended_during_outage(monkeypatch, tail_tokens=400):
        monkeypatch.setattr("services.voice_realtime_telemetry.get_telemetry_settings", lambda: {"enabled": True})
        server = _FakeRedis()
        t = _bare_telemetry(server)
        t._prom = MagicMock()
        await t.session_start("o1")
        await t.record_response_done("o1", input_tokens=100)
        t._get_redis = AsyncMock(return_value=None)  # outage
        await t.record_response_done("o1", input_tokens=tail_tokens)
        ended = await t.session_end("o1")
        return server, t, ended

    @pytest.mark.asyncio
    async def test_redis_holds_the_end_and_the_full_usage_once_after_the_next_operation(self, monkeypatch):
        server, t, ended = await self._ended_during_outage(monkeypatch)
        stored = json.loads(server.stored["voice_realtime_session:o1"])
        assert stored["ended_at"] is None and stored["input_tokens"] == 100  # the outage left the tail behind
        assert "o1" not in t._in_memory_sessions and "o1" in t._ended_unflushed
        t._get_redis = AsyncMock(return_value=server)
        await t.session_start("other")  # any operation that reaches Redis flushes it
        stored = json.loads(server.stored["voice_realtime_session:o1"])
        assert stored["ended_at"] == ended.ended_at and stored["duration_s"] == ended.duration_s
        assert stored["input_tokens"] == 500 and stored["estimated_cost_usd"] > 0
        await t.record_audio("other", "input", 1.0)  # a later operation must not apply it again
        assert json.loads(server.stored["voice_realtime_session:o1"])["input_tokens"] == 500
        assert t._ended_unflushed == {}

    @pytest.mark.asyncio
    async def test_an_unflushed_ended_session_past_the_abandoned_age_is_dropped_with_a_warning(
        self, monkeypatch, caplog
    ):
        from datetime import datetime, timedelta, timezone

        from services import voice_realtime_telemetry as module

        _, t, _ = await self._ended_during_outage(monkeypatch)
        old = datetime.now(timezone.utc) - timedelta(seconds=module.abandoned_session_max_age_s(t._max_seconds) + 60)
        t._ended_unflushed["o1"].ended.ended_at = old.isoformat()
        t._evict_abandoned_sessions()
        assert t._ended_unflushed == {} and "session_id=o1" in caplog.text
