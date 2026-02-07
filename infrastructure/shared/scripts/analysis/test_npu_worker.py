#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simplified NPU Worker Test for AutoBot Startup
==============================================

Tests basic NPU Worker functionality without external dependencies.
Used during AutoBot startup to verify NPU Worker health.
"""

import json
import sys

try:
    import urllib.error
    import urllib.request

    URLLIB_AVAILABLE = True
except ImportError:
    URLLIB_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class SimpleNPUTester:
    """Simplified NPU Worker tester with no external dependencies"""

    def __init__(self, npu_url="http://localhost:8081"):
        self.npu_url = npu_url
        self.timeout = 10

    def test_health_urllib(self):
        """Test health endpoint using urllib (no dependencies)"""
        try:
            url = f"{self.npu_url}/health"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    print(f"✅ NPU Worker health check passed: {data}")
                    return True, data
                else:
                    print(f"❌ NPU Worker health check failed: HTTP {response.status}")
                    return False, None
        except urllib.error.URLError as e:
            print(f"❌ NPU Worker connection failed: {e}")
            return False, None
        except Exception as e:
            print(f"❌ NPU Worker test error: {e}")
            return False, None

    def test_health_requests(self):
        """Test health endpoint using requests library"""
        try:
            response = requests.get(f"{self.npu_url}/health", timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ NPU Worker health check passed: {data}")
                return True, data
            else:
                print(f"❌ NPU Worker health check failed: HTTP {response.status_code}")
                return False, None
        except requests.exceptions.RequestException as e:
            print(f"❌ NPU Worker connection failed: {e}")
            return False, None
        except Exception as e:
            print(f"❌ NPU Worker test error: {e}")
            return False, None

    def test_basic_endpoints(self, health_data):
        """Test basic endpoints if health check passed"""
        results = {"health": True}

        # Test models endpoint
        try:
            if REQUESTS_AVAILABLE:
                response = requests.get(f"{self.npu_url}/models", timeout=self.timeout)
                results["models_endpoint"] = response.status_code == 200
            elif URLLIB_AVAILABLE:
                req = urllib.request.Request(f"{self.npu_url}/models")
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    results["models_endpoint"] = response.status == 200
            else:
                results["models_endpoint"] = False
                print("⚠️  Cannot test models endpoint - no HTTP library available")
        except Exception:
            results["models_endpoint"] = False

        # Check if device is available
        device = health_data.get("device", "unknown") if health_data else "unknown"
        results["device_available"] = device != "unknown"

        # Check uptime (should be > 0 if running)
        uptime = health_data.get("uptime_seconds", 0) if health_data else 0
        results["service_running"] = uptime > 0

        return results

    def run_tests(self):
        """Run all NPU Worker tests"""
        print("🧪 AutoBot NPU Worker Quick Test")
        print("=" * 40)

        # Try health check with available HTTP library
        health_passed = False
        health_data = None

        if REQUESTS_AVAILABLE:
            print("📡 Testing with requests library...")
            health_passed, health_data = self.test_health_requests()
        elif URLLIB_AVAILABLE:
            print("📡 Testing with urllib (built-in)...")
            health_passed, health_data = self.test_health_urllib()
        else:
            print("❌ No HTTP library available for testing")
            return {"overall": False, "error": "No HTTP library available"}

        if not health_passed:
            return {"overall": False, "health": False}

        # Test additional endpoints
        results = self.test_basic_endpoints(health_data)

        # Overall assessment
        passed_tests = sum(1 for result in results.values() if result)
        total_tests = len(results)
        overall_pass = passed_tests >= (total_tests * 0.8)  # 80% pass rate

        print(f"\n📊 Test Results: {passed_tests}/{total_tests} passed")
        for test_name, passed in results.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {test_name}")

        results["overall"] = overall_pass
        results["pass_rate"] = f"{passed_tests}/{total_tests}"

        return results


def main():
    """Main test function for startup integration"""
    tester = SimpleNPUTester()
    results = tester.run_tests()

    if results.get("overall", False):
        print("\n🎉 NPU Worker tests passed!")
        return 0
    else:
        print("\n⚠️  NPU Worker tests failed (continuing anyway)")
        print("💡 NPU Worker may still function for basic operations")
        return 1


if __name__ == "__main__":
    sys.exit(main())
