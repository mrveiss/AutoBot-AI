# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Playwright API endpoints - Embedded Docker Integration
Provides native API access to containerized Playwright functionality
"""

import base64

import aiohttp
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from api.schemas_code import (
    AiProposeRegionsResponse,
    FrontendTestRequest,
    PageRegion,
    PlaywrightBrowserActionResponse,
    PlaywrightCapabilitiesResponse,
    PlaywrightInteractRequest,
    PlaywrightNavigateRequest,
    PlaywrightQuickTestResponse,
    PlaywrightReloadRequest,
    PlaywrightScreenshotRequest,
    PlaywrightSearchRequest,
    PlaywrightStatusResponse,
    PlaywrightWorkerStatusResponse,
    SnapshotWithRegionsRequest,
    SnapshotWithRegionsResponse,
    TestMessageRequest,
)
from api.schemas_common import DataResponse
from api.schemas_system import PlaywrightEmbeddedResultResponse
from api.system_health import ComponentHealth, register_health_probe
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from constants.network_constants import NetworkConstants
from research_browser_manager import get_research_browser_manager
from services.playwright_service import (
    get_playwright_service,
    playwright_service,
    search_web_embedded,
    send_test_message_embedded,
    test_frontend_embedded,
)
from services.web_pipeline.snapshot import AccessibilitySnapshot

router = APIRouter(dependencies=[Depends(check_admin_permission)])
logger = get_logger(__name__)


# Browser VM connection
BROWSER_VM_URL = f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}"


@router.get("/status", response_model=PlaywrightStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_playwright_status",
    error_code_prefix="PLAYWRIGHT",
)
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
            "error": "Internal server error",
            "ready": False,
            "integration_type": "embedded_docker",
        }


@register_health_probe("playwright")
async def probe_playwright(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for playwright module.

    Lightweight check: inspect the module-level singleton without forcing
    creation (which would require env-var resolution and a network probe).
    ``ok`` if already initialized; ``degraded`` if not yet initialized.
    """
    try:
        from services import playwright_service as _ps_mod

        if getattr(_ps_mod, "_playwright_service", None) is None:
            return ComponentHealth(
                name="playwright",
                status="degraded",
                detail="service not yet initialized",
            )
        return ComponentHealth(name="playwright", status="ok")
    except Exception as exc:
        return ComponentHealth(
            name="playwright",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


@router.post("/search", response_model=PlaywrightEmbeddedResultResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="web_search",
    error_code_prefix="PLAYWRIGHT",
)
async def web_search(request: PlaywrightSearchRequest):
    """
    Perform web search using embedded Playwright

    This endpoint provides the same functionality as direct container access
    but integrated into the main API
    """
    try:
        logger.info(f"Web search request: '{request.query}' via {request.search_engine}")

        result = await search_web_embedded(
            query=request.query,
            search_engine=request.search_engine,
            max_results=request.max_results,
        )

        if result.get("success", False):
            return result
        else:
            logger.warning("Web search failed: %s", result.get("error", "Unknown error"))
            raise HTTPException(status_code=500, detail=result.get("error", "Web search failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Web search error: %s", e)
        raise HTTPException(status_code=500, detail="Web search failed")


@router.post("/test-frontend", response_model=PlaywrightEmbeddedResultResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_frontend",
    error_code_prefix="PLAYWRIGHT",
)
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
            logger.warning(f"Frontend test failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(status_code=500, detail=result.get("error", "Frontend test failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Frontend test error: %s", e)
        raise HTTPException(status_code=500, detail="Frontend test failed")


@router.post("/send-test-message", response_model=PlaywrightEmbeddedResultResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_test_message",
    error_code_prefix="PLAYWRIGHT",
)
async def send_test_message(request: TestMessageRequest):
    """
    Send test message through frontend using embedded Playwright

    Automates message sending for testing chat functionality
    """
    try:
        logger.info(f"Test message request: '{request.message}' to {request.frontend_url}")

        result = await send_test_message_embedded(message=request.message, frontend_url=request.frontend_url)

        if result.get("success", False):
            return result
        else:
            logger.warning(f"Test message failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(status_code=500, detail=result.get("error", "Test message failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Test message error: %s", e)
        raise HTTPException(status_code=500, detail="Test message failed")


@router.post("/screenshot", response_model=PlaywrightEmbeddedResultResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="capture_screenshot",
    error_code_prefix="PLAYWRIGHT",
)
async def capture_screenshot(request: PlaywrightScreenshotRequest):
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
            logger.warning("Screenshot failed: %s", result.get("error", "Unknown error"))
            raise HTTPException(status_code=500, detail=result.get("error", "Screenshot capture failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Screenshot error: %s", e)
        raise HTTPException(status_code=500, detail="Screenshot failed")


@router.post("/automation/quick-test", response_model=PlaywrightQuickTestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="quick_automation_test",
    error_code_prefix="PLAYWRIGHT",
)
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
            search_result = await search_web_embedded("AutoBot system test", max_results=2)
            logger.info("Search test: %s results", len(search_result.get("results", [])))

            # Test 3: Frontend test
            frontend_result = await test_frontend_embedded()
            test_count = len(frontend_result.get("tests", []))
            passed = len([t for t in frontend_result.get("tests", []) if t.get("status") == "PASS"])
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


@router.post("/navigate", response_model=PlaywrightBrowserActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="navigate_to_url",
    error_code_prefix="PLAYWRIGHT",
)
async def navigate_to_url(request: PlaywrightNavigateRequest):
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
        raise HTTPException(status_code=503, detail="Browser VM unavailable")
    except Exception as e:
        logger.error("Navigation error: %s", e)
        raise HTTPException(status_code=500, detail="Navigation failed")


@router.post("/reload", response_model=PlaywrightBrowserActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reload_page",
    error_code_prefix="PLAYWRIGHT",
)
async def reload_page(request: PlaywrightReloadRequest):
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
        raise HTTPException(status_code=503, detail="Browser VM unavailable")
    except Exception as e:
        logger.error("Reload error: %s", e)
        raise HTTPException(status_code=500, detail="Reload failed")


@router.post("/back", response_model=PlaywrightBrowserActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="go_back",
    error_code_prefix="PLAYWRIGHT",
)
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
        raise HTTPException(status_code=503, detail="Browser VM unavailable")
    except Exception as e:
        logger.error("Back navigation error: %s", e)
        raise HTTPException(status_code=500, detail="Back navigation failed")


@router.post("/forward", response_model=PlaywrightBrowserActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="go_forward",
    error_code_prefix="PLAYWRIGHT",
)
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
                logger.info("Forward navigation successful: %s", result.get("final_url"))
                return result
            else:
                logger.error("Forward navigation failed: %s", result)
                raise HTTPException(
                    status_code=response.status,
                    detail=result.get("error", "Forward navigation failed"),
                )

    except aiohttp.ClientError as e:
        logger.error("Browser VM connection error: %s", e)
        raise HTTPException(status_code=503, detail="Browser VM unavailable")
    except Exception as e:
        logger.error("Forward navigation error: %s", e)
        raise HTTPException(status_code=500, detail="Forward navigation failed")


@router.get("/worker-status", response_model=PlaywrightWorkerStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_worker_status",
    error_code_prefix="PLAYWRIGHT",
)
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
            data = await response.json()
            logger.info("Worker status: %s", data.get("status"))
            # Browser VM returns null fields when no session is connected;
            # PlaywrightWorkerStatusResponse.browser_connected is non-nullable
            # so coerce to bool here (None -> False).
            page_open = data.get("page_open")
            return {
                "status": str(data.get("status") or "unknown"),
                "browser_connected": bool(data.get("browser_connected")),
                "page_open": page_open if isinstance(page_open, bool) else None,
            }
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


@router.post("/worker-screenshot", response_model=PlaywrightBrowserActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="take_worker_screenshot",
    error_code_prefix="PLAYWRIGHT",
)
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
        raise HTTPException(status_code=503, detail="Browser VM unavailable")
    except Exception as e:
        logger.error("Worker screenshot error: %s", e)
        raise HTTPException(status_code=500, detail="Screenshot failed")


@router.post("/interact", response_model=PlaywrightBrowserActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="interact_with_page",
    error_code_prefix="PLAYWRIGHT",
)
async def interact_with_page(request: PlaywrightInteractRequest):
    """Proxy interactive browser actions to Browser VM (#1416)"""
    allowed = {"click", "scroll", "type", "hover"}
    if request.action not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action: {request.action}. Allowed: {', '.join(sorted(allowed))}",
        )
    try:
        payload: dict = {}
        if request.action in ("click", "hover"):
            if request.x is None or request.y is None:
                raise HTTPException(status_code=400, detail="x and y required")
            payload = {"x": request.x, "y": request.y}
        elif request.action == "scroll":
            payload = {"deltaX": request.deltaX, "deltaY": request.deltaY}
        elif request.action == "type":
            if not request.text:
                raise HTTPException(status_code=400, detail="text required")
            payload = {"text": request.text}

        http_client = get_http_client()
        async with await http_client.post(
            f"{BROWSER_VM_URL}/{request.action}",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            result = await response.json()
            if response.status == 200:
                return result
            else:
                raise HTTPException(
                    status_code=response.status,
                    detail=result.get("error", "Interaction failed"),
                )
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        logger.error("Browser VM connection error: %s", e)
        raise HTTPException(status_code=503, detail="Browser VM unavailable")
    except Exception as e:
        logger.error("Interact error: %s", e)
        raise HTTPException(status_code=500, detail="Interaction failed")


@router.get("/capabilities", response_model=PlaywrightCapabilitiesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_capabilities",
    error_code_prefix="PLAYWRIGHT",
)
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
            "/api/playwright/interact",
        ],
        "container_integration": {
            "type": "embedded",
            "container_port": NetworkConstants.BROWSER_SERVICE_PORT,
            "health_monitoring": True,
            "auto_reconnect": True,
            "description": "Docker container with native API integration",
        },
    }


# JavaScript used by snapshot_with_regions to walk the DOM and collect regions.
_JS_COLLECT_REGIONS = """
() => {
  const results = [];
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  while (walker.nextNode()) {
    const el = walker.currentNode;
    const rect = el.getBoundingClientRect();
    const area = rect.width * rect.height;
    if (area < 20) continue;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
    if (rect.width === 0 || rect.height === 0) continue;
    const key = `${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)},${Math.round(rect.height)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const textPreview = (el.textContent || '').trim().slice(0, 80);
    if (!textPreview && !el.getAttribute('aria-label') && !el.getAttribute('alt')) continue;
    let selector = el.tagName.toLowerCase();
    if (el.id) selector = `#${el.id}`;
    else if (el.className && typeof el.className === 'string') {
      const cls = el.className.trim().split(/\\s+/)[0];
      if (cls) selector = `.${cls}`;
    }
    let xpath = '';
    let node = el;
    while (node && node !== document.body) {
      const tag = node.tagName.toLowerCase();
      const idx = Array.from(node.parentElement?.children || [])
        .filter(c => c.tagName === node.tagName).indexOf(node) + 1;
      xpath = `/${tag}[${idx}]${xpath}`;
      node = node.parentElement;
    }
    xpath = `/html/body${xpath}`;
    results.push({
      selector,
      xpath,
      rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
      textPreview: textPreview || el.getAttribute('aria-label') || el.getAttribute('alt') || '',
      role
    });
  }
  return results.slice(0, 200);
}
"""


@router.post(
    "/snapshot-with-regions",
    response_model=DataResponse[SnapshotWithRegionsResponse],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="snapshot_with_regions",
    error_code_prefix="PLAYWRIGHT",
)
async def snapshot_with_regions(request: SnapshotWithRegionsRequest):
    """
    Take a screenshot of a research browser session and return detected page regions.

    Returns a base64 PNG screenshot together with a list of interactive DOM regions
    (selector, xpath, bounding rect, text preview, ARIA role) so the frontend can
    overlay clickable highlights for scraping-template creation. (#5136)
    """
    manager = get_research_browser_manager()
    session = manager.get_session(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.page is None:
        raise HTTPException(status_code=400, detail="Browser page not initialized")

    logger.info("snapshot-with-regions: session=%s goal=%r", request.session_id, request.goal)

    screenshot_bytes: bytes = await session.page.screenshot(type="png")
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    raw_regions: list = await session.page.evaluate(_JS_COLLECT_REGIONS)

    viewport_size = session.page.viewport_size or {}

    regions = [
        {
            "selector": r.get("selector", ""),
            "xpath": r.get("xpath", ""),
            "rect": r.get("rect", {"x": 0, "y": 0, "w": 0, "h": 0}),
            "text_preview": r.get("textPreview", ""),
            "role": r.get("role", ""),
        }
        for r in raw_regions
    ]

    # Capture ARIA accessibility tree for LLM consumption (#5136 Phase 1, closes #5138)
    accessibility_text = ""
    try:
        snap = AccessibilitySnapshot()
        tree = await snap.capture(session.page)
        if tree is not None:
            accessibility_text = snap.to_text(tree)
    except Exception as exc:
        logger.warning("snapshot-with-regions: accessibility capture failed: %s", exc)

    logger.info(
        "snapshot-with-regions: captured %d regions for session %s (accessibility_text=%d chars)",
        len(regions),
        request.session_id,
        len(accessibility_text),
    )

    return DataResponse(
        data=SnapshotWithRegionsResponse(
            screenshot=screenshot_b64,
            regions=regions,
            viewport=dict(viewport_size),
            accessibility_text=accessibility_text,
        )
    )


_AI_PROPOSE_SYSTEM_PROMPT = (
    "You are a web scraping assistant. Given a screenshot and a list of page regions,"
    " identify which regions are most relevant to the user's data extraction goal."
    ' Return a JSON array of objects with "selector" and "label" fields.'
    " Only include regions that are clearly relevant."
    " Return valid JSON only — no markdown fences, no commentary."
)

_AI_PROPOSE_USER_TEMPLATE = """Goal: {goal}

Page regions (selector → text preview):
{regions_text}

Return a JSON array like: [{{"selector": "...", "label": "..."}}]"""


@router.post(
    "/ai-propose-regions",
    response_model=DataResponse[AiProposeRegionsResponse],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="ai_propose_regions",
    error_code_prefix="PLAYWRIGHT",
)
async def ai_propose_regions(request: SnapshotWithRegionsRequest):
    """
    Use an AI vision model to propose relevant page regions for a given extraction goal.

    Takes a snapshot of the current browser session, then asks the LLM to identify
    which regions match the user's goal. Returns matched PageRegion objects with
    AI-generated labels. (MVA-1380 / GH#5136 Phase 3)
    """
    import json as _json

    from modern_ai_integration import get_modern_ai_integration

    manager = get_research_browser_manager()
    session = manager.get_session(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.page is None:
        raise HTTPException(status_code=400, detail="Browser page not initialized")

    logger.info("ai-propose-regions: session=%s goal=%r", request.session_id, request.goal)

    # 1. Take snapshot + regions (reuse snapshot logic inline)
    screenshot_bytes: bytes = await session.page.screenshot(type="png")
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    raw_regions: list = await session.page.evaluate(_JS_COLLECT_REGIONS)
    regions = [
        {
            "selector": r.get("selector", ""),
            "xpath": r.get("xpath", ""),
            "rect": r.get("rect", {"x": 0, "y": 0, "w": 0, "h": 0}),
            "text_preview": r.get("textPreview", ""),
            "role": r.get("role", ""),
        }
        for r in raw_regions
    ]

    # 2. Build DOM text summary for LLM
    regions_text = "\n".join(f"  {r['selector']}: {r['text_preview'][:80]}" for r in regions[:80] if r["text_preview"])

    goal = request.goal or "extract useful data from this page"
    prompt = _AI_PROPOSE_USER_TEMPLATE.format(goal=goal, regions_text=regions_text)

    # 3. Call LLM with screenshot as vision attachment
    ai = get_modern_ai_integration()
    response = await ai.process_with_ai(
        provider=ai._select_vision_provider(None),
        prompt=prompt,
        images=[screenshot_b64],
        system_message=_AI_PROPOSE_SYSTEM_PROMPT,
        task_type="region_proposal",
    )

    # 4. Parse LLM output — expect [{selector, label}]
    proposed_pairs: list = []
    try:
        content = response.content.strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        proposed_pairs = _json.loads(content)
        if not isinstance(proposed_pairs, list):
            proposed_pairs = []
    except Exception as exc:
        logger.warning("ai-propose-regions: LLM JSON parse failed: %s", exc)

    # 5. Match proposed selectors back to full region objects
    selector_to_region = {r["selector"]: r for r in regions}
    proposed_regions: list[PageRegion] = []
    seen_selectors: set[str] = set()
    for pair in proposed_pairs:
        sel = pair.get("selector", "")
        label = pair.get("label", "")
        if not sel or sel in seen_selectors:
            continue
        seen_selectors.add(sel)
        region = selector_to_region.get(sel)
        if region:
            proposed_regions.append(
                PageRegion(
                    selector=region["selector"],
                    xpath=region["xpath"],
                    rect=region["rect"],
                    text_preview=label or region["text_preview"],
                    role=region["role"],
                )
            )

    logger.info(
        "ai-propose-regions: proposed %d regions for session %s",
        len(proposed_regions),
        request.session_id,
    )

    return DataResponse(data=AiProposeRegionsResponse(proposed_regions=proposed_regions))
