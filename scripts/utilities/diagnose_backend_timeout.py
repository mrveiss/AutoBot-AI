#!/usr/bin/env python3
"""
Backend Timeout Diagnostic Script
Helps identify the cause of backend API timeouts
"""

import asyncio
import logging
import sys
import time
from typing import Any, Dict

import aiohttp
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class BackendDiagnostic:
    """Diagnose backend timeout issues"""

    def __init__(self, base_url: str = ServiceURLs.BACKEND_LOCAL):
        self.base_url = base_url
        self.results = {}

    def test_socket_connection(self) -> bool:
        """Test basic socket connectivity"""
        import socket

        try:
            logger.info("🔌 Testing socket connection...")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            result = s.connect_ex(("localhost", 8001))
            s.close()

            if result == 0:
                logger.info("✅ Socket connection: SUCCESS")
                return True
            else:
                logger.error(f"❌ Socket connection failed: {result}")
                return False
        except Exception as e:
            logger.error(f"❌ Socket test error: {e}")
            return False

    def test_tcp_connection(self) -> bool:
        """Test TCP connection with timeout"""
        try:
            logger.info("🌐 Testing TCP connection with telnet-like approach...")
            import socket
            from src.constants import NetworkConstants, ServiceURLs

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect(("localhost", 8001))

            # Try to send a minimal HTTP request
            request = (
                b"HEAD / HTTP/1.1\r\nHost: localhost:8001\r\nConnection: close\r\n\r\n"
            )
            s.send(request)

            # Try to receive response
            start_time = time.time()
            response = s.recv(1024)
            elapsed = time.time() - start_time
            s.close()

            if response:
                logger.info(f"✅ TCP HTTP response received in {elapsed:.3f}s")
                logger.info(f"📋 Response preview: {response[:100]}")
                return True
            else:
                logger.error(f"❌ No response received after {elapsed:.3f}s")
                return False

        except socket.timeout:
            logger.error("❌ TCP connection timed out")
            return False
        except Exception as e:
            logger.error(f"❌ TCP test error: {e}")
            return False

    async def test_async_request(self) -> bool:
        """Test async HTTP request with detailed timeout control"""
        try:
            logger.info("⚡ Testing async HTTP request...")
            timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=5)

            start_time = time.time()

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/") as response:
                    elapsed = time.time() - start_time
                    status = response.status
                    content_length = len(await response.text())

                    logger.info(
                        f"✅ Async request: Status {status}, {content_length} bytes in {elapsed:.3f}s"
                    )
                    return True

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error(f"❌ Async request timed out after {elapsed:.3f}s")
            return False
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ Async request error after {elapsed:.3f}s: {e}")
            return False

    def test_sync_request(self) -> bool:
        """Test synchronous HTTP request"""
        try:
            logger.info("📡 Testing synchronous HTTP request...")
            start_time = time.time()

            response = requests.get(
                f"{self.base_url}/",
                timeout=(3, 7),  # (connect, read) timeout
                stream=False,
            )

            elapsed = time.time() - start_time
            logger.info(
                f"✅ Sync request: Status {response.status_code} in {elapsed:.3f}s"
            )
            return True

        except requests.exceptions.Timeout:
            elapsed = time.time() - start_time
            logger.error(f"❌ Sync request timed out after {elapsed:.3f}s")
            return False
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ Sync request error after {elapsed:.3f}s: {e}")
            return False

    def test_specific_endpoints(self) -> Dict[str, bool]:
        """Test specific endpoints to narrow down the issue"""
        endpoints = ["/", "/docs", "/openapi.json", "/api/system/health"]

        results = {}

        for endpoint in endpoints:
            try:
                logger.info(f"🎯 Testing endpoint: {endpoint}")
                start_time = time.time()

                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)

                elapsed = time.time() - start_time
                results[endpoint] = True
                logger.info(
                    f"✅ {endpoint}: Status {response.status_code} in {elapsed:.3f}s"
                )

            except Exception as e:
                elapsed = time.time() - start_time
                results[endpoint] = False
                logger.error(f"❌ {endpoint}: Failed in {elapsed:.3f}s - {e}")

        return results

    async def run_diagnostics(self) -> Dict[str, Any]:
        """Run complete diagnostic suite"""
        logger.info("🚀 Starting Backend Timeout Diagnostics...")
        logger.info("=" * 60)

        results = {
            "socket_connection": self.test_socket_connection(),
            "tcp_connection": self.test_tcp_connection(),
            "async_request": await self.test_async_request(),
            "sync_request": self.test_sync_request(),
            "endpoint_tests": self.test_specific_endpoints(),
        }

        return results

    def print_summary(self, results: Dict[str, Any]):
        """Print diagnostic summary"""
        logger.info("\n" + "=" * 60)
        logger.info("📊 DIAGNOSTIC SUMMARY")
        logger.info("=" * 60)

        # Basic connectivity
        socket_ok = results["socket_connection"]
        tcp_ok = results["tcp_connection"]
        async_ok = results["async_request"]
        sync_ok = results["sync_request"]

        logger.info(f"🔌 Socket Connection: {'✅ PASS' if socket_ok else '❌ FAIL'}")
        logger.info(f"🌐 TCP Connection: {'✅ PASS' if tcp_ok else '❌ FAIL'}")
        logger.info(f"⚡ Async HTTP: {'✅ PASS' if async_ok else '❌ FAIL'}")
        logger.info(f"📡 Sync HTTP: {'✅ PASS' if sync_ok else '❌ FAIL'}")

        # Endpoint tests
        endpoint_results = results["endpoint_tests"]
        working_endpoints = sum(1 for success in endpoint_results.values() if success)
        total_endpoints = len(endpoint_results)

        logger.info(
            f"\n🎯 Endpoint Tests: {working_endpoints}/{total_endpoints} working"
        )
        for endpoint, success in endpoint_results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            logger.info(f"   {endpoint}: {status}")

        # Diagnosis
        logger.info(f"\n🔍 DIAGNOSIS:")
        if socket_ok and not (async_ok or sync_ok):
            logger.info("🔧 Issue appears to be in HTTP/application layer")
            logger.info(
                "💡 Possible causes: FastAPI middleware, blocking startup, or request handling"
            )
        elif not socket_ok:
            logger.info("🔧 Issue appears to be at network/socket level")
            logger.info("💡 Possible causes: Port binding, firewall, or process issues")
        elif working_endpoints == 0:
            logger.info("🔧 All endpoints failing - likely application-wide issue")
            logger.info(
                "💡 Possible causes: Database locks, initialization blocks, or dependency issues"
            )
        elif working_endpoints < total_endpoints:
            logger.info("🔧 Partial endpoint failure - specific route issues")
            logger.info(
                "💡 Possible causes: Middleware on specific routes or dependency timeouts"
            )
        else:
            logger.info("🎉 All tests passing - timeout issue may be intermittent")


async def main():
    """Run backend diagnostics"""
    diagnostic = BackendDiagnostic()

    try:
        results = await diagnostic.run_diagnostics()
        diagnostic.print_summary(results)

        # Return exit code based on results
        any_success = any(
            [
                results["socket_connection"],
                results["tcp_connection"],
                results["async_request"],
                results["sync_request"],
            ]
        )

        return 0 if any_success else 1

    except Exception as e:
        logger.error(f"❌ Diagnostic failed: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
