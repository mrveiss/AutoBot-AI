#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Phase 9 Performance Optimization Testing
================================================

Performance testing for AutoBot optimizations including:
- GPU acceleration inventory
- NPU worker responsiveness
- Multi-core CPU utilisation under concurrent load
- Memory growth / leak detection
- Response caching on repeated reads

Converted from a CLI benchmark harness to a pytest suite (#14979). The class
defined ``__init__``, so pytest collected none of its five ``test_*`` methods:
they recorded ``BenchmarkResult`` rows for an ``argparse`` driver that wrote a
JSON report under ``tests/results/`` and never failed on anything. Every check
now asserts against the baselines the harness only ever printed, and the report
writer is gone — a test run must not deposit artefacts in the source tree.

Three sub-measurements were dropped rather than converted, because each drove
an endpoint that does not exist and asserted nothing about the result:
``{npu}/api/ai/process`` (the NPU worker serves only ``/health`` and ``/`` —
see ``roles/npu-worker/templates/npu-worker.py.j2``), ``/api/hot_reload/status``
+ ``/api/system/reload`` + ``/api/config/reload`` (no router serves them), and
the knowledge-base search timing folded into the GPU test (it measured the
backend, not the GPU).
"""

import concurrent.futures
import shutil
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

import psutil
import pytest
import requests

from autobot_shared.live_service_probe import require_live_endpoint
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# #12510: this suite drives a running backend and measures a real host.
pytestmark = pytest.mark.performance

# #1618: endpoints from the SSOT — no hardcoded hosts or ports.
BACKEND_URL = config.backend_url
NPU_WORKER_URL = config.npu_worker_url

# Env-var-backed module constants rather than literals at the call sites: a
# loaded fleet host needs a different budget from a loopback dev box, and no
# caller should hardcode its own.
HTTP_TIMEOUT_SECONDS = 15.0
MAX_RSS_GROWTH_MB = 50.0

# Unauthenticated read endpoints the backend actually serves. Every other
# endpoint the original harness polled either does not exist (404) or requires
# a session (401), which is why none of its measurements ever asserted.
CACHEABLE_ENDPOINTS = ("/api/system/health", "/api/health", "/api/version")
LOAD_ENDPOINT = "/api/health"

THREAD_POOL_SIZES = (4, 8, 12, 16, 20)
THREAD_POOL_TASKS = 20
MEMORY_CYCLES = 5
REQUESTS_PER_MEMORY_CYCLE = 10


@dataclass
class PerformanceMetric:
    """Performance measurement result"""

    metric_name: str
    value: float
    unit: str
    category: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)


@pytest.fixture(autouse=True)
def _require_live_backend() -> None:
    """Skip when the AutoBot backend is absent (#14930).

    Every measurement here describes *AutoBot's* performance on this host. With
    no backend running, the GPU/CPU/memory figures describe the runner's
    hardware inventory instead — the non-result class #14930 exists to stop —
    so the whole module is gated on the one service that makes it meaningful.
    """
    require_live_endpoint(BACKEND_URL, what="the AutoBot backend API")


def _log_metrics(metrics: List[PerformanceMetric]) -> None:
    """Emit each measurement so a passing run still reports its numbers."""
    for metric in metrics:
        logger.info("%s [%s]: %.3f %s", metric.metric_name, metric.category, metric.value, metric.unit)


def _read_gpu_inventory() -> List[str]:
    """Return the nvidia-smi CSV fields for GPU 0, skipping when absent."""
    if shutil.which("nvidia-smi") is None:
        pytest.skip("nvidia-smi is not installed — this test measures a live NVIDIA GPU")

    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=HTTP_TIMEOUT_SECONDS,
        encoding="utf-8",
    )
    if result.returncode != 0:
        pytest.skip(f"nvidia-smi reported no usable GPU on this host: {result.stderr.strip()!r}")

    first_gpu = result.stdout.strip().splitlines()[0]
    return [field_value.strip() for field_value in first_gpu.split(",")]


def _timed_get(endpoint: str) -> tuple[requests.Response, float]:
    """GET a backend endpoint and return the response with its elapsed seconds."""
    started = time.time()
    response = requests.get(f"{BACKEND_URL}{endpoint}", timeout=HTTP_TIMEOUT_SECONDS)
    return response, time.time() - started


def _load_request_outcome(endpoint: str) -> str:
    """Return one load request's HTTP status, or the transport fault that ended it.

    Under concurrency a refused or timed-out request is a *measurement*, not an
    error — the ``concurrent_requests`` success-rate baseline exists to score
    exactly that. The fault type is carried into the assertion message instead
    of raised, so a degraded backend reports "13/20 returned 200, 7 ReadTimeout"
    rather than one stack trace that hides the other 19 results.
    """
    try:
        return str(_timed_get(endpoint)[0].status_code)
    except requests.RequestException as exc:
        return type(exc).__name__


def _cpu_bound_work() -> int:
    """A deterministic CPU-bound unit of work for the thread-pool sweep."""
    return sum(index * index for index in range(10000))


class TestPerformanceOptimization:
    """Performance and resource-utilisation assertions against a live stack."""

    def setup_method(self) -> None:
        """Bind the performance baselines every assertion below is measured against."""
        self.baselines = {
            "api_response_time": 2.0,  # seconds
            "kb_search_time": 5.0,  # seconds
            "chat_response_time": 20.0,  # seconds
            "concurrent_requests": 0.9,  # success rate
            "memory_usage": 80.0,  # percentage
            "cpu_usage": 70.0,  # percentage
        }

    def test_gpu_acceleration_performance(self) -> None:
        """The GPU reports a coherent memory and utilisation inventory."""
        name, used_raw, total_raw, utilization_raw = _read_gpu_inventory()
        memory_used, memory_total, utilization = int(used_raw), int(total_raw), int(utilization_raw)

        _log_metrics(
            [
                PerformanceMetric("gpu_memory_usage", (memory_used / memory_total) * 100, "%", "GPU"),
                PerformanceMetric("gpu_utilization", utilization, "%", "GPU"),
                PerformanceMetric("gpu_memory_total", memory_total, "MB", "GPU"),
            ]
        )

        assert memory_total > 0, f"GPU {name!r} reports {memory_total} MB of total memory, expected a positive figure"
        assert memory_used <= memory_total, (
            f"GPU {name!r} reports {memory_used} MB used of {memory_total} MB total — the driver is reporting "
            f"an impossible allocation"
        )
        assert 0 <= utilization <= 100, f"GPU {name!r} reports {utilization}% utilisation, outside the 0-100 range"

    def test_npu_acceleration(self) -> None:
        """The NPU worker answers its health probe inside the API budget."""
        require_live_endpoint(NPU_WORKER_URL, what="the AutoBot NPU worker")
        budget = self.baselines["api_response_time"]

        started = time.time()
        response = requests.get(f"{NPU_WORKER_URL}/health", timeout=HTTP_TIMEOUT_SECONDS)
        elapsed = time.time() - started

        _log_metrics([PerformanceMetric("npu_worker_response_time", elapsed, "seconds", "NPU")])

        assert (
            response.status_code == 200
        ), f"NPU worker {NPU_WORKER_URL}/health returned HTTP {response.status_code}, expected 200"
        assert elapsed < budget, f"NPU worker health probe took {elapsed:.3f}s, over the {budget:.1f}s budget"

        capabilities = response.json().get("capabilities", {})
        assert capabilities.get("device"), f"NPU worker names no inference device: {capabilities!r}"

    def test_cpu_optimization(self) -> None:
        """Concurrent requests sized to the core count meet the success-rate baseline."""
        cores = psutil.cpu_count(logical=True)
        assert cores and cores >= 1, f"psutil reports {cores!r} logical cores, expected at least one"

        concurrency = min(cores, 20)
        started = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            statuses = list(executor.map(lambda _: _load_request_outcome(LOAD_ENDPOINT), range(concurrency)))
        duration = time.time() - started

        succeeded = statuses.count("200")
        success_rate = succeeded / concurrency
        _log_metrics(
            [
                PerformanceMetric("concurrent_success_rate", success_rate * 100, "%", "CPU"),
                PerformanceMetric("requests_per_second", succeeded / duration, "req/s", "CPU"),
                PerformanceMetric("cpu_logical_cores", cores, "cores", "CPU"),
            ]
        )

        baseline = self.baselines["concurrent_requests"]
        assert success_rate >= baseline, (
            f"only {succeeded}/{concurrency} concurrent requests to {LOAD_ENDPOINT} returned 200 "
            f"({success_rate:.0%}), under the {baseline:.0%} baseline; statuses={statuses!r}"
        )

        self._assert_thread_pool_completes_every_task()

    def test_memory_management(self) -> None:
        """Repeated backend traffic does not grow this process without bound."""
        process = psutil.Process()
        rss_before = process.memory_info().rss / (1024**2)
        cycle_growth: List[float] = []

        for _ in range(MEMORY_CYCLES):
            cycle_start = process.memory_info().rss / (1024**2)
            for _ in range(REQUESTS_PER_MEMORY_CYCLE):
                response, _elapsed = _timed_get(LOAD_ENDPOINT)
                assert response.status_code == 200, (
                    f"{LOAD_ENDPOINT} returned HTTP {response.status_code} mid-run; the memory measurement "
                    f"below would describe a failing endpoint"
                )
                response.json()
            cycle_growth.append(process.memory_info().rss / (1024**2) - cycle_start)

        total_growth = process.memory_info().rss / (1024**2) - rss_before
        _log_metrics(
            [
                PerformanceMetric("rss_growth_total", total_growth, "MB", "Memory"),
                PerformanceMetric("rss_growth_per_cycle", statistics.mean(cycle_growth), "MB", "Memory"),
                PerformanceMetric("system_memory_percent", psutil.virtual_memory().percent, "%", "Memory"),
            ]
        )

        assert total_growth < MAX_RSS_GROWTH_MB, (
            f"resident memory grew {total_growth:.1f} MB over {MEMORY_CYCLES * REQUESTS_PER_MEMORY_CYCLE} "
            f"requests, over the {MAX_RSS_GROWTH_MB:.0f} MB budget; per-cycle growth was {cycle_growth!r}"
        )

    def test_hot_reload_performance(self) -> None:
        """Repeated reads of cacheable endpoints stay inside the API budget."""
        budget = self.baselines["api_response_time"]
        first_times: List[float] = []
        repeat_times: List[float] = []

        for endpoint in CACHEABLE_ENDPOINTS:
            first_response, first_elapsed = _timed_get(endpoint)
            repeat_response, repeat_elapsed = _timed_get(endpoint)

            assert (
                first_response.status_code == 200
            ), f"{endpoint} returned HTTP {first_response.status_code} on the first read, expected 200"
            assert (
                repeat_response.status_code == 200
            ), f"{endpoint} returned HTTP {repeat_response.status_code} on the repeat read, expected 200"
            first_times.append(first_elapsed)
            repeat_times.append(repeat_elapsed)

        self._assert_repeat_reads_within_budget(first_times, repeat_times, budget)

    def _assert_repeat_reads_within_budget(
        self, first_times: List[float], repeat_times: List[float], budget: float
    ) -> None:
        """Assert the warm read of each endpoint stays inside the response budget."""
        avg_first = statistics.mean(first_times)
        avg_repeat = statistics.mean(repeat_times)
        _log_metrics(
            [
                PerformanceMetric("avg_first_request_time", avg_first, "seconds", "Caching"),
                PerformanceMetric("avg_cached_request_time", avg_repeat, "seconds", "Caching"),
                PerformanceMetric(
                    "cache_improvement_percent",
                    ((avg_first - avg_repeat) / avg_first) * 100 if avg_first else 0.0,
                    "%",
                    "Caching",
                ),
            ]
        )

        slowest = max(repeat_times)
        assert slowest < budget, (
            f"the slowest warm read of {CACHEABLE_ENDPOINTS!r} took {slowest:.3f}s, over the "
            f"{budget:.1f}s budget; cold reads were {first_times!r}"
        )

    def _assert_thread_pool_completes_every_task(self) -> None:
        """Every submitted CPU-bound task completes at each pool size."""
        expected = _cpu_bound_work()
        throughput: Dict[int, float] = {}

        for size in THREAD_POOL_SIZES:
            started = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=size) as executor:
                results = list(executor.map(lambda _: _cpu_bound_work(), range(THREAD_POOL_TASKS)))
            throughput[size] = THREAD_POOL_TASKS / (time.time() - started)

            assert (
                len(results) == THREAD_POOL_TASKS
            ), f"a {size}-worker pool returned {len(results)} of {THREAD_POOL_TASKS} submitted tasks"
            assert all(
                value == expected for value in results
            ), f"a {size}-worker pool returned a wrong result for a deterministic task: {set(results)!r}"

        optimal = max(throughput, key=lambda size: throughput[size])
        _log_metrics([PerformanceMetric("optimal_thread_count", optimal, "threads", "CPU")])
