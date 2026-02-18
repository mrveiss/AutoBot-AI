"""
Benchmark Base Framework

Core utilities and base classes for performance benchmarking.

Issue #58 - Performance Benchmarking Suite
Author: mrveiss
"""

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run"""

    name: str
    iterations: int
    total_time_ms: float
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float
    median_time_ms: float
    std_dev_ms: float
    p95_time_ms: float
    p99_time_ms: float
    ops_per_second: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    passed: bool = True
    error: Optional[str] = None


@dataclass
class RegressionCheck:
    """Result of regression detection"""

    benchmark_name: str
    current_avg_ms: float
    baseline_avg_ms: float
    regression_percent: float
    is_regression: bool
    threshold_percent: float


class BenchmarkTimer:
    """Context manager for timing benchmark operations"""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.elapsed_ms = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000


class BenchmarkRunner:
    """Core benchmark execution and analysis"""

    def __init__(
        self,
        warmup_iterations: int = 3,
        default_iterations: int = 10,
        regression_threshold_percent: float = 20.0,
    ):
        self.warmup_iterations = warmup_iterations
        self.default_iterations = default_iterations
        self.regression_threshold = regression_threshold_percent
        self.results: List[BenchmarkResult] = []
        self.baselines: Dict[str, BenchmarkResult] = {}

    def run_benchmark(
        self,
        name: str,
        func: Callable,
        iterations: Optional[int] = None,
        setup: Optional[Callable] = None,
        teardown: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BenchmarkResult:
        """Run a benchmark function multiple times and collect statistics"""

        if iterations is None:
            iterations = self.default_iterations

        # Setup
        if setup:
            setup()

        # Warmup runs (not counted)
        for _ in range(self.warmup_iterations):
            try:
                func()
            except Exception:
                pass

        # Actual benchmark runs
        times_ms: List[float] = []
        error_msg = None

        for _ in range(iterations):
            with BenchmarkTimer() as timer:
                try:
                    func()
                except Exception as e:
                    error_msg = str(e)
                    break
            times_ms.append(timer.elapsed_ms)

        # Teardown
        if teardown:
            teardown()

        # Calculate statistics
        if times_ms:
            total_time = sum(times_ms)
            avg_time = statistics.mean(times_ms)
            min_time = min(times_ms)
            max_time = max(times_ms)
            median_time = statistics.median(times_ms)
            std_dev = statistics.stdev(times_ms) if len(times_ms) > 1 else 0.0

            # Percentiles
            sorted_times = sorted(times_ms)
            p95_idx = int(len(sorted_times) * 0.95)
            p99_idx = int(len(sorted_times) * 0.99)
            p95_time = sorted_times[min(p95_idx, len(sorted_times) - 1)]
            p99_time = sorted_times[min(p99_idx, len(sorted_times) - 1)]

            ops_per_second = 1000.0 / avg_time if avg_time > 0 else 0.0
        else:
            total_time = avg_time = min_time = max_time = median_time = std_dev = 0.0
            p95_time = p99_time = 0.0
            ops_per_second = 0.0

        result = BenchmarkResult(
            name=name,
            iterations=len(times_ms),
            total_time_ms=total_time,
            avg_time_ms=avg_time,
            min_time_ms=min_time,
            max_time_ms=max_time,
            median_time_ms=median_time,
            std_dev_ms=std_dev,
            p95_time_ms=p95_time,
            p99_time_ms=p99_time,
            ops_per_second=ops_per_second,
            metadata=metadata or {},
            passed=error_msg is None,
            error=error_msg,
        )

        self.results.append(result)
        return result

    async def run_async_benchmark(
        self,
        name: str,
        func: Callable,
        iterations: Optional[int] = None,
        setup: Optional[Callable] = None,
        teardown: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BenchmarkResult:
        """Run an async benchmark function"""
        import asyncio

        if iterations is None:
            iterations = self.default_iterations

        # Setup
        if setup:
            if asyncio.iscoroutinefunction(setup):
                await setup()
            else:
                setup()

        # Warmup runs
        for _ in range(self.warmup_iterations):
            try:
                if asyncio.iscoroutinefunction(func):
                    await func()
                else:
                    func()
            except Exception:
                pass

        # Actual benchmark runs
        times_ms: List[float] = []
        error_msg = None

        for _ in range(iterations):
            start = time.perf_counter()
            try:
                if asyncio.iscoroutinefunction(func):
                    await func()
                else:
                    func()
            except Exception as e:
                error_msg = str(e)
                break
            elapsed_ms = (time.perf_counter() - start) * 1000
            times_ms.append(elapsed_ms)

        # Teardown
        if teardown:
            if asyncio.iscoroutinefunction(teardown):
                await teardown()
            else:
                teardown()

        # Calculate statistics (same as sync version)
        if times_ms:
            total_time = sum(times_ms)
            avg_time = statistics.mean(times_ms)
            min_time = min(times_ms)
            max_time = max(times_ms)
            median_time = statistics.median(times_ms)
            std_dev = statistics.stdev(times_ms) if len(times_ms) > 1 else 0.0
            sorted_times = sorted(times_ms)
            p95_idx = int(len(sorted_times) * 0.95)
            p99_idx = int(len(sorted_times) * 0.99)
            p95_time = sorted_times[min(p95_idx, len(sorted_times) - 1)]
            p99_time = sorted_times[min(p99_idx, len(sorted_times) - 1)]
            ops_per_second = 1000.0 / avg_time if avg_time > 0 else 0.0
        else:
            total_time = avg_time = min_time = max_time = median_time = std_dev = 0.0
            p95_time = p99_time = 0.0
            ops_per_second = 0.0

        result = BenchmarkResult(
            name=name,
            iterations=len(times_ms),
            total_time_ms=total_time,
            avg_time_ms=avg_time,
            min_time_ms=min_time,
            max_time_ms=max_time,
            median_time_ms=median_time,
            std_dev_ms=std_dev,
            p95_time_ms=p95_time,
            p99_time_ms=p99_time,
            ops_per_second=ops_per_second,
            metadata=metadata or {},
            passed=error_msg is None,
            error=error_msg,
        )

        self.results.append(result)
        return result

    def check_regression(self, result: BenchmarkResult) -> Optional[RegressionCheck]:
        """Check if benchmark result shows regression from baseline"""
        if result.name not in self.baselines:
            return None

        baseline = self.baselines[result.name]
        if baseline.avg_time_ms == 0:
            return None

        regression_percent = (
            (result.avg_time_ms - baseline.avg_time_ms) / baseline.avg_time_ms
        ) * 100

        is_regression = regression_percent > self.regression_threshold

        return RegressionCheck(
            benchmark_name=result.name,
            current_avg_ms=result.avg_time_ms,
            baseline_avg_ms=baseline.avg_time_ms,
            regression_percent=regression_percent,
            is_regression=is_regression,
            threshold_percent=self.regression_threshold,
        )

    def set_baseline(self, name: str, result: BenchmarkResult):
        """Set baseline for regression detection"""
        self.baselines[name] = result

    def save_results(self, filepath: Path):
        """Save benchmark results to JSON file"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "total_benchmarks": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "results": [asdict(r) for r in self.results],
        }

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def load_baselines(self, filepath: Path):
        """Load baselines from previous benchmark run"""
        if not filepath.exists():
            return

        with open(filepath) as f:
            data = json.load(f)

        for result_data in data.get("results", []):
            result = BenchmarkResult(**result_data)
            self.baselines[result.name] = result

    def generate_report(self) -> str:
        """Generate text report of benchmark results"""
        lines = [
            "=" * 80,
            "PERFORMANCE BENCHMARK REPORT",
            f"Generated: {datetime.now().isoformat()}",
            "=" * 80,
            "",
        ]

        # Summary
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        lines.append(f"Total Benchmarks: {total}")
        lines.append(f"Passed: {passed}")
        lines.append(f"Failed: {failed}")
        lines.append("")

        # Individual results
        for result in self.results:
            lines.append("-" * 80)
            lines.append(f"Benchmark: {result.name}")
            lines.append(f"  Status: {'PASS' if result.passed else 'FAIL'}")
            if result.error:
                lines.append(f"  Error: {result.error}")
            else:
                lines.append(f"  Iterations: {result.iterations}")
                lines.append(f"  Avg Time: {result.avg_time_ms:.2f} ms")
                lines.append(f"  Min Time: {result.min_time_ms:.2f} ms")
                lines.append(f"  Max Time: {result.max_time_ms:.2f} ms")
                lines.append(f"  Median: {result.median_time_ms:.2f} ms")
                lines.append(f"  Std Dev: {result.std_dev_ms:.2f} ms")
                lines.append(f"  P95: {result.p95_time_ms:.2f} ms")
                lines.append(f"  P99: {result.p99_time_ms:.2f} ms")
                lines.append(f"  Ops/sec: {result.ops_per_second:.2f}")

                # Check for regression
                regression = self.check_regression(result)
                if regression:
                    status = "REGRESSION" if regression.is_regression else "OK"
                    lines.append(f"  Regression Check: {status}")
                    lines.append(f"    Baseline: {regression.baseline_avg_ms:.2f} ms")
                    lines.append(f"    Change: {regression.regression_percent:+.1f}%")

            lines.append("")

        lines.append("=" * 80)
        return "\n".join(lines)


