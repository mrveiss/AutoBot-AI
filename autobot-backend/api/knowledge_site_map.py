# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
POST /knowledge/site-map — Domain URL enumeration endpoint.

Issue #7403: Site-map extraction feature.

API contract::

    POST /knowledge/site-map
    {
      "domain":         "example.com",
      "max_urls":       500,           # default: 500
      "respect_robots": true           # default: true
    }

    200 OK::
    {
      "domain":  "example.com",
      "source":  "sitemap" | "crawl",
      "urls":    [{"url": "...", "title": null, "depth": 0}, ...],
      "count":   42
    }

    4xx / 5xx::
    {
      "detail": "<error message>"
    }
"""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from autobot_shared.logging_manager import get_logger
from web_fetch.site_mapper import SiteMapEntry, SiteMapper, SiteMapResult

logger = get_logger(__name__)

router = APIRouter()


class SiteMapRequest(BaseModel):
    """Request body for POST /knowledge/site-map."""

    domain: str = Field(..., min_length=1, max_length=500, description="Domain to enumerate (bare or with scheme)")
    max_urls: int = Field(default=500, ge=1, le=5000, description="Maximum URLs to return")
    respect_robots: bool = Field(default=True, description="Honour robots.txt during crawl fallback")


class SiteMapUrlEntry(BaseModel):
    """A single discovered URL in the site-map response."""

    url: str
    title: str | None = None
    depth: int


class SiteMapResponse(BaseModel):
    """Success response for POST /knowledge/site-map."""

    domain: str
    source: str  # "sitemap" or "crawl"
    urls: List[SiteMapUrlEntry]
    count: int


def _entries_to_response_urls(entries: List[SiteMapEntry]) -> List[SiteMapUrlEntry]:
    """Convert SiteMapEntry list to Pydantic response models."""
    return [SiteMapUrlEntry(url=e.url, title=e.title, depth=e.depth) for e in entries]


@router.post("/site-map", response_model=SiteMapResponse, summary="Enumerate URLs for a domain via sitemap or crawl")
async def get_site_map(request: SiteMapRequest) -> SiteMapResponse:
    """Return a list of URLs discovered for *request.domain*.

    Discovery strategy:
    1. Try ``https://{domain}/sitemap.xml`` (and follow sitemapindex one level).
    2. Fall back to BFS crawl with ``max_depth=3`` when sitemap is absent.

    The crawl fallback honours ``respect_robots`` via :class:`web_fetch.RobotsCache`.
    The ``title`` field is null for all entries (bodies are not fetched in the
    crawl fallback; sitemap.xml does not provide titles either).
    """
    try:
        result: SiteMapResult = await SiteMapper.map_site(
            domain=request.domain,
            max_urls=request.max_urls,
            respect_robots=request.respect_robots,
        )
    except Exception as exc:
        logger.error("site-map failed for domain %s: %s", request.domain, exc)
        raise HTTPException(status_code=500, detail=f"site-map extraction failed: {exc}") from exc

    urls = _entries_to_response_urls(result.entries)
    return SiteMapResponse(
        domain=result.domain,
        source=result.source,
        urls=urls,
        count=len(urls),
    )
