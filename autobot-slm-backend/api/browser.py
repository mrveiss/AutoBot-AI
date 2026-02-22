# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Browser MCP API Routes

Proxy endpoints for the SLM admin browser tool (BrowserTool.vue).
Forwards requests to the browser worker at 172.16.168.25:3000.
Related to Issue #1120.
"""

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/browser/mcp", tags=["browser"])

BROWSER_WORKER_URL = os.getenv("BROWSER_WORKER_URL", "http://172.16.168.25:3000")


class NavigateRequest(BaseModel):
    url: str


@router.get("/status")
async def browser_status() -> dict:
    """Return status of the persistent browser page."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BROWSER_WORKER_URL}/status")
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Browser worker unavailable")
    except Exception as exc:
        logger.error("Browser status error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/navigate")
async def browser_navigate(body: NavigateRequest) -> dict:
    """Navigate the persistent browser page to a URL.

    Handles javascript: scheme shortcuts used by BrowserTool.vue for
    back/forward/refresh operations.
    """
    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            response = await client.post(
                f"{BROWSER_WORKER_URL}/navigate",
                json={"url": body.url},
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Browser worker unavailable")
    except Exception as exc:
        logger.error("Browser navigate error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/screenshot")
async def browser_screenshot() -> dict:
    """Capture a screenshot of the current browser page as base64 PNG."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{BROWSER_WORKER_URL}/screenshot",
                json={},
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Browser worker unavailable")
    except Exception as exc:
        logger.error("Browser screenshot error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
