#!/usr/bin/env python3
"""
Comprehensive Test Suite for Codebase Indexing Functionality
Tests all aspects of the codebase analytics API
"""

import asyncio
import json
import redis
import requests
import time
from pathlib import Path
from typing import Dict, Any, List

class CodebaseIndexingTester:
    def __init__(self, base_url: str = "http://localhost:8001", redis_host: str = "172.16.168.23"):
        self.base_url = base_url
        self.redis_host = redis_host
        self.api_prefix = f"{base_url}/api/analytics/codebase"
        self.test_results = []

    def log_test(self, test_name: str, status: str, message: str, details: Any = None):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "message": message,
            "timestamp": time.time(),
            "details": details
        }
        self.test_results.append(result)
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {message}")
        if details and status != "PASS":
            print(f"   Details: {details}")

    def test_redis_connection(self):
        """Test Redis DB 11 connection"""
        try:
            redis_client = redis.Redis(
                host=self.redis_host,
                port=6379,
                db=11,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            redis_client.ping()
            self.log_test("Redis DB 11 Connection", "PASS", "Successfully connected to Redis DB 11")
            return redis_client
        except Exception as e:
            self.log_test("Redis DB 11 Connection", "FAIL", f"Failed to connect to Redis DB 11: {e}")
            return None

    def test_backend_health(self):
        """Test backend health"""
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            if response.status_code == 200:
                self.log_test("Backend Health", "PASS", "Backend is healthy")
                return True
            else:
                self.log_test("Backend Health", "FAIL", f"Backend returned status {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Backend Health", "FAIL", f"Backend health check failed: {e}")
            return False

    def test_codebase_indexing(self):
        """Test the main indexing functionality"""
        try:
            print(f"\n🔍 Starting codebase indexing test...")

            # Clear any existing cache first
            clear_response = requests.delete(f"{self.api_prefix}/cache", timeout=60)
            if clear_response.status_code == 200:
                print(f"   Cleared existing cache")

            # Start indexing
            index_response = requests.post(
                f"{self.api_prefix}/index",
                params={"root_path": "/home/kali/Desktop/AutoBot"},
                timeout=120  # 2 minutes timeout for indexing
            )

            if index_response.status_code == 200:
                data = index_response.json()
                stats = data.get("stats", {})

                self.log_test("Codebase Indexing", "PASS",
                            f"Successfully indexed {stats.get('total_files', 0)} files",
                            stats)
                return data
            else:
                self.log_test("Codebase Indexing", "FAIL",
                            f"Indexing failed with status {index_response.status_code}",
                            index_response.text)
                return None

        except Exception as e:
            self.log_test("Codebase Indexing", "FAIL", f"Indexing failed: {e}")
            return None

    def test_file_type_detection(self, indexing_data: Dict):
        """Test that different file types are properly detected"""
        if not indexing_data:
            self.log_test("File Type Detection", "SKIP", "No indexing data available")
            return

        stats = indexing_data.get("stats", {})

        expected_files = {
            "python_files": 0,
            "javascript_files": 0,
            "vue_files": 0,
            "total_files": 0
        }

        for file_type, count in expected_files.items():
            actual_count = stats.get(file_type, 0)
            if actual_count > 0:
                self.log_test(f"File Type Detection - {file_type}", "PASS",
                            f"Found {actual_count} {file_type}")
            else:
                self.log_test(f"File Type Detection - {file_type}", "WARN",
                            f"No {file_type} found")

    def test_hardcode_detection(self):
        """Test hardcode detection functionality"""
        try:
            response = requests.get(f"{self.api_prefix}/hardcodes", timeout=30)

            if response.status_code == 200:
                data = response.json()
                hardcodes = data.get("hardcodes", [])
                hardcode_types = data.get("hardcode_types", [])

                # Check for specific hardcode types we expect
                expected_types = ["ip", "url", "api_path"]
                found_ips = False
                found_urls = False

                for hardcode in hardcodes:
                    if hardcode.get("type") == "ip" and "172.16.168" in hardcode.get("value", ""):
                        found_ips = True
                    if hardcode.get("type") in ["url", "api_path"]:
                        found_urls = True

                if found_ips:
                    self.log_test("Hardcode Detection - IPs", "PASS",
                                f"Found IP addresses (172.16.168.x)")
                else:
                    self.log_test("Hardcode Detection - IPs", "WARN",
                                "No 172.16.168.x IP addresses detected")

                if found_urls:
                    self.log_test("Hardcode Detection - URLs", "PASS",
                                f"Found URL/API path hardcodes")
                else:
                    self.log_test("Hardcode Detection - URLs", "WARN",
                                "No URL hardcodes detected")

                self.log_test("Hardcode Detection", "PASS",
                            f"Found {len(hardcodes)} hardcoded values of types: {hardcode_types}")

                return hardcodes
            else:
                self.log_test("Hardcode Detection", "FAIL",
                            f"Failed to get hardcodes: {response.status_code}")
                return []

        except Exception as e:
            self.log_test("Hardcode Detection", "FAIL", f"Hardcode detection failed: {e}")
            return []

    def test_function_class_extraction(self):
        """Test function and class declaration extraction"""
        try:
            response = requests.get(f"{self.api_prefix}/declarations", timeout=30)

            if response.status_code == 200:
                data = response.json()
                declarations = data.get("declarations", [])
                functions = data.get("functions", 0)
                classes = data.get("classes", 0)

                if functions > 0:
                    self.log_test("Function Extraction", "PASS",
                                f"Found {functions} function declarations")
                else:
                    self.log_test("Function Extraction", "WARN",
                                "No function declarations found")

                if classes > 0:
                    self.log_test("Class Extraction", "PASS",
                                f"Found {classes} class declarations")
                else:
                    self.log_test("Class Extraction", "WARN",
                                "No class declarations found")

                # Check for specific expected functions/classes
                declaration_names = [d.get("name", "") for d in declarations]

                expected_functions = ["scan_codebase", "analyze_python_file", "get_redis_connection"]
                found_expected = [func for func in expected_functions if func in declaration_names]

                if found_expected:
                    self.log_test("Expected Functions Found", "PASS",
                                f"Found expected functions: {found_expected}")
                else:
                    self.log_test("Expected Functions Found", "WARN",
                                "No expected functions found in declarations")

                return declarations
            else:
                self.log_test("Function/Class Extraction", "FAIL",
                            f"Failed to get declarations: {response.status_code}")
                return []

        except Exception as e:
            self.log_test("Function/Class Extraction", "FAIL", f"Declaration extraction failed: {e}")
            return []

    def test_problem_detection(self):
        """Test code problem detection"""
        try:
            response = requests.get(f"{self.api_prefix}/problems", timeout=30)

            if response.status_code == 200:
                data = response.json()
                problems = data.get("problems", [])
                problem_types = data.get("problem_types", [])

                if problems:
                    severity_counts = {}
                    for problem in problems:
                        severity = problem.get("severity", "unknown")
                        severity_counts[severity] = severity_counts.get(severity, 0) + 1

                    self.log_test("Problem Detection", "PASS",
                                f"Found {len(problems)} problems: {severity_counts}")
                else:
                    self.log_test("Problem Detection", "INFO",
                                "No code problems detected (good!)")

                return problems
            else:
                self.log_test("Problem Detection", "FAIL",
                            f"Failed to get problems: {response.status_code}")
                return []

        except Exception as e:
            self.log_test("Problem Detection", "FAIL", f"Problem detection failed: {e}")
            return []

    def test_stats_endpoint(self):
        """Test the stats endpoint"""
        try:
            response = requests.get(f"{self.api_prefix}/stats", timeout=30)

            if response.status_code == 200:
                data = response.json()
                stats = data.get("stats", {})
                last_indexed = data.get("last_indexed", "Never")

                required_stats = [
                    "total_files", "python_files", "javascript_files", "vue_files",
                    "total_lines", "total_functions", "total_classes"
                ]

                missing_stats = [stat for stat in required_stats if stat not in stats]

                if not missing_stats:
                    self.log_test("Stats Endpoint", "PASS",
                                f"All required stats present. Last indexed: {last_indexed}",
                                stats)
                else:
                    self.log_test("Stats Endpoint", "FAIL",
                                f"Missing stats: {missing_stats}")

                return stats
            else:
                self.log_test("Stats Endpoint", "FAIL",
                            f"Stats endpoint failed: {response.status_code}")
                return {}

        except Exception as e:
            self.log_test("Stats Endpoint", "FAIL", f"Stats endpoint failed: {e}")
            return {}

    def test_redis_data_storage(self, redis_client):
        """Test that data is properly stored in Redis DB 11"""
        if not redis_client:
            self.log_test("Redis Data Storage", "SKIP", "No Redis connection available")
            return

        try:
            # Check for main data keys
            expected_keys = [
                "codebase:analysis:full",
                "codebase:analysis:timestamp",
                "codebase:stats"
            ]

            found_keys = []
            missing_keys = []

            for key in expected_keys:
                if redis_client.exists(key):
                    found_keys.append(key)
                else:
                    missing_keys.append(key)

            if not missing_keys:
                self.log_test("Redis Data Storage", "PASS",
                            f"All expected keys found in Redis DB 11")
            else:
                self.log_test("Redis Data Storage", "FAIL",
                            f"Missing keys in Redis: {missing_keys}")

            # Check for dynamic keys (functions, classes, etc.)
            function_keys = list(redis_client.scan_iter(match="codebase:functions:*"))
            class_keys = list(redis_client.scan_iter(match="codebase:classes:*"))
            hardcode_keys = list(redis_client.scan_iter(match="codebase:hardcodes:*"))

            self.log_test("Redis Function Keys", "PASS" if function_keys else "WARN",
                        f"Found {len(function_keys)} function keys")
            self.log_test("Redis Class Keys", "PASS" if class_keys else "WARN",
                        f"Found {len(class_keys)} class keys")
            self.log_test("Redis Hardcode Keys", "PASS" if hardcode_keys else "WARN",
                        f"Found {len(hardcode_keys)} hardcode keys")

        except Exception as e:
            self.log_test("Redis Data Storage", "FAIL", f"Redis data check failed: {e}")

    def test_cache_clearing(self):
        """Test cache clearing functionality"""
        try:
            response = requests.delete(f"{self.api_prefix}/cache", timeout=30)

            if response.status_code == 200:
                data = response.json()
                deleted_keys = data.get("deleted_keys", 0)

                self.log_test("Cache Clearing", "PASS",
                            f"Successfully cleared {deleted_keys} cache entries")
                return True
            else:
                self.log_test("Cache Clearing", "FAIL",
                            f"Cache clearing failed: {response.status_code}")
                return False

        except Exception as e:
            self.log_test("Cache Clearing", "FAIL", f"Cache clearing failed: {e}")
            return False

    def run_comprehensive_test(self):
        """Run all tests in sequence"""
        print("🚀 Starting Comprehensive Codebase Indexing Test Suite")
        print("=" * 60)

        # Test 1: Basic connectivity
        print("\n📡 Testing Basic Connectivity...")
        backend_healthy = self.test_backend_health()
        redis_client = self.test_redis_connection()

        if not backend_healthy:
            print("❌ Backend not healthy - aborting tests")
            return self.test_results

        # Test 2: Clear cache
        print("\n🧹 Testing Cache Management...")
        self.test_cache_clearing()

        # Test 3: Main indexing
        print("\n🔍 Testing Codebase Indexing...")
        indexing_data = self.test_codebase_indexing()

        # Test 4: File type detection
        print("\n📁 Testing File Type Detection...")
        self.test_file_type_detection(indexing_data)

        # Test 5: Feature-specific tests
        print("\n🔧 Testing Feature Detection...")
        hardcodes = self.test_hardcode_detection()
        declarations = self.test_function_class_extraction()
        problems = self.test_problem_detection()

        # Test 6: Stats endpoint
        print("\n📊 Testing Stats Endpoint...")
        stats = self.test_stats_endpoint()

        # Test 7: Redis storage verification
        print("\n💾 Testing Redis Data Storage...")
        self.test_redis_data_storage(redis_client)

        # Test 8: Final cache clear
        print("\n🧹 Final Cache Clear Test...")
        self.test_cache_clearing()

        return self.test_results

    def generate_report(self):
        """Generate a comprehensive test report"""
        print("\n" + "=" * 60)
        print("📋 COMPREHENSIVE TEST REPORT")
        print("=" * 60)

        passed = len([r for r in self.test_results if r["status"] == "PASS"])
        failed = len([r for r in self.test_results if r["status"] == "FAIL"])
        warned = len([r for r in self.test_results if r["status"] == "WARN"])
        skipped = len([r for r in self.test_results if r["status"] == "SKIP"])
        total = len(self.test_results)

        print(f"📊 SUMMARY: {total} tests total")
        print(f"   ✅ PASSED: {passed}")
        print(f"   ❌ FAILED: {failed}")
        print(f"   ⚠️  WARNINGS: {warned}")
        print(f"   ⏭️  SKIPPED: {skipped}")

        if failed > 0:
            print(f"\n❌ FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"   • {result['test']}: {result['message']}")

        if warned > 0:
            print(f"\n⚠️  WARNINGS:")
            for result in self.test_results:
                if result["status"] == "WARN":
                    print(f"   • {result['test']}: {result['message']}")

        success_rate = (passed / total * 100) if total > 0 else 0
        print(f"\n🎯 SUCCESS RATE: {success_rate:.1f}%")

        if success_rate >= 80:
            print("🎉 TEST SUITE PASSED - Codebase indexing is working correctly!")
        elif success_rate >= 60:
            print("⚠️  TEST SUITE PARTIAL - Some issues need attention")
        else:
            print("❌ TEST SUITE FAILED - Major issues detected")

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "skipped": skipped,
            "success_rate": success_rate,
            "results": self.test_results
        }

def main():
    """Main test execution"""
    tester = CodebaseIndexingTester()

    # Run comprehensive tests
    results = tester.run_comprehensive_test()

    # Generate report
    report = tester.generate_report()

    # Save detailed results to file
    results_file = "/home/kali/Desktop/AutoBot/tests/results/codebase_indexing_test_results.json"
    Path(results_file).parent.mkdir(parents=True, exist_ok=True)

    with open(results_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n📝 Detailed results saved to: {results_file}")

    return report["success_rate"] >= 80

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)