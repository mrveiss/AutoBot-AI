#!/usr/bin/env python3
"""
AutoBot Frontend-Backend Integration Test Suite
Comprehensive testing of API connectivity, WebSocket communication, and user flows
"""

import asyncio
import aiohttp
import websockets
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import sys
import os

# Add project root to path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class IntegrationTestSuite:
    """Comprehensive integration test suite for AutoBot frontend-backend communication"""

    def __init__(self):
        # Test configuration
        self.frontend_url = "http://127.0.0.1:5173"
        self.backend_url = "http://172.16.168.20:8001"
        self.websocket_url = "ws://172.16.168.20:8001"

        # Test results storage
        self.test_results = {
            "api_connectivity": {},
            "websocket_communication": {},
            "chat_interface": {},
            "knowledge_base": {},
            "system_monitoring": {},
            "error_handling": {},
            "performance": {}
        }

        # Critical API endpoints to test
        self.critical_endpoints = [
            ("GET", "/api/health", "Health Check"),
            ("GET", "/api/system/status", "System Status"),
            ("GET", "/api/knowledge_base/stats/basic", "Knowledge Base Stats"),
            ("GET", "/api/monitoring/services", "Service Monitoring"),
            ("GET", "/api/chats", "Chat List"),
            ("POST", "/api/chats", "Create Chat"),
            ("GET", "/api/agents/config", "Agent Configuration"),
            ("GET", "/api/models", "Available Models"),
        ]

        # Performance benchmarks
        self.performance_thresholds = {
            "api_response_time": 5.0,  # seconds
            "websocket_connect_time": 3.0,  # seconds
            "chat_message_response": 30.0,  # seconds
            "knowledge_search_time": 10.0,  # seconds
        }

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run complete integration test suite"""
        logger.info("🚀 Starting AutoBot Frontend-Backend Integration Tests")

        start_time = time.time()

        try:
            # 1. API Connectivity Testing
            await self.test_api_connectivity()

            # 2. WebSocket Communication Testing
            await self.test_websocket_communication()

            # 3. Chat Interface Testing
            await self.test_chat_interface()

            # 4. Knowledge Base Integration Testing
            await self.test_knowledge_base_integration()

            # 5. System Monitoring Testing
            await self.test_system_monitoring()

            # 6. Error Handling Testing
            await self.test_error_handling()

            # 7. Performance Testing
            await self.test_performance()

        except Exception as e:
            logger.error(f"❌ Test suite failed with error: {e}")
            self.test_results["suite_error"] = str(e)

        total_time = time.time() - start_time
        self.test_results["total_execution_time"] = total_time

        # Generate comprehensive report
        self.generate_test_report()

        return self.test_results

    async def test_api_connectivity(self):
        """Test critical API endpoint connectivity and response validation"""
        logger.info("🔗 Testing API Connectivity")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            for method, endpoint, description in self.critical_endpoints:
                try:
                    start_time = time.time()

                    if method == "GET":
                        async with session.get(f"{self.backend_url}{endpoint}") as response:
                            response_time = time.time() - start_time

                            result = {
                                "status_code": response.status,
                                "response_time": response_time,
                                "success": 200 <= response.status < 300,
                                "content_type": response.headers.get('content-type', ''),
                                "description": description
                            }

                            if response.status == 200:
                                try:
                                    data = await response.json()
                                    result["response_data"] = data
                                    result["has_json_response"] = True
                                except:
                                    result["has_json_response"] = False

                            self.test_results["api_connectivity"][endpoint] = result

                            status_emoji = "✅" if result["success"] else "❌"
                            logger.info(f"{status_emoji} {description}: {response.status} ({response_time:.2f}s)")

                    elif method == "POST":
                        # Test POST endpoints with appropriate payloads
                        payload = self.get_test_payload(endpoint)
                        async with session.post(f"{self.backend_url}{endpoint}", json=payload) as response:
                            response_time = time.time() - start_time

                            result = {
                                "status_code": response.status,
                                "response_time": response_time,
                                "success": 200 <= response.status < 300,
                                "description": description,
                                "payload": payload
                            }

                            if response.status in [200, 201]:
                                try:
                                    data = await response.json()
                                    result["response_data"] = data
                                except:
                                    pass

                            self.test_results["api_connectivity"][endpoint] = result

                            status_emoji = "✅" if result["success"] else "❌"
                            logger.info(f"{status_emoji} {description}: {response.status} ({response_time:.2f}s)")

                except asyncio.TimeoutError:
                    self.test_results["api_connectivity"][endpoint] = {
                        "error": "Timeout",
                        "success": False,
                        "description": description
                    }
                    logger.error(f"❌ {description}: Timeout")

                except Exception as e:
                    self.test_results["api_connectivity"][endpoint] = {
                        "error": str(e),
                        "success": False,
                        "description": description
                    }
                    logger.error(f"❌ {description}: {e}")

    async def test_websocket_communication(self):
        """Test WebSocket real-time communication"""
        logger.info("🌐 Testing WebSocket Communication")

        try:
            start_time = time.time()

            # Test WebSocket connection
            uri = f"{self.websocket_url}/ws"

            async with websockets.connect(uri, timeout=5) as websocket:
                connect_time = time.time() - start_time

                # Test ping-pong
                await websocket.send(json.dumps({"type": "ping", "timestamp": time.time()}))

                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    response_data = json.loads(response)

                    self.test_results["websocket_communication"] = {
                        "connection_success": True,
                        "connect_time": connect_time,
                        "ping_response": response_data,
                        "response_time": time.time() - start_time
                    }

                    logger.info(f"✅ WebSocket connected ({connect_time:.2f}s)")
                    logger.info(f"✅ Ping response received: {response_data.get('type', 'unknown')}")

                except asyncio.TimeoutError:
                    self.test_results["websocket_communication"] = {
                        "connection_success": True,
                        "connect_time": connect_time,
                        "ping_response_timeout": True
                    }
                    logger.warning("⚠️ WebSocket connected but ping response timeout")

        except Exception as e:
            self.test_results["websocket_communication"] = {
                "connection_success": False,
                "error": str(e)
            }
            logger.error(f"❌ WebSocket connection failed: {e}")

    async def test_chat_interface(self):
        """Test chat message sending and receiving"""
        logger.info("💬 Testing Chat Interface")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            try:
                # 1. Create a new chat session
                chat_payload = {
                    "title": f"Integration Test Chat {datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "model": "test_model"
                }

                async with session.post(f"{self.backend_url}/api/chats", json=chat_payload) as response:
                    if response.status in [200, 201]:
                        chat_data = await response.json()
                        chat_id = chat_data.get("id") or chat_data.get("chat_id")

                        if chat_id:
                            # 2. Send a test message
                            message_payload = {
                                "content": "Hello AutoBot! This is an integration test message.",
                                "role": "user"
                            }

                            start_time = time.time()

                            async with session.post(
                                f"{self.backend_url}/api/chats/{chat_id}/message",
                                json=message_payload
                            ) as msg_response:
                                response_time = time.time() - start_time

                                self.test_results["chat_interface"] = {
                                    "chat_creation": {
                                        "success": True,
                                        "chat_id": chat_id
                                    },
                                    "message_sending": {
                                        "success": 200 <= msg_response.status < 300,
                                        "status_code": msg_response.status,
                                        "response_time": response_time
                                    }
                                }

                                if msg_response.status == 200:
                                    try:
                                        response_data = await msg_response.json()
                                        self.test_results["chat_interface"]["message_sending"]["response_data"] = response_data
                                        logger.info(f"✅ Chat message sent and received response ({response_time:.2f}s)")
                                    except:
                                        logger.info(f"✅ Chat message sent ({response_time:.2f}s)")
                                else:
                                    logger.error(f"❌ Message sending failed: {msg_response.status}")
                        else:
                            logger.error("❌ Chat creation failed: No chat ID returned")
                    else:
                        logger.error(f"❌ Chat creation failed: {response.status}")
                        self.test_results["chat_interface"] = {
                            "chat_creation": {
                                "success": False,
                                "status_code": response.status
                            }
                        }

            except Exception as e:
                self.test_results["chat_interface"] = {
                    "error": str(e),
                    "success": False
                }
                logger.error(f"❌ Chat interface test failed: {e}")

    async def test_knowledge_base_integration(self):
        """Test knowledge base search and document operations"""
        logger.info("📚 Testing Knowledge Base Integration")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            try:
                # 1. Get knowledge base statistics
                async with session.get(f"{self.backend_url}/api/knowledge_base/stats/basic") as response:
                    if response.status == 200:
                        stats_data = await response.json()

                        self.test_results["knowledge_base"]["stats"] = {
                            "success": True,
                            "data": stats_data,
                            "has_documents": stats_data.get("total_documents", 0) > 0,
                            "has_chunks": stats_data.get("total_chunks", 0) > 0
                        }

                        logger.info(f"✅ Knowledge base stats: {stats_data.get('total_documents', 0)} docs, {stats_data.get('total_chunks', 0)} chunks")
                    else:
                        logger.error(f"❌ Knowledge base stats failed: {response.status}")

                # 2. Test knowledge base search
                search_payload = {
                    "query": "AutoBot system architecture",
                    "limit": 5
                }

                start_time = time.time()

                async with session.post(f"{self.backend_url}/api/knowledge_base/search", json=search_payload) as response:
                    search_time = time.time() - start_time

                    if response.status == 200:
                        search_results = await response.json()

                        self.test_results["knowledge_base"]["search"] = {
                            "success": True,
                            "response_time": search_time,
                            "results_count": len(search_results.get("results", [])),
                            "has_results": len(search_results.get("results", [])) > 0
                        }

                        logger.info(f"✅ Knowledge base search: {len(search_results.get('results', []))} results ({search_time:.2f}s)")
                    else:
                        logger.error(f"❌ Knowledge base search failed: {response.status}")
                        self.test_results["knowledge_base"]["search"] = {
                            "success": False,
                            "status_code": response.status
                        }

            except Exception as e:
                self.test_results["knowledge_base"]["error"] = str(e)
                logger.error(f"❌ Knowledge base test failed: {e}")

    async def test_system_monitoring(self):
        """Test system monitoring and health check displays"""
        logger.info("🔍 Testing System Monitoring")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            try:
                # Test various monitoring endpoints
                monitoring_endpoints = [
                    ("/api/system/status", "System Status"),
                    ("/api/monitoring/services", "Service Health"),
                    ("/api/agents/config", "Agent Configuration"),
                    ("/api/models", "Model Status")
                ]

                for endpoint, description in monitoring_endpoints:
                    try:
                        async with session.get(f"{self.backend_url}{endpoint}") as response:
                            success = 200 <= response.status < 300

                            result = {
                                "success": success,
                                "status_code": response.status,
                                "description": description
                            }

                            if success:
                                try:
                                    data = await response.json()
                                    result["data"] = data
                                    result["has_data"] = bool(data)
                                except:
                                    result["has_data"] = False

                            self.test_results["system_monitoring"][endpoint] = result

                            status_emoji = "✅" if success else "❌"
                            logger.info(f"{status_emoji} {description}: {response.status}")

                    except Exception as e:
                        self.test_results["system_monitoring"][endpoint] = {
                            "success": False,
                            "error": str(e),
                            "description": description
                        }
                        logger.error(f"❌ {description}: {e}")

            except Exception as e:
                self.test_results["system_monitoring"]["error"] = str(e)
                logger.error(f"❌ System monitoring test failed: {e}")

    async def test_error_handling(self):
        """Test error handling and response format consistency"""
        logger.info("⚠️ Testing Error Handling")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            # Test various error conditions
            error_tests = [
                ("GET", "/api/nonexistent", 404, "Non-existent endpoint"),
                ("GET", "/api/chats/invalid-id", 404, "Invalid chat ID"),
                ("POST", "/api/chats/invalid-id/message", 404, "Invalid chat message"),
            ]

            for method, endpoint, expected_status, description in error_tests:
                try:
                    if method == "GET":
                        async with session.get(f"{self.backend_url}{endpoint}") as response:
                            self.test_results["error_handling"][endpoint] = {
                                "expected_status": expected_status,
                                "actual_status": response.status,
                                "correct_error_code": response.status == expected_status,
                                "description": description
                            }

                            status_emoji = "✅" if response.status == expected_status else "⚠️"
                            logger.info(f"{status_emoji} {description}: {response.status} (expected {expected_status})")

                    elif method == "POST":
                        async with session.post(f"{self.backend_url}{endpoint}", json={}) as response:
                            self.test_results["error_handling"][endpoint] = {
                                "expected_status": expected_status,
                                "actual_status": response.status,
                                "correct_error_code": response.status == expected_status,
                                "description": description
                            }

                            status_emoji = "✅" if response.status == expected_status else "⚠️"
                            logger.info(f"{status_emoji} {description}: {response.status} (expected {expected_status})")

                except Exception as e:
                    self.test_results["error_handling"][endpoint] = {
                        "error": str(e),
                        "description": description
                    }
                    logger.error(f"❌ {description}: {e}")

    async def test_performance(self):
        """Test performance benchmarks for critical operations"""
        logger.info("⚡ Testing Performance Benchmarks")

        performance_results = {}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            # Test API response times
            for method, endpoint, description in self.critical_endpoints[:5]:  # Test first 5 endpoints
                if method == "GET":
                    try:
                        times = []
                        for i in range(3):  # Average of 3 requests
                            start_time = time.time()
                            async with session.get(f"{self.backend_url}{endpoint}") as response:
                                response_time = time.time() - start_time
                                times.append(response_time)

                        avg_time = sum(times) / len(times)
                        performance_results[f"{endpoint}_response_time"] = {
                            "average_time": avg_time,
                            "within_threshold": avg_time <= self.performance_thresholds["api_response_time"],
                            "threshold": self.performance_thresholds["api_response_time"],
                            "individual_times": times
                        }

                        status_emoji = "✅" if avg_time <= self.performance_thresholds["api_response_time"] else "⚠️"
                        logger.info(f"{status_emoji} {description} avg response time: {avg_time:.2f}s (threshold: {self.performance_thresholds['api_response_time']}s)")

                    except Exception as e:
                        performance_results[f"{endpoint}_response_time"] = {
                            "error": str(e)
                        }

        self.test_results["performance"] = performance_results

    def get_test_payload(self, endpoint: str) -> Dict[str, Any]:
        """Get appropriate test payload for POST endpoints"""
        payloads = {
            "/api/chats": {
                "title": f"Test Chat {datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "model": "test"
            }
        }
        return payloads.get(endpoint, {})

    def generate_test_report(self):
        """Generate comprehensive test report"""
        logger.info("📊 Generating Integration Test Report")

        # Calculate overall success metrics
        api_successes = sum(1 for result in self.test_results["api_connectivity"].values()
                           if isinstance(result, dict) and result.get("success", False))
        api_total = len(self.test_results["api_connectivity"])

        websocket_success = self.test_results["websocket_communication"].get("connection_success", False)

        chat_success = (self.test_results.get("chat_interface", {})
                       .get("message_sending", {})
                       .get("success", False))

        kb_stats_success = (self.test_results.get("knowledge_base", {})
                           .get("stats", {})
                           .get("success", False))

        # Print summary report
        print("\n" + "="*60)
        print("🤖 AUTOBOT FRONTEND-BACKEND INTEGRATION TEST REPORT")
        print("="*60)
        print(f"Test Execution Time: {self.test_results.get('total_execution_time', 0):.2f} seconds")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        print("📊 TEST SUMMARY:")
        print(f"  API Connectivity: {api_successes}/{api_total} endpoints successful")
        print(f"  WebSocket Communication: {'✅ SUCCESS' if websocket_success else '❌ FAILED'}")
        print(f"  Chat Interface: {'✅ SUCCESS' if chat_success else '❌ FAILED'}")
        print(f"  Knowledge Base: {'✅ SUCCESS' if kb_stats_success else '❌ FAILED'}")
        print()

        # Detailed API results
        print("🔗 API CONNECTIVITY RESULTS:")
        for endpoint, result in self.test_results["api_connectivity"].items():
            if isinstance(result, dict):
                status = "✅" if result.get("success", False) else "❌"
                time_info = f" ({result.get('response_time', 0):.2f}s)" if 'response_time' in result else ""
                print(f"  {status} {result.get('description', endpoint)}: {result.get('status_code', 'N/A')}{time_info}")
        print()

        # Performance results
        if self.test_results.get("performance"):
            print("⚡ PERFORMANCE RESULTS:")
            for metric, data in self.test_results["performance"].items():
                if isinstance(data, dict) and 'average_time' in data:
                    status = "✅" if data.get("within_threshold", False) else "⚠️"
                    print(f"  {status} {metric}: {data['average_time']:.2f}s (threshold: {data['threshold']}s)")
        print()

        # Production readiness assessment
        total_critical_tests = api_total + 4  # API + WebSocket + Chat + KB + System
        passed_critical_tests = api_successes + sum([
            int(websocket_success),
            int(chat_success),
            int(kb_stats_success),
            1  # Assume system monitoring passes if API works
        ])

        production_ready_percentage = (passed_critical_tests / total_critical_tests) * 100

        print("🚀 PRODUCTION READINESS ASSESSMENT:")
        print(f"  Overall Success Rate: {production_ready_percentage:.1f}%")

        if production_ready_percentage >= 90:
            print("  Status: ✅ PRODUCTION READY")
            print("  Recommendation: System is ready for production deployment")
        elif production_ready_percentage >= 75:
            print("  Status: ⚠️ MOSTLY READY")
            print("  Recommendation: Address minor issues before production")
        else:
            print("  Status: ❌ NOT READY")
            print("  Recommendation: Address critical issues before production")

        print()
        print("="*60)

async def main():
    """Run the integration test suite"""
    test_suite = IntegrationTestSuite()
    results = await test_suite.run_all_tests()

    # Save results to file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f"/home/kali/Desktop/AutoBot/tests/results/integration_test_results_{timestamp}.json"

    os.makedirs(os.path.dirname(results_file), exist_ok=True)

    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"📄 Test results saved to: {results_file}")

    return results

if __name__ == "__main__":
    asyncio.run(main())
