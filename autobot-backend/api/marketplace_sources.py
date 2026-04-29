# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin Marketplace Sources

Issue #6481 - User-extensible marketplace sources. Users register custom
catalog URLs alongside the built-in AutoBot marketplace.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.redis_client import get_async_redis_client

logger = logging.getLogger(__name__)

router = APIRouter()

_SOURCES_KEY = "plugins:marketplaces"
_BUILTIN_ID = "builtin"
_BUILTIN_NAME = "AutoBot Marketplace"
_BUILTIN_DESCRIPTION = "Default AutoBot plugin marketplace"

_NAME_PATTERN = re.compile(r"^[\w\s.\-()]{1,64}$")
_FETCH_TIMEOUT_SECONDS = 15
_MAX_CATALOG_BYTES = 4 * 1024 * 1024  # 4 MB cap on catalog JSON


class MarketplaceSource(BaseModel):
    id: str = Field(..., description="Unique source ID; 'builtin' for the default")
    name: str = Field(..., description="Display name shown in the UI")
    url: Optional[str] = Field(
        default=None, description="Catalog URL; null for the built-in source"
    )
    description: Optional[str] = Field(default=None)
    is_builtin: bool = Field(default=False)
    created_at: Optional[str] = Field(default=None)


class MarketplaceSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    url: HttpUrl
    description: Optional[str] = Field(default=None, max_length=200)


class MarketplaceSourcesResponse(BaseModel):
    sources: list[MarketplaceSource]


class CatalogPlugin(BaseModel):
    """A single plugin entry as listed in an external marketplace catalog."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    git_url: str
    ref: Optional[str] = None
    category: str = "other"
    tags: list[str] = Field(default_factory=list)


class CatalogDocument(BaseModel):
    """The schema an external marketplace URL must return."""

    name: str
    version: str = "1"
    plugins: list[CatalogPlugin]


def _builtin_source() -> MarketplaceSource:
    return MarketplaceSource(
        id=_BUILTIN_ID,
        name=_BUILTIN_NAME,
        url=None,
        description=_BUILTIN_DESCRIPTION,
        is_builtin=True,
    )


async def _list_user_sources() -> list[MarketplaceSource]:
    redis = await get_async_redis_client(database="main")
    if redis is None:
        return []
    raw_map = await redis.hgetall(_SOURCES_KEY)
    sources: list[MarketplaceSource] = []
    for raw in raw_map.values():
        try:
            sources.append(MarketplaceSource.model_validate_json(raw))
        except Exception as exc:
            logger.warning("Skipping malformed marketplace source: %s", exc)
    sources.sort(key=lambda s: s.created_at or "")
    return sources


async def list_sources() -> list[MarketplaceSource]:
    """Return the built-in source plus all user-added sources."""
    return [_builtin_source(), *await _list_user_sources()]


def _validate_url_scheme(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Marketplace URL must use http or https",
        )


def _validate_source_name(name: str) -> str:
    name = name.strip()
    if not _NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source name contains unsupported characters",
        )
    return name


@router.get(
    "/marketplaces",
    response_model=MarketplaceSourcesResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_marketplaces",
    error_code_prefix="MARKETPLACE_SOURCES",
)
async def list_marketplaces() -> MarketplaceSourcesResponse:
    """Issue #6481: list built-in + user-added marketplace sources."""
    return MarketplaceSourcesResponse(sources=await list_sources())


@router.post(
    "/marketplaces",
    status_code=status.HTTP_201_CREATED,
    response_model=MarketplaceSource,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_marketplace",
    error_code_prefix="MARKETPLACE_SOURCES",
)
async def add_marketplace(
    request: MarketplaceSourceCreate,
    admin_check: bool = Depends(check_admin_permission),
) -> MarketplaceSource:
    """Issue #6481: add a custom marketplace source. Validates the URL by
    fetching and parsing the catalog before persisting."""
    url = str(request.url)
    _validate_url_scheme(url)
    name = _validate_source_name(request.name)
    # Validate the URL serves a valid catalog before saving — fail-fast.
    await _fetch_catalog_document(url)
    source = MarketplaceSource(
        id=str(uuid.uuid4()),
        name=name,
        url=url,
        description=request.description,
        is_builtin=False,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    redis = await get_async_redis_client(database="main")
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend unavailable",
        )
    await redis.hset(_SOURCES_KEY, source.id, source.model_dump_json())
    logger.info("Added marketplace source '%s' (%s)", source.name, source.id)
    return source


@router.delete(
    "/marketplaces/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_marketplace",
    error_code_prefix="MARKETPLACE_SOURCES",
)
async def delete_marketplace(
    source_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> None:
    """Issue #6481: remove a custom marketplace source. Built-in is protected."""
    if source_id == _BUILTIN_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The built-in marketplace cannot be removed",
        )
    redis = await get_async_redis_client(database="main")
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend unavailable",
        )
    deleted = await redis.hdel(_SOURCES_KEY, source_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marketplace source '{source_id}' not found",
        )
    logger.info("Removed marketplace source %s", source_id)


async def _fetch_catalog_document(url: str) -> CatalogDocument:
    """Fetch and validate a catalog JSON document from a remote URL.

    Bounded by `_FETCH_TIMEOUT_SECONDS` and `_MAX_CATALOG_BYTES`. Raises
    HTTPException(400) on any fetch/parse/validation failure.
    """
    timeout = aiohttp.ClientTimeout(total=_FETCH_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Marketplace URL returned HTTP {response.status}",
                    )
                # Reject if the server advertises an enormous body up front.
                content_length = response.headers.get("Content-Length")
                if (
                    content_length
                    and content_length.isdigit()
                    and int(content_length) > _MAX_CATALOG_BYTES
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Marketplace catalog exceeds 4MB",
                    )
                # Read with a hard cap regardless of Content-Length.
                body = await response.content.read(_MAX_CATALOG_BYTES + 1)
                if len(body) > _MAX_CATALOG_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Marketplace catalog exceeds 4MB",
                    )
    except aiohttp.ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to reach marketplace URL: {exc}",
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Marketplace URL timed out",
        ) from exc

    try:
        data = json.loads(body)
        return CatalogDocument.model_validate(data)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Marketplace URL did not return valid JSON: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Marketplace catalog schema invalid: {exc}",
        ) from exc


async def get_source_by_id(source_id: str) -> Optional[MarketplaceSource]:
    """Look up a single source by id (built-in or user-added)."""
    if source_id == _BUILTIN_ID:
        return _builtin_source()
    redis = await get_async_redis_client(database="main")
    if redis is None:
        return None
    raw = await redis.hget(_SOURCES_KEY, source_id)
    if raw is None:
        return None
    try:
        return MarketplaceSource.model_validate_json(raw)
    except Exception as exc:
        logger.warning("Malformed source %s in registry: %s", source_id, exc)
        return None


async def fetch_remote_catalog(url: str) -> list[dict[str, Any]]:
    """Public helper: fetch a remote catalog and return its plugin list as
    dicts (suitable for marketplace.py's catalog response shaping)."""
    doc = await _fetch_catalog_document(url)
    return [plugin.model_dump() for plugin in doc.plugins]
