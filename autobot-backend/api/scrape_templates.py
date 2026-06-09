# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Scrape Template CRUD and runner endpoints (GH#5136 Phase 4).

API contract::

    POST /scrape-templates/
        Create a named template from a list of CSS/XPath regions.

    GET /scrape-templates/
        List all templates for the current session/user.

    GET /scrape-templates/{id}
        Fetch a single template by UUID.

    DELETE /scrape-templates/{id}
        Delete a template and remove it from the per-user index.

    POST /scrape-templates/{id}/run?url=<target-url>
        Navigate to *url*, extract each region by selector/xpath,
        return {label: extracted_text} dict.

Redis layout:
    scrape:template:{template_id}        → JSON-encoded ScrapeTemplate
    scrape:template:index:{created_by}   → Redis set of template IDs (no TTL)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth_middleware import check_admin_permission
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Issue #1009: Graceful fallback when playwright is not installed
try:
    from research_browser_manager import get_research_browser_manager

    _BROWSER_AVAILABLE = True
except ImportError:
    get_research_browser_manager = None  # type: ignore[assignment]
    _BROWSER_AVAILABLE = False
    logger.warning("research_browser_manager unavailable — template runner disabled")

try:
    from autobot_shared.redis_client import get_async_redis_client

    _REDIS_AVAILABLE = True
except ImportError:
    get_async_redis_client = None  # type: ignore[assignment]
    _REDIS_AVAILABLE = False
    logger.warning("redis_client unavailable — scrape templates will not persist")

router = APIRouter(
    dependencies=[Depends(check_admin_permission)],
)

# ---------------------------------------------------------------------------
# Redis key helpers
# ---------------------------------------------------------------------------

_KEY_PREFIX = "scrape:template"


def _template_key(template_id: str) -> str:
    return f"{_KEY_PREFIX}:{template_id}"


def _index_key(created_by: str) -> str:
    return f"{_KEY_PREFIX}:index:{created_by}"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ScrapeRegion(BaseModel):
    """A single labeled extraction region."""

    label: str = Field(..., description="Human-readable label for this region")
    selector: Optional[str] = Field(default=None, description="CSS selector")
    xpath: Optional[str] = Field(default=None, description="XPath expression (used when selector is absent)")


class ScrapeTemplate(BaseModel):
    """Persisted scrape template."""

    id: str
    name: str
    url_pattern: str
    regions: List[ScrapeRegion]
    created_by: str
    created_at: str  # ISO-8601


class CreateTemplateRequest(BaseModel):
    """Request body for POST /scrape-templates/."""

    name: str = Field(..., min_length=1, max_length=200, description="Template name")
    url_pattern: str = Field(..., description="URL or glob pattern this template targets")
    regions: List[ScrapeRegion] = Field(..., min_length=1, description="Extraction regions")


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


async def _get_redis():
    if not _REDIS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Redis unavailable — scrape templates cannot be persisted")
    redis = await get_async_redis_client()
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis connection failed")
    return redis


async def _save_template(template: ScrapeTemplate) -> None:
    redis = await _get_redis()
    payload = template.model_dump_json()
    await redis.set(_template_key(template.id), payload)
    await redis.sadd(_index_key(template.created_by), template.id)


async def _load_template(template_id: str) -> ScrapeTemplate | None:
    redis = await _get_redis()
    raw = await redis.get(_template_key(template_id))
    if raw is None:
        return None
    return ScrapeTemplate.model_validate_json(raw)


async def _delete_template(template: ScrapeTemplate) -> None:
    redis = await _get_redis()
    await redis.delete(_template_key(template.id))
    await redis.srem(_index_key(template.created_by), template.id)


async def _list_templates(created_by: str) -> List[ScrapeTemplate]:
    redis = await _get_redis()
    ids = await redis.smembers(_index_key(created_by))
    if not ids:
        return []
    keys = [_template_key(tid.decode() if isinstance(tid, bytes) else tid) for tid in ids]
    raws = await redis.mget(*keys)
    templates = []
    for raw in raws:
        if raw is not None:
            try:
                templates.append(ScrapeTemplate.model_validate_json(raw))
            except Exception as exc:
                logger.warning("Skipping malformed scrape template: %s", exc)
    templates.sort(key=lambda t: t.created_at, reverse=True)
    return templates


