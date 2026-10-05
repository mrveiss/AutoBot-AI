# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Benchmark result records for the SLM monitoring modules (#16282).

Extracted from `performance_benchmark.py`, which carries a recorded file-size
ceiling it may not exceed. Both are `@dataclass` records whose only methods
format themselves for a report, and neither is used outside that module -- so
they are the cheapest cohesive piece to lift, and lifting them makes room for
changes inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class BenchmarkResult:
    """Result of a performance benchmark test."""

    test_name: str
    category: str  # "api", "database", "network", "system", "multimodal"
    duration_seconds: float
    operations_count: int
    operations_per_second: float
    average_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    success_rate: float
    error_count: int
    timestamp: str
    metadata: Dict[str, Any] = None

    def get_summary_line(self) -> str:
        """Get formatted summary line for logging (Issue #372 - reduces feature envy)."""
        return (
            f"{self.test_name}: {self.operations_per_second:.1f} ops/sec, "
            f"{self.average_latency_ms:.1f}ms avg, {self.success_rate:.1f}% success"
        )

    def get_latency_only_line(self) -> str:
        """Get latency-focused summary for network tests (Issue #372 - reduces feature envy)."""
        return f"{self.test_name}: {self.average_latency_ms:.1f}ms avg, " f"{self.success_rate:.1f}% success"


@dataclass
class SystemBenchmark:
    """System-level benchmark results."""

    cpu_benchmark_score: float
    memory_bandwidth_mbps: float
    disk_io_mbps: float
    network_throughput_mbps: float
    gpu_compute_score: float | None = None
    npu_inference_score: float | None = None

    def get_summary_lines(self) -> List[str]:
        """Get formatted summary lines for logging (Issue #372 - reduces feature envy)."""
        lines = [
            f"  CPU Score: {self.cpu_benchmark_score:.1f}",
            f"  Memory Bandwidth: {self.memory_bandwidth_mbps:.1f} MB/s",
            f"  Disk I/O: {self.disk_io_mbps:.1f} MB/s",
            f"  Network Throughput: {self.network_throughput_mbps:.1f} MB/s",
        ]
        if self.gpu_compute_score:
            lines.append(f"  GPU Score: {self.gpu_compute_score:.1f}")
        if self.npu_inference_score:
            lines.append(f"  NPU Score: {self.npu_inference_score:.1f}")
        return lines

    def to_hardware_summary_dict(self) -> Dict[str, Any]:
        """Convert to hardware summary dictionary (Issue #372 - reduces feature envy)."""
        return {
            "cpu_score": self.cpu_benchmark_score,
            "memory_bandwidth_mbps": self.memory_bandwidth_mbps,
            "disk_io_mbps": self.disk_io_mbps,
            "network_throughput_mbps": self.network_throughput_mbps,
            "gpu_available": self.gpu_compute_score is not None,
            "npu_available": self.npu_inference_score is not None,
            "gpu_score": self.gpu_compute_score,
            "npu_score": self.npu_inference_score,
        }
