# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for TTS synthesis throughput metrics (#12460).

The real-time factor is what separates "speech starts late" (fixed in #13215)
from "speech stutters": below 1.0x the player drains its buffer faster than the
worker refills it. These tests pin that the factor is computed, exported, and
that the below-real-time counter only moves when it should.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry

from autobot_shared.monitoring.metrics.tts import REALTIME_FACTOR_FLOOR, TTSMetricsRecorder


def _sample(registry: CollectorRegistry, name: str, **labels: str) -> float | None:
    """Return one exported sample value, or None when it was never recorded."""
    return registry.get_sample_value(name, labels or None)


class TestTTSMetricsRecorder:
    """TTSMetricsRecorder throughput recording."""

    def test_below_real_time_synthesis_is_counted_and_exported(self) -> None:
        """3.4s of audio in 15s is 0.22x — the measured stutter case from #12460."""
        registry = CollectorRegistry()
        recorder = TTSMetricsRecorder(registry)

        recorder.record_synthesis("stream", audio_seconds=3.36, wall_seconds=15.03)

        assert _sample(registry, "autobot_tts_synthesis_total", route="stream") == 1.0
        assert _sample(registry, "autobot_tts_synthesis_below_realtime_total", route="stream") == 1.0
        factor = _sample(registry, "autobot_tts_realtime_factor_last", route="stream")
        assert factor is not None
        assert factor < REALTIME_FACTOR_FLOOR

    def test_real_time_synthesis_does_not_move_the_below_real_time_counter(self) -> None:
        """A worker keeping up is counted as a synthesis but not as a shortfall."""
        registry = CollectorRegistry()
        recorder = TTSMetricsRecorder(registry)

        recorder.record_synthesis("stream", audio_seconds=4.0, wall_seconds=2.0)

        assert _sample(registry, "autobot_tts_synthesis_total", route="stream") == 1.0
        assert _sample(registry, "autobot_tts_synthesis_below_realtime_total", route="stream") is None
        assert _sample(registry, "autobot_tts_realtime_factor_last", route="stream") == 2.0

    def test_zero_duration_is_counted_but_carries_no_factor(self) -> None:
        """A synthesis that produced no measurable audio must not land as a 0.0x outlier."""
        registry = CollectorRegistry()
        recorder = TTSMetricsRecorder(registry)

        recorder.record_synthesis("stream", audio_seconds=0.0, wall_seconds=5.0)

        assert _sample(registry, "autobot_tts_synthesis_total", route="stream") == 1.0
        assert _sample(registry, "autobot_tts_realtime_factor_last", route="stream") is None
        assert _sample(registry, "autobot_tts_synthesis_below_realtime_total", route="stream") is None

    def test_routes_are_tracked_separately(self) -> None:
        """The streaming and whole-utterance routes have different throughput profiles."""
        registry = CollectorRegistry()
        recorder = TTSMetricsRecorder(registry)

        recorder.record_synthesis("stream", audio_seconds=1.0, wall_seconds=5.0)
        recorder.record_synthesis("blob", audio_seconds=4.0, wall_seconds=1.0)

        assert _sample(registry, "autobot_tts_realtime_factor_last", route="stream") == 0.2
        assert _sample(registry, "autobot_tts_realtime_factor_last", route="blob") == 4.0

    def test_first_chunk_latency_is_observed(self) -> None:
        """Time-to-first-audio stays visible alongside the throughput it trades against."""
        registry = CollectorRegistry()
        recorder = TTSMetricsRecorder(registry)

        recorder.record_first_chunk_latency("stream", 0.8)

        assert _sample(registry, "autobot_tts_first_chunk_seconds_count", route="stream") == 1.0

    def test_negative_first_chunk_latency_is_ignored(self) -> None:
        """A clock that went backwards must not corrupt the latency histogram."""
        registry = CollectorRegistry()
        recorder = TTSMetricsRecorder(registry)

        recorder.record_first_chunk_latency("stream", -1.0)

        assert _sample(registry, "autobot_tts_first_chunk_seconds_count", route="stream") is None
