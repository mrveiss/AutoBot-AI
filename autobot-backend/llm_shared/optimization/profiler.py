# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Layered Inference Profiler — per-stage timing and peak VRAM tracking.

Measures time spent in each inference pipeline stage (disk I/O, memory pinning,
CPU-to-GPU transfer, decompression, compute) and tracks peak VRAM usage.

Toggleable via AUTOBOT_INFERENCE_PROFILING env var — zero overhead when disabled.

Issue #1956: Layered inference profiler with per-stage timing and peak VRAM tracking.

Usage:
    profiler = LayeredProfiler("llama-7b")
    with profiler.stage("load_safetensor"):
        data = load_weights(path)
    with profiler.stage("compute"):
        output = model.forward(data)
    profiler.log_summary()
"""

import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# Default inference stages in typical execution order
INFERENCE_STAGES: List[str] = [
    "load_safetensor",
    "pin_memory",
    "compression",
    "create_layer",
    "cpu_wait",
    "prefetch",
    "compute",
]


def _is_profiling_enabled() -> bool:
    """Check if inference profiling is enabled via environment variable."""
    return config.inference_profiling.lower() in (
        "1",
        "true",
        "yes",
    )


def _get_history_dir() -> Path:
    """Get the directory for storing profiling history. Issue #1956."""
    base = Path(config.data_dir)
    history_dir = base / "profiling" / "inference"
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir


class _StageAccumulator:
    """Accumulates timing data for a single inference stage."""

    __slots__ = ("total_ns", "call_count", "min_ns", "max_ns")

    def __init__(self) -> None:
        self.total_ns: int = 0
        self.call_count: int = 0
        self.min_ns: int = 0
        self.max_ns: int = 0

    def record(self, elapsed_ns: int) -> None:
        """Record a single timing measurement for this stage."""
        self.total_ns += elapsed_ns
        self.call_count += 1
        if self.call_count == 1:
            self.min_ns = elapsed_ns
            self.max_ns = elapsed_ns
        else:
            self.min_ns = min(self.min_ns, elapsed_ns)
            self.max_ns = max(self.max_ns, elapsed_ns)

    @property
    def avg_ns(self) -> float:
        """Average nanoseconds per call."""
        return self.total_ns / self.call_count if self.call_count > 0 else 0.0


class _VRAMTracker:
    """Tracks peak VRAM usage via torch.cuda.mem_get_info(). Issue #1956."""

    def __init__(self) -> None:
        self.peak_allocated_bytes: int = 0
        self.total_bytes: int = 0
        self._cuda_available: bool | None = None

    def _check_cuda(self) -> bool:
        """Lazy-check for CUDA availability."""
        if self._cuda_available is None:
            try:
                import torch

                self._cuda_available = torch.cuda.is_available()
            except (ImportError, RuntimeError):
                self._cuda_available = False
        return self._cuda_available

    def sample(self) -> None:
        """Sample current VRAM state and update peak if higher."""
        if not self._check_cuda():
            return
        self._sample_cuda_memory()

    def _sample_cuda_memory(self) -> None:
        """Read CUDA memory state. Issue #1956."""
        import torch

        free, total = torch.cuda.mem_get_info()
        allocated = total - free
        self.total_bytes = total
        if allocated > self.peak_allocated_bytes:
            self.peak_allocated_bytes = allocated

    def to_dict(self) -> Dict[str, Any]:
        """Return VRAM tracking data as a dictionary."""
        return {
            "peak_allocated_bytes": self.peak_allocated_bytes,
            "peak_allocated_mb": round(self.peak_allocated_bytes / (1024 * 1024), 2),
            "total_bytes": self.total_bytes,
            "total_mb": round(self.total_bytes / (1024 * 1024), 2),
        }


