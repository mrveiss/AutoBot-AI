# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Embedded Playwright Service
Integrates Docker-based Playwright into the main AutoBot application
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
from backend.constants.network_constants import NetworkConstants, ServiceURLs
from backend.type_defs.common import Metadata
from backend.utils.chat_exceptions import ServiceUnavailableError

from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)


class PlaywrightService:
    """
    Embedded Playwright service that communicates with Docker container
    but feels like a native part of the application
    """

    def __init__(
        self,
        container_host: str = "localhost",
        container_port: int = NetworkConstants.BROWSER_SERVICE_PORT,
        timeout: int = 30,
    ):
        """Initialize Playwright service with container connection settings."""
        self.base_url = f"http://{container_host}:{container_port}"
        self.timeout = timeout
        self.http_client = get_http_client()
        self._healthy = False

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()

    async def initialize(self):
        """Initialize the Playwright service connection"""
        # Check if container is healthy
        await self._health_check()
        logger.info("Playwright service initialized at %s", self.base_url)

    async def cleanup(self):
        """Cleanup resources"""
        # HTTPClient singleton doesn't need cleanup per instance
        logger.info("Playwright service cleaned up")

    async def _health_check(self) -> bool:
        """Check if Playwright container is healthy"""
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with await self.http_client.get(
                f"{self.base_url}/health", timeout=timeout
            ) as response:
                if response.status == 200:
                    health_data = await response.json()
                    self._healthy = health_data.get("status") == "healthy"
                    logger.debug("Playwright health check: %s", health_data)
                    return self._healthy
                else:
                    logger.warning(
                        "Playwright health check failed: %s", response.status
                    )
                    self._healthy = False
                    return False

        except asyncio.TimeoutError:
            logger.error(
                f"Playwright health check timed out after {self.timeout}s "
                f"at {self.base_url}"
            )
            self._healthy = False
            return False
        except aiohttp.ClientConnectorError as e:
            logger.error(
                f"Playwright service connection refused at {self.base_url}: {e}"
            )
            self._healthy = False
            return False
        except aiohttp.ClientError as e:
            logger.error("Playwright health check HTTP error: %s", e)
            self._healthy = False
            return False
        except Exception as e:
            logger.error("Playwright health check unexpected error: %s", e)
            self._healthy = False
            return False

    async def is_ready(self) -> bool:
        """Check if service is ready for requests"""
        if not self._healthy:
            await self._health_check()
        return self._healthy

    async def _post_and_parse(self, endpoint: str, payload: dict) -> dict:
        """
        POST to a Playwright container endpoint and return parsed JSON. Ref: #1088.

        Helper for search_web, test_frontend, and send_test_message.
        Raises RuntimeError on non-200 status; caller handles connection errors.
        """
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with await self.http_client.post(
            f"{self.base_url}/{endpoint}", json=payload, timeout=timeout
        ) as response:
            if response.status == 200:
                return await response.json()
            error_text = await response.text()
            raise RuntimeError(f"{endpoint} failed: {response.status} - {error_text}")

    def _format_test_frontend_exception(self, e: Exception) -> str:
        """
        Build detailed error string for unexpected test_frontend exceptions. Ref: #1088.

        Helper for test_frontend.
        """
        import traceback

        error_details = f"Exception: {type(e).__name__}: {str(e)}"
        if hasattr(e, "__cause__") and e.__cause__:
            error_details += f" | Caused by: {e.__cause__}"
        error_details += (
            f" | Traceback: {traceback.format_exc()[-500:]}"  # Last 500 chars
        )
        return error_details

    async def search_web(
        self, query: str, search_engine: str = "duckduckgo", max_results: int = 5
    ) -> Metadata:
        """
        Perform web search using embedded Playwright

        Args:
            query: Search query
            search_engine: Search engine to use
            max_results: Maximum number of results

        Returns:
            Search results with metadata
        """
        try:
            if not await self.is_ready():
                raise ServiceUnavailableError(
                    "Playwright service not available",
                    service="playwright",
                    url=self.base_url,
                )

            payload = {
                "query": query,
                "search_engine": search_engine,
                "max_results": max_results,
            }
            result = await self._post_and_parse("search", payload)
            logger.info(
                f"Web search completed: '{query}' -> {len(result.get('results', []))} results"
            )
            return result

        except asyncio.TimeoutError:
            logger.error("Web search timed out after %ss: '%s'", self.timeout, query)
            return {
                "success": False,
                "error": f"Search timed out after {self.timeout}s",
                "query": query,
                "results": [],
            }
        except aiohttp.ClientConnectorError as e:
            logger.error("Web search connection error: %s", e)
            return {
                "success": False,
                "error": "Playwright service connection failed",
                "query": query,
                "results": [],
            }
        except ServiceUnavailableError:
            # Re-raise without wrapping
            return {
                "success": False,
                "error": "Playwright service not available",
                "query": query,
                "results": [],
            }
        except Exception as e:
            logger.error("Web search error: %s", e)
            return {"success": False, "error": str(e), "query": query, "results": []}

    async def test_frontend(
        self, frontend_url: str = ServiceURLs.FRONTEND_LOCAL
    ) -> Metadata:
        """
        Test frontend functionality using embedded Playwright

        Args:
            frontend_url: URL of frontend to test

        Returns:
            Test results with detailed analysis
        """
        try:
            if not await self.is_ready():
                raise ServiceUnavailableError(
                    "Playwright service not available",
                    service="playwright",
                    url=self.base_url,
                )

            result = await self._post_and_parse(
                "test-frontend", {"frontend_url": frontend_url}
            )
            logger.info("Frontend test completed: %s", result.get("summary", {}))
            return result

        except asyncio.TimeoutError:
            logger.error(
                "Frontend test timed out after %ss: %s", self.timeout, frontend_url
            )
            return {
                "success": False,
                "error": f"Frontend test timed out after {self.timeout}s",
                "frontend_url": frontend_url,
                "tests": [],
            }
        except aiohttp.ClientConnectorError as e:
            logger.error("Frontend test connection error: %s", e)
            return {
                "success": False,
                "error": "Playwright service connection failed",
                "frontend_url": frontend_url,
                "tests": [],
            }
        except ServiceUnavailableError:
            return {
                "success": False,
                "error": "Playwright service not available",
                "frontend_url": frontend_url,
                "tests": [],
            }
        except Exception as e:
            error_details = self._format_test_frontend_exception(e)
            logger.error("Frontend test error: %s", error_details)
            return {
                "success": False,
                "error": error_details,
                "frontend_url": frontend_url,
                "tests": [],
            }

    async def send_test_message(
        self,
        message: str = "what network scanning tools do we have available?",
        frontend_url: str = ServiceURLs.FRONTEND_LOCAL,
    ) -> Metadata:
        """
        Send test message through frontend using embedded Playwright

        Args:
            message: Message to send
            frontend_url: Frontend URL

        Returns:
            Message sending results with step-by-step details
        """
        try:
            if not await self.is_ready():
                raise ServiceUnavailableError(
                    "Playwright service not available",
                    service="playwright",
                    url=self.base_url,
                )

            result = await self._post_and_parse(
                "send-test-message", {"message": message, "frontend_url": frontend_url}
            )
            logger.info(
                f"Test message sent: '{message}' -> {len(result.get('steps', []))} steps completed"
            )
            return result

        except asyncio.TimeoutError:
            logger.error("Test message timed out after %ss", self.timeout)
            return {
                "success": False,
                "error": f"Test message timed out after {self.timeout}s",
                "message": message,
                "steps": [],
            }
        except aiohttp.ClientConnectorError as e:
            logger.error("Test message connection error: %s", e)
            return {
                "success": False,
                "error": "Playwright service connection failed",
                "message": message,
                "steps": [],
            }
        except ServiceUnavailableError:
            return {
                "success": False,
                "error": "Playwright service not available",
                "message": message,
                "steps": [],
            }
        except Exception as e:
            logger.error("Test message error: %s", e)
            return {"success": False, "error": str(e), "message": message, "steps": []}

    async def capture_screenshot(
        self, url: str, full_page: bool = True, wait_timeout: int = 5000
    ) -> Metadata:
        """
        Capture screenshot of webpage

        Args:
            url: URL to capture
            full_page: Whether to capture full page
            wait_timeout: How long to wait before capture

        Returns:
            Screenshot metadata and status
        """
        try:
            if not await self.is_ready():
                raise RuntimeError("Playwright service not available")

            # This would require adding a screenshot endpoint to playwright-server.js
            # For now, we can use the test-frontend endpoint which includes screenshots
            payload = {"frontend_url": url}

            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with await self.http_client.post(
                f"{self.base_url}/test-frontend", json=payload, timeout=timeout
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    screenshot_info = {
                        "success": result.get("has_screenshot", False),
                        "size": result.get("screenshot_size", 0),
                        "url": url,
                        "timestamp": result.get("timestamp"),
                    }
                    logger.info(
                        f"Screenshot captured: {url} -> {screenshot_info['size']} bytes"
                    )
                    return screenshot_info
                else:
                    error_text = await response.text()
                    logger.error(
                        "Screenshot failed: %s - %s", response.status, error_text
                    )
                    raise RuntimeError(f"Screenshot failed: {response.status}")

        except aiohttp.ClientError as e:
            logger.error("Screenshot HTTP error: %s", e)
            return {
                "success": False,
                "error": f"Connection error: {str(e)}",
                "url": url,
            }
        except Exception as e:
            logger.error("Screenshot error: %s", e)
            return {"success": False, "error": str(e), "url": url}

    async def get_service_status(self) -> Metadata:
        """Get detailed service status"""
        try:
            await self._health_check()

            status = {
                "service": "playwright",
                "status": "healthy" if self._healthy else "unhealthy",
                "container_url": self.base_url,
                "capabilities": [
                    "web_search",
                    "frontend_testing",
                    "message_automation",
                    "screenshot_capture",
                ],
                "ready": self._healthy,
                "integration_type": "embedded_docker",
            }

            if self._healthy:
                # Get additional health info from container
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with await self.http_client.get(
                    f"{self.base_url}/health", timeout=timeout
                ) as response:
                    if response.status == 200:
                        container_health = await response.json()
                        status.update(
                            {
                                "browser_connected": container_health.get(
                                    "browser_connected", False
                                ),
                                "container_timestamp": container_health.get(
                                    "timestamp"
                                ),
                                "uptime": "active",
                            }
                        )

            return status

        except aiohttp.ClientError as e:
            return {
                "service": "playwright",
                "status": "error",
                "error": f"Connection error: {str(e)}",
                "ready": False,
                "integration_type": "embedded_docker",
            }
        except Exception as e:
            return {
                "service": "playwright",
                "status": "error",
                "error": str(e),
                "ready": False,
                "integration_type": "embedded_docker",
            }


# Global service instance (thread-safe)
import asyncio as _asyncio_lock

_playwright_service: Optional[PlaywrightService] = None
_playwright_service_lock = _asyncio_lock.Lock()


async def get_playwright_service() -> PlaywrightService:
    """Get or create the global Playwright service instance (thread-safe)."""
    global _playwright_service

    if _playwright_service is None:
        async with _playwright_service_lock:
            # Double-check after acquiring lock
            if _playwright_service is None:
                # Use correct Playwright container IP address
                container_host = os.getenv("AUTOBOT_BROWSER_SERVICE_HOST")
                if not container_host:
                    raise ValueError(
                        "AUTOBOT_BROWSER_SERVICE_HOST environment variable must be set"
                    )
                _playwright_service = PlaywrightService(container_host=container_host)
                await _playwright_service.initialize()

    return _playwright_service


@asynccontextmanager
async def playwright_service():
    """Context manager for Playwright service"""
    service = await get_playwright_service()
    try:
        yield service
    finally:
        # Keep service alive for reuse
        pass


# Convenience functions for common operations
async def search_web_embedded(query: str, **kwargs) -> Metadata:
    """Convenience function for web search"""
    async with playwright_service() as service:
        return await service.search_web(query, **kwargs)


async def test_frontend_embedded(frontend_url: str = None) -> Metadata:
    """Convenience function for frontend testing"""
    async with playwright_service() as service:
        return await service.test_frontend(frontend_url or ServiceURLs.FRONTEND_LOCAL)


async def send_test_message_embedded(message: str, **kwargs) -> Metadata:
    """Convenience function for sending test messages"""
    async with playwright_service() as service:
        return await service.send_test_message(message, **kwargs)
