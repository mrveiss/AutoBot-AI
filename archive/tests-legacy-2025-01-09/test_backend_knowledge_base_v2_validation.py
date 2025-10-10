#!/usr/bin/env python3
"""
Comprehensive Backend Testing for knowledge_base_v2.py Fixes

Tests the following critical fixes:
1. Async performance (event loop non-blocking)
2. Pipeline batching (N+1 query elimination)
3. Pagination support (limit/offset)
4. Collection filtering
5. Error handling edge cases
"""

import asyncio
import time
import httpx
import sys
from typing import Dict, List, Any

# Test configuration
BACKEND_BASE_URL = "http://172.16.168.20:8001"
TIMEOUT = 30.0

class BackendKnowledgeBaseValidator:
    """Validates backend knowledge_base_v2.py fixes"""

    def __init__(self):
        self.results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "test_details": []
        }

    async def test_async_performance(self) -> Dict[str, Any]:
        """Test 1.1: Verify async performance and event loop non-blocking"""
        test_name = "Async Performance - Event Loop Non-Blocking"
        print(f"\n{'='*60}")
        print(f"TEST 1.1: {test_name}")
        print(f"{'='*60}")

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Single request timing
                start_time = time.time()
                response = await client.get(f"{BACKEND_BASE_URL}/api/knowledge_base/categories/main")
                single_request_time = time.time() - start_time

                print(f"Single request time: {single_request_time:.3f}s")
                print(f"Status code: {response.status_code}")

                if response.status_code != 200:
                    return {
                        "test": test_name,
                        "status": "FAILED",
                        "error": f"HTTP {response.status_code}",
                        "response_time": single_request_time
                    }

                # Concurrent requests test
                print("\nTesting concurrent requests (5 simultaneous)...")
                start_time = time.time()

                tasks = [
                    client.get(f"{BACKEND_BASE_URL}/api/knowledge_base/categories/main")
                    for _ in range(5)
                ]

                responses = await asyncio.gather(*tasks, return_exceptions=True)
                concurrent_request_time = time.time() - start_time

                print(f"Concurrent requests time: {concurrent_request_time:.3f}s")

                # Check for errors
                errors = [r for r in responses if isinstance(r, Exception)]
                if errors:
                    return {
                        "test": test_name,
                        "status": "FAILED",
                        "error": f"{len(errors)} requests failed: {errors[0]}",
                        "response_time": concurrent_request_time
                    }

                # Validate performance
                if single_request_time > 0.5:
                    return {
                        "test": test_name,
                        "status": "WARNING",
                        "message": f"Single request took {single_request_time:.3f}s (expected < 0.5s)",
                        "response_time": single_request_time
                    }

                if concurrent_request_time > 2.0:
                    return {
                        "test": test_name,
                        "status": "WARNING",
                        "message": f"Concurrent requests took {concurrent_request_time:.3f}s (expected < 2.0s)",
                        "response_time": concurrent_request_time
                    }

                return {
                    "test": test_name,
                    "status": "PASSED",
                    "single_request_time": single_request_time,
                    "concurrent_request_time": concurrent_request_time,
                    "message": "Async performance meets expectations"
                }

        except Exception as e:
            return {
                "test": test_name,
                "status": "FAILED",
                "error": str(e)
            }

    async def test_pipeline_batching(self) -> Dict[str, Any]:
        """Test 1.2: Verify Redis pipeline batching performance"""
        test_name = "Pipeline Batching - N+1 Query Elimination"
        print(f"\n{'='*60}")
        print(f"TEST 1.2: {test_name}")
        print(f"{'='*60}")

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Test with different pagination limits
                test_limits = [10, 50, 100]
                results = []

                for limit in test_limits:
                    start_time = time.time()
                    response = await client.get(
                        f"{BACKEND_BASE_URL}/api/knowledge_base/facts",
                        params={"limit": limit}
                    )
                    response_time = time.time() - start_time

                    print(f"Limit {limit}: {response_time:.3f}s")

                    if response.status_code == 200:
                        data = response.json()
                        results.append({
                            "limit": limit,
                            "time": response_time,
                            "count": len(data) if isinstance(data, list) else 0
                        })

                if not results:
                    return {
                        "test": test_name,
                        "status": "FAILED",
                        "error": "No successful responses"
                    }

                # Check if response time scales linearly (not exponentially)
                time_ratios = []
                for i in range(1, len(results)):
                    prev = results[i-1]
                    curr = results[i]
                    expected_ratio = curr["limit"] / prev["limit"]
                    actual_ratio = curr["time"] / prev["time"] if prev["time"] > 0 else 0
                    time_ratios.append({
                        "from_limit": prev["limit"],
                        "to_limit": curr["limit"],
                        "expected_ratio": expected_ratio,
                        "actual_ratio": actual_ratio
                    })
                    print(f"  Scaling {prev['limit']}→{curr['limit']}: "
                          f"expected {expected_ratio:.1f}x, actual {actual_ratio:.1f}x")

                # Pipeline batching should prevent exponential scaling
                exponential_scaling = any(
                    r["actual_ratio"] > r["expected_ratio"] * 2
                    for r in time_ratios
                )

                if exponential_scaling:
                    return {
                        "test": test_name,
                        "status": "WARNING",
                        "message": "Response time may scale exponentially (pipeline batching issue?)",
                        "results": results
                    }

                return {
                    "test": test_name,
                    "status": "PASSED",
                    "message": "Pipeline batching performs as expected",
                    "results": results
                }

        except Exception as e:
            return {
                "test": test_name,
                "status": "FAILED",
                "error": str(e)
            }

    async def test_pagination(self) -> Dict[str, Any]:
        """Test 1.3: Verify pagination functionality"""
        test_name = "Pagination Support - Limit & Offset"
        print(f"\n{'='*60}")
        print(f"TEST 1.3: {test_name}")
        print(f"{'='*60}")

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Get first page
                page1 = await client.get(
                    f"{BACKEND_BASE_URL}/api/knowledge_base/facts",
                    params={"limit": 5, "offset": 0}
                )

                if page1.status_code != 200:
                    return {
                        "test": test_name,
                        "status": "FAILED",
                        "error": f"Page 1 failed: HTTP {page1.status_code}"
                    }

                page1_data = page1.json()
                print(f"Page 1: {len(page1_data)} facts")

                # Get second page
                page2 = await client.get(
                    f"{BACKEND_BASE_URL}/api/knowledge_base/facts",
                    params={"limit": 5, "offset": 5}
                )

                if page2.status_code != 200:
                    return {
                        "test": test_name,
                        "status": "FAILED",
                        "error": f"Page 2 failed: HTTP {page2.status_code}"
                    }

                page2_data = page2.json()
                print(f"Page 2: {len(page2_data)} facts")

                # Check for overlap
                if isinstance(page1_data, list) and isinstance(page2_data, list):
                    page1_ids = {
                        f.get("fact_id", f.get("id", str(i)))
                        for i, f in enumerate(page1_data)
                    }
                    page2_ids = {
                        f.get("fact_id", f.get("id", str(i)))
                        for i, f in enumerate(page2_data)
                    }

                    overlap = page1_ids.intersection(page2_ids)
                    print(f"Overlap: {len(overlap)} fact(s)")

                    if overlap:
                        return {
                            "test": test_name,
                            "status": "FAILED",
                            "error": f"Pages overlap with {len(overlap)} duplicate fact(s)",
                            "overlapping_ids": list(overlap)
                        }

                    return {
                        "test": test_name,
                        "status": "PASSED",
                        "message": "Pagination works correctly with no overlap",
                        "page1_count": len(page1_data),
                        "page2_count": len(page2_data)
                    }
                else:
                    return {
                        "test": test_name,
                        "status": "WARNING",
                        "message": "Response format unexpected (not a list)",
                        "page1_type": type(page1_data).__name__,
                        "page2_type": type(page2_data).__name__
                    }

        except Exception as e:
            return {
                "test": test_name,
                "status": "FAILED",
                "error": str(e)
            }

    async def test_collection_filtering(self) -> Dict[str, Any]:
        """Test 1.4: Verify collection filtering"""
        test_name = "Collection Filtering"
        print(f"\n{'='*60}")
        print(f"TEST 1.4: {test_name}")
        print(f"{'='*60}")

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Test collection=all
                all_response = await client.get(
                    f"{BACKEND_BASE_URL}/api/knowledge_base/facts",
                    params={"collection": "all", "limit": 10}
                )

                if all_response.status_code != 200:
                    return {
                        "test": test_name,
                        "status": "FAILED",
                        "error": f"collection=all failed: HTTP {all_response.status_code}"
                    }

                all_data = all_response.json()
                print(f"collection=all: {len(all_data)} facts")

                # Test specific collection (if exists)
                specific_response = await client.get(
                    f"{BACKEND_BASE_URL}/api/knowledge_base/facts",
                    params={"collection": "documentation", "limit": 10}
                )

                print(f"collection=documentation: HTTP {specific_response.status_code}")

                if specific_response.status_code == 200:
                    specific_data = specific_response.json()
                    print(f"  Found {len(specific_data)} facts")

                return {
                    "test": test_name,
                    "status": "PASSED",
                    "message": "Collection filtering endpoint accessible",
                    "all_collection_count": len(all_data) if isinstance(all_data, list) else 0
                }

        except Exception as e:
            return {
                "test": test_name,
                "status": "FAILED",
                "error": str(e)
            }

    async def test_error_handling(self) -> Dict[str, Any]:
        """Test 1.5: Verify error handling"""
        test_name = "Error Handling - Edge Cases"
        print(f"\n{'='*60}")
        print(f"TEST 1.5: {test_name}")
        print(f"{'='*60}")

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Test invalid limit
                invalid_limit = await client.get(
                    f"{BACKEND_BASE_URL}/api/knowledge_base/facts",
                    params={"limit": -1}
                )
                print(f"Invalid limit (-1): HTTP {invalid_limit.status_code}")

                # Test very large offset
                large_offset = await client.get(
                    f"{BACKEND_BASE_URL}/api/knowledge_base/facts",
                    params={"offset": 999999}
                )
                print(f"Large offset (999999): HTTP {large_offset.status_code}")

                # Both should handle gracefully (not 500)
                if invalid_limit.status_code == 500 or large_offset.status_code == 500:
                    return {
                        "test": test_name,
                        "status": "FAILED",
                        "error": "Server returned 500 for edge case (poor error handling)"
                    }

                return {
                    "test": test_name,
                    "status": "PASSED",
                    "message": "Error handling works gracefully for edge cases",
                    "invalid_limit_status": invalid_limit.status_code,
                    "large_offset_status": large_offset.status_code
                }

        except Exception as e:
            return {
                "test": test_name,
                "status": "FAILED",
                "error": str(e)
            }

    async def run_all_tests(self):
        """Execute all backend validation tests"""
        print("\n" + "="*80)
        print("BACKEND KNOWLEDGE BASE V2 VALIDATION TEST SUITE")
        print("="*80)

        tests = [
            self.test_async_performance(),
            self.test_pipeline_batching(),
            self.test_pagination(),
            self.test_collection_filtering(),
            self.test_error_handling()
        ]

        results = await asyncio.gather(*tests, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                self.results["test_details"].append({
                    "test": "Unknown",
                    "status": "FAILED",
                    "error": str(result)
                })
                self.results["failed"] += 1
            else:
                self.results["test_details"].append(result)

                if result["status"] == "PASSED":
                    self.results["passed"] += 1
                elif result["status"] == "FAILED":
                    self.results["failed"] += 1
                elif result["status"] == "WARNING":
                    self.results["warnings"] += 1

            self.results["total_tests"] += 1

        return self.results

    def print_summary(self):
        """Print test results summary"""
        print("\n" + "="*80)
        print("TEST RESULTS SUMMARY")
        print("="*80)
        print(f"Total Tests:  {self.results['total_tests']}")
        print(f"Passed:       {self.results['passed']} ✅")
        print(f"Failed:       {self.results['failed']} ❌")
        print(f"Warnings:     {self.results['warnings']} ⚠️")
        print("="*80)

        if self.results['failed'] > 0:
            print("\nFAILED TESTS:")
            for detail in self.results['test_details']:
                if detail['status'] == 'FAILED':
                    print(f"\n❌ {detail['test']}")
                    print(f"   Error: {detail.get('error', 'Unknown error')}")

        if self.results['warnings'] > 0:
            print("\nWARNINGS:")
            for detail in self.results['test_details']:
                if detail['status'] == 'WARNING':
                    print(f"\n⚠️  {detail['test']}")
                    print(f"   Message: {detail.get('message', 'No details')}")


async def main():
    """Main test execution"""
    validator = BackendKnowledgeBaseValidator()

    try:
        results = await validator.run_all_tests()
        validator.print_summary()

        # Return appropriate exit code
        if results['failed'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"\n❌ TEST SUITE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
