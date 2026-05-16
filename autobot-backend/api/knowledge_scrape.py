# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
POST /knowledge/scrape — Unified web scrape endpoint.

Issue #7401: Scrape-consolidation layer.

Exposes a single endpoint that:
1. Fetches the URL through :class:`web_fetch.WebFetcher` (supporting
   Jina/BS4/Playwright render modes).
2. Returns the markdown, raw HTML, and metadata to the caller.
3. Optionally ingests the result into ChromaDB when ``ingest=True``.

API contract::

    POST /knowledge/scrape
    {
      "url":    "https://...",
      "render": "auto" | "fast" | "playwright",   # default: "auto"
      "ingest": true | false,                       # default: false
      "format": "markdown" | "html" | "json"        # default: "markdown"
    }

    200 OK::
    {
      "url": "https://...",
      "markdown": "...",          # omitted when format != "markdown"
      "html": "...",              # omitted when format != "html"
      "metadata": {
        "title": "...",
        "fetched_at": "2026-05-10T..."
      },
      "indexed": true | false
    }

    4xx / 5xx::
    {
      "success": false,
      "error_code": "...",
      "retryable": true | false
    }
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from autobot_shared.logging_manager import get_logger
from web_fetch import FetchResult, RenderMode, WebFetcher

logger = get_logger(__name__)

router = APIRouter()


class ScrapeRequest(BaseModel):
    """Request body for POST /knowledge/scrape."""

    url: str = Field(..., min_length=1, max_length=2000, description="Absolute URL to scrape")
    render: Literal["auto", "fast", "playwright"] = Field(default="auto", description="Render mode")
    ingest: bool = Field(default=False, description="Index scraped content into ChromaDB")
    format: Literal["markdown", "html", "json"] = Field(default="markdown", description="Response format")


class ScrapeMetadata(BaseModel):
    """Metadata block returned with every scrape response."""

    title: str
    fetched_at: str


class ScrapeResponse(BaseModel):
    """Success response for POST /knowledge/scrape."""

    url: str
    markdown: str | None = None
    html: str | None = None
    metadata: ScrapeMetadata
    indexed: bool


@router.post("/scrape", response_model=ScrapeResponse, summary="Scrape and optionally ingest a URL")
async def scrape_url(request: ScrapeRequest) -> ScrapeResponse:
    """Fetch *request.url* and return markdown content.

    The render mode controls which backend is tried:
    - ``auto``: Jina → BS4 → Playwright (default).
    - ``fast``: Jina → BS4 only (no Playwright).
    - ``playwright``: Skip Jina/BS4, go straight to Playwright JS render.

    When ``ingest=True``, the fetched content is chunked and embedded into
    ChromaDB via :mod:`web_fetch.ingest`.
    """
    render_mode = RenderMode(request.render)
    result: FetchResult = await WebFetcher.fetch(request.url, render=render_mode)

    if not result.success:
        raise HTTPException(
            status_code=502,
            detail={
                "success": False,
                "error_code": result.error_code or "unknown",
                "retryable": result.retryable,
            },
        )

    fetched_at = datetime.now(tz=timezone.utc).isoformat()
    indexed = await _maybe_ingest(result, request.ingest)

    return ScrapeResponse(
        url=result.url,
        markdown=result.markdown if request.format in ("markdown", "json") else None,
        html=None,  # HTML not preserved by WebFetcher — markdown only
        metadata=ScrapeMetadata(title=result.title, fetched_at=fetched_at),
        indexed=indexed,
    )


async def _maybe_ingest(result: FetchResult, ingest: bool) -> bool:
    """Ingest markdown into ChromaDB when *ingest* is True.

    Returns True when ingest was requested and at least one chunk was stored.
    Returns False when ingest is disabled or when ingest fails (non-fatal).
    """
    if not ingest:
        return False
    try:
        from web_fetch.ingest import ingest_markdown

        return await ingest_markdown(result.url, result.markdown, result.title)
    except Exception as exc:
        logger.warning("scrape ingest failed for %s: %s", result.url, exc)
        return False
