"""
Embedded Playwright Service
Integrates Docker-based Playwright into the main AutoBot application
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
import aiohttp
import json
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class PlaywrightService:
    """
    Embedded Playwright service that communicates with Docker container
    but feels like a native part of the application
    """

    def __init__(
        self,
        container_host: str = "localhost",
        container_port: int = 3000,
        timeout: int = 30
    ):
        self.base_url = f"http://{container_host}:{container_port}"
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
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
        if self._session is None:
            # Create HTTP session with proper timeout and error handling
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
            
        # Check if container is healthy
        await self._health_check()
        logger.info(f"Playwright service initialized at {self.base_url}")

    async def cleanup(self):
        """Cleanup resources"""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Playwright service cleaned up")

    async def _health_check(self) -> bool:
        """Check if Playwright container is healthy"""
        try:
            if not self._session:
                await self.initialize()
                
            async with self._session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    self._healthy = health_data.get("status") == "healthy"
                    logger.debug(f"Playwright health check: {health_data}")
                    return self._healthy
                else:
                    logger.warning(f"Playwright health check failed: {response.status}")
                    self._healthy = False
                    return False
                    
        except Exception as e:
            logger.error(f"Playwright health check error: {e}")
            self._healthy = False
            return False

    async def is_ready(self) -> bool:
        """Check if service is ready for requests"""
        if not self._healthy:
            await self._health_check()
        return self._healthy

    async def search_web(
        self, 
        query: str, 
        search_engine: str = "duckduckgo",
        max_results: int = 5
    ) -> Dict[str, Any]:
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
                raise RuntimeError("Playwright service not available")

            payload = {
                "query": query,
                "search_engine": search_engine,
                "max_results": max_results
            }

            async with self._session.post(f"{self.base_url}/search", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Web search completed: '{query}' -> {len(result.get('results', []))} results")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Search failed: {response.status} - {error_text}")
                    raise RuntimeError(f"Search failed: {response.status}")
                    
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "results": []
            }

    async def test_frontend(self, frontend_url: str = "http://localhost:5173") -> Dict[str, Any]:
        """
        Test frontend functionality using embedded Playwright
        
        Args:
            frontend_url: URL of frontend to test
            
        Returns:
            Test results with detailed analysis
        """
        try:
            if not await self.is_ready():
                raise RuntimeError("Playwright service not available")

            payload = {"frontend_url": frontend_url}

            async with self._session.post(f"{self.base_url}/test-frontend", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Frontend test completed: {result.get('summary', {})}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Frontend test failed: {response.status} - {error_text}")
                    raise RuntimeError(f"Frontend test failed: {response.status}")
                    
        except Exception as e:
            import traceback
            error_details = f"Exception: {type(e).__name__}: {str(e)}"
            if hasattr(e, '__cause__') and e.__cause__:
                error_details += f" | Caused by: {e.__cause__}"
            error_details += f" | Traceback: {traceback.format_exc()[-500:]}"  # Last 500 chars
            logger.error(f"Frontend test error: {error_details}")
            return {
                "success": False,
                "error": error_details,
                "frontend_url": frontend_url,
                "tests": []
            }

    async def send_test_message(
        self, 
        message: str = "what network scanning tools do we have available?",
        frontend_url: str = "http://localhost:5173"
    ) -> Dict[str, Any]:
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
                raise RuntimeError("Playwright service not available")

            payload = {
                "message": message,
                "frontend_url": frontend_url
            }

            async with self._session.post(f"{self.base_url}/send-test-message", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Test message sent: '{message}' -> {len(result.get('steps', []))} steps completed")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Test message failed: {response.status} - {error_text}")
                    raise RuntimeError(f"Test message failed: {response.status}")
                    
        except Exception as e:
            logger.error(f"Test message error: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": message,
                "steps": []
            }

    async def capture_screenshot(
        self, 
        url: str, 
        full_page: bool = True,
        wait_timeout: int = 5000
    ) -> Dict[str, Any]:
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

            async with self._session.post(f"{self.base_url}/test-frontend", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    screenshot_info = {
                        "success": result.get("has_screenshot", False),
                        "size": result.get("screenshot_size", 0),
                        "url": url,
                        "timestamp": result.get("timestamp")
                    }
                    logger.info(f"Screenshot captured: {url} -> {screenshot_info['size']} bytes")
                    return screenshot_info
                else:
                    error_text = await response.text()
                    logger.error(f"Screenshot failed: {response.status} - {error_text}")
                    raise RuntimeError(f"Screenshot failed: {response.status}")
                    
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return {
                "success": False,
                "error": str(e),
                "url": url
            }

    async def get_service_status(self) -> Dict[str, Any]:
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
                    "screenshot_capture"
                ],
                "ready": self._healthy,
                "integration_type": "embedded_docker"
            }
            
            if self._healthy:
                # Get additional health info from container
                async with self._session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        container_health = await response.json()
                        status.update({
                            "browser_connected": container_health.get("browser_connected", False),
                            "container_timestamp": container_health.get("timestamp"),
                            "uptime": "active"
                        })
                        
            return status
            
        except Exception as e:
            return {
                "service": "playwright",
                "status": "error", 
                "error": str(e),
                "ready": False,
                "integration_type": "embedded_docker"
            }


# Global service instance
_playwright_service: Optional[PlaywrightService] = None


async def get_playwright_service() -> PlaywrightService:
    """Get or create the global Playwright service instance"""
    global _playwright_service
    
    if _playwright_service is None:
        # Use correct Playwright container IP address
        _playwright_service = PlaywrightService(container_host="172.16.168.25")
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
async def search_web_embedded(query: str, **kwargs) -> Dict[str, Any]:
    """Convenience function for web search"""
    async with playwright_service() as service:
        return await service.search_web(query, **kwargs)


async def test_frontend_embedded(frontend_url: str = None) -> Dict[str, Any]:
    """Convenience function for frontend testing"""
    async with playwright_service() as service:
        return await service.test_frontend(frontend_url or "http://localhost:5173")


async def send_test_message_embedded(message: str, **kwargs) -> Dict[str, Any]:
    """Convenience function for sending test messages"""
    async with playwright_service() as service:
        return await service.send_test_message(message, **kwargs)