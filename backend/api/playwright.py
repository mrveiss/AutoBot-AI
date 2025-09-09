"""
Playwright API endpoints - Embedded Docker Integration
Provides native API access to containerized Playwright functionality
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from src.config_helper import cfg
from backend.services.playwright_service import (
    get_playwright_service,
    playwright_service,
    search_web_embedded,
    test_frontend_embedded,
    send_test_message_embedded
)

router = APIRouter()
logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str
    search_engine: str = "duckduckgo"
    max_results: int = 5


class TestMessageRequest(BaseModel):
    message: str = "what network scanning tools do we have available?"
    frontend_url: str = cfg.get_service_url('frontend')


class FrontendTestRequest(BaseModel):
    frontend_url: str = cfg.get_service_url('frontend')


class ScreenshotRequest(BaseModel):
    url: str
    full_page: bool = True
    wait_timeout: int = 5000


@router.get("/status")
async def get_playwright_status():
    """Get Playwright service status and capabilities"""
    try:
        service = await get_playwright_service()
        status = await service.get_service_status()
        return status
    except Exception as e:
        logger.error(f"Error getting Playwright status: {e}")
        return {
            "service": "playwright",
            "status": "error",
            "error": str(e),
            "ready": False,
            "integration_type": "embedded_docker"
        }


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
            "message": "Playwright service is ready" if is_ready else "Playwright service unavailable"
        }
    except Exception as e:
        logger.error(f"Playwright health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Playwright service unavailable: {str(e)}")


@router.post("/search")
async def web_search(request: SearchRequest):
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
            max_results=request.max_results
        )
        
        if result.get("success", False):
            return result
        else:
            logger.warning(f"Web search failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=500, 
                detail=result.get('error', 'Web search failed')
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Web search error: {e}")
        raise HTTPException(status_code=500, detail=f"Web search failed: {str(e)}")


@router.post("/test-frontend")
async def test_frontend(request: FrontendTestRequest):
    """
    Test frontend functionality using embedded Playwright
    
    Runs comprehensive tests on the frontend interface
    """
    try:
        logger.info(f"Frontend test request for: {request.frontend_url}")
        
        result = await test_frontend_embedded(request.frontend_url)
        
        if result.get("success", False):
            return result
        else:
            logger.warning(f"Frontend test failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=500,
                detail=result.get('error', 'Frontend test failed')
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Frontend test error: {e}")
        raise HTTPException(status_code=500, detail=f"Frontend test failed: {str(e)}")


@router.post("/send-test-message")
async def send_test_message(request: TestMessageRequest):
    """
    Send test message through frontend using embedded Playwright
    
    Automates message sending for testing chat functionality
    """
    try:
        logger.info(f"Test message request: '{request.message}' to {request.frontend_url}")
        
        result = await send_test_message_embedded(
            message=request.message,
            frontend_url=request.frontend_url
        )
        
        if result.get("success", False):
            return result
        else:
            logger.warning(f"Test message failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=500,
                detail=result.get('error', 'Test message failed')
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test message error: {e}")
        raise HTTPException(status_code=500, detail=f"Test message failed: {str(e)}")


@router.post("/screenshot")
async def capture_screenshot(request: ScreenshotRequest):
    """
    Capture screenshot of webpage using embedded Playwright
    
    Returns metadata about captured screenshot
    """
    try:
        logger.info(f"Screenshot request for: {request.url}")
        
        async with playwright_service() as service:
            result = await service.capture_screenshot(
                url=request.url,
                full_page=request.full_page,
                wait_timeout=request.wait_timeout
            )
            
        if result.get("success", False):
            return result
        else:
            logger.warning(f"Screenshot failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=500,
                detail=result.get('error', 'Screenshot capture failed')
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        raise HTTPException(status_code=500, detail=f"Screenshot failed: {str(e)}")


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
            logger.info(f"Service health: {health.get('status')}")
            
            # Test 2: Web search
            search_result = await search_web_embedded("AutoBot system test", max_results=2)
            logger.info(f"Search test: {len(search_result.get('results', []))} results")
            
            # Test 3: Frontend test
            frontend_result = await test_frontend_embedded()
            test_count = len(frontend_result.get('tests', []))
            passed = len([t for t in frontend_result.get('tests', []) if t.get('status') == 'PASS'])
            logger.info(f"Frontend test: {passed}/{test_count} tests passed")
            
            logger.info("Quick automation test suite completed successfully")
            
        except Exception as e:
            logger.error(f"Automation test suite failed: {e}")
    
    # Start tests in background
    background_tasks.add_task(run_automation_tests)
    
    return {
        "status": "started",
        "message": "Quick automation test suite started in background",
        "check_logs": "Monitor logs for detailed results",
        "tests": [
            "service_health_check",
            "web_search_functionality", 
            "frontend_interaction_test"
        ]
    }


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
                "description": "Automated web search with result extraction"
            },
            "frontend_testing": {
                "navigation": True,
                "interaction": True,
                "screenshot": True,
                "description": "Comprehensive frontend functionality testing"
            },
            "message_automation": {
                "send_messages": True,
                "workflow_testing": True,
                "response_monitoring": True,
                "description": "Automated message sending and response monitoring"
            },
            "screenshot_capture": {
                "full_page": True,
                "element_specific": False,
                "formats": ["png"],
                "description": "Webpage screenshot capture"
            }
        },
        "endpoints": [
            "/api/playwright/status",
            "/api/playwright/health",
            "/api/playwright/search",
            "/api/playwright/test-frontend",
            "/api/playwright/send-test-message",
            "/api/playwright/screenshot",
            "/api/playwright/automation/quick-test"
        ],
        "container_integration": {
            "type": "embedded",
            "container_port": 3000,
            "health_monitoring": True,
            "auto_reconnect": True,
            "description": "Docker container with native API integration"
        }
    }