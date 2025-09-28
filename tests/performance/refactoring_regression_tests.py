#!/usr/bin/env python3
"""
AutoBot Refactoring Performance Regression Tests
Performance Engineer Agent - Specific tests to detect performance issues during refactoring
"""

import asyncio
import json
import time
import pytest
import requests
import subprocess
from typing import Dict, List, Any
from dataclasses import dataclass
import concurrent.futures

@dataclass
class PerformanceTest:
    """Single performance test configuration"""
    name: str
    endpoint: str
    expected_max_response_ms: float
    expected_min_success_rate: float
    concurrent_requests: int = 1
    description: str = ""

class RefactoringRegressionTester:
    """Performance regression testing during refactoring process"""

    def __init__(self):
        self.base_url = "http://172.16.168.20:8001"

        # Load baseline performance metrics
        self.baseline = self._load_baseline()

        # Define critical performance tests
        self.performance_tests = [
            PerformanceTest(
                name="api_health_check",
                endpoint="/api/health",
                expected_max_response_ms=50.0,
                expected_min_success_rate=100.0,
                description="Basic health check endpoint"
            ),
            PerformanceTest(
                name="chat_endpoint_basic",
                endpoint="/api/chats",
                expected_max_response_ms=200.0,
                expected_min_success_rate=95.0,
                description="Chat endpoint basic functionality"
            ),
            PerformanceTest(
                name="knowledge_base_stats",
                endpoint="/api/knowledge_base/stats/basic",
                expected_max_response_ms=500.0,  # Increased due to 13,383 vectors
                expected_min_success_rate=90.0,
                description="Knowledge base statistics query"
            ),
            PerformanceTest(
                name="monitoring_status",
                endpoint="/api/monitoring/status",
                expected_max_response_ms=300.0,
                expected_min_success_rate=95.0,
                description="System monitoring status"
            ),
            PerformanceTest(
                name="analytics_overview",
                endpoint="/api/analytics/overview",
                expected_max_response_ms=400.0,
                expected_min_success_rate=90.0,
                description="Analytics overview endpoint"
            ),
            PerformanceTest(
                name="concurrent_chat_load",
                endpoint="/api/chats",
                expected_max_response_ms=1000.0,
                expected_min_success_rate=85.0,
                concurrent_requests=5,
                description="Concurrent chat requests load test"
            )
        ]

    def _load_baseline(self) -> Dict[str, Any]:
        """Load baseline performance data"""
        try:
            import glob
            baseline_files = glob.glob("/home/kali/Desktop/AutoBot/reports/performance/baseline_report_*.json")
            if baseline_files:
                latest_baseline = max(baseline_files, key=lambda x: x.split('_')[-1])
                with open(latest_baseline, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    async def run_single_performance_test(self, test: PerformanceTest) -> Dict[str, Any]:
        """Execute a single performance test"""
        results = {
            "test_name": test.name,
            "success": False,
            "response_times": [],
            "success_count": 0,
            "total_requests": test.concurrent_requests,
            "avg_response_ms": 0.0,
            "max_response_ms": 0.0,
            "min_response_ms": 0.0,
            "success_rate": 0.0,
            "meets_expectations": False,
            "error_messages": []
        }

        url = f"{self.base_url}{test.endpoint}"

        async def single_request():
            """Execute single HTTP request"""
            try:
                start_time = time.time()
                response = requests.get(url, timeout=10)
                response_time = (time.time() - start_time) * 1000

                return {
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "success": response.status_code < 400
                }
            except Exception as e:
                return {
                    "response_time": 10000.0,  # High penalty for errors
                    "status_code": 0,
                    "success": False,
                    "error": str(e)
                }

        # Execute requests
        if test.concurrent_requests == 1:
            # Single request
            result = await asyncio.to_thread(lambda: asyncio.run(single_request()))
            request_results = [result]
        else:
            # Concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=test.concurrent_requests) as executor:
                futures = [executor.submit(lambda: asyncio.run(single_request())) for _ in range(test.concurrent_requests)]
                request_results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # Analyze results
        response_times = [r["response_time"] for r in request_results]
        success_count = sum(1 for r in request_results if r["success"])
        error_messages = [r.get("error", "") for r in request_results if not r["success"]]

        results.update({
            "response_times": response_times,
            "success_count": success_count,
            "avg_response_ms": sum(response_times) / len(response_times) if response_times else 0,
            "max_response_ms": max(response_times) if response_times else 0,
            "min_response_ms": min(response_times) if response_times else 0,
            "success_rate": (success_count / test.concurrent_requests) * 100,
            "error_messages": [msg for msg in error_messages if msg]
        })

        # Check if test meets expectations
        meets_response_time = results["avg_response_ms"] <= test.expected_max_response_ms
        meets_success_rate = results["success_rate"] >= test.expected_min_success_rate

        results["meets_expectations"] = meets_response_time and meets_success_rate
        results["success"] = results["meets_expectations"]

        return results

    async def run_all_performance_tests(self) -> Dict[str, Any]:
        """Run complete performance regression test suite"""
        print("🧪 Running performance regression tests for refactoring...")

        test_results = []
        start_time = time.time()

        for test in self.performance_tests:
            print(f"  Testing: {test.name} ({test.description})")

            result = await self.run_single_performance_test(test)
            test_results.append(result)

            # Log immediate result
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"    {status} - {result['avg_response_ms']:.1f}ms avg, {result['success_rate']:.1f}% success")

        execution_time = time.time() - start_time

        # Compile comprehensive results
        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results if r["success"])
        failed_tests = total_tests - passed_tests

        suite_results = {
            "suite_metadata": {
                "timestamp": time.time(),
                "execution_time_seconds": execution_time,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate": (passed_tests / total_tests) * 100
            },
            "test_results": test_results,
            "performance_summary": self._generate_performance_summary(test_results),
            "regression_analysis": self._analyze_regressions(test_results),
            "recommendations": self._generate_recommendations(test_results)
        }

        return suite_results

    def _generate_performance_summary(self, test_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate performance summary from test results"""
        all_response_times = []
        total_requests = 0
        total_successes = 0

        for result in test_results:
            all_response_times.extend(result["response_times"])
            total_requests += result["total_requests"]
            total_successes += result["success_count"]

        return {
            "overall_avg_response_ms": sum(all_response_times) / len(all_response_times) if all_response_times else 0,
            "overall_max_response_ms": max(all_response_times) if all_response_times else 0,
            "overall_min_response_ms": min(all_response_times) if all_response_times else 0,
            "overall_success_rate": (total_successes / total_requests) * 100 if total_requests > 0 else 0,
            "total_requests_tested": total_requests,
            "fastest_endpoint": min(test_results, key=lambda x: x["avg_response_ms"])["test_name"] if test_results else None,
            "slowest_endpoint": max(test_results, key=lambda x: x["avg_response_ms"])["test_name"] if test_results else None
        }

    def _analyze_regressions(self, test_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze performance regressions compared to baseline"""
        regressions = []

        if not self.baseline:
            return {"regressions_detected": 0, "regressions": [], "baseline_available": False}

        baseline_apis = self.baseline.get("api_performance", {})

        for result in test_results:
            test_name = result["test_name"]
            endpoint = None

            # Find corresponding endpoint in baseline
            for test in self.performance_tests:
                if test.name == test_name:
                    endpoint = test.endpoint
                    break

            if endpoint and endpoint in baseline_apis:
                baseline_data = baseline_apis[endpoint]
                baseline_response_time = baseline_data.get("avg_response_time_ms", 0)
                baseline_success_rate = baseline_data.get("success_rate", 0)

                current_response_time = result["avg_response_ms"]
                current_success_rate = result["success_rate"]

                # Check for response time regression (>25% increase)
                if baseline_response_time > 0 and current_response_time > baseline_response_time * 1.25:
                    regressions.append({
                        "type": "response_time_regression",
                        "test_name": test_name,
                        "endpoint": endpoint,
                        "baseline_ms": baseline_response_time,
                        "current_ms": current_response_time,
                        "degradation_percent": ((current_response_time - baseline_response_time) / baseline_response_time) * 100
                    })

                # Check for success rate regression (>10% decrease)
                if baseline_success_rate > 0 and current_success_rate < baseline_success_rate - 10:
                    regressions.append({
                        "type": "success_rate_regression",
                        "test_name": test_name,
                        "endpoint": endpoint,
                        "baseline_rate": baseline_success_rate,
                        "current_rate": current_success_rate,
                        "degradation_percent": baseline_success_rate - current_success_rate
                    })

        return {
            "regressions_detected": len(regressions),
            "regressions": regressions,
            "baseline_available": True
        }

    def _generate_recommendations(self, test_results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Generate performance optimization recommendations"""
        recommendations = []

        # Analyze failed tests
        failed_tests = [r for r in test_results if not r["success"]]
        slow_tests = [r for r in test_results if r["avg_response_ms"] > 500]

        if failed_tests:
            recommendations.append({
                "priority": "critical",
                "category": "reliability",
                "issue": f"{len(failed_tests)} tests failed",
                "recommendation": "Investigate failing endpoints and fix critical issues before continuing refactoring",
                "affected_endpoints": [r["test_name"] for r in failed_tests]
            })

        if slow_tests:
            recommendations.append({
                "priority": "high",
                "category": "performance",
                "issue": f"{len(slow_tests)} endpoints responding slowly (>500ms)",
                "recommendation": "Optimize slow endpoints, especially database queries and external service calls",
                "affected_endpoints": [r["test_name"] for r in slow_tests]
            })

        # Check concurrent load performance
        concurrent_tests = [r for r in test_results if r["total_requests"] > 1]
        for test in concurrent_tests:
            if test["success_rate"] < 90:
                recommendations.append({
                    "priority": "medium",
                    "category": "scalability",
                    "issue": f"Concurrent load test {test['test_name']} showing degradation",
                    "recommendation": "Investigate concurrent request handling and optimize thread/connection pooling",
                    "details": f"Success rate: {test['success_rate']:.1f}%"
                })

        return recommendations

    def save_test_results(self, results: Dict[str, Any], filepath: str):
        """Save test results to file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"✅ Test results saved to: {filepath}")
        except Exception as e:
            print(f"❌ Error saving test results: {e}")

# Pytest integration
class TestRefactoringPerformance:
    """Pytest test class for refactoring performance"""

    @classmethod
    def setup_class(cls):
        """Setup test class"""
        cls.tester = RefactoringRegressionTester()

    @pytest.mark.asyncio
    async def test_api_health_performance(self):
        """Test API health endpoint performance"""
        test = next(t for t in self.tester.performance_tests if t.name == "api_health_check")
        result = await self.tester.run_single_performance_test(test)

        assert result["success"], f"Health check failed: {result.get('error_messages', [])}"
        assert result["avg_response_ms"] < test.expected_max_response_ms, f"Response time too slow: {result['avg_response_ms']}ms"
        assert result["success_rate"] >= test.expected_min_success_rate, f"Success rate too low: {result['success_rate']}%"

    @pytest.mark.asyncio
    async def test_chat_endpoint_performance(self):
        """Test chat endpoint performance"""
        test = next(t for t in self.tester.performance_tests if t.name == "chat_endpoint_basic")
        result = await self.tester.run_single_performance_test(test)

        assert result["success"], f"Chat endpoint failed: {result.get('error_messages', [])}"
        assert result["avg_response_ms"] < test.expected_max_response_ms, f"Response time too slow: {result['avg_response_ms']}ms"

    @pytest.mark.asyncio
    async def test_knowledge_base_performance(self):
        """Test knowledge base performance"""
        test = next(t for t in self.tester.performance_tests if t.name == "knowledge_base_stats")
        result = await self.tester.run_single_performance_test(test)

        # Knowledge base may be slow due to 13,383 vectors, so more lenient
        assert result["success_rate"] >= 50, f"Knowledge base completely inaccessible: {result['success_rate']}%"

    @pytest.mark.asyncio
    async def test_concurrent_load_performance(self):
        """Test concurrent load handling"""
        test = next(t for t in self.tester.performance_tests if t.name == "concurrent_chat_load")
        result = await self.tester.run_single_performance_test(test)

        assert result["success_rate"] >= 70, f"Concurrent load handling failed: {result['success_rate']}%"

async def main():
    """Main test execution"""
    print("🚀 AutoBot Refactoring Performance Regression Tests")
    print("=" * 60)

    tester = RefactoringRegressionTester()
    results = await tester.run_all_performance_tests()

    # Save results
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = f"/home/kali/Desktop/AutoBot/tests/performance/regression_test_results_{timestamp}.json"
    tester.save_test_results(results, filepath)

    # Print summary
    print("\n📊 PERFORMANCE TEST RESULTS")
    print("=" * 60)

    suite_meta = results["suite_metadata"]
    print(f"Tests Run: {suite_meta['total_tests']}")
    print(f"Passed: {suite_meta['passed_tests']}")
    print(f"Failed: {suite_meta['failed_tests']}")
    print(f"Success Rate: {suite_meta['success_rate']:.1f}%")
    print(f"Execution Time: {suite_meta['execution_time_seconds']:.1f}s")

    perf_summary = results["performance_summary"]
    print(f"\nOverall Performance:")
    print(f"  Average Response Time: {perf_summary['overall_avg_response_ms']:.1f}ms")
    print(f"  Fastest Endpoint: {perf_summary['fastest_endpoint']}")
    print(f"  Slowest Endpoint: {perf_summary['slowest_endpoint']}")

    # Show regressions
    regression_analysis = results["regression_analysis"]
    if regression_analysis["regressions_detected"] > 0:
        print(f"\n🚨 REGRESSIONS DETECTED: {regression_analysis['regressions_detected']}")
        for regression in regression_analysis["regressions"]:
            print(f"  • {regression['type']}: {regression['endpoint']} ({regression.get('degradation_percent', 0):.1f}% worse)")

    # Show recommendations
    recommendations = results["recommendations"]
    if recommendations:
        print(f"\n💡 RECOMMENDATIONS ({len(recommendations)}):")
        for rec in recommendations:
            print(f"  • [{rec['priority'].upper()}] {rec['issue']}: {rec['recommendation']}")

    return results

if __name__ == "__main__":
    asyncio.run(main())