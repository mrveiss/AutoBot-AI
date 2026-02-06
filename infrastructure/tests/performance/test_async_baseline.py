#!/usr/bin/env python3
"""
AutoBot Async Operations Baseline Performance Testing
Week 2-3: Task 2.5 - Performance Load Testing

CRITICAL: This script establishes the BASELINE performance metrics BEFORE async conversions.
After senior-backend-engineer completes async conversions (Tasks 2.1-2.4), re-run this script
to validate 10-50x performance improvements.

Test Scenarios (from implementation plan):
1. 50 concurrent chat requests
2. 100 concurrent Redis operations
3. Mixed file I/O and Redis operations
4. Cross-VM concurrent requests

Success Metrics:
- Chat response time: <2s (p95), down from 10-50s baseline
- 50+ concurrent users supported without degradation
- Event loop blocking eliminated (measured with profiling)
- Cross-VM latency: <100ms (p95)
"""

import asyncio
import json
import logging
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import aiohttp

from src.constants.network_constants import NetworkConstants, ServiceURLs

# Import canonical Redis client pattern
from src.utils.redis_client import get_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance test results"""

    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    duration_seconds: float
    requests_per_second: float
    mean_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    std_dev_latency_ms: float
    timestamp: str
    metadata: Dict[str, Any] = None


class AsyncBaselineTest:
    """Async operations baseline performance testing suite"""

    def __init__(self):
        self.backend_url = ServiceURLs.BACKEND_API
        self.redis_host = NetworkConstants.REDIS_VM_IP
        self.redis_port = NetworkConstants.REDIS_PORT
        self.results = []

    async def measure_latency(self, coro) -> float:
        """Measure coroutine execution latency in milliseconds"""
        start = time.perf_counter()
        await coro
        end = time.perf_counter()
        return (end - start) * 1000  # Convert to ms

    def calculate_metrics(
        self,
        test_name: str,
        latencies: List[float],
        success_count: int,
        fail_count: int,
        duration: float,
        metadata: Dict[str, Any] = None,
    ) -> PerformanceMetrics:
        """Calculate performance metrics from latency measurements"""
        total = success_count + fail_count

        if latencies:
            mean = statistics.mean(latencies)
            median = statistics.median(latencies)
            p95 = (
                sorted(latencies)[int(len(latencies) * 0.95)]
                if len(latencies) > 1
                else mean
            )
            p99 = (
                sorted(latencies)[int(len(latencies) * 0.99)]
                if len(latencies) > 1
                else mean
            )
            min_lat = min(latencies)
            max_lat = max(latencies)
            std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
        else:
            mean = median = p95 = p99 = min_lat = max_lat = std_dev = 0.0

        return PerformanceMetrics(
            test_name=test_name,
            total_requests=total,
            successful_requests=success_count,
            failed_requests=fail_count,
            duration_seconds=duration,
            requests_per_second=total / duration if duration > 0 else 0,
            mean_latency_ms=mean,
            median_latency_ms=median,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            min_latency_ms=min_lat,
            max_latency_ms=max_lat,
            std_dev_latency_ms=std_dev,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {},
        )

    async def test_concurrent_chat_requests(
        self, concurrent_users: int = 50
    ) -> PerformanceMetrics:
        """
        Test Scenario 1: Concurrent chat requests

        Baseline expectation: 10-50s response time with event loop blocking
        Target after async: <2s (p95) without blocking
        """
        logger.info(f"🚀 Starting concurrent chat test ({concurrent_users} users)...")

        test_message = "What is AutoBot's architecture?"
        latencies = []
        success_count = 0
        fail_count = 0

        async def send_chat_request(session, user_id):
            """Send single chat request"""
            try:
                url = f"{self.backend_url}/api/chat"
                payload = {
                    "message": test_message,
                    "session_id": f"baseline_test_session_{user_id}",
                }

                start = time.perf_counter()
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=60.0)
                ) as response:
                    await response.text()
                    end = time.perf_counter()

                    latency = (end - start) * 1000  # ms
                    latencies.append(latency)

                    if response.status < 400:
                        return "success"
                    else:
                        return "failed"

            except Exception as e:
                logger.debug(f"Chat request failed for user {user_id}: {e}")
                return "failed"

        start_time = time.perf_counter()

        async with aiohttp.ClientSession() as session:
            # Launch all requests concurrently
            tasks = [send_chat_request(session, i) for i in range(concurrent_users)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.perf_counter()
        duration = end_time - start_time

        # Count successes and failures
        success_count = sum(1 for r in results if r == "success")
        fail_count = sum(
            1 for r in results if r == "failed" or isinstance(r, Exception)
        )

        metrics = self.calculate_metrics(
            test_name=f"concurrent_chat_{concurrent_users}_users",
            latencies=latencies,
            success_count=success_count,
            fail_count=fail_count,
            duration=duration,
            metadata={
                "concurrent_users": concurrent_users,
                "test_message": test_message,
                "baseline_threshold": "10-50s",
                "target_after_async": "<2s p95",
            },
        )

        self.results.append(metrics)
        logger.info(
            f"✅ Chat test complete: {success_count}/{concurrent_users} successful, "
            f"p95={metrics.p95_latency_ms:.0f}ms, duration={duration:.1f}s"
        )

        return metrics

    async def test_concurrent_redis_operations(
        self, operations: int = 100
    ) -> PerformanceMetrics:
        """
        Test Scenario 2: Concurrent Redis operations

        Tests synchronous vs async Redis client performance under load
        """
        logger.info(f"🗄️  Starting concurrent Redis test ({operations} operations)...")

        latencies = []
        success_count = 0
        fail_count = 0

        async def redis_operation(redis_client, op_id):
            """Single Redis set/get operation"""
            try:
                key = f"baseline_test_key_{op_id}"
                value = f"baseline_test_value_{op_id}"

                start = time.perf_counter()

                # Write operation
                await redis_client.set(key, value, ex=60)  # 60s TTL

                # Read operation
                retrieved = await redis_client.get(key)

                end = time.perf_counter()

                latency = (end - start) * 1000  # ms
                latencies.append(latency)

                if retrieved:
                    return "success"
                else:
                    return "failed"

            except Exception as e:
                logger.debug(f"Redis operation failed for op {op_id}: {e}")
                return "failed"

        start_time = time.perf_counter()

        # Create async Redis connection using canonical pattern
        redis_client = await get_redis_client(
            async_client=True, database="metrics"  # METRICS_DB
        )

        try:
            # Launch all operations concurrently
            tasks = [redis_operation(redis_client, i) for i in range(operations)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        finally:
            await redis_client.close()

        end_time = time.perf_counter()
        duration = end_time - start_time

        # Count successes and failures
        success_count = sum(1 for r in results if r == "success")
        fail_count = sum(
            1 for r in results if r == "failed" or isinstance(r, Exception)
        )

        metrics = self.calculate_metrics(
            test_name=f"concurrent_redis_{operations}_ops",
            latencies=latencies,
            success_count=success_count,
            fail_count=fail_count,
            duration=duration,
            metadata={
                "total_operations": operations,
                "operations_per_request": 2,  # set + get
                "redis_host": self.redis_host,
            },
        )

        self.results.append(metrics)
        logger.info(
            f"✅ Redis test complete: {success_count}/{operations} successful, "
            f"p95={metrics.p95_latency_ms:.0f}ms, {metrics.requests_per_second:.0f} ops/sec"
        )

        return metrics

    async def test_mixed_io_operations(
        self, operations: int = 50
    ) -> PerformanceMetrics:
        """
        Test Scenario 3: Mixed file I/O and Redis operations

        Tests realistic workload combining file writes and Redis caching
        """
        logger.info(f"💾 Starting mixed I/O test ({operations} operations)...")

        latencies = []
        success_count = 0
        fail_count = 0

        # Create temp directory for test files
        test_dir = Path("/tmp/autobot_baseline_test")
        test_dir.mkdir(parents=True, exist_ok=True)

        async def mixed_io_operation(redis_client, op_id):
            """Combined file write + Redis operation"""
            try:
                import aiofiles

                start = time.perf_counter()

                # File write operation (simulate transcript append)
                file_path = test_dir / f"test_file_{op_id}.json"
                test_data = {"op_id": op_id, "timestamp": datetime.now().isoformat()}

                async with aiofiles.open(file_path, "w") as f:
                    await f.write(json.dumps(test_data))

                # Redis cache operation
                cache_key = f"baseline_cache_{op_id}"
                await redis_client.set(cache_key, json.dumps(test_data), ex=60)

                # Verify both operations
                async with aiofiles.open(file_path, "r") as f:
                    file_content = await f.read()

                cached_content = await redis_client.get(cache_key)

                end = time.perf_counter()

                latency = (end - start) * 1000  # ms
                latencies.append(latency)

                # Cleanup
                file_path.unlink()

                if file_content and cached_content:
                    return "success"
                else:
                    return "failed"

            except Exception as e:
                logger.debug(f"Mixed I/O operation failed for op {op_id}: {e}")
                return "failed"

        start_time = time.perf_counter()

        # Create async Redis connection using canonical pattern
        redis_client = await get_redis_client(
            async_client=True, database="metrics"  # METRICS_DB
        )

        try:
            # Launch all operations concurrently
            tasks = [mixed_io_operation(redis_client, i) for i in range(operations)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        finally:
            await redis_client.close()
            # Cleanup test directory
            import shutil

            shutil.rmtree(test_dir, ignore_errors=True)

        end_time = time.perf_counter()
        duration = end_time - start_time

        # Count successes and failures
        success_count = sum(1 for r in results if r == "success")
        fail_count = sum(
            1 for r in results if r == "failed" or isinstance(r, Exception)
        )

        metrics = self.calculate_metrics(
            test_name=f"mixed_io_{operations}_ops",
            latencies=latencies,
            success_count=success_count,
            fail_count=fail_count,
            duration=duration,
            metadata={
                "total_operations": operations,
                "io_types": ["file_write", "redis_set", "file_read", "redis_get"],
            },
        )

        self.results.append(metrics)
        logger.info(
            f"✅ Mixed I/O test complete: {success_count}/{operations} successful, "
            f"p95={metrics.p95_latency_ms:.0f}ms"
        )

        return metrics

    async def test_cross_vm_latency(self, requests: int = 20) -> PerformanceMetrics:
        """
        Test Scenario 4: Cross-VM concurrent requests

        Tests inter-VM communication performance (main -> frontend, npu-worker, etc.)
        """
        logger.info(f"🔗 Starting cross-VM latency test ({requests} requests per VM)...")

        vm_endpoints = {
            "frontend": f"{ServiceURLs.FRONTEND_VM}/",
            "npu-worker": f"{ServiceURLs.NPU_WORKER_SERVICE}/health",
            "redis": f"{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.REDIS_PORT}",  # Redis uses different protocol
            "ai-stack": f"{ServiceURLs.AI_STACK_SERVICE}/health",
        }

        latencies = []
        success_count = 0
        fail_count = 0

        async def test_vm_endpoint(session, vm_name, endpoint, request_id):
            """Test single VM endpoint"""
            try:
                if vm_name == "redis":
                    # Special handling for Redis (not HTTP) using canonical pattern
                    redis_client = await get_redis_client(
                        async_client=True, database="main"  # MAIN_DB (default DB 0)
                    )
                    try:
                        start = time.perf_counter()
                        await redis_client.ping()
                        end = time.perf_counter()
                    finally:
                        await redis_client.close()
                else:
                    # HTTP endpoint
                    start = time.perf_counter()
                    async with session.get(
                        endpoint, timeout=aiohttp.ClientTimeout(total=10.0)
                    ) as response:
                        await response.text()
                        end = time.perf_counter()

                latency = (end - start) * 1000  # ms
                latencies.append(latency)
                return "success"

            except Exception as e:
                logger.debug(
                    f"Cross-VM request failed ({vm_name}, req {request_id}): {e}"
                )
                return "failed"

        start_time = time.perf_counter()

        async with aiohttp.ClientSession() as session:
            # Create tasks for all VMs and requests
            tasks = []
            for vm_name, endpoint in vm_endpoints.items():
                for req_id in range(requests):
                    tasks.append(test_vm_endpoint(session, vm_name, endpoint, req_id))

            results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.perf_counter()
        duration = end_time - start_time

        # Count successes and failures
        success_count = sum(1 for r in results if r == "success")
        fail_count = sum(
            1 for r in results if r == "failed" or isinstance(r, Exception)
        )

        metrics = self.calculate_metrics(
            test_name=f"cross_vm_latency_{len(vm_endpoints)}_vms",
            latencies=latencies,
            success_count=success_count,
            fail_count=fail_count,
            duration=duration,
            metadata={
                "vms_tested": list(vm_endpoints.keys()),
                "requests_per_vm": requests,
                "target_p95": "<100ms",
            },
        )

        self.results.append(metrics)
        logger.info(
            f"✅ Cross-VM test complete: {success_count}/{len(tasks)} successful, "
            f"p95={metrics.p95_latency_ms:.0f}ms"
        )

        return metrics

    async def run_comprehensive_baseline(self) -> Dict[str, Any]:
        """Run all baseline performance tests"""
        logger.info("=" * 80)
        logger.info("🚀 AutoBot Async Baseline Performance Testing")
        logger.info("Week 2-3 Task 2.5: Baseline Measurement BEFORE Async Conversions")
        logger.info("=" * 80)

        start_time = time.perf_counter()

        # Run all test scenarios
        await self.test_concurrent_chat_requests(concurrent_users=50)
        await asyncio.sleep(2)  # Brief pause between tests

        await self.test_concurrent_redis_operations(operations=100)
        await asyncio.sleep(2)

        await self.test_mixed_io_operations(operations=50)
        await asyncio.sleep(2)

        await self.test_cross_vm_latency(requests=20)

        total_duration = time.perf_counter() - start_time

        # Generate summary report
        summary = self.generate_baseline_report(total_duration)

        logger.info("=" * 80)
        logger.info("✅ Baseline Testing Complete")
        logger.info("=" * 80)

        return summary

    def generate_baseline_report(self, total_duration: float) -> Dict[str, Any]:
        """Generate comprehensive baseline report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "test_phase": "BASELINE_BEFORE_ASYNC_CONVERSIONS",
            "total_duration_seconds": total_duration,
            "total_tests": len(self.results),
            "test_results": [asdict(r) for r in self.results],
            "summary": {},
            "performance_analysis": {},
        }

        # Calculate summary statistics
        total_requests = sum(r.total_requests for r in self.results)
        total_successful = sum(r.successful_requests for r in self.results)

        report["summary"] = {
            "total_requests": total_requests,
            "total_successful": total_successful,
            "overall_success_rate": (total_successful / total_requests * 100)
            if total_requests > 0
            else 0,
        }

        # Performance analysis against targets
        chat_test = next(
            (r for r in self.results if "concurrent_chat" in r.test_name), None
        )
        redis_test = next(
            (r for r in self.results if "concurrent_redis" in r.test_name), None
        )
        cross_vm_test = next(
            (r for r in self.results if "cross_vm" in r.test_name), None
        )

        report["performance_analysis"] = {
            "chat_performance": {
                "baseline_p95_ms": chat_test.p95_latency_ms if chat_test else 0,
                "target_after_async_ms": 2000,  # 2s target
                "meets_target": (chat_test.p95_latency_ms < 2000)
                if chat_test
                else False,
                "improvement_needed": "10-50x faster"
                if chat_test and chat_test.p95_latency_ms > 10000
                else "Already fast",
            },
            "redis_performance": {
                "baseline_ops_per_sec": redis_test.requests_per_second
                if redis_test
                else 0,
                "target_ops_per_sec": 1000,  # Target throughput
                "meets_target": (redis_test.requests_per_second > 1000)
                if redis_test
                else False,
            },
            "cross_vm_latency": {
                "baseline_p95_ms": cross_vm_test.p95_latency_ms if cross_vm_test else 0,
                "target_p95_ms": 100,  # <100ms target
                "meets_target": (cross_vm_test.p95_latency_ms < 100)
                if cross_vm_test
                else False,
            },
        }

        # Save report to file
        output_dir = Path("/home/kali/Desktop/AutoBot/tests/performance/results")
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_dir / f"async_baseline_{timestamp_str}.json"

        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"📊 Baseline report saved: {report_file}")

        # Print summary
        print("\n" + "=" * 80)
        print("📊 BASELINE PERFORMANCE SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {report['total_tests']}")
        print(f"Total Requests: {total_requests}")
        print(f"Success Rate: {report['summary']['overall_success_rate']:.1f}%")
        print()

        if chat_test:
            print("Chat Performance (50 concurrent users):")
            print(f"  P95 Latency: {chat_test.p95_latency_ms:.0f}ms")
            print("  Target After Async: <2000ms")
            print(
                f"  Status: {'✅ MEETS TARGET' if chat_test.p95_latency_ms < 2000 else '❌ NEEDS ASYNC OPTIMIZATION'}"
            )
            print()

        if redis_test:
            print("Redis Performance (100 concurrent ops):")
            print(f"  Throughput: {redis_test.requests_per_second:.0f} ops/sec")
            print(f"  P95 Latency: {redis_test.p95_latency_ms:.0f}ms")
            print(
                f"  Status: {'✅ GOOD' if redis_test.requests_per_second > 500 else '⚠️ COULD BE FASTER'}"
            )
            print()

        if cross_vm_test:
            print("Cross-VM Latency:")
            print(f"  P95 Latency: {cross_vm_test.p95_latency_ms:.0f}ms")
            print("  Target: <100ms")
            print(
                f"  Status: {'✅ MEETS TARGET' if cross_vm_test.p95_latency_ms < 100 else '❌ HIGH LATENCY'}"
            )
            print()

        print("=" * 80)
        print(f"📄 Full report: {report_file}")
        print("=" * 80)

        return report


async def main():
    """Main execution function"""
    tester = AsyncBaselineTest()

    try:
        await tester.run_comprehensive_baseline()
        return 0
    except KeyboardInterrupt:
        logger.warning("🛑 Testing interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"❌ Testing failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
