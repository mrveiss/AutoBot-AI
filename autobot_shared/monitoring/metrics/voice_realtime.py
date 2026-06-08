# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Voice Realtime WebRTC metrics recorder.

Prometheus metrics for OpenAI Realtime API sessions.
Issue #7421 — cost + duration telemetry for Realtime WebRTC.
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class VoiceRealtimeMetricsRecorder(BaseMetricsRecorder):
    """Recorder for OpenAI Realtime WebRTC session metrics."""

    def _init_metrics(self) -> None:
        self._init_session_metrics()
        self._init_audio_metrics()
        self._init_token_metrics()
        self._init_tool_metrics()
        self._init_cost_metrics()

    def _init_session_metrics(self) -> None:
        self.sessions_total = Counter(
            "autobot_voice_realtime_sessions_total",
            "Total Realtime WebRTC sessions started",
            ["model"],
            registry=self.registry,
        )
        self.session_seconds_total = Counter(
            "autobot_voice_realtime_session_seconds_total",
            "Cumulative Realtime session wall-clock duration in seconds",
            ["model"],
            registry=self.registry,
        )
        self.sessions_active = Gauge(
            "autobot_voice_realtime_sessions_active",
            "Currently active Realtime WebRTC sessions",
            ["model"],
            registry=self.registry,
        )
        self.session_duration = Histogram(
            "autobot_voice_realtime_session_duration_seconds",
            "Per-session duration in seconds",
            ["model", "disconnect_reason"],
            buckets=[10, 30, 60, 300, 600, 1800, 3600],
            registry=self.registry,
        )

    def _init_audio_metrics(self) -> None:
        self.audio_seconds_total = Counter(
            "autobot_voice_realtime_audio_seconds_total",
            "Cumulative audio seconds streamed",
            ["direction"],  # input | output
            registry=self.registry,
        )

    def _init_token_metrics(self) -> None:
        self.tokens_total = Counter(
            "autobot_voice_realtime_tokens_total",
            "Cumulative Realtime API tokens consumed",
            ["type"],  # input | output | cached_input
            registry=self.registry,
        )

    def _init_tool_metrics(self) -> None:
        self.tool_calls_total = Counter(
            "autobot_voice_realtime_tool_calls_total",
            "Total tool calls made during Realtime sessions",
            ["tool", "outcome"],  # outcome: success | error
            registry=self.registry,
        )
        self.tool_call_duration = Histogram(
            "autobot_voice_realtime_tool_call_duration_seconds",
            "Realtime tool call round-trip latency",
            ["tool"],
            buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
            registry=self.registry,
        )

    def _init_cost_metrics(self) -> None:
        self.estimated_cost_usd = Counter(
            "autobot_voice_realtime_estimated_cost_usd_total",
            "Cumulative estimated USD cost for Realtime sessions",
            ["model"],
            registry=self.registry,
        )
        self.cap_breaches_total = Counter(
            "autobot_voice_realtime_cap_breaches_total",
            "Total sessions auto-disconnected due to cap breach",
            ["reason"],  # duration | cost
            registry=self.registry,
        )