# Pytest fixtures and markers for benchmark tests
@pytest.fixture
def benchmark_runner():
    """Pytest fixture providing benchmark runner instance"""
    return BenchmarkRunner()


def benchmark_test(func):
    """Decorator to mark a function as a benchmark test"""
    return pytest.mark.benchmark(func)


# Performance assertion helpers
def assert_performance(
    result: BenchmarkResult,
    max_avg_ms: Optional[float] = None,
    max_p95_ms: Optional[float] = None,
    max_p99_ms: Optional[float] = None,
    min_ops_per_second: Optional[float] = None,
):
    """Assert performance meets specified thresholds"""
    errors = []

    if max_avg_ms and result.avg_time_ms > max_avg_ms:
        errors.append(
            f"Average time {result.avg_time_ms:.2f}ms exceeds max {max_avg_ms}ms"
        )

    if max_p95_ms and result.p95_time_ms > max_p95_ms:
        errors.append(f"P95 time {result.p95_time_ms:.2f}ms exceeds max {max_p95_ms}ms")

    if max_p99_ms and result.p99_time_ms > max_p99_ms:
        errors.append(f"P99 time {result.p99_time_ms:.2f}ms exceeds max {max_p99_ms}ms")

    if min_ops_per_second and result.ops_per_second < min_ops_per_second:
        errors.append(
            f"Ops/sec {result.ops_per_second:.2f} below minimum {min_ops_per_second}"
        )

    if errors:
        raise AssertionError("Performance requirements not met:\n" + "\n".join(errors))
