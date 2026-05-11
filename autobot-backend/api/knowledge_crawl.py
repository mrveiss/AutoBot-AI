# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
POST /knowledge/crawl — BFS web crawl with optional KB ingest.

Issue #7508: Thin HTTP route wrapping WebCrawlerConnector.crawl().

API contract::

    POST /knowledge/crawl
    {
      "seeds":          ["https://..."],
      "max_depth":      1,           # default: 1
      "max_pages":      100,         # default: 100
      "respect_robots": true,        # default: true
      "ingest":         true,        # default: true
      "same_origin":    true,        # default: true
      "render":         "auto"       # default: "auto"
    }

    200 OK::
    {
      "pages":   [{"url": "...", "markdown": "...", "depth": 0, "success": true}, ...],
      "count":   N,
      "indexed": true | false
    }

    502::
    {
      "success":    false,
      "error_code": "...",
      "retryable":  true
    }
"""

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.web_crawler import WebCrawlerConnector
from web_fetch import FetchResult, RenderMode

logger = logging.getLogger(__name__)

router = APIRouter()

_CONNECTOR_ID = "api_crawl"


class CrawlRequest(BaseModel):
    """Request body for POST /knowledge/crawl."""

    seeds: List[str] = Field(..., min_length=1, description="Seed URLs to crawl")
    max_depth: int = Field(default=1, ge=1, le=10, description="Crawl depth (1 = seeds only)")
    max_pages: int = Field(default=100, ge=1, le=500, description="Hard cap on pages fetched")
    respect_robots: bool = Field(default=True, description="Honour robots.txt")
    ingest: bool = Field(default=True, description="Index crawled pages into ChromaDB")
    same_origin: bool = Field(default=True, description="Restrict crawl to same scheme+host per seed")
    render: Literal["auto", "fast", "playwright"] = Field(default="auto", description="Render mode")


class CrawlPageEntry(BaseModel):
    """A single crawled page in the response."""

    url: str
    markdown: str
    depth: int = 0
    success: bool


class CrawlResponse(BaseModel):
    """Success response for POST /knowledge/crawl."""

    pages: List[Dict[str, Any]]
    count: int
    indexed: bool


def _make_connector(request: CrawlRequest) -> WebCrawlerConnector:
    """Instantiate WebCrawlerConnector from a CrawlRequest."""
    cfg = ConnectorConfig(
        connector_id=_CONNECTOR_ID,
        connector_type="web_crawler",
        name="api_crawl",
        config={
            "urls": request.seeds,
            "max_depth": request.max_depth,
            "max_pages": request.max_pages,
            "respect_robots": request.respect_robots,
            "same_origin": request.same_origin,
        },
    )
    return WebCrawlerConnector(cfg)


def _fetch_results_to_pages(results: List[FetchResult]) -> List[Dict[str, Any]]:
    """Convert FetchResult list to plain-dict page entries for the response."""
    return [
        {
            "url": r.url,
            "markdown": r.markdown,
            "depth": 0,
            "success": r.success,
        }
        for r in results
    ]


@router.post("/crawl", response_model=CrawlResponse, summary="BFS crawl seed URLs and optionally ingest into KB")
async def crawl_url_endpoint(request: CrawlRequest) -> CrawlResponse:
    """BFS-crawl *request.seeds* and return the fetched pages.

    Delegates entirely to :class:`knowledge.connectors.web_crawler.WebCrawlerConnector`
    — no BFS or robots logic is duplicated here.

    When ``ingest=True``, each successfully-crawled page is written to the KB
    via the connector's built-in ingest path.  The ``indexed`` field in the
    response reflects whether ingest was requested.

    The ``render`` field is validated to one of the ``RenderMode`` enum values
    but the connector internally uses BS4 for all crawl fetches (single HTTP
    round-trip per URL keeps link extraction and content extraction in sync).
    The field is accepted on the wire for forward-compatibility.
    """
    _render_mode = RenderMode(request.render)  # validate enum; surfaced in future connector update

    connector = _make_connector(request)
    try:
        results: List[FetchResult] = await connector.crawl(
            seed_urls=request.seeds,
            max_depth=request.max_depth,
            max_pages=request.max_pages,
            respect_robots=request.respect_robots,
            ingest=request.ingest,
            same_origin=request.same_origin,
        )
    except Exception as exc:
        logger.error("crawl failed for seeds %s: %s", request.seeds, exc)
        raise HTTPException(
            status_code=502,
            detail={"success": False, "error_code": "crawl_failed", "retryable": True},
        ) from exc

    pages = _fetch_results_to_pages(results)
    return CrawlResponse(pages=pages, count=len(pages), indexed=request.ingest)
