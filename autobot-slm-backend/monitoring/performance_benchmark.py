#!/usr/bin/env python3
"""
AutoBot Performance Benchmark Suite
Comprehensive benchmarking tools for measuring AutoBot distributed system performance
across different workloads and configurations.

Issue #396: Converted blocking subprocess.run to asyncio.create_subprocess_exec.
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import matplotlib.pyplot as plt
import numpy as np
from performance_monitor import VMS

from src.constants.model_constants import ModelConstants
from autobot_shared.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


# Issue #339: Extracted helper for HTTP request execution
async def _execute_http_request(
    session: aiohttp.ClientSession, method: str, url: str, data: Dict
) -> bool:
    """Execute HTTP request and return success status (Issue #339 - extracted helper)."""
    if method == "GET":
        async with session.get(url) as response:
            await response.text()
            return response.status < 400
    elif method == "POST":
        async with session.post(url, json=data) as response:
            await response.text()
            return response.status < 400
    return False


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
        return (
            f"{self.test_name}: {self.average_latency_ms:.1f}ms avg, "
            f"{self.success_rate:.1f}% success"
        )


@dataclass
class SystemBenchmark:
    """System-level benchmark results."""

    cpu_benchmark_score: float
    memory_bandwidth_mbps: float
    disk_io_mbps: float
    network_throughput_mbps: float
    gpu_compute_score: Optional[float] = None
    npu_inference_score: Optional[float] = None

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


class PerformanceBenchmark:
    """Comprehensive performance benchmarking suite for AutoBot."""

    def __init__(self, output_dir: str = "/home/kali/Desktop/AutoBot/logs/benchmarks"):
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results = []

    async def run_api_benchmark(
        self, duration_seconds: int = 60
    ) -> List[BenchmarkResult]:
        """Benchmark AutoBot API endpoints performance."""
        self.logger.info(f"🚀 Starting API benchmark (duration: {duration_seconds}s)")

        results = []

        # Define API endpoints to benchmark
        api_endpoints = [
            (
                "Backend Health",
                "GET",
                f"http://{VMS['main']}:{NetworkConstants.BACKEND_PORT}/api/health",
                {},
            ),
            (
                "System Status",
                "GET",
                f"http://{VMS['main']}:{NetworkConstants.BACKEND_PORT}/api/system/status",
                {},
            ),
            (
                "Chat History",
                "GET",
                f"http://{VMS['main']}:{NetworkConstants.BACKEND_PORT}/api/chats",
                {},
            ),
            (
                "Knowledge Search",
                "POST",
                f"http://{VMS['main']}:{NetworkConstants.BACKEND_PORT}/api/knowledge_base/search",
                {"query": "AutoBot system information", "limit": 5},
            ),
            (
                "LLM Request",
                "POST",
                f"http://{VMS['main']}:{NetworkConstants.BACKEND_PORT}/api/llm/request",
                {
                    "prompt": "What is AutoBot?",
                    "model": ModelConstants.DEFAULT_OLLAMA_MODEL,
                },
            ),
        ]

        for endpoint_name, method, url, data in api_endpoints:
            try:
                result = await self._benchmark_endpoint(
                    endpoint_name, method, url, data, duration_seconds
                )
                results.append(result)
            except Exception as e:
                self.logger.error(f"Error benchmarking {endpoint_name}: {e}")

        return results

    async def _benchmark_endpoint(
        self, name: str, method: str, url: str, data: Dict, duration_seconds: int
    ) -> BenchmarkResult:
        """Benchmark a specific API endpoint."""
        # Issue #339: Refactored to use extracted helper, reducing depth from 7 to 4
        latencies = []
        success_count = 0
        error_count = 0
        start_time = time.time()

        timeout = aiohttp.ClientTimeout(total=30.0)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            while time.time() - start_time < duration_seconds:
                request_start = time.time()

                try:
                    success = await _execute_http_request(session, method, url, data)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1
                    request_time = (time.time() - request_start) * 1000  # Convert to ms
                    latencies.append(request_time)

                except Exception as e:
                    error_count += 1
                    self.logger.debug(f"Request error for {name}: {e}")

                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.1)

        total_operations = success_count + error_count
        actual_duration = time.time() - start_time

        if latencies:
            avg_latency = statistics.mean(latencies)
            p95_latency = (
                np.percentile(latencies, 95) if len(latencies) > 1 else avg_latency
            )
            p99_latency = (
                np.percentile(latencies, 99) if len(latencies) > 1 else avg_latency
            )
        else:
            avg_latency = p95_latency = p99_latency = 0.0

        return BenchmarkResult(
            test_name=f"API_{name.replace(' ', '_')}",
            category="api",
            duration_seconds=actual_duration,
            operations_count=total_operations,
            operations_per_second=total_operations / actual_duration
            if actual_duration > 0
            else 0,
            average_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            success_rate=(success_count / total_operations) * 100
            if total_operations > 0
            else 0,
            error_count=error_count,
            timestamp=datetime.now().isoformat(),
            metadata={"endpoint": url, "method": method},
        )

    async def run_database_benchmark(
        self, duration_seconds: int = 30
    ) -> List[BenchmarkResult]:
        """Benchmark Redis database performance across different operations."""
        self.logger.info(
            f"🗄️ Starting database benchmark (duration: {duration_seconds}s)"
        )

        results = []

        # Test different Redis databases
        redis_dbs = [0, 1, 4, 7, 8]  # Main, Knowledge, Metrics, Workflows, Vectors

        for db_num in redis_dbs:
            try:
                # Connection benchmark
                conn_result = await self._benchmark_redis_connections(
                    db_num, duration_seconds // 5
                )
                results.append(conn_result)

                # Read/Write benchmark
                rw_result = await self._benchmark_redis_operations(
                    db_num, duration_seconds // 5
                )
                results.append(rw_result)

            except Exception as e:
                self.logger.error(f"Error benchmarking Redis DB {db_num}: {e}")

        return results

    async def _benchmark_redis_connections(
        self, db_num: int, duration_seconds: int
    ) -> BenchmarkResult:
        """Benchmark Redis connection performance using canonical utility.

        This follows CLAUDE.md "🔴 REDIS CLIENT USAGE" policy.
        Maps DB numbers to named databases for benchmarking.
        """
        from autobot_shared.redis_client import get_redis_client

        # Map DB numbers to database names for canonical utility
        db_name_map = {
            0: "main",
            1: "knowledge",
            4: "metrics",
            7: "workflows",
            8: "vectors",
        }

        latencies = []
        success_count = 0
        error_count = 0
        start_time = time.time()

        while time.time() - start_time < duration_seconds:
            conn_start = time.time()

            try:
                # Get client using canonical utility with named database
                db_name = db_name_map.get(db_num, "main")
                client = get_redis_client(database=db_name)
                if client is None:
                    raise Exception(
                        f"Redis client initialization returned None for DB {db_num}"
                    )

                # Test connection with ping
                client.ping()
                client.close()

                conn_time = (time.time() - conn_start) * 1000  # Convert to ms
                latencies.append(conn_time)
                success_count += 1

            except Exception as e:
                error_count += 1
                self.logger.debug(f"Redis connection error DB {db_num}: {e}")

            await asyncio.sleep(0.05)  # Brief pause

        total_operations = success_count + error_count
        actual_duration = time.time() - start_time

        if latencies:
            avg_latency = statistics.mean(latencies)
            p95_latency = (
                np.percentile(latencies, 95) if len(latencies) > 1 else avg_latency
            )
            p99_latency = (
                np.percentile(latencies, 99) if len(latencies) > 1 else avg_latency
            )
        else:
            avg_latency = p95_latency = p99_latency = 0.0

        return BenchmarkResult(
            test_name=f"Redis_DB{db_num}_Connections",
            category="database",
            duration_seconds=actual_duration,
            operations_count=total_operations,
            operations_per_second=total_operations / actual_duration
            if actual_duration > 0
            else 0,
            average_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            success_rate=(success_count / total_operations) * 100
            if total_operations > 0
            else 0,
            error_count=error_count,
            timestamp=datetime.now().isoformat(),
            metadata={"database": f"Redis_DB_{db_num}", "operation": "connection"},
        )

    async def _benchmark_redis_operations(
        self, db_num: int, duration_seconds: int
    ) -> BenchmarkResult:
        """Benchmark Redis read/write operations using canonical utility.

        This follows CLAUDE.md "🔴 REDIS CLIENT USAGE" policy.
        Maps DB numbers to named databases for benchmarking.
        """
        from autobot_shared.redis_client import get_redis_client

        # Map DB numbers to database names for canonical utility
        db_name_map = {
            0: "main",
            1: "knowledge",
            4: "metrics",
            7: "workflows",
            8: "vectors",
        }

        latencies = []
        success_count = 0
        error_count = 0
        start_time = time.time()

        try:
            # Get client using canonical utility with named database
            db_name = db_name_map.get(db_num, "main")
            client = get_redis_client(database=db_name)
            if client is None:
                raise Exception(
                    f"Redis client initialization returned None for DB {db_num}"
                )

            operation_counter = 0

            while time.time() - start_time < duration_seconds:
                op_start = time.time()

                try:
                    # Alternate between read and write operations
                    key = f"benchmark_key_{operation_counter % 1000}"

                    if operation_counter % 2 == 0:
                        # Write operation
                        client.set(key, f"benchmark_value_{operation_counter}")
                    else:
                        # Read operation
                        client.get(key)

                    op_time = (time.time() - op_start) * 1000  # Convert to ms
                    latencies.append(op_time)
                    success_count += 1

                except Exception as e:
                    error_count += 1
                    self.logger.debug(f"Redis operation error: {e}")

                operation_counter += 1

                # Brief pause to avoid overwhelming Redis
                await asyncio.sleep(0.01)

            client.close()

        except Exception as e:
            self.logger.error(f"Redis benchmark setup error for DB {db_num}: {e}")
            return BenchmarkResult(
                test_name=f"Redis_DB{db_num}_Operations",
                category="database",
                duration_seconds=0,
                operations_count=0,
                operations_per_second=0,
                average_latency_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                success_rate=0,
                error_count=1,
                timestamp=datetime.now().isoformat(),
                metadata={
                    "database": f"Redis_DB_{db_num}",
                    "operation": "read_write",
                    "error": str(e),
                },
            )

        total_operations = success_count + error_count
        actual_duration = time.time() - start_time

        if latencies:
            avg_latency = statistics.mean(latencies)
            p95_latency = (
                np.percentile(latencies, 95) if len(latencies) > 1 else avg_latency
            )
            p99_latency = (
                np.percentile(latencies, 99) if len(latencies) > 1 else avg_latency
            )
        else:
            avg_latency = p95_latency = p99_latency = 0.0

        return BenchmarkResult(
            test_name=f"Redis_DB{db_num}_Operations",
            category="database",
            duration_seconds=actual_duration,
            operations_count=total_operations,
            operations_per_second=total_operations / actual_duration
            if actual_duration > 0
            else 0,
            average_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            success_rate=(success_count / total_operations) * 100
            if total_operations > 0
            else 0,
            error_count=error_count,
            timestamp=datetime.now().isoformat(),
            metadata={"database": f"Redis_DB_{db_num}", "operation": "read_write"},
        )

    async def run_network_benchmark(
        self, duration_seconds: int = 30
    ) -> List[BenchmarkResult]:
        """Benchmark inter-VM network performance."""
        self.logger.info(
            f"🔗 Starting network benchmark (duration: {duration_seconds}s)"
        )

        results = []

        # Test network performance to each VM
        for vm_name, vm_ip in VMS.items():
            if vm_name == "main":
                continue

            try:
                result = await self._benchmark_network_latency(
                    vm_name, vm_ip, duration_seconds // len(VMS)
                )
                results.append(result)
            except Exception as e:
                self.logger.error(f"Error benchmarking network to {vm_name}: {e}")

        return results

    async def _benchmark_network_latency(
        self, vm_name: str, vm_ip: str, duration_seconds: int
    ) -> BenchmarkResult:
        """Benchmark network latency to a specific VM."""
        latencies = []
        success_count = 0
        error_count = 0
        start_time = time.time()

        while time.time() - start_time < duration_seconds:
            # Issue #382: Removed unused ping_start variable
            try:
                # Use asyncio subprocess for non-blocking ping
                process = await asyncio.create_subprocess_exec(
                    "ping",
                    "-c",
                    "1",
                    "-W",
                    "1",
                    vm_ip,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    # Parse ping output for latency
                    output = stdout.decode()
                    for line in output.split("\n"):
                        if "time=" in line:
                            time_part = line.split("time=")[1].split()[0]
                            latency_ms = float(time_part)
                            latencies.append(latency_ms)
                            success_count += 1
                            break
                else:
                    error_count += 1

            except Exception as e:
                error_count += 1
                self.logger.debug(f"Ping error to {vm_name}: {e}")

            await asyncio.sleep(0.5)  # Half-second intervals

        total_operations = success_count + error_count
        actual_duration = time.time() - start_time

        if latencies:
            avg_latency = statistics.mean(latencies)
            p95_latency = (
                np.percentile(latencies, 95) if len(latencies) > 1 else avg_latency
            )
            p99_latency = (
                np.percentile(latencies, 99) if len(latencies) > 1 else avg_latency
            )
        else:
            avg_latency = p95_latency = p99_latency = 0.0

        return BenchmarkResult(
            test_name=f"Network_Latency_{vm_name}",
            category="network",
            duration_seconds=actual_duration,
            operations_count=total_operations,
            operations_per_second=total_operations / actual_duration
            if actual_duration > 0
            else 0,
            average_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            success_rate=(success_count / total_operations) * 100
            if total_operations > 0
            else 0,
            error_count=error_count,
            timestamp=datetime.now().isoformat(),
            metadata={"target_vm": vm_name, "target_ip": vm_ip},
        )

    async def run_system_benchmark(self) -> SystemBenchmark:
        """Run comprehensive system benchmarks."""
        self.logger.info("🖥️ Starting system benchmark")

        # CPU benchmark (simplified computation test)
        cpu_score = await self._benchmark_cpu()

        # Memory benchmark
        memory_bandwidth = await self._benchmark_memory()

        # Disk I/O benchmark
        disk_io = await self._benchmark_disk_io()

        # Network throughput
        network_throughput = await self._benchmark_network_throughput()

        # GPU benchmark (if available)
        gpu_score = await self._benchmark_gpu()

        # NPU benchmark (if available)
        npu_score = await self._benchmark_npu()

        return SystemBenchmark(
            cpu_benchmark_score=cpu_score,
            memory_bandwidth_mbps=memory_bandwidth,
            disk_io_mbps=disk_io,
            network_throughput_mbps=network_throughput,
            gpu_compute_score=gpu_score,
            npu_inference_score=npu_score,
        )

    async def _benchmark_cpu(self) -> float:
        """Benchmark CPU performance with mathematical computations."""
        start_time = time.time()

        # Prime number calculation benchmark
        def calculate_primes(limit):
            primes = []
            for num in range(2, limit):
                for i in range(2, int(num**0.5) + 1):
                    if num % i == 0:
                        break
                else:
                    primes.append(num)
            return len(primes)

        # Run CPU-intensive task
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(calculate_primes, 10000) for _ in range(4)]
            results = [future.result() for future in futures]

        duration = time.time() - start_time

        # Calculate score (operations per second, normalized)
        total_operations = sum(results)
        score = (total_operations / duration) / 100  # Normalize to reasonable scale

        return score

    async def _benchmark_memory(self) -> float:
        """Benchmark memory bandwidth."""
        try:
            # Simple memory bandwidth test
            start_time = time.time()

            # Allocate and manipulate large arrays
            data_size = 100 * 1024 * 1024  # 100MB
            test_data = bytearray(data_size)

            # Write test
            for i in range(0, data_size, 1024):
                test_data[i : i + 1024] = b"A" * 1024

            # Read test - sum for memory read timing, result intentionally unused
            _ = sum(test_data[::1024])

            duration = time.time() - start_time

            # Calculate bandwidth in MB/s
            bandwidth = (data_size * 2) / (1024 * 1024 * duration)  # *2 for read+write

            return bandwidth

        except Exception as e:
            self.logger.error(f"Memory benchmark error: {e}")
            return 0.0

    async def _benchmark_disk_io(self) -> float:
        """Benchmark disk I/O performance."""
        try:
            test_file = Path("/tmp/autobot_disk_benchmark.tmp")
            data_size = 50 * 1024 * 1024  # 50MB
            test_data = os.urandom(data_size)

            start_time = time.time()

            # Write test
            with open(test_file, "wb") as f:
                f.write(test_data)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk

            # Read test - read for timing, result intentionally unused
            with open(test_file, "rb") as f:
                _ = f.read()

            duration = time.time() - start_time

            # Cleanup
            test_file.unlink(missing_ok=True)

            # Calculate bandwidth in MB/s
            bandwidth = (data_size * 2) / (1024 * 1024 * duration)  # *2 for read+write

            return bandwidth

        except Exception as e:
            self.logger.error(f"Disk I/O benchmark error: {e}")
            return 0.0

    async def _benchmark_network_throughput(self) -> float:
        """Benchmark network throughput (simplified)."""
        try:
            # Use a simple HTTP throughput test
            timeout = aiohttp.ClientTimeout(total=10.0)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                start_time = time.time()

                # Download a test payload from the backend
                async with session.get(
                    f"http://{VMS['main']}:{NetworkConstants.BACKEND_PORT}/api/health"
                ) as response:
                    data = await response.read()

                duration = time.time() - start_time

                if duration > 0 and len(data) > 0:
                    throughput = (len(data) / duration) / 1024  # KB/s
                    return throughput / 1024  # Convert to MB/s

        except Exception as e:
            self.logger.error(f"Network throughput benchmark error: {e}")

        return 0.0

    async def _benchmark_gpu(self) -> Optional[float]:
        """Benchmark GPU performance (if available)."""
        try:
            # Check if nvidia-smi is available using async subprocess
            process = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
                if process.returncode == 0:
                    # GPU is available, return a simple score
                    # This is a placeholder - actual GPU benchmarking requires CUDA/OpenCL
                    return 85.0  # Placeholder score for RTX 4070
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

        except Exception as e:
            self.logger.debug(f"GPU benchmark error: {e}")

        return None

    async def _benchmark_npu(self) -> Optional[float]:
        """Benchmark NPU performance (Intel AI Boost chip)."""
        try:
            # Check if Intel OpenVINO is available using async subprocess
            openvino_script = (
                "import openvino as ov; "
                "core = ov.Core(); "
                "print(core.available_devices)"
            )
            process = await asyncio.create_subprocess_exec(
                "python3",
                "-c",
                openvino_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
                if process.returncode == 0 and "NPU" in stdout.decode("utf-8"):
                    # NPU is available, return a simple score
                    # Placeholder - actual NPU benchmarking requires specific Intel tools
                    return 45.0  # Placeholder score for Intel NPU
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

        except Exception as e:
            self.logger.debug(f"NPU benchmark error: {e}")

        return None

    async def run_comprehensive_benchmark(self) -> Dict[str, Any]:
        """Run comprehensive benchmark suite."""
        self.logger.info("🚀 Starting comprehensive AutoBot performance benchmark")

        start_time = time.time()

        # Run all benchmark categories
        api_results = await self.run_api_benchmark(duration_seconds=120)
        database_results = await self.run_database_benchmark(duration_seconds=60)
        network_results = await self.run_network_benchmark(duration_seconds=60)
        system_benchmark = await self.run_system_benchmark()

        total_duration = time.time() - start_time

        # Compile all results
        all_results = api_results + database_results + network_results
        self.results.extend(all_results)

        # Generate summary
        summary = self._generate_benchmark_summary(all_results, system_benchmark)

        # Save results
        await self._save_benchmark_results(all_results, system_benchmark, summary)

        self.logger.info(
            f"✅ Comprehensive benchmark completed in {total_duration:.1f}s"
        )

        return {
            "summary": summary,
            "api_results": [asdict(r) for r in api_results],
            "database_results": [asdict(r) for r in database_results],
            "network_results": [asdict(r) for r in network_results],
            "system_benchmark": asdict(system_benchmark),
            "total_duration_seconds": total_duration,
        }

    def _generate_benchmark_summary(
        self, results: List[BenchmarkResult], system_benchmark: SystemBenchmark
    ) -> Dict[str, Any]:
        """Generate benchmark summary statistics."""
        if not results:
            return {}

        # Group results by category
        by_category = {}
        for result in results:
            if result.category not in by_category:
                by_category[result.category] = []
            by_category[result.category].append(result)

        # Calculate category summaries
        category_summaries = {}
        for category, cat_results in by_category.items():
            avg_ops_per_sec = statistics.mean(
                [r.operations_per_second for r in cat_results]
            )
            avg_latency = statistics.mean([r.average_latency_ms for r in cat_results])
            avg_success_rate = statistics.mean([r.success_rate for r in cat_results])

            category_summaries[category] = {
                "test_count": len(cat_results),
                "average_ops_per_second": avg_ops_per_sec,
                "average_latency_ms": avg_latency,
                "average_success_rate": avg_success_rate,
                "total_errors": sum([r.error_count for r in cat_results]),
            }

        # Overall system score (simplified)
        system_score = self._calculate_overall_score(results, system_benchmark)

        return {
            "timestamp": datetime.now().isoformat(),
            "overall_system_score": system_score,
            "total_tests": len(results),
            "category_summaries": category_summaries,
            "system_hardware": {
                "cpu_score": system_benchmark.cpu_benchmark_score,
                "memory_bandwidth_mbps": system_benchmark.memory_bandwidth_mbps,
                "disk_io_mbps": system_benchmark.disk_io_mbps,
                "network_throughput_mbps": system_benchmark.network_throughput_mbps,
                "gpu_available": system_benchmark.gpu_compute_score is not None,
                "npu_available": system_benchmark.npu_inference_score is not None,
            },
            "performance_grade": self._get_performance_grade(system_score),
        }

    def _calculate_overall_score(
        self, results: List[BenchmarkResult], system_benchmark: SystemBenchmark
    ) -> float:
        """Calculate overall system performance score (0-100)."""
        if not results:
            return 0.0

        # Weight different aspects
        weights = {
            "api_performance": 0.3,
            "database_performance": 0.25,
            "network_performance": 0.2,
            "system_performance": 0.25,
        }

        scores = {}

        # API performance score (based on ops/sec and success rate)
        api_results = [r for r in results if r.category == "api"]
        if api_results:
            avg_ops = statistics.mean([r.operations_per_second for r in api_results])
            avg_success = statistics.mean([r.success_rate for r in api_results])
            scores["api_performance"] = min(100, (avg_ops * avg_success) / 10)
        else:
            scores["api_performance"] = 0

        # Database performance score
        db_results = [r for r in results if r.category == "database"]
        if db_results:
            avg_ops = statistics.mean([r.operations_per_second for r in db_results])
            avg_success = statistics.mean([r.success_rate for r in db_results])
            scores["database_performance"] = min(100, (avg_ops * avg_success) / 50)
        else:
            scores["database_performance"] = 0

        # Network performance score
        network_results = [r for r in results if r.category == "network"]
        if network_results:
            avg_success = statistics.mean([r.success_rate for r in network_results])
            avg_latency = statistics.mean(
                [r.average_latency_ms for r in network_results]
            )
            # Lower latency is better
            latency_score = max(0, 100 - avg_latency)
            scores["network_performance"] = (avg_success + latency_score) / 2
        else:
            scores["network_performance"] = 0

        # System performance score (normalized hardware benchmarks)
        cpu_score = min(100, system_benchmark.cpu_benchmark_score * 2)  # Normalize
        memory_score = min(
            100, system_benchmark.memory_bandwidth_mbps / 50
        )  # Normalize
        disk_score = min(100, system_benchmark.disk_io_mbps / 10)  # Normalize

        scores["system_performance"] = (cpu_score + memory_score + disk_score) / 3

        # Calculate weighted overall score
        overall_score = sum(
            scores[aspect] * weights[aspect] for aspect in weights.keys()
        )

        return round(overall_score, 1)

    # Issue #339: Grade thresholds as lookup table
    _GRADE_THRESHOLDS = [
        (90, "A+"),
        (80, "A"),
        (70, "B+"),
        (60, "B"),
        (50, "C+"),
        (40, "C"),
    ]

    def _get_performance_grade(self, score: float) -> str:
        """Get performance grade based on score (Issue #339 - refactored with lookup table)."""
        for threshold, grade in self._GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return "D"

    async def _save_benchmark_results(
        self,
        results: List[BenchmarkResult],
        system_benchmark: SystemBenchmark,
        summary: Dict[str, Any],
    ):
        """Save benchmark results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save JSON results
        json_file = self.output_dir / f"benchmark_results_{timestamp}.json"
        benchmark_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "results": [asdict(r) for r in results],
            "system_benchmark": asdict(system_benchmark),
        }

        with open(json_file, "w") as f:
            json.dump(benchmark_data, f, indent=2)

        self.logger.info(f"📊 Benchmark results saved to: {json_file}")

        # Generate and save performance charts
        await self._generate_performance_charts(results, timestamp)

    async def _generate_performance_charts(
        self, results: List[BenchmarkResult], timestamp: str
    ):
        """Generate performance visualization charts."""
        try:
            plt.style.use("dark_background")
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
            fig.suptitle(
                "AutoBot Performance Benchmark Results", fontsize=16, color="white"
            )

            # Chart 1: Operations per Second by Test
            test_names = [r.test_name for r in results]
            ops_per_sec = [r.operations_per_second for r in results]

            ax1.barh(test_names, ops_per_sec, color="skyblue")
            ax1.set_xlabel("Operations per Second")
            ax1.set_title("Throughput Performance")
            ax1.tick_params(axis="y", labelsize=8)

            # Chart 2: Latency Distribution
            latencies = [
                r.average_latency_ms for r in results if r.average_latency_ms > 0
            ]
            if latencies:
                ax2.hist(latencies, bins=20, color="lightgreen", alpha=0.7)
                ax2.set_xlabel("Average Latency (ms)")
                ax2.set_ylabel("Frequency")
                ax2.set_title("Latency Distribution")

            # Chart 3: Success Rate by Category
            categories = list(set([r.category for r in results]))
            success_rates = []
            for category in categories:
                cat_results = [r for r in results if r.category == category]
                avg_success = statistics.mean([r.success_rate for r in cat_results])
                success_rates.append(avg_success)

            ax3.bar(categories, success_rates, color="orange")
            ax3.set_ylabel("Success Rate (%)")
            ax3.set_title("Success Rate by Category")
            ax3.set_ylim(0, 100)

            # Chart 4: P95 vs P99 Latency
            p95_latencies = [r.p95_latency_ms for r in results if r.p95_latency_ms > 0]
            p99_latencies = [r.p99_latency_ms for r in results if r.p99_latency_ms > 0]

            if p95_latencies and p99_latencies:
                x = range(len(p95_latencies))
                ax4.plot(x, p95_latencies, "o-", label="P95", color="yellow")
                ax4.plot(x, p99_latencies, "s-", label="P99", color="red")
                ax4.set_xlabel("Test Number")
                ax4.set_ylabel("Latency (ms)")
                ax4.set_title("P95 vs P99 Latency")
                ax4.legend()

            plt.tight_layout()

            # Save chart
            chart_file = self.output_dir / f"benchmark_charts_{timestamp}.png"
            plt.savefig(chart_file, dpi=150, bbox_inches="tight", facecolor="black")
            plt.close()

            self.logger.info(f"📈 Performance charts saved to: {chart_file}")

        except Exception as e:
            self.logger.error(f"Error generating performance charts: {e}")


async def main():
    """Main function for performance benchmarking."""
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot Performance Benchmark Suite")
    parser.add_argument(
        "--test",
        choices=["api", "database", "network", "system", "comprehensive"],
        default="comprehensive",
        help="Type of benchmark to run",
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="Benchmark duration in seconds"
    )
    parser.add_argument(
        "--output-dir",
        default="/home/kali/Desktop/AutoBot/logs/benchmarks",
        help="Output directory for results",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    benchmark = PerformanceBenchmark(output_dir=args.output_dir)

    logger.info("🚀 AutoBot Performance Benchmark Suite")
    logger.info("=" * 60)

    if args.test == "comprehensive":
        results = await benchmark.run_comprehensive_benchmark()

        logger.info("\n📊 Comprehensive Benchmark Results:")
        logger.info("=" * 60)

        summary = results["summary"]
        logger.info(
            f"Overall System Score: {summary['overall_system_score']:.1f}/100 (Grade: {summary['performance_grade']})"
        )
        logger.info(f"Total Tests: {summary['total_tests']}")
        logger.info("")

        logger.info("Category Performance:")
        for category, stats in summary["category_summaries"].items():
            logger.info(f"  {category.title()}:")
            logger.info(f"    Avg Ops/Sec: {stats['average_ops_per_second']:.1f}")
            logger.info(f"    Avg Latency: {stats['average_latency_ms']:.1f}ms")
            logger.info(f"    Success Rate: {stats['average_success_rate']:.1f}%")
            logger.info(f"    Errors: {stats['total_errors']}")
            logger.info("")

        logger.info("Hardware Performance:")
        hw = summary["system_hardware"]
        logger.info(f"  CPU Score: {hw['cpu_score']:.1f}")
        logger.info(f"  Memory Bandwidth: {hw['memory_bandwidth_mbps']:.1f} MB/s")
        logger.info(f"  Disk I/O: {hw['disk_io_mbps']:.1f} MB/s")
        logger.info(f"  Network Throughput: {hw['network_throughput_mbps']:.1f} MB/s")
        logger.info(f"  GPU Available: {'Yes' if hw['gpu_available'] else 'No'}")
        logger.info(f"  NPU Available: {'Yes' if hw['npu_available'] else 'No'}")

    elif args.test == "api":
        results = await benchmark.run_api_benchmark(duration_seconds=args.duration)
        logger.info(f"\n📡 API Benchmark Results ({len(results)} tests):")
        # Issue #372: Use model method to reduce feature envy
        for result in results:
            logger.info(f"  {result.get_summary_line()}")

    elif args.test == "database":
        results = await benchmark.run_database_benchmark(duration_seconds=args.duration)
        logger.info(f"\n🗄️ Database Benchmark Results ({len(results)} tests):")
        # Issue #372: Use model method to reduce feature envy
        for result in results:
            logger.info(f"  {result.get_summary_line()}")

    elif args.test == "network":
        results = await benchmark.run_network_benchmark(duration_seconds=args.duration)
        logger.info(f"\n🔗 Network Benchmark Results ({len(results)} tests):")
        # Issue #372: Use model method for latency-focused output
        for result in results:
            logger.info(f"  {result.get_latency_only_line()}")

    elif args.test == "system":
        result = await benchmark.run_system_benchmark()
        logger.info("\n🖥️ System Benchmark Results:")
        # Issue #372: Use model method to reduce feature envy
        for line in result.get_summary_lines():
            logger.info(line)


if __name__ == "__main__":
    asyncio.run(main())
