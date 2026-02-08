#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Manager Performance Testing
GitHub Issue #163 - Task 4.3: Performance Testing with Large Datasets

Tests performance targets for:
1. Category filtering operations (<200ms target)
2. Vectorization status loading (<500ms for 1000 facts target)
3. UI responsiveness (no freezing)

Test Scenarios:
- 1000+ facts with categories
- Mixed vectorization states
- Rapid filtering operations
- Cache effectiveness
- Concurrent operations
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
from typing import Any, Dict, List, Optional

import aiohttp
from src.constants.network_constants import ServiceURLs

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
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    std_dev_latency_ms: float
    cache_hit_ratio: Optional[float]
    timestamp: str
    passed: bool
    target_ms: float
    metadata: Dict[str, Any] = None


class KnowledgePerformanceTest:
    """Knowledge Manager performance testing suite"""

    def __init__(self):
        self.backend_url = ServiceURLs.BACKEND_API
        self.results = []

        # Performance targets from Issue #163
        self.CATEGORY_FILTER_TARGET_MS = 200
        self.STATUS_LOAD_TARGET_MS = 500
        self.RAPID_FILTER_TARGET_MS = 200

    def calculate_metrics(
        self,
        test_name: str,
        latencies: List[float],
        success_count: int,
        fail_count: int,
        duration: float,
        target_ms: float,
        cache_hit_ratio: Optional[float] = None,
        metadata: Dict[str, Any] = None,
    ) -> PerformanceMetrics:
        """Calculate performance metrics from latency measurements"""
        total = success_count + fail_count

        if latencies:
            mean = statistics.mean(latencies)
            median = statistics.median(latencies)
            sorted_latencies = sorted(latencies)
            p50 = (
                sorted_latencies[int(len(latencies) * 0.50)]
                if len(latencies) > 1
                else mean
            )
            p95 = (
                sorted_latencies[int(len(latencies) * 0.95)]
                if len(latencies) > 1
                else mean
            )
            p99 = (
                sorted_latencies[int(len(latencies) * 0.99)]
                if len(latencies) > 1
                else mean
            )
            min_lat = min(latencies)
            max_lat = max(latencies)
            std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
        else:
            mean = median = p50 = p95 = p99 = min_lat = max_lat = std_dev = 0.0

        # Test passes if p95 latency is below target
        passed = p95 < target_ms

        return PerformanceMetrics(
            test_name=test_name,
            total_requests=total,
            successful_requests=success_count,
            failed_requests=fail_count,
            duration_seconds=duration,
            requests_per_second=total / duration if duration > 0 else 0,
            mean_latency_ms=mean,
            median_latency_ms=median,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            min_latency_ms=min_lat,
            max_latency_ms=max_lat,
            std_dev_latency_ms=std_dev,
            cache_hit_ratio=cache_hit_ratio,
            timestamp=datetime.now().isoformat(),
            passed=passed,
            target_ms=target_ms,
            metadata=metadata or {},
        )

    async def get_knowledge_stats(self) -> Dict[str, Any]:
        """Get current knowledge base statistics"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.backend_url}/api/knowledge_base/stats"
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10.0)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Failed to get stats: {response.status}")
                        return {}
            except Exception as e:
                logger.warning(f"Error getting stats: {e}")
                return {}

    async def populate_test_data_if_needed(self, target_facts: int = 1000) -> bool:
        """
        Ensure knowledge base has sufficient test data.
        Returns True if sufficient data exists, False otherwise.
        """
        logger.info(f"📊 Checking knowledge base for at least {target_facts} facts...")

        stats = await self.get_knowledge_stats()
        current_facts = stats.get("total_facts", 0)

        logger.info(f"Current facts in knowledge base: {current_facts}")

        if current_facts >= target_facts:
            logger.info(f"✅ Sufficient test data exists ({current_facts} facts)")
            return True
        else:
            logger.warning(
                f"⚠️  Insufficient test data: {current_facts}/{target_facts} facts"
            )
            logger.warning(
                "Please populate knowledge base with system commands and man pages:"
            )
            logger.warning(
                f"  curl -X POST {self.backend_url}/api/knowledge_base/populate_system_commands"
            )
            logger.warning(
                f"  curl -X POST {self.backend_url}/api/knowledge_base/populate_man_pages"
            )
            return False

    async def test_category_filter_performance(
        self, iterations: int = 50
    ) -> PerformanceMetrics:
        """
        Test Scenario 1: Category Filter Performance
        Target: < 200ms per filter operation

        Tests:
        - Filter with 1000+ facts
        - Multiple categories
        - Cache hit vs cache miss
        """
        logger.info(f"🔍 Starting category filter test ({iterations} iterations)...")

        # Get list of available categories
        stats = await self.get_knowledge_stats()
        categories = stats.get("categories", [])

        if not categories:
            logger.error("No categories found in knowledge base")
            return self.calculate_metrics(
                test_name="category_filter_performance",
                latencies=[],
                success_count=0,
                fail_count=iterations,
                duration=0.0,
                target_ms=self.CATEGORY_FILTER_TARGET_MS,
                metadata={"error": "No categories found"},
            )

        logger.info(f"Testing with {len(categories)} categories: {categories[:5]}...")

        latencies = []
        success_count = 0
        fail_count = 0
        cache_hits = 0
        cache_misses = 0

        async def filter_by_category(session, category: Optional[str], iteration: int):
            """Single category filter request"""
            try:
                url = f"{self.backend_url}/api/knowledge_base/facts/by_category"
                params = {"limit": 100}
                if category:
                    params["category"] = category

                start = time.perf_counter()
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=5.0)
                ) as response:
                    _data = await response.json()
                    end = time.perf_counter()

                    latency = (end - start) * 1000  # ms
                    latencies.append(latency)

                    # Detect cache hit/miss from response time
                    # Cache hits should be < 50ms typically
                    nonlocal cache_hits, cache_misses
                    if latency < 50:
                        cache_hits += 1
                    else:
                        cache_misses += 1

                    if response.status == 200:
                        return "success"
                    else:
                        logger.debug(f"Filter failed: {response.status}")
                        return "failed"

            except Exception as e:
                logger.debug(f"Category filter request failed (iter {iteration}): {e}")
                return "failed"

        start_time = time.perf_counter()

        async with aiohttp.ClientSession() as session:
            tasks = []

            # Test with multiple categories
            for i in range(iterations):
                # Alternate between different categories and "all"
                if i % 5 == 0:
                    category = None  # Get all categories
                else:
                    category = categories[i % len(categories)]

                tasks.append(filter_by_category(session, category, i))

            results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.perf_counter()
        duration = end_time - start_time

        # Count successes and failures
        success_count = sum(1 for r in results if r == "success")
        fail_count = sum(
            1 for r in results if r == "failed" or isinstance(r, Exception)
        )

        cache_hit_ratio = (
            cache_hits / (cache_hits + cache_misses)
            if (cache_hits + cache_misses) > 0
            else 0.0
        )

        metrics = self.calculate_metrics(
            test_name="category_filter_performance",
            latencies=latencies,
            success_count=success_count,
            fail_count=fail_count,
            duration=duration,
            target_ms=self.CATEGORY_FILTER_TARGET_MS,
            cache_hit_ratio=cache_hit_ratio,
            metadata={
                "iterations": iterations,
                "categories_tested": len(categories),
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
                "total_facts": stats.get("total_facts", 0),
            },
        )

        self.results.append(metrics)

        status_icon = "✅" if metrics.passed else "❌"
        logger.info(
            f"{status_icon} Category filter test complete: {success_count}/{iterations} successful, "
            f"p95={metrics.p95_latency_ms:.0f}ms (target: {self.CATEGORY_FILTER_TARGET_MS}ms), "
            f"cache_hit_ratio={cache_hit_ratio:.1%}"
        )

        return metrics

    async def test_vectorization_status_load(
        self, fact_count: int = 1000
    ) -> PerformanceMetrics:
        """
        Test Scenario 2: Vectorization Status Load Performance
        Target: < 500ms for 1000 facts

        Tests batch status check for multiple facts
        """
        logger.info(
            f"🔢 Starting vectorization status test (checking {fact_count} facts)..."
        )

        # First, get list of fact IDs from knowledge base
        async with aiohttp.ClientSession() as session:
            # Get all entries
            url = f"{self.backend_url}/api/knowledge_base/entries"
            try:
                async with session.get(
                    url,
                    params={"limit": fact_count},
                    timeout=aiohttp.ClientTimeout(total=10.0),
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get entries: {response.status}")
                        return self.calculate_metrics(
                            test_name="vectorization_status_load",
                            latencies=[],
                            success_count=0,
                            fail_count=1,
                            duration=0.0,
                            target_ms=self.STATUS_LOAD_TARGET_MS,
                            metadata={"error": "Could not fetch fact entries"},
                        )

                    entries_data = await response.json()
                    entries = entries_data.get("entries", [])

                    if not entries:
                        logger.error("No facts found in knowledge base")
                        return self.calculate_metrics(
                            test_name="vectorization_status_load",
                            latencies=[],
                            success_count=0,
                            fail_count=1,
                            duration=0.0,
                            target_ms=self.STATUS_LOAD_TARGET_MS,
                            metadata={"error": "No facts found"},
                        )

                    # Extract fact IDs
                    fact_ids = []
                    for entry in entries[:fact_count]:
                        # Try to get ID from various possible fields
                        fact_id = (
                            entry.get("id") or entry.get("key") or entry.get("fact_id")
                        )
                        if fact_id:
                            # Clean up fact ID if it has "fact:" prefix
                            if isinstance(fact_id, str) and fact_id.startswith("fact:"):
                                fact_id = fact_id[5:]  # Remove "fact:" prefix
                            fact_ids.append(str(fact_id))

                    logger.info(f"Testing with {len(fact_ids)} fact IDs...")

            except Exception as e:
                logger.error(f"Error fetching entries: {e}")
                return self.calculate_metrics(
                    test_name="vectorization_status_load",
                    latencies=[],
                    success_count=0,
                    fail_count=1,
                    duration=0.0,
                    target_ms=self.STATUS_LOAD_TARGET_MS,
                    metadata={"error": str(e)},
                )

        if not fact_ids:
            logger.error("No valid fact IDs extracted")
            return self.calculate_metrics(
                test_name="vectorization_status_load",
                latencies=[],
                success_count=0,
                fail_count=1,
                duration=0.0,
                target_ms=self.STATUS_LOAD_TARGET_MS,
                metadata={"error": "No valid fact IDs"},
            )

        # Now test vectorization status check
        latencies = []
        success_count = 0
        fail_count = 0

        async def check_vectorization_status(
            session, batch_ids: List[str], batch_num: int
        ):
            """Check vectorization status for a batch of facts"""
            try:
                url = f"{self.backend_url}/api/knowledge_base/bulk/vectorization_status"
                payload = {"fact_ids": batch_ids, "include_dimensions": True}

                start = time.perf_counter()
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=10.0)
                ) as response:
                    _data = await response.json()
                    end = time.perf_counter()

                    latency = (end - start) * 1000  # ms
                    latencies.append(latency)

                    if response.status == 200:
                        return "success"
                    else:
                        logger.debug(
                            f"Status check failed (batch {batch_num}): {response.status}"
                        )
                        return "failed"

            except Exception as e:
                logger.debug(
                    f"Vectorization status request failed (batch {batch_num}): {e}"
                )
                return "failed"

        start_time = time.perf_counter()

        # Test with multiple batch sizes
        batch_sizes = [100, 250, 500, 1000]

        async with aiohttp.ClientSession() as session:
            tasks = []

            for i, batch_size in enumerate(batch_sizes):
                # Get up to batch_size IDs
                batch_ids = fact_ids[: min(batch_size, len(fact_ids))]
                if batch_ids:
                    tasks.append(check_vectorization_status(session, batch_ids, i))

            results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.perf_counter()
        duration = end_time - start_time

        # Count successes and failures
        success_count = sum(1 for r in results if r == "success")
        fail_count = sum(
            1 for r in results if r == "failed" or isinstance(r, Exception)
        )

        metrics = self.calculate_metrics(
            test_name="vectorization_status_load",
            latencies=latencies,
            success_count=success_count,
            fail_count=fail_count,
            duration=duration,
            target_ms=self.STATUS_LOAD_TARGET_MS,
            metadata={
                "fact_count": len(fact_ids),
                "batch_sizes_tested": batch_sizes,
                "batches_tested": len(batch_sizes),
            },
        )

        self.results.append(metrics)

        status_icon = "✅" if metrics.passed else "❌"
        logger.info(
            f"{status_icon} Vectorization status test complete: {success_count}/{len(tasks)} successful, "
            f"p95={metrics.p95_latency_ms:.0f}ms (target: {self.STATUS_LOAD_TARGET_MS}ms)"
        )

        return metrics

    async def test_rapid_sequential_filtering(
        self, operations: int = 100
    ) -> PerformanceMetrics:
        """
        Test Scenario 3: Rapid Sequential Filtering
        Target: No UI blocking, < 200ms per operation

        Tests rapid filter changes like user quickly switching categories
        """
        logger.info(
            f"⚡ Starting rapid sequential filtering test ({operations} operations)..."
        )

        stats = await self.get_knowledge_stats()
        categories = stats.get("categories", [])

        if not categories:
            logger.error("No categories found")
            return self.calculate_metrics(
                test_name="rapid_sequential_filtering",
                latencies=[],
                success_count=0,
                fail_count=operations,
                duration=0.0,
                target_ms=self.RAPID_FILTER_TARGET_MS,
                metadata={"error": "No categories"},
            )

        latencies = []
        success_count = 0
        fail_count = 0

        async with aiohttp.ClientSession() as session:
            start_time = time.perf_counter()

            # Simulate rapid sequential filtering (not concurrent - sequential like user clicking)
            for i in range(operations):
                category = categories[i % len(categories)]

                try:
                    url = f"{self.backend_url}/api/knowledge_base/facts/by_category"
                    params = {"category": category, "limit": 50}

                    req_start = time.perf_counter()
                    async with session.get(
                        url, params=params, timeout=aiohttp.ClientTimeout(total=2.0)
                    ) as response:
                        await response.json()
                        req_end = time.perf_counter()

                        latency = (req_end - req_start) * 1000
                        latencies.append(latency)

                        if response.status == 200:
                            success_count += 1
                        else:
                            fail_count += 1

                except Exception as e:
                    logger.debug(f"Rapid filter failed (op {i}): {e}")
                    fail_count += 1

                # Small delay to simulate user think time (100ms between clicks)
                await asyncio.sleep(0.1)

            end_time = time.perf_counter()
            duration = end_time - start_time

        metrics = self.calculate_metrics(
            test_name="rapid_sequential_filtering",
            latencies=latencies,
            success_count=success_count,
            fail_count=fail_count,
            duration=duration,
            target_ms=self.RAPID_FILTER_TARGET_MS,
            metadata={
                "operations": operations,
                "categories_count": len(categories),
                "user_think_time_ms": 100,
            },
        )

        self.results.append(metrics)

        status_icon = "✅" if metrics.passed else "❌"
        logger.info(
            f"{status_icon} Rapid filtering test complete: {success_count}/{operations} successful, "
            f"p95={metrics.p95_latency_ms:.0f}ms (target: {self.RAPID_FILTER_TARGET_MS}ms)"
        )

        return metrics

    async def test_concurrent_mixed_operations(
        self, concurrent: int = 20
    ) -> PerformanceMetrics:
        """
        Test Scenario 4: Concurrent Mixed Operations
        Simulates multiple users accessing different features simultaneously
        """
        logger.info(
            f"🔄 Starting concurrent mixed operations test ({concurrent} concurrent ops)..."
        )

        stats = await self.get_knowledge_stats()
        categories = stats.get("categories", [])

        latencies = []
        success_count = 0
        fail_count = 0

        async def mixed_operation(session, op_id: int):
            """Execute random operation"""
            try:
                # Randomly choose operation type
                op_type = op_id % 3

                if op_type == 0:
                    # Category filter
                    url = f"{self.backend_url}/api/knowledge_base/facts/by_category"
                    params = {
                        "category": categories[op_id % len(categories)]
                        if categories
                        else None,
                        "limit": 50,
                    }
                    start = time.perf_counter()
                    async with session.get(
                        url, params=params, timeout=aiohttp.ClientTimeout(total=5.0)
                    ) as response:
                        await response.json()
                        end = time.perf_counter()

                elif op_type == 1:
                    # Get stats
                    url = f"{self.backend_url}/api/knowledge_base/stats"
                    start = time.perf_counter()
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=5.0)
                    ) as response:
                        await response.json()
                        end = time.perf_counter()

                else:
                    # Get entries
                    url = f"{self.backend_url}/api/knowledge_base/entries"
                    params = {"limit": 20}
                    start = time.perf_counter()
                    async with session.get(
                        url, params=params, timeout=aiohttp.ClientTimeout(total=5.0)
                    ) as response:
                        await response.json()
                        end = time.perf_counter()

                latency = (end - start) * 1000
                latencies.append(latency)

                if response.status == 200:
                    return "success"
                else:
                    return "failed"

            except Exception as e:
                logger.debug(f"Mixed operation failed (op {op_id}): {e}")
                return "failed"

        start_time = time.perf_counter()

        async with aiohttp.ClientSession() as session:
            tasks = [mixed_operation(session, i) for i in range(concurrent)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.perf_counter()
        duration = end_time - start_time

        success_count = sum(1 for r in results if r == "success")
        fail_count = sum(
            1 for r in results if r == "failed" or isinstance(r, Exception)
        )

        metrics = self.calculate_metrics(
            test_name="concurrent_mixed_operations",
            latencies=latencies,
            success_count=success_count,
            fail_count=fail_count,
            duration=duration,
            target_ms=500,  # General responsiveness target
            metadata={
                "concurrent_operations": concurrent,
                "operation_types": ["category_filter", "stats", "entries"],
            },
        )

        self.results.append(metrics)

        status_icon = "✅" if metrics.passed else "❌"
        logger.info(
            f"{status_icon} Concurrent mixed operations test complete: {success_count}/{concurrent} successful, "
            f"p95={metrics.p95_latency_ms:.0f}ms"
        )

        return metrics

    async def run_comprehensive_test_suite(self) -> Dict[str, Any]:
        """Run all performance tests"""
        logger.info("=" * 80)
        logger.info("🚀 Knowledge Manager Performance Testing")
        logger.info("GitHub Issue #163 - Task 4.3")
        logger.info("=" * 80)

        # Check test data availability
        has_data = await self.populate_test_data_if_needed(target_facts=1000)
        if not has_data:
            logger.error(
                "❌ Insufficient test data - cannot proceed with performance testing"
            )
            return {
                "error": "Insufficient test data",
                "message": "Please populate knowledge base before running performance tests",
            }

        start_time = time.perf_counter()

        # Run all test scenarios
        logger.info("\n" + "=" * 80)
        await self.test_category_filter_performance(iterations=50)
        await asyncio.sleep(1)

        logger.info("\n" + "=" * 80)
        await self.test_vectorization_status_load(fact_count=1000)
        await asyncio.sleep(1)

        logger.info("\n" + "=" * 80)
        await self.test_rapid_sequential_filtering(operations=100)
        await asyncio.sleep(1)

        logger.info("\n" + "=" * 80)
        await self.test_concurrent_mixed_operations(concurrent=20)

        total_duration = time.perf_counter() - start_time

        # Generate summary report
        summary = self.generate_performance_report(total_duration)

        logger.info("\n" + "=" * 80)
        logger.info("✅ Performance Testing Complete")
        logger.info("=" * 80)

        return summary

    def generate_performance_report(self, total_duration: float) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "test_suite": "Knowledge Manager Performance Testing",
            "github_issue": "#163",
            "task": "4.3 - Performance Testing with Large Datasets",
            "total_duration_seconds": total_duration,
            "total_tests": len(self.results),
            "test_results": [asdict(r) for r in self.results],
            "summary": {},
            "performance_analysis": {},
            "pass_fail_summary": {},
        }

        # Calculate summary statistics
        total_requests = sum(r.total_requests for r in self.results)
        total_successful = sum(r.successful_requests for r in self.results)
        tests_passed = sum(1 for r in self.results if r.passed)
        tests_failed = sum(1 for r in self.results if not r.passed)

        report["summary"] = {
            "total_requests": total_requests,
            "total_successful": total_successful,
            "overall_success_rate": (total_successful / total_requests * 100)
            if total_requests > 0
            else 0,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "pass_rate": (tests_passed / len(self.results) * 100)
            if self.results
            else 0,
        }

        # Performance analysis for each test
        for result in self.results:
            report["performance_analysis"][result.test_name] = {
                "p95_latency_ms": result.p95_latency_ms,
                "target_ms": result.target_ms,
                "passed": result.passed,
                "margin_ms": result.target_ms - result.p95_latency_ms,
                "margin_percentage": (
                    (result.target_ms - result.p95_latency_ms) / result.target_ms * 100
                )
                if result.target_ms > 0
                else 0,
                "success_rate": (
                    result.successful_requests / result.total_requests * 100
                )
                if result.total_requests > 0
                else 0,
            }

        # Pass/Fail summary
        report["pass_fail_summary"] = {
            "category_filter": next(
                (r.passed for r in self.results if "category_filter" in r.test_name),
                None,
            ),
            "vectorization_status": next(
                (
                    r.passed
                    for r in self.results
                    if "vectorization_status" in r.test_name
                ),
                None,
            ),
            "rapid_filtering": next(
                (r.passed for r in self.results if "rapid_sequential" in r.test_name),
                None,
            ),
            "concurrent_mixed": next(
                (r.passed for r in self.results if "concurrent_mixed" in r.test_name),
                None,
            ),
            "overall_passed": tests_failed == 0,
        }

        # Save report to proper directory (NOT root!)
        output_dir = Path("/home/kali/Desktop/AutoBot/reports/performance")
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_dir / f"knowledge_performance_{timestamp_str}.json"

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"📊 Performance report saved: {report_file}")

        # Print detailed summary
        self.print_summary_report(report, report_file)

        return report

    def print_summary_report(self, report: Dict[str, Any], report_file: Path):
        """Print human-readable summary"""
        print("\n" + "=" * 80)
        print("📊 KNOWLEDGE MANAGER PERFORMANCE SUMMARY")
        print("=" * 80)
        print("GitHub Issue: #163 - Task 4.3")
        print(f"Total Tests: {report['total_tests']}")
        print(f"Total Requests: {report['summary']['total_requests']}")
        print(f"Success Rate: {report['summary']['overall_success_rate']:.1f}%")
        print(
            f"Tests Passed: {report['summary']['tests_passed']}/{report['total_tests']}"
        )
        print()

        # Category Filter Performance
        cat_result = next(
            (r for r in self.results if "category_filter" in r.test_name), None
        )
        if cat_result:
            status = "✅ PASS" if cat_result.passed else "❌ FAIL"
            print(f"1. Category Filter Performance: {status}")
            print(f"   Target: <{self.CATEGORY_FILTER_TARGET_MS}ms (p95)")
            print(f"   Actual: {cat_result.p95_latency_ms:.0f}ms (p95)")
            print(
                f"   Margin: {self.CATEGORY_FILTER_TARGET_MS - cat_result.p95_latency_ms:+.0f}ms"
            )
            if cat_result.cache_hit_ratio:
                print(f"   Cache Hit Ratio: {cat_result.cache_hit_ratio:.1%}")
            print()

        # Vectorization Status Load
        vec_result = next(
            (r for r in self.results if "vectorization_status" in r.test_name), None
        )
        if vec_result:
            status = "✅ PASS" if vec_result.passed else "❌ FAIL"
            print(f"2. Vectorization Status Load: {status}")
            print(f"   Target: <{self.STATUS_LOAD_TARGET_MS}ms (p95) for 1000 facts")
            print(f"   Actual: {vec_result.p95_latency_ms:.0f}ms (p95)")
            print(
                f"   Margin: {self.STATUS_LOAD_TARGET_MS - vec_result.p95_latency_ms:+.0f}ms"
            )
            print()

        # Rapid Sequential Filtering
        rapid_result = next(
            (r for r in self.results if "rapid_sequential" in r.test_name), None
        )
        if rapid_result:
            status = "✅ PASS" if rapid_result.passed else "❌ FAIL"
            print(f"3. Rapid Sequential Filtering: {status}")
            print(f"   Target: <{self.RAPID_FILTER_TARGET_MS}ms (p95)")
            print(f"   Actual: {rapid_result.p95_latency_ms:.0f}ms (p95)")
            print(
                f"   Margin: {self.RAPID_FILTER_TARGET_MS - rapid_result.p95_latency_ms:+.0f}ms"
            )
            print()

        # Concurrent Mixed Operations
        mixed_result = next(
            (r for r in self.results if "concurrent_mixed" in r.test_name), None
        )
        if mixed_result:
            status = "✅ PASS" if mixed_result.passed else "❌ FAIL"
            print(f"4. Concurrent Mixed Operations: {status}")
            print("   Target: <500ms (p95)")
            print(f"   Actual: {mixed_result.p95_latency_ms:.0f}ms (p95)")
            print(f"   Throughput: {mixed_result.requests_per_second:.1f} req/sec")
            print()

        # Overall verdict
        print("=" * 80)
        if report["pass_fail_summary"]["overall_passed"]:
            print("🎉 OVERALL RESULT: ALL PERFORMANCE TARGETS MET ✅")
        else:
            print("⚠️  OVERALL RESULT: SOME PERFORMANCE TARGETS NOT MET ❌")
            print("\nFailed Tests:")
            for result in self.results:
                if not result.passed:
                    print(
                        f"  - {result.test_name}: {result.p95_latency_ms:.0f}ms vs {result.target_ms}ms target"
                    )

        print("=" * 80)
        print(f"📄 Full report: {report_file}")
        print("=" * 80)


async def main():
    """Main execution function"""
    tester = KnowledgePerformanceTest()

    try:
        await tester.run_comprehensive_test_suite()
        return 0
    except KeyboardInterrupt:
        logger.warning("🛑 Testing interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"❌ Testing failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
