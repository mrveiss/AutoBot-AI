# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared doubles for the voice realtime telemetry tests (#21678)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from autobot_shared.time_utils import utc_timestamp
from testkit.fake_redis_pipeline import FakeAsyncPipeline


def make_record(**kwargs):
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


def bare_telemetry(fake_redis, prom=None, max_seconds=1800, max_cost=5.0):
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
    t._pending = {}
    t._ended_unflushed = {}
    return t


class FakeRedis:
    """One in-memory Redis shared by every worker under test; its pipeline is the canonical fake (#18991)."""

    def __init__(self, stored: dict[str, str] | None = None):
        self.stored: dict[str, str] = stored if stored is not None else {}

    async def get(self, key):
        return self.stored.get(key)

    async def set(self, key, value, ex=None):
        self.stored[key] = value

    def pipeline(self, transaction=True):
        return FakeAsyncPipeline(self, transaction=transaction, detect_watch_conflicts=True)
