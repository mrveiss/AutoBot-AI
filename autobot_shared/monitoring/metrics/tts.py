# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""TTS synthesis throughput metrics.

Issue #12460 — the TTS worker's real-time factor (audio-seconds produced per
wall-second) decides whether streamed speech can play without stuttering: below
1.0x the player drains its buffer faster than the worker refills it. The factor
was computable from the worker log all along and nothing consumed it, so a
worker sustaining 0.2x looked healthy on every dashboard. These metrics make it
observable and alertable.
"""

from enum import StrEnum

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder

# Real-time factor below which streamed playback cannot keep up (#12460).
REALTIME_FACTOR_FLOOR = 1.0


class TtsRoute(StrEnum):
    """The ``route`` label on every metric below (#13841).

    It was two bare strings at the call site, and a Prometheus label is the one
    place a typo costs more than a typo: ``"strema"`` does not raise, it silently
    opens a NEW time series, so the dashboards keep showing the old one flat and
    nothing anywhere reports an error. A ``StrEnum`` is still a ``str`` for
    labelling, so this changes no metric name or value -- it moves the typo from
    runtime-invisible to author-time.

    The recorders below accept ``TtsRoute | str``, not ``TtsRoute``, and the union is a
    constraint rather than a preference: ``prometheus_metrics.py`` delegates to them and
    passes ``route: str``, typing it through would need one import line there, and that
    file sits AT its ratchet ceiling (949), which may not grow. So the enum is enforced
    where route values are authored -- ``tts_client.py``, the only place that constructs
    one -- and the delegating layer stays as it is. A typo there is still possible; a
    typo at the producer is now an ``AttributeError`` at import of that line, not a label
    nobody notices.
    """

    STREAM = "stream"
    BLOB = "blob"


class TTSMetricsRecorder(BaseMetricsRecorder):
    """Recorder for TTS worker synthesis throughput metrics."""

    def _init_metrics(self) -> None:
        self.synthesis_total = Counter(
            "autobot_tts_synthesis_total",
            "Total TTS syntheses completed",
            ["route"],
            registry=self.registry,
        )
        self.below_realtime_total = Counter(
            "autobot_tts_synthesis_below_realtime_total",
            "TTS syntheses that produced audio slower than it plays back",
            ["route"],
            registry=self.registry,
        )
        self.realtime_factor = Histogram(
            "autobot_tts_realtime_factor",
            "Audio-seconds of speech produced per wall-second of synthesis",
            ["route"],
            # Bucketed around the 1.0 floor; the low buckets match the 0.09x-0.83x
            # range measured on a loaded host in #12460.
            buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0, 8.0],
            registry=self.registry,
        )
        self.realtime_factor_last = Gauge(
            "autobot_tts_realtime_factor_last",
            "Real-time factor of the most recent TTS synthesis",
            ["route"],
            registry=self.registry,
        )
        self.first_chunk_seconds = Histogram(
            "autobot_tts_first_chunk_seconds",
            "Wall-seconds from synthesis request to the first audio chunk",
            ["route"],
            buckets=[0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0],
            registry=self.registry,
        )

    def record_synthesis(self, route: TtsRoute | str, audio_seconds: float, wall_seconds: float) -> None:
        """Record one completed synthesis and its real-time factor.

        A non-positive duration on either side carries no rate information, so it
        is counted but not folded into the factor.
        """
        self.synthesis_total.labels(route=route).inc()
        if audio_seconds <= 0 or wall_seconds <= 0:
            return
        factor = audio_seconds / wall_seconds
        self.realtime_factor.labels(route=route).observe(factor)
        self.realtime_factor_last.labels(route=route).set(factor)
        if factor < REALTIME_FACTOR_FLOOR:
            self.below_realtime_total.labels(route=route).inc()

    def record_first_chunk_latency(self, route: TtsRoute | str, seconds: float) -> None:
        """Record how long the caller waited for the first audio chunk."""
        if seconds < 0:
            return
        self.first_chunk_seconds.labels(route=route).observe(seconds)


__all__ = ["TTSMetricsRecorder", "REALTIME_FACTOR_FLOOR"]