class _NoOpContext:
    """No-op context manager returned when profiling is disabled."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


_NOOP = _NoOpContext()


class LayeredProfiler:
    """
    Per-stage inference profiler with VRAM tracking.

    Accumulates timing across all layers for each stage, tracks peak VRAM,
    and optionally exports to Prometheus and persists history for comparison.

    Issue #1956.
    """

    def __init__(self, model_name: str, *, enabled: bool | None = None):
        """
        Initialize the profiler for a model.

        Args:
            model_name: Identifier for the model being profiled.
            enabled: Override enable state. If None, reads AUTOBOT_INFERENCE_PROFILING env var.
        """
        self._model_name = model_name
        self._enabled = enabled if enabled is not None else _is_profiling_enabled()
        self._stages: Dict[str, _StageAccumulator] = {}
        self._stage_order: List[str] = []
        self._vram = _VRAMTracker()
        self._start_ns: int = 0
        self._end_ns: int = 0

    @property
    def enabled(self) -> bool:
        """Whether profiling is active."""
        return self._enabled

    @property
    def model_name(self) -> str:
        """The model being profiled."""
        return self._model_name

    @contextmanager
    def stage(self, name: str):
        """
        Time an inference stage as a context manager.

        When profiling is disabled, returns a no-op context with zero overhead.
        """
        if not self._enabled:
            yield _NOOP
            return
        acc = self._get_or_create_stage(name)
        self._vram.sample()
        start = time.perf_counter_ns()
        try:
            yield self
        finally:
            elapsed = time.perf_counter_ns() - start
            acc.record(elapsed)
            self._vram.sample()

    def _get_or_create_stage(self, name: str) -> _StageAccumulator:
        """Get an existing stage accumulator or create a new one. Issue #1956."""
        if name not in self._stages:
            self._stages[name] = _StageAccumulator()
            self._stage_order.append(name)
        return self._stages[name]

    def start(self) -> None:
        """Mark the start of the overall profiling session."""
        if self._enabled:
            self._start_ns = time.perf_counter_ns()
            self._vram.sample()

    def stop(self) -> None:
        """Mark the end of the overall profiling session."""
        if self._enabled:
            self._end_ns = time.perf_counter_ns()
            self._vram.sample()

    # =========================================================================
    # Summary and Reporting
    # =========================================================================

    def summary(self) -> Dict[str, Any]:
        """
        Generate a profiling summary with per-stage breakdown.

        Returns a dict with total time, per-stage timing and percentages,
        VRAM data, and the model name.
        """
        if not self._enabled:
            return {"model": self._model_name, "enabled": False}
        total_ns = sum(s.total_ns for s in self._stages.values())
        stages = self._build_stage_summaries(total_ns)
        return {
            "model": self._model_name,
            "enabled": True,
            "total_ms": round(total_ns / 1_000_000, 3),
            "wall_clock_ms": self._wall_clock_ms(),
            "stages": stages,
            "stage_order": list(self._stage_order),
            "vram": self._vram.to_dict(),
        }

    def _build_stage_summaries(self, total_ns: int) -> Dict[str, Dict[str, Any]]:
        """Build per-stage summary dicts. Issue #1956."""
        stages: Dict[str, Dict[str, Any]] = {}
        for name in self._stage_order:
            acc = self._stages[name]
            pct = (acc.total_ns / total_ns * 100) if total_ns > 0 else 0.0
            stages[name] = {
                "total_ms": round(acc.total_ns / 1_000_000, 3),
                "calls": acc.call_count,
                "avg_ms": round(acc.avg_ns / 1_000_000, 3),
                "min_ms": round(acc.min_ns / 1_000_000, 3),
                "max_ms": round(acc.max_ns / 1_000_000, 3),
                "percentage": round(pct, 1),
            }
        return stages

    def _wall_clock_ms(self) -> float:
        """Calculate wall-clock elapsed time. Issue #1956."""
        if self._start_ns and self._end_ns:
            return round((self._end_ns - self._start_ns) / 1_000_000, 3)
        return 0.0

    def log_summary(self, level: int = logging.INFO) -> None:
        """Log the profiling summary at the specified log level."""
        if not self._enabled:
            return
        report = self.summary()
        parts = [f"[{self._model_name}] {report['total_ms']:.1f}ms total"]
        for name in self._stage_order:
            stg = report["stages"][name]
            parts.append(f"{name}: {stg['total_ms']:.1f}ms ({stg['percentage']:.0f}%)")
        vram = report["vram"]
        if vram["peak_allocated_bytes"] > 0:
            parts.append(f"VRAM peak: {vram['peak_allocated_mb']:.0f}MB")
        logger.log(level, " | ".join(parts))

    # =========================================================================
    # Prometheus Export
    # =========================================================================

    def export_to_prometheus(self) -> None:
        """
        Export profiling data to Prometheus via the shared metrics manager.

        Uses get_metrics_manager() to access the singleton. Fails silently
        if the metrics system is not initialized.
        """
        if not self._enabled:
            return
        try:
            self._do_prometheus_export()
        except Exception:
            logger.debug("Prometheus export skipped — metrics not available")

    def _do_prometheus_export(self) -> None:
        """Perform the actual Prometheus export. Issue #1956."""
        from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

        metrics = get_metrics_manager()
        report = self.summary()
        for name, stg in report["stages"].items():
            metrics.record_inference_stage_duration(self._model_name, name, stg["total_ms"] / 1000)
        vram = report["vram"]
        if vram["peak_allocated_bytes"] > 0:
            metrics.record_inference_vram_peak(self._model_name, vram["peak_allocated_bytes"])
        total_s = report["total_ms"] / 1000
        metrics.record_inference_session_complete(self._model_name, total_s)

    # =========================================================================
    # History Persistence
    # =========================================================================

    def save_history(self) -> Path | None:
        """
        Save the profiling summary to a JSON file for later comparison.

        Returns the path to the saved file, or None if profiling is disabled.
        """
        if not self._enabled:
            return None
        report = self.summary()
        report["timestamp"] = time.time()
        history_dir = _get_history_dir()
        safe_name = self._model_name.replace("/", "_").replace("..", "_")
        filename = f"{safe_name}_{int(time.time())}.json"
        filepath = history_dir / filename
        filepath.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.debug("Profiling history saved to %s", filepath)
        return filepath

    def reset(self) -> None:
        """Reset all accumulated profiling data."""
        self._stages.clear()
        self._stage_order.clear()
        self._vram = _VRAMTracker()
        self._start_ns = 0
        self._end_ns = 0


__all__ = [
    "LayeredProfiler",
    "INFERENCE_STAGES",
]
