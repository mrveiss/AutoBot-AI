# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request and response models for the knowledge web-ingestion routes (#16375).

POST /knowledge/crawl (``api/knowledge_crawl.py``), POST /knowledge/scrape
(``api/knowledge_scrape.py``), POST /knowledge/site-map
(``api/knowledge_site_map.py``) and POST /knowledge/extract
(``api/knowledge_extract.py``). Moved here unchanged from those routers, where
they were local definitions: the no-local-schemas hook (#6056) blocks any edit of
a router file that still defines its own ``BaseModel``, and ``schemas_knowledge.py``
is at its recorded size ceiling.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CrawlRequest(BaseModel):
    """Request body for POST /knowledge/crawl."""

    seeds: List[str] = Field(..., min_length=1, description="Seed URLs to crawl")
    max_depth: int = Field(default=1, ge=1, le=10, description="Crawl depth (1 = seeds only)")
    max_pages: int = Field(default=100, ge=1, le=500, description="Hard cap on pages fetched")
    respect_robots: bool = Field(default=True, description="Honour robots.txt")
    ingest: bool = Field(default=True, description="Index crawled pages into ChromaDB")
    same_origin: bool = Field(default=True, description="Restrict crawl to same scheme+host per seed")
    render: Literal["auto", "fast", "playwright"] = Field(default="auto", description="Render mode")
    # Issue #5136 Phase 4: run a scrape template on every crawled URL and merge
    # region-extracted fields into the KB document.
    scrape_template_id: Optional[str] = Field(
        default=None, description="UUID of a ScrapeTemplate to apply to every crawled page"
    )


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


class ExtractRequest(BaseModel):
    """Request body for POST /knowledge/extract.

    The field ``json_schema`` is serialised as ``schema`` on the wire via
    ``alias``.  ``schema`` is a reserved attribute on ``BaseModel`` so we
    cannot use it as a Python field name directly.
    """

    model_config = {"populate_by_name": True}

    url: str = Field(..., min_length=1, max_length=2000, description="Absolute URL to fetch and extract from")
    json_schema: Dict[str, Any] = Field(
        ..., alias="schema", description="JSON Schema (draft 2020-12) for the expected output shape"
    )
    render: Literal["auto", "fast", "playwright"] = Field(default="auto", description="Render mode")
    ingest: bool = Field(default=False, description="Index raw page markdown into ChromaDB when True")


class ExtractResponse(BaseModel):
    """Success response for POST /knowledge/extract."""

    url: str
    data: Dict[str, Any]
    schema_valid: bool
