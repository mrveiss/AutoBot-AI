# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Playwright API endpoints - Embedded Docker Integration
Provides native API access to containerized Playwright functionality
"""

import logging

import aiohttp
from config import ConfigManager
from constants.network_constants import NetworkConstants
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from services.playwright_service import (
    get_playwright_service,
    playwright_service,
    search_web_embedded,
    send_test_message_embedded,
    test_frontend_embedded,
)

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_client import get_http_client

# Create singleton config instance
config = ConfigManager()

router = APIRouter()
logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str
    search_engine: str = "duckduckgo"
    max_results: int = 5


class TestMessageRequest(BaseModel):
    message: str = "what network scanning tools do we have available?"
    frontend_url: str = config.get_service_url("frontend")


class FrontendTestRequest(BaseModel):
    frontend_url: str = config.get_service_url("frontend")


class ScreenshotRequest(BaseModel):
    url: str
    full_page: bool = True
    wait_timeout: int = 5000


class NavigateRequest(BaseModel):
    url: str
    wait_until: str = "networkidle"
    timeout: int = 30000


class ReloadRequest(BaseModel):
    wait_until: str = "networkidle"


# Browser VM connection
BROWSER_VM_URL = (
    f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}"
)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_playwright_status",
    error_code_prefix="PLAYWRIGHT",
)
@router.get("/status")
async def get_playwright_status():
    """Get Playwright service status and capabilities"""
    try:
        service = await get_playwright_service()
        status = await service.get_service_status()
        return status
    except Exception as e:
        logger.error("Error getting Playwright status: %s", e)
        return {
            "service": "playwright",
            "status": "error",
            "error": str(e),
            "ready": False,
            "integration_type": "embedded_docker",
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="health_check",
    error_code_prefix="PLAYWRIGHT",
)
@router.get("/health")
async def health_check():
    """Health check endpoint for Playwright service"""
    try:
        service = await get_playwright_service()
        is_ready = await service.is_ready()

        return {
            "status": "healthy" if is_ready else "unhealthy",
            "ready": is_ready,
            "service": "playwright_embedded",
            "message": (
                "Playwright service is ready"
                if is_ready
                else "Playwright service unavailable"
            ),
        }
    except Exception as e:
        logger.error("Playwright health check failed: %s", e)
        raise HTTPException(
            status_code=503, detail=f"Playwright service unavailable: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="web_search",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/search")
async def web_search(request: SearchRequest):
    """
    Perform web search using embedded Playwright

    This endpoint provides the same functionality as direct container access
    but integrated into the main API
    """
    try:
        logger.info(
            f"Web search request: '{request.query}' via {request.search_engine}"
        )

        result = await search_web_embedded(
            query=request.query,
            search_engine=request.search_engine,
            max_results=request.max_results,
        )

        if result.get("success", False):
            return result
        else:
            logger.warning(
                "Web search failed: %s", result.get("error", "Unknown error")
            )
            raise HTTPException(
                status_code=500, detail=result.get("error", "Web search failed")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Web search error: %s", e)
        raise HTTPException(status_code=500, detail=f"Web search failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_frontend",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/test-frontend")
async def test_frontend(request: FrontendTestRequest):
    """
    Test frontend functionality using embedded Playwright

    Runs comprehensive tests on the frontend interface
    """
    try:
        logger.info("Frontend test request for: %s", request.frontend_url)

        result = await test_frontend_embedded(request.frontend_url)

        if result.get("success", False):
            return result
        else:
            logger.warning(
                f"Frontend test failed: {result.get('error', 'Unknown error')}"
            )
            raise HTTPException(
                status_code=500, detail=result.get("error", "Frontend test failed")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Frontend test error: %s", e)
        raise HTTPException(status_code=500, detail=f"Frontend test failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_test_message",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/send-test-message")
async def send_test_message(request: TestMessageRequest):
    """
    Send test message through frontend using embedded Playwright

    Automates message sending for testing chat functionality
    """
    try:
        logger.info(
            f"Test message request: '{request.message}' to {request.frontend_url}"
        )

        result = await send_test_message_embedded(
            message=request.message, frontend_url=request.frontend_url
        )

        if result.get("success", False):
            return result
        else:
            logger.warning(
                f"Test message failed: {result.get('error', 'Unknown error')}"
            )
            raise HTTPException(
                status_code=500, detail=result.get("error", "Test message failed")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Test message error: %s", e)
        raise HTTPException(status_code=500, detail=f"Test message failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="capture_screenshot",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/screenshot")
async def capture_screenshot(request: ScreenshotRequest):
    """
    Capture screenshot of webpage using embedded Playwright

    Returns metadata about captured screenshot
    """
    try:
        logger.info("Screenshot request for: %s", request.url)

        async with playwright_service() as service:
            result = await service.capture_screenshot(
                url=request.url,
                full_page=request.full_page,
                wait_timeout=request.wait_timeout,
            )

        if result.get("success", False):
            return result
        else:
            logger.warning(
                "Screenshot failed: %s", result.get("error", "Unknown error")
            )
            raise HTTPException(
                status_code=500, detail=result.get("error", "Screenshot capture failed")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Screenshot error: %s", e)
        raise HTTPException(status_code=500, detail=f"Screenshot failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="quick_automation_test",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/automation/quick-test")
async def quick_automation_test(background_tasks: BackgroundTasks):
    """
    Quick automation test to verify all Playwright functionality

    Runs in background and returns immediate response
    """

    async def run_automation_tests():
        """Background task to run comprehensive automation tests"""
        try:
            logger.info("Starting quick automation test suite")

            # Test 1: Service health
            service = await get_playwright_service()
            health = await service.get_service_status()
            logger.info("Service health: %s", health.get("status"))

            # Test 2: Web search
            search_result = await search_web_embedded(
                "AutoBot system test", max_results=2
            )
            logger.info(
                "Search test: %s results", len(search_result.get("results", []))
            )

            # Test 3: Frontend test
            frontend_result = await test_frontend_embedded()
            test_count = len(frontend_result.get("tests", []))
            passed = len(
                [
                    t
                    for t in frontend_result.get("tests", [])
                    if t.get("status") == "PASS"
                ]
            )
            logger.info("Frontend test: %s/%s tests passed", passed, test_count)

            logger.info("Quick automation test suite completed successfully")

        except Exception as e:
            logger.error("Automation test suite failed: %s", e)

    # Start tests in background
    background_tasks.add_task(run_automation_tests)

    return {
        "status": "started",
        "message": "Quick automation test suite started in background",
        "check_logs": "Monitor logs for detailed results",
        "tests": [
            "service_health_check",
            "web_search_functionality",
            "frontend_interaction_test",
        ],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="navigate",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/navigate")
async def navigate_to_url(request: NavigateRequest):
    """
    Navigate to a URL using Playwright on Browser VM

    Forwards navigation request to Browser VM (NetworkConstants.BROWSER_VM_IP)
    """
    try:
        logger.info("Navigate request: %s", request.url)

        http_client = get_http_client()
        async with await http_client.post(
            f"{BROWSER_VM_URL}/navigate",
            json={
                "url": request.url,
                "wait_until": request.wait_until,
                "timeout": request.timeout,
            },
            timeout=aiohttp.ClientTimeout(total=request.timeout / 1000 + 5),
        ) as response:
            result = await response.json()

            if response.status == 200:
                logger.info("Navigation successful: %s", result.get("url"))
                return result
            else:
                logger.error("Navigation failed: %s", result)
                raise HTTPException(
                    status_code=response.status,
                    detail=result.get("error", "Navigation failed"),
                )

    except aiohttp.ClientError as e:
        logger.error("Browser VM connection error: %s", e)
        raise HTTPException(status_code=503, detail=f"Browser VM unavailable: {str(e)}")
    except Exception as e:
        logger.error("Navigation error: %s", e)
        raise HTTPException(status_code=500, detail=f"Navigation failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reload",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/reload")
async def reload_page(request: ReloadRequest):
    """
    Reload the current page using Playwright on Browser VM

    Forwards reload request to Browser VM (NetworkConstants.BROWSER_VM_IP)
    """
    try:
        logger.info("Reload request")

        http_client = get_http_client()
        async with await http_client.post(
            f"{BROWSER_VM_URL}/reload",
            json={"wait_until": request.wait_until},
            timeout=aiohttp.ClientTimeout(total=35),
        ) as response:
            result = await response.json()

            if response.status == 200:
                logger.info("Reload successful")
                return result
            else:
                logger.error("Reload failed: %s", result)
                raise HTTPException(
                    status_code=response.status,
                    detail=result.get("error", "Reload failed"),
                )

    except aiohttp.ClientError as e:
        logger.error("Browser VM connection error: %s", e)
        raise HTTPException(status_code=503, detail=f"Browser VM unavailable: {str(e)}")
    except Exception as e:
        logger.error("Reload error: %s", e)
        raise HTTPException(status_code=500, detail=f"Reload failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="go_back",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/back")
async def go_back():
    """
    Navigate back in browser history using Playwright on Browser VM

    Forwards back navigation request to Browser VM (NetworkConstants.BROWSER_VM_IP)
    Issue #552: Added missing endpoint for frontend PopoutChromiumBrowser.vue
    """
    try:
        logger.info("Back navigation request")

        http_client = get_http_client()
        async with await http_client.post(
            f"{BROWSER_VM_URL}/back",
            json={},
            timeout=aiohttp.ClientTimeout(total=35),
        ) as response:
            result = await response.json()

            if response.status == 200:
                logger.info("Back navigation successful: %s", result.get("final_url"))
                return result
            else:
                logger.error("Back navigation failed: %s", result)
                raise HTTPException(
                    status_code=response.status,
                    detail=result.get("error", "Back navigation failed"),
                )

    except aiohttp.ClientError as e:
        logger.error("Browser VM connection error: %s", e)
        raise HTTPException(status_code=503, detail=f"Browser VM unavailable: {str(e)}")
    except Exception as e:
        logger.error("Back navigation error: %s", e)
        raise HTTPException(status_code=500, detail=f"Back navigation failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="go_forward",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/forward")
async def go_forward():
    """
    Navigate forward in browser history using Playwright on Browser VM

    Forwards forward navigation request to Browser VM (NetworkConstants.BROWSER_VM_IP)
    Issue #552: Added missing endpoint for frontend PopoutChromiumBrowser.vue
    """
    try:
        logger.info("Forward navigation request")

        http_client = get_http_client()
        async with await http_client.post(
            f"{BROWSER_VM_URL}/forward",
            json={},
            timeout=aiohttp.ClientTimeout(total=35),
        ) as response:
            result = await response.json()

            if response.status == 200:
                logger.info(
                    "Forward navigation successful: %s", result.get("final_url")
                )
                return result
            else:
                logger.error("Forward navigation failed: %s", result)
                raise HTTPException(
                    status_code=response.status,
                    detail=result.get("error", "Forward navigation failed"),
                )

    except aiohttp.ClientError as e:
        logger.error("Browser VM connection error: %s", e)
        raise HTTPException(status_code=503, detail=f"Browser VM unavailable: {str(e)}")
    except Exception as e:
        logger.error("Forward navigation error: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Forward navigation failed: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="worker_status",
    error_code_prefix="PLAYWRIGHT",
)
@router.get("/worker-status")
async def get_worker_status():
    """
    Get browser worker connectivity status from Browser VM (#1130)

    Proxies to Browser VM /status endpoint which checks the persistent navPage.
    """
    try:
        http_client = get_http_client()
        async with await http_client.get(
            f"{BROWSER_VM_URL}/status",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            result = await response.json()
            logger.info("Worker status: %s", result.get("status"))
            return result
    except aiohttp.ClientError as e:
        logger.warning("Browser VM unreachable: %s", e)
        return {
            "status": "disconnected",
            "browser_connected": False,
            "page_open": False,
        }
    except Exception as e:
        logger.error("Worker status error: %s", e)
        return {"status": "error", "browser_connected": False, "page_open": False}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="worker_screenshot",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/worker-screenshot")
async def take_worker_screenshot():
    """
    Take screenshot of the persistent navigation page on Browser VM (#1130)

    Unlike /screenshot which takes a fresh-page screenshot for a given URL,
    this returns a screenshot of the current state of the persistent navPage.
    """
    try:
        http_client = get_http_client()
        async with await http_client.post(
            f"{BROWSER_VM_URL}/screenshot",
            json={},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            result = await response.json()
            if response.status == 200:
                logger.info("Worker screenshot captured")
                return result
            else:
                logger.error("Worker screenshot failed: %s", result)
                raise HTTPException(
                    status_code=response.status,
                    detail=result.get("error", "Screenshot failed"),
                )
    except aiohttp.ClientError as e:
        logger.error("Browser VM connection error: %s", e)
        raise HTTPException(status_code=503, detail=f"Browser VM unavailable: {str(e)}")
    except Exception as e:
        logger.error("Worker screenshot error: %s", e)
        raise HTTPException(status_code=500, detail=f"Screenshot failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_capabilities",
    error_code_prefix="PLAYWRIGHT",
)
@router.get("/capabilities")
async def get_capabilities():
    """Get Playwright service capabilities and features"""
    return {
        "service": "playwright_embedded",
        "integration": "docker_container",
        "capabilities": {
            "web_search": {
                "engines": ["duckduckgo"],
                "max_results": 10,
                "description": "Automated web search with result extraction",
            },
            "frontend_testing": {
                "navigation": True,
                "interaction": True,
                "screenshot": True,
                "description": "Comprehensive frontend functionality testing",
            },
            "message_automation": {
                "send_messages": True,
                "workflow_testing": True,
                "response_monitoring": True,
                "description": "Automated message sending and response monitoring",
            },
            "screenshot_capture": {
                "full_page": True,
                "element_specific": False,
                "formats": ["png"],
                "description": "Webpage screenshot capture",
            },
        },
        "endpoints": [
            "/api/playwright/status",
            "/api/playwright/health",
            "/api/playwright/search",
            "/api/playwright/test-frontend",
            "/api/playwright/send-test-message",
            "/api/playwright/screenshot",
            "/api/playwright/automation/quick-test",
            "/api/playwright/navigate",
            "/api/playwright/reload",
            "/api/playwright/back",
            "/api/playwright/forward",
        ],
        "container_integration": {
            "type": "embedded",
            "container_port": NetworkConstants.BROWSER_SERVICE_PORT,
            "health_monitoring": True,
            "auto_reconnect": True,
            "description": "Docker container with native API integration",
        },
    }
