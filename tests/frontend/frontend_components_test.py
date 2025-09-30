#!/usr/bin/env python3
"""
Comprehensive Frontend Components Test
Tests Vue application loading and component functionality
"""
import requests
import json
import time
from datetime import datetime

class FrontendComponentsTest:
    def __init__(self):
        self.frontend_url = "http://172.16.168.21:5173"
        self.backend_url = "http://172.16.168.20:8001"
        self.results = []

    def log_result(self, test_name, success, details, response_time=None):
        """Log test result"""
        result = {
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "response_time_ms": response_time
        }
        self.results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        print(f"   Details: {details}")
        if response_time:
            print(f"   Response Time: {response_time}ms")
        print()

    def test_frontend_server_accessibility(self):
        """Test if frontend server is accessible and responsive"""
        try:
            start_time = time.time()
            response = requests.head(self.frontend_url, timeout=10)
            response_time = int((time.time() - start_time) * 1000)

            success = response.status_code == 200
            details = f"HTTP {response.status_code}, Headers: {dict(response.headers)}"
            self.log_result("Frontend Server Accessibility", success, details, response_time)
            return success
        except Exception as e:
            self.log_result("Frontend Server Accessibility", False, f"Error: {str(e)}")
            return False

    def test_html_content_loading(self):
        """Test if HTML content loads correctly"""
        try:
            start_time = time.time()
            response = requests.get(self.frontend_url, timeout=10)
            response_time = int((time.time() - start_time) * 1000)

            has_app_div = 'id="app"' in response.text
            has_main_script = 'src="/src/main.ts"' in response.text
            success = response.status_code == 200 and has_app_div and has_main_script

            app_status = "Yes" if has_app_div else "No"
            script_status = "Yes" if has_main_script else "No"
            details = f"HTML size: {len(response.text)} chars, Contains app div: {app_status}, Contains main.ts: {script_status}"
            self.log_result("HTML Content Loading", success, details, response_time)
            return success
        except Exception as e:
            self.log_result("HTML Content Loading", False, f"Error: {str(e)}")
            return False

    def test_vue_main_script_loading(self):
        """Test if Vue main script is accessible"""
        try:
            start_time = time.time()
            main_url = f"{self.frontend_url}/src/main.ts"
            response = requests.get(main_url, timeout=10)
            response_time = int((time.time() - start_time) * 1000)

            has_create_app = 'createApp' in response.text
            has_import_meta = 'import.meta.env' in response.text
            success = response.status_code == 200 and has_create_app and has_import_meta

            create_app_status = "Yes" if has_create_app else "No"
            details = f"Script size: {len(response.text)} chars, Contains createApp: {create_app_status}"
            self.log_result("Vue Main Script Loading", success, details, response_time)
            return success
        except Exception as e:
            self.log_result("Vue Main Script Loading", False, f"Error: {str(e)}")
            return False

    def test_api_proxy_functionality(self):
        """Test if API proxy to backend works"""
        try:
            start_time = time.time()
            health_url = f"{self.frontend_url}/api/health"
            response = requests.get(health_url, timeout=10)
            response_time = int((time.time() - start_time) * 1000)

            success = response.status_code == 200
            if success:
                try:
                    data = response.json()
                    success = data.get('status') == 'healthy'
                    details = f"Backend status: {data.get('status')}, Response: {json.dumps(data, indent=2)}"
                except:
                    details = f"Valid HTTP response but invalid JSON: {response.text[:200]}"
            else:
                details = f"HTTP {response.status_code}: {response.text[:200]}"

            self.log_result("API Proxy Functionality", success, details, response_time)
            return success
        except Exception as e:
            self.log_result("API Proxy Functionality", False, f"Error: {str(e)}")
            return False

    def test_knowledge_manager_api(self):
        """Test Knowledge Manager API through frontend proxy"""
        try:
            start_time = time.time()
            kb_url = f"{self.frontend_url}/api/knowledge_base/stats"
            response = requests.get(kb_url, timeout=10)
            response_time = int((time.time() - start_time) * 1000)

            success = response.status_code == 200
            if success:
                try:
                    data = response.json()
                    required_keys = ['total_documents', 'categories', 'status']
                    success = all(key in data for key in required_keys)
                    details = f"Knowledge base data: {json.dumps(data, indent=2)}"
                except:
                    success = False
                    details = f"Invalid JSON response: {response.text[:200]}"
            else:
                details = f"HTTP {response.status_code}: {response.text[:200]}"

            self.log_result("Knowledge Manager API", success, details, response_time)
            return success
        except Exception as e:
            self.log_result("Knowledge Manager API", False, f"Error: {str(e)}")
            return False

    def test_websocket_endpoint(self):
        """Test WebSocket endpoint accessibility"""
        try:
            # Test WebSocket endpoint by checking HTTP upgrade potential
            ws_url = f"{self.frontend_url}/ws"
            headers = {
                'Connection': 'Upgrade',
                'Upgrade': 'websocket',
                'Sec-WebSocket-Version': '13',
                'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ=='
            }

            start_time = time.time()
            response = requests.get(ws_url, headers=headers, timeout=5)
            response_time = int((time.time() - start_time) * 1000)

            # WebSocket upgrade should return 101 or 400/426 (bad request but endpoint exists)
            success = response.status_code in [101, 400, 426]
            details = f"WebSocket endpoint HTTP {response.status_code} (expected 101/400/426 for existing endpoint)"

            self.log_result("WebSocket Endpoint", success, details, response_time)
            return success
        except Exception as e:
            self.log_result("WebSocket Endpoint", False, f"Error: {str(e)}")
            return False

    def test_direct_backend_connection(self):
        """Test direct backend connection (not through proxy)"""
        try:
            start_time = time.time()
            backend_health = f"{self.backend_url}/api/health"
            response = requests.get(backend_health, timeout=5)
            response_time = int((time.time() - start_time) * 1000)

            success = response.status_code == 200
            if success:
                data = response.json()
                details = f"Direct backend connection successful: {data.get('status')}"
            else:
                details = f"Direct backend failed: HTTP {response.status_code}"

            self.log_result("Direct Backend Connection", success, details, response_time)
            return success
        except Exception as e:
            self.log_result("Direct Backend Connection", False, f"Error: {str(e)}")
            return False

    def test_vite_dev_server_features(self):
        """Test Vite development server specific features"""
        try:
            # Test Vite client connection
            vite_client_url = f"{self.frontend_url}/@vite/client"
            start_time = time.time()
            response = requests.get(vite_client_url, timeout=5)
            response_time = int((time.time() - start_time) * 1000)

            has_vite = 'vite' in response.text.lower() or 'HMR' in response.text
            success = response.status_code == 200 and has_vite
            details = f"Vite client script accessible, size: {len(response.text)} chars"

            self.log_result("Vite Dev Server Features", success, details, response_time)
            return success
        except Exception as e:
            self.log_result("Vite Dev Server Features", False, f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all frontend tests"""
        print("🚀 Starting Comprehensive Frontend Components Test")
        print(f"Frontend URL: {self.frontend_url}")
        print(f"Backend URL: {self.backend_url}")
        print("=" * 60)
        print()

        tests = [
            self.test_frontend_server_accessibility,
            self.test_html_content_loading,
            self.test_vue_main_script_loading,
            self.test_vite_dev_server_features,
            self.test_api_proxy_functionality,
            self.test_knowledge_manager_api,
            self.test_websocket_endpoint,
            self.test_direct_backend_connection,
        ]

        passed = 0
        total = len(tests)

        for test in tests:
            if test():
                passed += 1

        print("=" * 60)
        print(f"📊 TEST SUMMARY: {passed}/{total} tests passed")

        if passed == total:
            print("🎉 All frontend components are working correctly!")
            print("✅ Frontend server is properly configured for distributed architecture")
            print("✅ Vue application should be loading and functioning normally")
        else:
            print(f"⚠️  {total - passed} issues detected")
            print("🔍 Check the failed tests above for specific issues")

        return passed == total

if __name__ == "__main__":
    test_suite = FrontendComponentsTest()
    all_passed = test_suite.run_all_tests()

    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"/home/kali/Desktop/AutoBot/tests/results/frontend_components_test_{timestamp}.json"

    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(test_suite.results),
            "passed_tests": len([r for r in test_suite.results if r["success"]]),
            "overall_success": all_passed,
            "test_results": test_suite.results
        }, f, indent=2)

    print(f"\n📁 Detailed results saved to: {results_file}")
    exit(0 if all_passed else 1)