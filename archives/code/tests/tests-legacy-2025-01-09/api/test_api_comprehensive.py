#!/usr/bin/env python3
"""
Comprehensive AutoBot API Testing Suite
Organized under tests/ directory as per testing standards

This test suite provides:
1. API endpoint health checking
2. Performance benchmarking
3. Error analysis and reporting
4. Backend deadlock detection
"""

import os
import sys
import time
import json
import asyncio
import aiohttp
import concurrent.futures
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class APITestResult:
    """Result of an individual API test"""
    endpoint: str
    method: str
    status_code: int
    response_time: float
    success: bool
    response_size: int = 0
    error_message: str = ""
    response_data: Any = None

@dataclass
class CategoryResults:
    """Results for a category of endpoints"""
    category: str
    total_tests: int
    successful_tests: int
    failed_tests: int
    average_response_time: float
    success_rate: float
    results: List[APITestResult]

class AutoBotAPITester:
    """Comprehensive API testing framework for AutoBot"""

    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.results: List[APITestResult] = []
        self.timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout

        # Test categories mapped from router registry
        self.test_categories = {
            "Core System": [
                ("/api/health", "GET"),
                ("/api/system/status", "GET"),
                ("/api/system/info", "GET"),
                ("/api/system/resources", "GET"),
            ],

            "Chat & Communication": [
                ("/api/chat/health", "GET"),
                ("/api/chat/chats", "GET"),
                ("/api/chat/chats/new", "POST"),
            ],

            "Configuration & Settings": [
                ("/api/settings/", "GET"),
                ("/api/settings/llm", "GET"),
                ("/api/agent-config/", "GET"),
                ("/api/agent-config/agents", "GET"),
            ],

            "Knowledge Base Operations": [
                ("/api/knowledge_base/stats", "GET"),
                ("/api/knowledge_base/detailed_stats", "GET"),
                ("/api/knowledge_base/search", "POST", {"query": "test search", "top_k": 5}),
                ("/api/knowledge", "GET"),
            ],

            "File Operations": [
                ("/api/files/stats", "GET"),
                ("/api/files/recent", "GET"),
                ("/api/files/search", "GET"),
            ],

            "LLM & AI Services": [
                ("/api/llm/status", "GET"),
                ("/api/llm/models", "GET"),
                ("/api/llm/health", "GET"),
                ("/api/prompts/", "GET"),
                ("/api/prompts/categories", "GET"),
            ],

            "Monitoring & Analytics": [
                ("/api/cache/stats", "GET"),
                ("/api/rum/dashboard", "GET"),
                ("/api/monitoring/services", "GET"),
                ("/api/infrastructure/health", "GET"),
                ("/api/validation-dashboard/status", "GET"),
            ],

            "Development Tools": [
                ("/api/developer/", "GET"),
                ("/api/templates/", "GET"),
                ("/api/secrets/status", "GET"),
                ("/api/logs/recent", "GET"),
            ],

            "Automation & Control": [
                ("/api/playwright/health", "GET"),
                ("/api/terminal/sessions", "GET"),
                ("/api/batch/status", "GET"),
                ("/api/research/health", "GET"),
            ]
        }

    async def test_single_endpoint(self, session: aiohttp.ClientSession,
                                 endpoint: str, method: str = "GET",
                                 data: Optional[Dict] = None) -> APITestResult:
        """Test a single API endpoint with timeout protection"""
        full_url = f"{self.base_url}{endpoint}"
        start_time = time.time()

        try:
            if method.upper() == "GET":
                async with session.get(full_url) as response:
                    response_text = await response.text()
                    response_size = len(response_text)
                    response_time = time.time() - start_time

                    try:
                        response_data = await response.json() if response_text else None
                    except:
                        response_data = response_text[:200] if response_text else None

                    return APITestResult(
                        endpoint=endpoint,
                        method=method,
                        status_code=response.status,
                        response_time=response_time,
                        success=200 <= response.status < 400,
                        response_size=response_size,
                        response_data=response_data
                    )

            elif method.upper() == "POST":
                async with session.post(full_url, json=data) as response:
                    response_text = await response.text()
                    response_size = len(response_text)
                    response_time = time.time() - start_time

                    try:
                        response_data = await response.json() if response_text else None
                    except:
                        response_data = response_text[:200] if response_text else None

                    return APITestResult(
                        endpoint=endpoint,
                        method=method,
                        status_code=response.status,
                        response_time=response_time,
                        success=200 <= response.status < 400,
                        response_size=response_size,
                        response_data=response_data
                    )

        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            return APITestResult(
                endpoint=endpoint,
                method=method,
                status_code=0,
                response_time=response_time,
                success=False,
                error_message="Timeout - Backend may be deadlocked"
            )

        except Exception as e:
            response_time = time.time() - start_time
            return APITestResult(
                endpoint=endpoint,
                method=method,
                status_code=0,
                response_time=response_time,
                success=False,
                error_message=str(e)[:100]
            )

    async def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run comprehensive API tests with detailed reporting"""
        print("🚀 AutoBot Comprehensive API Testing Suite")
        print("=" * 80)

        category_results = {}
        all_results = []
        total_success = 0
        total_tests = 0

        async with aiohttp.ClientSession(timeout=self.timeout) as session:

            for category, endpoints in self.test_categories.items():
                print(f"\n📂 Testing Category: {category}")
                print("-" * 60)

                category_test_results = []
                category_success = 0
                category_total = len(endpoints)

                # Test endpoints in this category
                for endpoint_data in endpoints:
                    endpoint = endpoint_data[0]
                    method = endpoint_data[1]
                    data = endpoint_data[2] if len(endpoint_data) > 2 else None

                    print(f"  Testing: {method:4} {endpoint}")

                    result = await self.test_single_endpoint(session, endpoint, method, data)
                    category_test_results.append(result)
                    all_results.append(result)

                    if result.success:
                        category_success += 1
                        total_success += 1
                        print(f"    ✅ {result.status_code} ({result.response_time:.3f}s)")
                    else:
                        print(f"    ❌ {result.status_code} ({result.response_time:.3f}s)")
                        if result.error_message:
                            print(f"       Error: {result.error_message}")

                # Calculate category statistics
                avg_response_time = sum(r.response_time for r in category_test_results) / len(category_test_results)
                success_rate = (category_success / category_total * 100) if category_total > 0 else 0

                category_results[category] = CategoryResults(
                    category=category,
                    total_tests=category_total,
                    successful_tests=category_success,
                    failed_tests=category_total - category_success,
                    average_response_time=avg_response_time,
                    success_rate=success_rate,
                    results=category_test_results
                )

                print(f"  📊 Category Results: {success_rate:.1f}% success ({category_success}/{category_total})")
                print(f"  ⏱️  Average Response Time: {avg_response_time:.3f}s")

                total_tests += category_total

        # Calculate overall statistics
        overall_success_rate = (total_success / total_tests * 100) if total_tests > 0 else 0
        overall_avg_response_time = sum(r.response_time for r in all_results) / len(all_results)

        # Generate comprehensive report
        self._generate_comprehensive_report(category_results, overall_success_rate,
                                          total_success, total_tests, overall_avg_response_time)

        return {
            "overall_success_rate": overall_success_rate,
            "total_tests": total_tests,
            "successful_tests": total_success,
            "failed_tests": total_tests - total_success,
            "average_response_time": overall_avg_response_time,
            "category_results": {k: asdict(v) for k, v in category_results.items()},
            "detailed_results": [asdict(r) for r in all_results]
        }

    def _generate_comprehensive_report(self, category_results: Dict[str, CategoryResults],
                                     overall_success_rate: float, total_success: int,
                                     total_tests: int, avg_response_time: float):
        """Generate detailed test report with analysis"""

        print("\n" + "=" * 80)
        print("📋 COMPREHENSIVE API TESTING REPORT")
        print("=" * 80)

        # Overall metrics
        print(f"\n🎯 OVERALL RESULTS:")
        print(f"   Success Rate: {overall_success_rate:.1f}% ({total_success}/{total_tests})")
        print(f"   Average Response Time: {avg_response_time:.3f}s")

        if overall_success_rate == 100:
            print("   🎉 TARGET ACHIEVED: 100% endpoint success rate!")
        else:
            print(f"   🔧 {total_tests - total_success} endpoints need fixes")

        # Category breakdown
        print(f"\n📊 CATEGORY BREAKDOWN:")
        for category, results in category_results.items():
            status_icon = "✅" if results.success_rate == 100 else "⚠️" if results.success_rate >= 80 else "❌"
            print(f"   {status_icon} {category:<25} {results.success_rate:>6.1f}% ({results.successful_tests}/{results.total_tests}) [{results.average_response_time:.3f}s avg]")

        # Failure analysis
        failed_results = []
        for results in category_results.values():
            failed_results.extend([r for r in results.results if not r.success])

        if failed_results:
            print(f"\n🔍 FAILURE ANALYSIS ({len(failed_results)} failures):")
            print("-" * 60)

            # Group by error type
            timeout_failures = [r for r in failed_results if "timeout" in r.error_message.lower()]
            connection_failures = [r for r in failed_results if "connection" in r.error_message.lower()]
            http_errors = [r for r in failed_results if r.status_code >= 400]
            other_failures = [r for r in failed_results if r not in timeout_failures + connection_failures + http_errors]

            if timeout_failures:
                print(f"   ⏰ Timeout Failures ({len(timeout_failures)}):")
                for failure in timeout_failures:
                    print(f"      {failure.method} {failure.endpoint}")
                print("      → Indicates backend deadlock or blocking operations")

            if connection_failures:
                print(f"   🔌 Connection Failures ({len(connection_failures)}):")
                for failure in connection_failures:
                    print(f"      {failure.method} {failure.endpoint}")
                print("      → Backend service may not be running")

            if http_errors:
                print(f"   🚫 HTTP Errors ({len(http_errors)}):")
                for failure in http_errors:
                    print(f"      {failure.method} {failure.endpoint} - {failure.status_code}")
                print("      → API endpoints may need implementation or fixes")

            if other_failures:
                print(f"   ❓ Other Failures ({len(other_failures)}):")
                for failure in other_failures:
                    print(f"      {failure.method} {failure.endpoint} - {failure.error_message}")

        # Performance analysis
        print(f"\n⚡ PERFORMANCE ANALYSIS:")
        fast_endpoints = sum(1 for results in category_results.values()
                           for r in results.results if r.success and r.response_time < 1.0)
        slow_endpoints = sum(1 for results in category_results.values()
                           for r in results.results if r.success and r.response_time > 5.0)

        print(f"   🚀 Fast endpoints (<1s): {fast_endpoints}")
        print(f"   🐌 Slow endpoints (>5s): {slow_endpoints}")

        if slow_endpoints > 0:
            print("   → Consider optimizing slow endpoints for better performance")

    def save_test_results(self, results: Dict[str, Any]) -> str:
        """Save detailed test results to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = "/home/kali/Desktop/AutoBot/tests/results"
        os.makedirs(results_dir, exist_ok=True)

        results_file = f"{results_dir}/api_comprehensive_test_{timestamp}.json"

        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        return results_file

async def main():
    """Main test execution"""
    tester = AutoBotAPITester()

    try:
        # Run comprehensive tests
        results = await tester.run_comprehensive_tests()

        # Save results
        results_file = tester.save_test_results(results)

        print(f"\n💾 Detailed results saved to: {results_file}")

        # Return appropriate exit code
        success_rate = results["overall_success_rate"]
        if success_rate == 100:
            print(f"\n🎉 SUCCESS: Achieved 100% API endpoint success rate!")
            return 0
        else:
            print(f"\n🔧 WORK NEEDED: {results['failed_tests']} endpoints require fixes to reach 100%")
            return 1

    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        print(f"\n❌ Test execution failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
