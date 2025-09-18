"""
Test script for Analytics API endpoints
Validates analytics functionality and integration
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnalyticsAPITester:
    """Test suite for Analytics API"""

    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30

    def test_endpoint(self, endpoint: str, method: str = "GET", data: dict = None, expected_status: int = 200):
        """Test a single endpoint"""
        url = f"{self.base_url}{endpoint}"

        logger.info(f"Testing {method} {endpoint}")

        try:
            if method == "GET":
                response = self.session.get(url)
            elif method == "POST":
                response = self.session.post(url, json=data or {})
            else:
                logger.error(f"Unsupported method: {method}")
                return False

            if response.status_code == expected_status:
                logger.info(f"✅ {endpoint} - Status {response.status_code}")

                # Try to parse JSON response
                try:
                    json_data = response.json()
                    logger.info(f"   Response keys: {list(json_data.keys()) if isinstance(json_data, dict) else 'Non-dict response'}")
                    return True
                except Exception as e:
                    logger.info(f"   Non-JSON response or parsing error: {e}")
                    return True
            else:
                logger.error(f"❌ {endpoint} - Expected {expected_status}, got {response.status_code}")
                logger.error(f"   Response: {response.text[:200]}")
                return False

        except Exception as e:
            logger.error(f"❌ {endpoint} - Exception: {e}")
            return False

    def run_tests(self):
        """Run comprehensive analytics API tests"""
        logger.info("🚀 Starting Analytics API Tests")

        results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "endpoints": []
        }

        # Test endpoints
        test_cases = [
            # Dashboard Overview
            ("/api/analytics/dashboard/overview", "GET"),
            ("/api/analytics/system/health-detailed", "GET"),
            ("/api/analytics/performance/metrics", "GET"),

            # Communication Patterns
            ("/api/analytics/communication/patterns", "GET"),
            ("/api/analytics/usage/statistics", "GET"),

            # Code Analysis
            ("/api/analytics/code/status", "GET"),
            ("/api/analytics/code/quality-metrics", "GET"),
            ("/api/analytics/code/communication-chains", "GET"),

            # Real-time Analytics
            ("/api/analytics/realtime/metrics", "GET"),
            ("/api/analytics/trends/historical", "GET"),

            # Management
            ("/api/analytics/status", "GET"),

            # POST endpoints
            ("/api/analytics/events/track", "POST", {
                "event_type": "test_event",
                "timestamp": datetime.now().isoformat(),
                "data": {"test": True},
                "severity": "info"
            }),
            ("/api/analytics/collection/start", "POST"),
            ("/api/analytics/collection/stop", "POST"),
        ]

        # Code analysis test (might take longer)
        code_analysis_test = ("/api/analytics/code/index", "POST", {
            "target_path": "/home/kali/Desktop/AutoBot",
            "analysis_type": "incremental",
            "include_metrics": True
        })

        for test_case in test_cases:
            endpoint = test_case[0]
            method = test_case[1]
            data = test_case[2] if len(test_case) > 2 else None

            results["total"] += 1

            success = self.test_endpoint(endpoint, method, data)

            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1

            results["endpoints"].append({
                "endpoint": endpoint,
                "method": method,
                "success": success
            })

            # Brief pause between tests
            time.sleep(0.5)

        # Test code analysis separately (may take longer)
        logger.info("\n🔍 Testing code analysis (may take longer)...")
        results["total"] += 1

        endpoint, method, data = code_analysis_test
        success = self.test_endpoint(endpoint, method, data)

        if success:
            results["passed"] += 1
        else:
            results["failed"] += 1

        results["endpoints"].append({
            "endpoint": endpoint,
            "method": method,
            "success": success
        })

        # Summary
        logger.info(f"\n📊 Test Results Summary:")
        logger.info(f"   Total Tests: {results['total']}")
        logger.info(f"   Passed: {results['passed']}")
        logger.info(f"   Failed: {results['failed']}")
        logger.info(f"   Success Rate: {results['passed']/results['total']*100:.1f}%")

        if results["failed"] > 0:
            logger.info(f"\n❌ Failed Endpoints:")
            for result in results["endpoints"]:
                if not result["success"]:
                    logger.info(f"   {result['method']} {result['endpoint']}")

        return results

    def test_websocket_connection(self):
        """Test WebSocket analytics streaming"""
        try:
            import websockets

            async def test_ws():
                uri = "ws://localhost:8001/api/analytics/ws/realtime"
                logger.info(f"Testing WebSocket connection to {uri}")

                try:
                    async with websockets.connect(uri) as websocket:
                        logger.info("✅ WebSocket connected successfully")

                        # Send test message
                        test_message = {
                            "type": "get_current",
                            "timestamp": datetime.now().isoformat()
                        }
                        await websocket.send(json.dumps(test_message))

                        # Wait for response
                        response = await asyncio.wait_for(websocket.recv(), timeout=10)
                        data = json.loads(response)

                        logger.info(f"✅ WebSocket response received: {data.get('type', 'unknown')}")
                        return True

                except Exception as e:
                    logger.error(f"❌ WebSocket test failed: {e}")
                    return False

            return asyncio.run(test_ws())

        except ImportError:
            logger.warning("⚠️  websockets library not available, skipping WebSocket test")
            return None
        except Exception as e:
            logger.error(f"❌ WebSocket test error: {e}")
            return False

def main():
    """Main test function"""
    tester = AnalyticsAPITester()

    # Test HTTP endpoints
    results = tester.run_tests()

    # Test WebSocket
    logger.info("\n🌐 Testing WebSocket Analytics...")
    ws_result = tester.test_websocket_connection()
    if ws_result is True:
        logger.info("✅ WebSocket analytics working")
    elif ws_result is False:
        logger.error("❌ WebSocket analytics failed")
    else:
        logger.info("⚠️  WebSocket analytics skipped")

    # Overall success
    overall_success = results["failed"] == 0 and (ws_result is not False)

    logger.info(f"\n🎯 Overall Result: {'SUCCESS' if overall_success else 'PARTIAL SUCCESS'}")

    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)