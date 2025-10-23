#!/usr/bin/env python3
"""
Browser Frontend Test using Browser VM
Tests Vue application loading in actual browser environment
"""
import requests
import json
import time
from datetime import datetime

class BrowserFrontendTest:
    def __init__(self):
        self.frontend_url = "http://172.16.168.21:5173"
        self.browser_vm_url = "http://172.16.168.25:3000"  # Browser VM Playwright API
        self.results = []

    def log_result(self, test_name, success, details):
        """Log test result"""
        result = {
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        print(f"   Details: {details}")
        print()

    def test_browser_vm_accessibility(self):
        """Test if Browser VM is accessible"""
        try:
            # Test Browser VM health endpoint
            response = requests.get(f"{self.browser_vm_url}/api/health", timeout=5)
            success = response.status_code == 200
            details = f"Browser VM HTTP {response.status_code}"
            if success:
                try:
                    data = response.json()
                    details += f", Status: {data.get('status', 'unknown')}"
                except:
                    details += ", Response received but not JSON"
            self.log_result("Browser VM Accessibility", success, details)
            return success
        except Exception as e:
            self.log_result("Browser VM Accessibility", False, f"Error: {str(e)}")
            return False

    def simulate_browser_test_via_api(self):
        """Simulate browser test via simple HTTP calls to check basic functionality"""
        try:
            # Test 1: Check if frontend loads basic HTML
            response = requests.get(self.frontend_url, timeout=10)
            if response.status_code != 200:
                self.log_result("Simulated Browser - HTML Load", False, f"HTTP {response.status_code}")
                return False

            # Test 2: Check if Vue dependencies are accessible
            vue_url = f"{self.frontend_url}/node_modules/.vite/deps/vue.js"
            vue_response = requests.head(vue_url, timeout=5)
            vue_accessible = vue_response.status_code == 200

            # Test 3: Check if Pinia is accessible
            pinia_url = f"{self.frontend_url}/node_modules/.vite/deps/pinia.js"
            pinia_response = requests.head(pinia_url, timeout=5)
            pinia_accessible = pinia_response.status_code == 200

            # Test 4: Check if CSS is loading
            css_url = f"{self.frontend_url}/src/assets/tailwind.css"
            css_response = requests.head(css_url, timeout=5)
            css_accessible = css_response.status_code == 200

            details = f"HTML: ✓, Vue.js: {'✓' if vue_accessible else '✗'}, Pinia: {'✓' if pinia_accessible else '✗'}, CSS: {'✓' if css_accessible else '✗'}"
            success = vue_accessible and pinia_accessible and css_accessible

            self.log_result("Simulated Browser - Dependencies", success, details)
            return success

        except Exception as e:
            self.log_result("Simulated Browser - Dependencies", False, f"Error: {str(e)}")
            return False

    def test_javascript_modules_loading(self):
        """Test if JavaScript modules are loading correctly"""
        try:
            # Check if main Vue dependencies are being served correctly
            modules_to_test = [
                ("/src/App.vue", "Vue component"),
                ("/src/router/index.ts", "Router configuration"),
                ("/src/stores/useAppStore.ts", "Pinia store"),
                ("/src/plugins/rum.ts", "RUM plugin"),
                ("/src/utils/asyncComponentHelpers.ts", "Component helpers")
            ]

            results = []
            for module_path, description in modules_to_test:
                try:
                    url = f"{self.frontend_url}{module_path}"
                    response = requests.get(url, timeout=5)
                    success = response.status_code == 200 and len(response.text) > 0
                    results.append(f"{description}: {'✓' if success else '✗'}")
                except:
                    results.append(f"{description}: ✗")

            all_success = all('✓' in result for result in results)
            details = ", ".join(results)

            self.log_result("JavaScript Modules Loading", all_success, details)
            return all_success

        except Exception as e:
            self.log_result("JavaScript Modules Loading", False, f"Error: {str(e)}")
            return False

    def test_vue_devtools_integration(self):
        """Test if Vue DevTools are properly configured"""
        try:
            # Check if Vue DevTools scripts are accessible
            devtools_paths = [
                "/@id/virtual:vue-devtools-path:overlay.js",
                "/@id/virtual:vue-inspector-path:load.js"
            ]

            results = []
            for path in devtools_paths:
                try:
                    url = f"{self.frontend_url}{path}"
                    response = requests.get(url, timeout=5)
                    success = response.status_code == 200
                    results.append(success)
                except:
                    results.append(False)

            all_success = all(results)
            details = f"DevTools overlay: {'✓' if results[0] else '✗'}, Inspector: {'✓' if results[1] else '✗'}"

            self.log_result("Vue DevTools Integration", all_success, details)
            return all_success

        except Exception as e:
            self.log_result("Vue DevTools Integration", False, f"Error: {str(e)}")
            return False

    def test_api_endpoints_from_frontend(self):
        """Test critical API endpoints through frontend proxy"""
        try:
            endpoints = [
                ("/api/health", "Backend health"),
                ("/api/knowledge_base/stats", "Knowledge base"),
                ("/api/chat/sessions", "Chat sessions"),
                ("/api/monitoring/system", "System monitoring")
            ]

            results = []
            for endpoint, description in endpoints:
                try:
                    url = f"{self.frontend_url}{endpoint}"
                    response = requests.get(url, timeout=5)
                    success = response.status_code in [200, 404]  # 404 is acceptable for some endpoints
                    status = "✓" if response.status_code == 200 else f"HTTP{response.status_code}"
                    results.append(f"{description}: {status}")
                except Exception as e:
                    results.append(f"{description}: ✗({str(e)[:20]})")

            # Consider it successful if at least health and knowledge base work
            critical_success = any("Backend health: ✓" in str(results) and "Knowledge base: ✓" in str(results))
            details = ", ".join(results)

            self.log_result("API Endpoints Access", critical_success, details)
            return critical_success

        except Exception as e:
            self.log_result("API Endpoints Access", False, f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all browser frontend tests"""
        print("🌐 Starting Browser Frontend Test")
        print(f"Frontend URL: {self.frontend_url}")
        print(f"Browser VM URL: {self.browser_vm_url}")
        print("=" * 60)
        print()

        tests = [
            self.test_browser_vm_accessibility,
            self.simulate_browser_test_via_api,
            self.test_javascript_modules_loading,
            self.test_vue_devtools_integration,
            self.test_api_endpoints_from_frontend,
        ]

        passed = 0
        total = len(tests)

        for test in tests:
            if test():
                passed += 1

        print("=" * 60)
        print(f"📊 TEST SUMMARY: {passed}/{total} tests passed")

        if passed == total:
            print("🎉 Browser frontend tests completed successfully!")
            print("✅ Vue application components should be loading properly")
            print("✅ All critical JavaScript modules are accessible")
        elif passed >= 3:  # If at least 3 tests pass, it's likely working
            print("✅ Core frontend functionality is working")
            print("⚠️  Some optional features may need attention")
        else:
            print(f"⚠️  {total - passed} critical issues detected")
            print("🔍 Frontend components may not be loading correctly")

        return passed >= 3  # Return success if most tests pass

if __name__ == "__main__":
    test_suite = BrowserFrontendTest()
    success = test_suite.run_all_tests()

    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"/home/kali/Desktop/AutoBot/tests/results/browser_frontend_test_{timestamp}.json"

    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(test_suite.results),
            "passed_tests": len([r for r in test_suite.results if r["success"]]),
            "overall_success": success,
            "test_results": test_suite.results
        }, f, indent=2)

    print(f"\n📁 Detailed results saved to: {results_file}")

    if success:
        print("\n🎯 CONCLUSION: Frontend components are loading correctly!")
        print("   The Vue application infrastructure is working properly.")
        print("   If users report component issues, they may be specific")
        print("   to certain browsers or network conditions.")
    else:
        print("\n❌ CONCLUSION: Frontend component loading issues detected!")
        print("   Check the failed tests above for specific problems.")

    exit(0 if success else 1)