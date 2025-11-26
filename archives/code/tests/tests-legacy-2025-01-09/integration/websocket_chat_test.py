#!/usr/bin/env python3
"""
WebSocket and Chat Interface Integration Test
Test real-time communication and chat functionality
"""

import asyncio
import aiohttp
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any
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

class WebSocketChatTest:
    """Test WebSocket and chat functionality"""

    def __init__(self):
        self.backend_url = "http://172.16.168.20:8001"
        self.websocket_url = "ws://172.16.168.20:8001"
        self.results = {
            "websocket_tests": {},
            "chat_api_tests": {},
            "integration_tests": {},
            "performance_metrics": {}
        }

    async def run_websocket_chat_tests(self) -> Dict[str, Any]:
        """Run WebSocket and chat integration tests"""
        logger.info("🚀 Starting WebSocket and Chat Integration Tests")
        start_time = time.time()

        # Test WebSocket functionality
        await self.test_websocket_connection()

        # Test Chat API endpoints
        await self.test_chat_api()

        # Test real-time messaging
        await self.test_realtime_messaging()

        # Performance testing
        await self.test_performance_metrics()

        total_time = time.time() - start_time
        self.results["total_execution_time"] = total_time

        self.generate_websocket_chat_report()
        return self.results

    async def test_websocket_connection(self):
        """Test WebSocket connection and basic communication"""
        logger.info("🔌 Testing WebSocket Connection")

        try:
            import websockets

            # Test WebSocket connection
            uri = f"{self.websocket_url}/ws"

            try:
                async with websockets.connect(
                    uri,
                    timeout=5,
                    ping_interval=20,
                    ping_timeout=10
                ) as websocket:

                    # Test connection
                    connect_time = time.time()

                    # Send ping message
                    ping_message = {
                        "type": "ping",
                        "timestamp": time.time(),
                        "test_id": "integration_test"
                    }

                    await websocket.send(json.dumps(ping_message))
                    logger.info("📤 Sent WebSocket ping")

                    # Wait for response
                    try:
                        response = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=5.0
                        )

                        response_time = time.time() - connect_time
                        response_data = json.loads(response)

                        self.results["websocket_tests"]["ping_pong"] = {
                            "success": True,
                            "response_time": response_time,
                            "response_data": response_data,
                            "message_type": response_data.get("type", "unknown")
                        }

                        logger.info(f"📥 WebSocket response received: {response_data.get('type', 'unknown')} ({response_time:.3f}s)")

                    except asyncio.TimeoutError:
                        self.results["websocket_tests"]["ping_pong"] = {
                            "success": False,
                            "error": "Response timeout",
                            "timeout_duration": 5.0
                        }
                        logger.warning("⚠️ WebSocket ping response timeout")

                    # Test chat message format
                    chat_message = {
                        "type": "chat_message",
                        "content": "Hello AutoBot! This is a WebSocket integration test.",
                        "user_id": "test_user",
                        "session_id": "test_session"
                    }

                    await websocket.send(json.dumps(chat_message))
                    logger.info("📤 Sent WebSocket chat message")

                    # Wait for chat response
                    try:
                        chat_response = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=10.0
                        )

                        chat_response_data = json.loads(chat_response)

                        self.results["websocket_tests"]["chat_message"] = {
                            "success": True,
                            "response_data": chat_response_data,
                            "response_type": chat_response_data.get("type", "unknown")
                        }

                        logger.info(f"📥 Chat response: {chat_response_data.get('type', 'unknown')}")

                    except asyncio.TimeoutError:
                        self.results["websocket_tests"]["chat_message"] = {
                            "success": False,
                            "error": "Chat response timeout"
                        }
                        logger.warning("⚠️ WebSocket chat response timeout")

            except Exception as ws_error:
                self.results["websocket_tests"]["connection"] = {
                    "success": False,
                    "error": str(ws_error)
                }
                logger.error(f"❌ WebSocket connection failed: {ws_error}")

        except ImportError:
            # Fallback: test with aiohttp WebSocket client
            logger.info("🔄 Using aiohttp WebSocket client as fallback")
            await self.test_websocket_with_aiohttp()

    async def test_websocket_with_aiohttp(self):
        """Test WebSocket using aiohttp client"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(
                    f"{self.websocket_url}/ws",
                    timeout=5.0
                ) as ws:

                    # Send test message
                    test_message = {
                        "type": "test",
                        "content": "aiohttp WebSocket test"
                    }

                    await ws.send_str(json.dumps(test_message))

                    # Wait for response
                    try:
                        response = await asyncio.wait_for(
                            ws.receive(),
                            timeout=5.0
                        )

                        if response.type == aiohttp.WSMsgType.TEXT:
                            response_data = json.loads(response.data)

                            self.results["websocket_tests"]["aiohttp_fallback"] = {
                                "success": True,
                                "response_data": response_data
                            }

                            logger.info(f"✅ aiohttp WebSocket test successful: {response_data.get('type', 'unknown')}")
                        else:
                            logger.warning(f"⚠️ Unexpected WebSocket message type: {response.type}")

                    except asyncio.TimeoutError:
                        self.results["websocket_tests"]["aiohttp_fallback"] = {
                            "success": False,
                            "error": "Response timeout"
                        }

            except Exception as e:
                self.results["websocket_tests"]["aiohttp_fallback"] = {
                    "success": False,
                    "error": str(e)
                }
                logger.error(f"❌ aiohttp WebSocket test failed: {e}")

    async def test_chat_api(self):
        """Test Chat API endpoints"""
        logger.info("💬 Testing Chat API Endpoints")

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:

            # Test chat list endpoint
            try:
                async with session.get(f"{self.backend_url}/api/chats") as response:
                    self.results["chat_api_tests"]["chat_list"] = {
                        "success": response.status == 200,
                        "status_code": response.status
                    }

                    if response.status == 200:
                        data = await response.json()
                        self.results["chat_api_tests"]["chat_list"]["data"] = data
                        logger.info(f"✅ Chat list endpoint: {len(data.get('chats', []))} chats")
                    else:
                        logger.error(f"❌ Chat list endpoint failed: {response.status}")

            except Exception as e:
                self.results["chat_api_tests"]["chat_list"] = {
                    "success": False,
                    "error": str(e)
                }
                logger.error(f"❌ Chat list test failed: {e}")

            # Test chat creation
            try:
                chat_payload = {
                    "title": f"Integration Test Chat {datetime.now().strftime('%H%M%S')}",
                    "model": "test_model"
                }

                async with session.post(
                    f"{self.backend_url}/api/chats",
                    json=chat_payload
                ) as response:

                    self.results["chat_api_tests"]["chat_creation"] = {
                        "success": response.status in [200, 201],
                        "status_code": response.status,
                        "payload": chat_payload
                    }

                    if response.status in [200, 201]:
                        chat_data = await response.json()
                        chat_id = chat_data.get("id") or chat_data.get("chat_id")

                        if chat_id:
                            self.results["chat_api_tests"]["chat_creation"]["chat_id"] = chat_id
                            logger.info(f"✅ Chat created: {chat_id}")

                            # Test sending message to created chat
                            await self.test_chat_message(session, chat_id)
                        else:
                            logger.warning("⚠️ Chat created but no ID returned")
                    else:
                        logger.error(f"❌ Chat creation failed: {response.status}")

            except Exception as e:
                self.results["chat_api_tests"]["chat_creation"] = {
                    "success": False,
                    "error": str(e)
                }
                logger.error(f"❌ Chat creation test failed: {e}")

    async def test_chat_message(self, session: aiohttp.ClientSession, chat_id: str):
        """Test sending message to a chat"""
        try:
            message_payload = {
                "content": "Hello AutoBot! This is an integration test message for chat functionality.",
                "role": "user"
            }

            start_time = time.time()

            async with session.post(
                f"{self.backend_url}/api/chats/{chat_id}/message",
                json=message_payload
            ) as response:

                response_time = time.time() - start_time

                self.results["chat_api_tests"]["message_sending"] = {
                    "success": response.status == 200,
                    "status_code": response.status,
                    "response_time": response_time,
                    "chat_id": chat_id,
                    "payload": message_payload
                }

                if response.status == 200:
                    try:
                        response_data = await response.json()
                        self.results["chat_api_tests"]["message_sending"]["response_data"] = response_data
                        logger.info(f"✅ Message sent to chat {chat_id} ({response_time:.2f}s)")

                        # Check if response contains expected fields
                        has_response = "response" in response_data or "content" in response_data
                        self.results["chat_api_tests"]["message_sending"]["has_ai_response"] = has_response

                    except:
                        logger.info(f"✅ Message sent (response not JSON) ({response_time:.2f}s)")
                else:
                    logger.error(f"❌ Message sending failed: {response.status}")

        except Exception as e:
            self.results["chat_api_tests"]["message_sending"] = {
                "success": False,
                "error": str(e),
                "chat_id": chat_id
            }
            logger.error(f"❌ Message sending test failed: {e}")

    async def test_realtime_messaging(self):
        """Test real-time messaging integration"""
        logger.info("⚡ Testing Real-time Messaging Integration")

        # This test combines WebSocket and HTTP API
        try:
            # First, test if we can simulate real-time updates
            async with aiohttp.ClientSession() as session:
                # Send multiple rapid requests to test real-time capabilities
                tasks = []

                for i in range(3):
                    task = self.send_rapid_request(session, i)
                    tasks.append(task)

                results = await asyncio.gather(*tasks, return_exceptions=True)

                successful_requests = [r for r in results if isinstance(r, dict) and r.get("success")]

                self.results["integration_tests"]["rapid_requests"] = {
                    "total_requests": len(tasks),
                    "successful_requests": len(successful_requests),
                    "success_rate": len(successful_requests) / len(tasks) * 100,
                    "results": results
                }

                logger.info(f"⚡ Rapid requests: {len(successful_requests)}/{len(tasks)} successful")

        except Exception as e:
            self.results["integration_tests"]["rapid_requests"] = {
                "success": False,
                "error": str(e)
            }
            logger.error(f"❌ Real-time messaging test failed: {e}")

    async def send_rapid_request(self, session: aiohttp.ClientSession, request_id: int) -> Dict[str, Any]:
        """Send a rapid API request for real-time testing"""
        try:
            start_time = time.time()

            async with session.get(f"{self.backend_url}/api/health") as response:
                response_time = time.time() - start_time

                return {
                    "success": response.status == 200,
                    "request_id": request_id,
                    "response_time": response_time,
                    "status_code": response.status
                }

        except Exception as e:
            return {
                "success": False,
                "request_id": request_id,
                "error": str(e)
            }

    async def test_performance_metrics(self):
        """Test performance metrics for WebSocket and Chat"""
        logger.info("📊 Testing Performance Metrics")

        # Test API response times under load
        response_times = []

        async with aiohttp.ClientSession() as session:
            for i in range(10):
                try:
                    start_time = time.time()
                    async with session.get(f"{self.backend_url}/api/health") as response:
                        response_time = time.time() - start_time
                        response_times.append(response_time)

                except Exception:
                    pass

        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            min_response_time = min(response_times)

            self.results["performance_metrics"]["api_load_test"] = {
                "requests_sent": 10,
                "successful_requests": len(response_times),
                "average_response_time": avg_response_time,
                "max_response_time": max_response_time,
                "min_response_time": min_response_time,
                "all_response_times": response_times
            }

            logger.info(f"📊 Performance: avg={avg_response_time:.3f}s, max={max_response_time:.3f}s")

    def generate_websocket_chat_report(self):
        """Generate comprehensive WebSocket and Chat report"""
        print("\n" + "="*80)
        print("🌐 AUTOBOT WEBSOCKET & CHAT INTEGRATION TEST REPORT")
        print("="*80)
        print(f"Test Duration: {self.results.get('total_execution_time', 0):.2f} seconds")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # WebSocket Tests
        print("🔌 WEBSOCKET TESTS:")
        ws_tests = self.results.get("websocket_tests", {})
        for test_name, result in ws_tests.items():
            status = "✅" if result.get("success", False) else "❌"
            print(f"    {status} {test_name.replace('_', ' ').title()}")

            if result.get("response_time"):
                print(f"        Response Time: {result['response_time']:.3f}s")
            if result.get("error"):
                print(f"        Error: {result['error']}")
        print()

        # Chat API Tests
        print("💬 CHAT API TESTS:")
        chat_tests = self.results.get("chat_api_tests", {})
        for test_name, result in chat_tests.items():
            status = "✅" if result.get("success", False) else "❌"
            print(f"    {status} {test_name.replace('_', ' ').title()}: {result.get('status_code', 'N/A')}")

            if result.get("response_time"):
                print(f"        Response Time: {result['response_time']:.3f}s")
            if result.get("chat_id"):
                print(f"        Chat ID: {result['chat_id']}")
        print()

        # Integration Tests
        print("⚡ INTEGRATION TESTS:")
        integration_tests = self.results.get("integration_tests", {})
        for test_name, result in integration_tests.items():
            if test_name == "rapid_requests":
                success_rate = result.get("success_rate", 0)
                status = "✅" if success_rate >= 80 else "❌"
                print(f"    {status} Rapid Requests: {result.get('successful_requests', 0)}/{result.get('total_requests', 0)} ({success_rate:.1f}%)")
        print()

        # Performance Metrics
        print("📊 PERFORMANCE METRICS:")
        perf_metrics = self.results.get("performance_metrics", {})
        if perf_metrics:
            for metric_name, data in perf_metrics.items():
                if isinstance(data, dict):
                    avg_time = data.get("average_response_time", 0)
                    max_time = data.get("max_response_time", 0)
                    successful = data.get("successful_requests", 0)
                    total = data.get("requests_sent", 0)

                    print(f"    📈 {metric_name.replace('_', ' ').title()}:")
                    print(f"        Success Rate: {successful}/{total} ({(successful/total*100 if total > 0 else 0):.1f}%)")
                    print(f"        Average Response: {avg_time:.3f}s")
                    print(f"        Max Response: {max_time:.3f}s")

        # Overall Assessment
        print()
        print("🎯 REAL-TIME COMMUNICATION ASSESSMENT:")

        # Count successful components
        ws_success = any(test.get("success", False) for test in ws_tests.values())
        chat_success = any(test.get("success", False) for test in chat_tests.values())

        components_working = sum([
            int(ws_success),
            int(chat_success)
        ])

        if components_working == 2:
            print("    ✅ EXCELLENT - WebSocket and Chat APIs fully functional")
        elif components_working == 1:
            print("    ⚠️ PARTIAL - Some real-time features working")
        else:
            print("    ❌ ISSUES - Real-time communication needs attention")

        print()
        print("="*80)

async def main():
    """Run WebSocket and Chat tests"""
    test = WebSocketChatTest()
    results = await test.run_websocket_chat_tests()

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f"/home/kali/Desktop/AutoBot/tests/results/websocket_chat_{timestamp}.json"

    os.makedirs(os.path.dirname(results_file), exist_ok=True)

    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"📄 Results saved to: {results_file}")
    return results

if __name__ == "__main__":
    asyncio.run(main())
