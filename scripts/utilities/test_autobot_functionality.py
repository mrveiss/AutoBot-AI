#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Functionality Test Suite
Comprehensive testing of all AutoBot components and features
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict

import requests

# Import centralized Redis client
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.constants.network_constants import NetworkConstants, ServiceURLs
from src.utils.redis_client import get_redis_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class AutoBotFunctionalityTest:
    """Test all AutoBot system functionality"""

    def __init__(self):
        """Initialize functionality test suite with service URLs and results."""
        self.services = {
            "frontend": ServiceURLs.FRONTEND_LOCAL,
            "backend": ServiceURLs.BACKEND_LOCAL,
            "npu_worker": ServiceURLs.NPU_WORKER_SERVICE,
            "ai_stack": ServiceURLs.AI_STACK_SERVICE,
            "redis": f"{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.REDIS_PORT}",
            "redis_insight": f"http://{NetworkConstants.LOCALHOST_NAME}:8002",  # RedisInsight port
        }
        self.results = {}

    def test_frontend_accessibility(self) -> bool:
        """Test frontend development server"""
        try:
            logger.info("🎨 Testing Frontend Development Server...")
            response = requests.get(self.services["frontend"], timeout=5)

            if response.status_code == 200 and "AutoBot" in response.text:
                logger.info("✅ Frontend: Accessible and serving AutoBot application")
                return True
            else:
                logger.error(f"❌ Frontend: Unexpected response {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Frontend: Connection failed - {e}")
            return False

    def test_backend_api(self) -> bool:
        """Test backend FastAPI endpoints"""
        try:
            logger.info("🔧 Testing Backend FastAPI API...")

            # Test health endpoint
            response = requests.get(
                f"{self.services['backend']}/api/system/health", timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Backend: API responding with health status")
                logger.info(f"📋 Backend status: {data.get('status', 'unknown')}")
                return True
            else:
                logger.error(
                    f"❌ Backend: Health endpoint returned {response.status_code}"
                )
                return False

        except requests.exceptions.ConnectionError:
            logger.warning("⚠️ Backend: Not running (expected if manually stopped)")
            return False
        except Exception as e:
            logger.error(f"❌ Backend: Connection failed - {e}")
            return False

    def test_npu_worker(self) -> bool:
        """Test NPU worker container"""
        try:
            logger.info("🔥 Testing NPU Worker Container...")
            response = requests.get(f"{self.services['npu_worker']}/health", timeout=5)

            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                npu_available = data.get("npu_available", False)
                optimal_device = data.get("optimal_device", "unknown")

                logger.info(f"✅ NPU Worker: {status}")
                logger.info(f"📋 NPU Available: {npu_available}")
                logger.info(f"📋 Optimal Device: {optimal_device}")

                return status == "healthy"
            else:
                logger.error(f"❌ NPU Worker: Returned {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ NPU Worker: Connection failed - {e}")
            return False

    def test_ai_stack_container(self) -> bool:
        """Test AI stack container with agent health"""
        try:
            logger.info("🤖 Testing AI Stack Container...")
            response = requests.get(f"{self.services['ai_stack']}/health", timeout=5)

            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                agents = data.get("agents", {})
                uptime = data.get("uptime_seconds", 0)

                logger.info(f"✅ AI Stack: {status}")
                logger.info(f"📋 Uptime: {uptime:.1f} seconds")
                logger.info(f"📋 Agents: {len(agents)} active")

                # Check individual agents
                healthy_agents = 0
                for agent_name, agent_data in agents.items():
                    agent_status = agent_data.get("status", "unknown")
                    if agent_status == "healthy":
                        healthy_agents += 1
                        logger.info(f"  ✅ {agent_name}: {agent_status}")
                    else:
                        logger.warning(f"  ⚠️ {agent_name}: {agent_status}")

                return status == "healthy" and healthy_agents > 0
            else:
                logger.error(f"❌ AI Stack: Returned {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ AI Stack: Connection failed - {e}")
            return False

    def test_redis_connectivity(self) -> bool:
        """Test Redis connectivity using centralized client"""
        try:
            logger.info("📊 Testing Redis Connectivity...")

            async def test_redis():
                redis_client = await get_redis_client('main')
                if not redis_client:
                    return False

                # Test basic operations
                await redis_client.ping()
                await redis_client.set("autobot_test_key", "test_value", ex=10)
                value = await redis_client.get("autobot_test_key")
                await redis_client.delete("autobot_test_key")

                return value == "test_value"

            # Run async test
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(test_redis())
            loop.close()

            if result:
                logger.info("✅ Redis: Connection and operations successful")
                return True
            else:
                logger.error("❌ Redis: Test operations failed")
                return False

        except Exception as e:
            logger.error(f"❌ Redis: Connection failed - {e}")
            return False

    def test_redis_insight(self) -> bool:
        """Test Redis Insight web interface"""
        try:
            logger.info("🔍 Testing Redis Insight Interface...")
            response = requests.get(self.services["redis_insight"], timeout=5)

            if response.status_code == 200:
                logger.info("✅ Redis Insight: Web interface accessible")
                return True
            else:
                logger.error(f"❌ Redis Insight: Returned {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Redis Insight: Connection failed - {e}")
            return False

    def test_docker_containers(self) -> bool:
        """Test Docker container status"""
        try:
            logger.info("🐳 Testing Docker Container Status...")
            import subprocess

            result = subprocess.run(
                ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                container_lines = result.stdout.strip().split("\n")[1:]  # Skip header
                autobot_containers = [
                    line for line in container_lines if "autobot" in line.lower()
                ]

                logger.info(
                    f"✅ Docker: {len(autobot_containers)} AutoBot containers found"
                )

                healthy_containers = 0
                for container_line in autobot_containers:
                    parts = container_line.split("\t")
                    if len(parts) >= 2:
                        name = parts[0]
                        status = parts[1]
                        if "healthy" in status.lower() or "up" in status.lower():
                            healthy_containers += 1
                            logger.info(f"  ✅ {name}: {status}")
                        else:
                            logger.warning(f"  ⚠️ {name}: {status}")

                return healthy_containers >= 3  # Expect at least 3 healthy containers
            else:
                logger.error(f"❌ Docker: Command failed with code {result.returncode}")
                return False

        except Exception as e:
            logger.error(f"❌ Docker: Status check failed - {e}")
            return False

    def test_system_integration(self) -> bool:
        """Test overall system integration"""
        try:
            logger.info("🔗 Testing System Integration...")

            # Check if key processes are running
            import subprocess

            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5
            )

            processes = result.stdout
            node_processes = len(
                [
                    line
                    for line in processes.split("\n")
                    if "node" in line and "vite" in line
                ]
            )
            python_processes = len(
                [
                    line
                    for line in processes.split("\n")
                    if "python" in line and "autobot" in line.lower()
                ]
            )

            logger.info(f"📋 Node.js processes (frontend): {node_processes}")
            logger.info(f"📋 Python processes (backend): {python_processes}")

            # System should have at least frontend processes running
            if node_processes > 0:
                logger.info("✅ System Integration: Frontend processes active")
                return True
            else:
                logger.warning("⚠️ System Integration: Limited processes active")
                return False

        except Exception as e:
            logger.error(f"❌ System Integration: Check failed - {e}")
            return False

    async def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run all functionality tests"""
        logger.info("🚀 Starting AutoBot Functionality Test Suite...")
        logger.info("=" * 70)

        tests = [
            ("Frontend Development Server", self.test_frontend_accessibility),
            ("Backend FastAPI", self.test_backend_api),
            ("NPU Worker Container", self.test_npu_worker),
            ("AI Stack Container", self.test_ai_stack_container),
            ("Redis Connectivity", self.test_redis_connectivity),
            ("Redis Insight Interface", self.test_redis_insight),
            ("Docker Containers", self.test_docker_containers),
            ("System Integration", self.test_system_integration),
        ]

        results = {}

        for test_name, test_func in tests:
            logger.info(f"\n🔍 Running: {test_name}")
            try:
                result = test_func()
                results[test_name] = result

                if result:
                    logger.info(f"✅ {test_name}: PASS")
                else:
                    logger.warning(f"⚠️ {test_name}: FAIL")

            except Exception as e:
                logger.error(f"❌ {test_name}: ERROR - {e}")
                results[test_name] = False

        return results

    def print_summary(self, results: Dict[str, Any]):
        """Print comprehensive test summary"""
        logger.info("\n" + "=" * 70)
        logger.info("📊 AUTOBOT FUNCTIONALITY TEST SUMMARY")
        logger.info("=" * 70)

        passed = sum(1 for result in results.values() if result)
        total = len(results)

        # Categorize results
        critical_tests = [
            "NPU Worker Container",
            "AI Stack Container",
            "Redis Connectivity",
            "Docker Containers",
        ]
        optional_tests = ["Backend FastAPI", "Redis Insight Interface"]

        critical_passed = sum(1 for test in critical_tests if results.get(test, False))
        critical_total = len(critical_tests)

        logger.info(f"📈 Overall Score: {passed}/{total} tests passed")
        logger.info(
            f"🎯 Critical Systems: {critical_passed}/{critical_total} operational"
        )

        logger.info("\n🔍 Detailed Results:")
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            criticality = (
                "🔴 CRITICAL"
                if test_name in critical_tests
                else "🟡 OPTIONAL"
                if test_name in optional_tests
                else "🟢 STANDARD"
            )
            logger.info(f"  {status} - {test_name} ({criticality})")

        # System status assessment
        logger.info("\n🎯 SYSTEM STATUS ASSESSMENT:")
        if critical_passed == critical_total and passed >= total * 0.75:
            logger.info("🎉 EXCELLENT: AutoBot system fully operational")
            logger.info("🚀 All critical components healthy and ready for use")
        elif critical_passed >= critical_total * 0.75:
            logger.info("✅ GOOD: AutoBot system mostly operational")
            logger.info("🔧 Some non-critical components may need attention")
        elif critical_passed >= critical_total * 0.5:
            logger.info("⚠️ PARTIAL: AutoBot system partially operational")
            logger.info("🔧 Several critical components need attention")
        else:
            logger.info("❌ POOR: AutoBot system requires significant repairs")
            logger.info("🔧 Multiple critical components are failing")


async def main():
    """Main test runner"""
    tester = AutoBotFunctionalityTest()

    try:
        results = await tester.run_comprehensive_tests()
        tester.print_summary(results)

        # Return appropriate exit code
        passed = sum(1 for result in results.values() if result)
        total = len(results)

        if passed >= total * 0.75:
            return 0  # Success
        elif passed >= total * 0.5:
            return 1  # Partial success
        else:
            return 2  # Failure

    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
