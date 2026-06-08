# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Inference Profiler Metrics Recorder

Prometheus metrics for per-stage inference pipeline profiling.
Tracks time spent in each inference stage and peak VRAM usage.

Issue #1956: Layered inference profiler with per-stage timing and peak VRAM tracking.
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class InferenceProfilerMetricsRecorder(BaseMetricsRecorder):
    """Recorder for inference pipeline profiling metrics."""

    def _init_metrics(self) -> None:
        """Initialize inference profiling metrics."""
        self._init_stage_timing_metrics()
        self._init_vram_metrics()
        self._init_session_metrics()

    def _init_stage_timing_metrics(self) -> None:
        """Initialize per-stage timing metrics. Issue #1956."""
        self.stage_duration = Histogram(
            "autobot_inference_stage_duration_seconds",
            "Duration of each inference pipeline stage in seconds",
            ["model_name", "stage"],
            buckets=[
                0.0001,
                0.0005,
                0.001,
                0.005,
                0.01,
                0.05,
                0.1,
                0.5,
                1.0,
                5.0,
                10.0,
            ],
            registry=self.registry,
        )

        self.stage_total_time = Counter(
            "autobot_inference_stage_total_seconds",
            "Cumulative time spent in each inference stage",
            ["model_name", "stage"],
            registry=self.registry,
        )

        self.stage_call_count = Counter(
            "autobot_inference_stage_calls_total",
            "Number of times each inference stage was entered",
            ["model_name", "stage"],
            registry=self.registry,
        )

    def _init_vram_metrics(self) -> None:
        """Initialize VRAM tracking metrics. Issue #1956."""
        self.vram_peak_bytes = Gauge(
            "autobot_inference_vram_peak_bytes",
            "Peak VRAM usage during inference in bytes",
            ["model_name"],
            registry=self.registry,
        )

        self.vram_allocated_bytes = Gauge(
            "autobot_inference_vram_allocated_bytes",
            "Current VRAM allocated during inference in bytes",
            ["model_name"],
            registry=self.registry,
        )

        self.vram_total_bytes = Gauge(
            "autobot_inference_vram_total_bytes",
            "Total VRAM available on the device in bytes",
            ["model_name"],
            registry=self.registry,
        )

    def _init_session_metrics(self) -> None:
        """Initialize profiling session metrics. Issue #1956."""
        self.profiling_sessions = Counter(
            "autobot_inference_profiling_sessions_total",
            "Total number of profiling sessions completed",
            ["model_name"],
            registry=self.registry,
        )

        self.total_inference_duration = Histogram(
            "autobot_inference_total_duration_seconds",
            "Total duration of a profiled inference run",
            ["model_name"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry,
        )

    # =========================================================================
    # Stage Timing Methods
    # =========================================================================

    def record_stage_duration(self, model_name: str, stage: str, duration_seconds: float) -> None:
        """Record a single stage duration measurement."""
        self.stage_duration.labels(model_name=model_name, stage=stage).observe(duration_seconds)
        self.stage_total_time.labels(model_name=model_name, stage=stage).inc(duration_seconds)
        self.stage_call_count.labels(model_name=model_name, stage=stage).inc()

    # =========================================================================
    # VRAM Methods
    # =========================================================================

    def update_vram_peak(self, model_name: str, peak_bytes: int) -> None:
        """Update the peak VRAM usage for a model."""
        self.vram_peak_bytes.labels(model_name=model_name).set(peak_bytes)

    def update_vram_allocated(self, model_name: str, allocated_bytes: int) -> None:
        """Update current VRAM allocation for a model."""
        self.vram_allocated_bytes.labels(model_name=model_name).set(allocated_bytes)

    def update_vram_total(self, model_name: str, total_bytes: int) -> None:
        """Update total VRAM available for a model."""
        self.vram_total_bytes.labels(model_name=model_name).set(total_bytes)

    # =========================================================================
    # Session Methods
    # =========================================================================

    def record_session_complete(self, model_name: str, total_duration_seconds: float) -> None:
        """Record a completed profiling session."""
        self.profiling_sessions.labels(model_name=model_name).inc()
        self.total_inference_duration.labels(model_name=model_name).observe(total_duration_seconds)


__all__ = ["InferenceProfilerMetricsRecorder"]