# ---------------------------------------------------------------------------
# Region extraction via Playwright
# ---------------------------------------------------------------------------

_JS_EXTRACT_SELECTOR = """
(selector) => {
    const el = document.querySelector(selector);
    return el ? (el.innerText || el.textContent || "").trim() : null;
}
"""

_JS_EXTRACT_XPATH = """
(xpath) => {
    const result = document.evaluate(
        xpath, document, null,
        XPathResult.FIRST_ORDERED_NODE_TYPE, null
    );
    const el = result.singleNodeValue;
    return el ? (el.innerText || el.textContent || "").trim() : null;
}
"""


async def _run_template_on_url(template: ScrapeTemplate, url: str) -> Dict[str, str | None]:
    """Navigate *url* in a research browser session and extract each region."""
    if not _BROWSER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Research browser unavailable (playwright not installed)")

    manager = get_research_browser_manager()
    session_id = await manager.create_session(
        conversation_id=f"scrape-template-{template.id}",
        headless=True,
    )
    if not session_id:
        raise HTTPException(status_code=503, detail="Failed to create browser session for template runner")

    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=503, detail="Browser session not found after creation")

    try:
        nav_result = await session.navigate_to(url)
        if not nav_result.get("success"):
            raise HTTPException(status_code=502, detail=f"Navigation failed: {nav_result.get('error', 'unknown')}")

        extracted: Dict[str, str | None] = {}
        for region in template.regions:
            value: str | None = None
            try:
                if region.selector:
                    value = await session.page.evaluate(_JS_EXTRACT_SELECTOR, region.selector)
                elif region.xpath:
                    value = await session.page.evaluate(_JS_EXTRACT_XPATH, region.xpath)
                else:
                    logger.warning("Region '%s' has no selector or xpath — skipping", region.label)
            except Exception as exc:
                logger.warning("Failed to extract region '%s': %s", region.label, exc)
            extracted[region.label] = value
    finally:
        await manager.cleanup_session(session_id)

    return extracted


# ---------------------------------------------------------------------------
# User identification helper
# ---------------------------------------------------------------------------


def _user_id_from_request(request: Request) -> str:
    """Return a stable identifier for the current caller.

    Tries the auth middleware user dict first; falls back to the X-Session-ID
    header so that unauthenticated single-user setups still work.
    """
    try:
        user = request.state.user if hasattr(request.state, "user") else None
        if user and user.get("username"):
            return user["username"]
    except Exception:
        pass
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        return f"session:{session_id}"
    return "anonymous"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/", summary="Create a scrape template", status_code=201)
async def create_template(body: CreateTemplateRequest, request: Request):
    """Persist a new scrape template and return it."""
    created_by = _user_id_from_request(request)
    template = ScrapeTemplate(
        id=str(uuid.uuid4()),
        name=body.name,
        url_pattern=body.url_pattern,
        regions=body.regions,
        created_by=created_by,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )
    await _save_template(template)
    logger.info("Created scrape template %s ('%s') for %s", template.id, template.name, created_by)
    return template


@router.get("/", summary="List scrape templates for current user")
async def list_templates(request: Request):
    """Return all templates owned by the current session/user."""
    created_by = _user_id_from_request(request)
    templates = await _list_templates(created_by)
    return {"templates": [t.model_dump() for t in templates], "count": len(templates)}


@router.get("/{template_id}", summary="Get a single scrape template")
async def get_template(template_id: str):
    """Fetch one template by UUID."""
    template = await _load_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id!r} not found")
    return template


@router.delete("/{template_id}", summary="Delete a scrape template", status_code=204)
async def delete_template(template_id: str):
    """Delete template and remove from per-user index."""
    template = await _load_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id!r} not found")
    await _delete_template(template)
    logger.info("Deleted scrape template %s", template_id)


@router.post("/{template_id}/run", summary="Execute a scrape template against a URL")
async def run_template(template_id: str, url: str):
    """Navigate to *url*, extract each region, return ``{label: text}`` dict."""
    if not url:
        raise HTTPException(status_code=422, detail="Query param 'url' is required")
    template = await _load_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id!r} not found")
    results = await _run_template_on_url(template, url)
    return {
        "template_id": template_id,
        "url": url,
        "results": results,
    }
