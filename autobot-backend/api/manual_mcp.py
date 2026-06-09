# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Manual MCP Bridge — man page and documentation lookup via MCP

Exposes man page lookup and documentation index queries as MCP tools for
LLM agents. Results are cached in Redis (knowledge database) to avoid
repeated subprocess invocations.

Issue #3287: Complete MCP manual integration.
"""

import asyncio
import json
from typing import List

from fastapi import APIRouter, Depends

from api.schemas_code import (
    ManPageRequest,
    ManPageSearchRequest,
    ManualMCPToolItem,
)
from api.schemas_common import DataResponse
from api.schemas_workflows import ManPageLookupData, ManPageSearchData
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from services.man_page_parser import ManPageContent, get_man_page_content

logger = get_logger(__name__)
router = APIRouter(tags=["manual_mcp", "mcp"])

# Cache TTL for man page results (seconds). Man pages are static; 24 h is safe.
_MAN_PAGE_CACHE_TTL = 86_400

# Redis key prefix so manual cache entries are namespaced.
_CACHE_PREFIX = "manual_mcp:man:"
# Doc-index cache key
_DOC_INDEX_CACHE_KEY = "manual_mcp:doc_index"
_DOC_INDEX_CACHE_TTL = 3_600  # 1 hour


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_key(command: str, section: str) -> str:
    """Build Redis key for a specific man page."""
    return f"{_CACHE_PREFIX}{command}:{section}"


def _serialize_man_page(content: ManPageContent, cached: bool) -> dict:
    """Convert ManPageContent to a JSON-serialisable dict."""
    return {
        "command": content.command,
        "section": content.section,
        "title": content.title,
        "synopsis": content.synopsis,
        "description": content.description,
        "options": content.options,
        "examples": content.examples,
        "see_also": content.see_also,
        "cached": cached,
    }


async def _get_cached_man_page(command: str, section: str) -> dict | None:
    """Return cached man page dict from Redis, or None on miss/error."""
    key = _cache_key(command, section)
    try:
        redis = get_redis_client(database="knowledge")
        raw = await asyncio.to_thread(redis.get, key)
        if raw:
            data = json.loads(raw)
            data["cached"] = True
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis cache read failed for %s(%s): %s", command, section, exc)
    return None


async def _store_man_page_cache(command: str, section: str, data: dict) -> None:
    """Store man page dict in Redis with TTL. Errors are non-fatal."""
    key = _cache_key(command, section)
    try:
        redis = get_redis_client(database="knowledge")
        payload = json.dumps(data)
        await asyncio.to_thread(redis.setex, key, _MAN_PAGE_CACHE_TTL, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis cache write failed for %s(%s): %s", command, section, exc)


# ---------------------------------------------------------------------------
# Core lookup logic
# ---------------------------------------------------------------------------


async def _fetch_man_page(command: str, section: str) -> dict:
    """
    Fetch and parse a man page.

    Tries the local `man` subprocess via ManPageParser. Returns a dict with
    parse_success=False when the command is unavailable rather than raising.
    """
    content: ManPageContent = await asyncio.to_thread(get_man_page_content, command, section)
    return _serialize_man_page(content, cached=False)


async def _lookup_man_page(command: str, section: str) -> dict:
    """
    Return man page data, using Redis cache when available.

    Cache miss  →  subprocess  →  store in cache  →  return.
    Cache hit   →  return immediately.
    Subprocess failure is surfaced in the result dict (parse_success is not
    exposed directly; callers check for empty title/description).
    """
    cached = await _get_cached_man_page(command, section)
    if cached is not None:
        logger.debug("Cache hit for man %s(%s)", command, section)
        return cached

    logger.debug("Cache miss for man %s(%s) — running subprocess", command, section)
    data = await _fetch_man_page(command, section)

    # Only cache successful fetches (non-empty title or description).
    if data.get("title") or data.get("description"):
        await _store_man_page_cache(command, section, data)

    return data


# ---------------------------------------------------------------------------
# Documentation index query
# ---------------------------------------------------------------------------


async def _query_doc_index(query: str, max_results: int) -> List[dict]:
    """
    Query the local documentation index using `man -k`.

    Returns a list of {command, section, summary} dicts.
    Results are cached in Redis for _DOC_INDEX_CACHE_TTL seconds.
    When `man` is unavailable an empty list is returned gracefully.
    """
    # Check full-index cache first
    try:
        redis = get_redis_client(database="knowledge")
        raw = await asyncio.to_thread(redis.get, _DOC_INDEX_CACHE_KEY)
        if raw:
            index: list = json.loads(raw)
            lower_q = query.lower()
            hits = [
                entry
                for entry in index
                if lower_q in entry.get("command", "").lower() or lower_q in entry.get("summary", "").lower()
            ]
            return hits[:max_results]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis doc-index cache read failed: %s", exc)

    # Fallback: run man -k
    import re
    import subprocess

    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["man", "-k", query],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = proc.stdout.splitlines()
    except Exception as exc:  # noqa: BLE001
        logger.warning("man -k subprocess failed: %s", exc)
        return []

    results: List[dict] = []
    pattern = re.compile(r"^(\S+)\s+\((\d[a-z]?)\)\s+-\s+(.+)$")
    for line in lines[:max_results]:
        m = pattern.match(line.strip())
        if m:
            results.append(
                {
                    "command": m.group(1),
                    "section": m.group(2),
                    "summary": m.group(3),
                }
            )

    # Cache the raw parsed results for future queries
    if results:
        try:
            redis = get_redis_client(database="knowledge")
            await asyncio.to_thread(
                redis.setex,
                _DOC_INDEX_CACHE_KEY,
                _DOC_INDEX_CACHE_TTL,
                json.dumps(results),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis doc-index cache write failed: %s", exc)

    return results


# ---------------------------------------------------------------------------
# MCP tool definitions
# ---------------------------------------------------------------------------


def _man_page_tool_schema() -> dict:
    return {
        "name": "lookup_man_page",
        "description": (
            "Fetch a Linux/Unix man page for a command. "
            "Returns structured sections: synopsis, description, options, examples, see-also."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command name (e.g. 'ls')"},
                "section": {
                    "type": "string",
                    "description": "Manual section 1-8 (default: 1)",
                },
            },
            "required": ["command"],
        },
    }


def _search_docs_tool_schema() -> dict:
    return {
        "name": "search_man_pages",
        "description": (
            "Search the system documentation index (man -k) for commands "
            "matching a keyword. Returns a ranked list of command names and brief summaries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (1-50, default 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    }


def _doc_index_tool_schema() -> dict:
    return {
        "name": "get_doc_index",
        "description": (
            "Query the cached documentation index. Similar to search_man_pages "
            "but queries against a pre-warmed Redis cache for lower latency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results (1-50, default 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/mcp/tools", response_model=List[ManualMCPToolItem])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_manual_mcp_tools",
    error_code_prefix="MANUAL_MCP",
)
async def get_manual_mcp_tools(
    current_user: dict = Depends(get_current_user),
) -> List[dict]:
    """List available MCP tools provided by the manual bridge.

    Issue #3287: Man page and documentation lookup tools.
    """
    return [
        _man_page_tool_schema(),
        _search_docs_tool_schema(),
        _doc_index_tool_schema(),
    ]


@router.post("/mcp/lookup_man_page", response_model=DataResponse[ManPageLookupData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_lookup_man_page",
    error_code_prefix="MANUAL_MCP",
)
async def mcp_lookup_man_page(
    request: ManPageRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """MCP tool: Fetch a man page for a command.

    Results are cached in Redis (knowledge database) with a 24-hour TTL.
    When MCP / man is unavailable the response includes success=False and
    a human-readable error rather than raising HTTP 500.

    Issue #3287.
    """
    section = request.section or "1"
    try:
        data = await _lookup_man_page(request.command, section)
        has_content = bool(data.get("title") or data.get("description"))
        return {
            "success": has_content,
            "command": request.command,
            "section": section,
            "result": data,
            "error": None if has_content else f"No man page found for '{request.command}'",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("lookup_man_page failed for %s: %s", request.command, exc)
        return {
            "success": False,
            "command": request.command,
            "section": section,
            "result": None,
            "error": "Man page lookup unavailable",
        }


@router.post("/mcp/search_man_pages", response_model=DataResponse[ManPageSearchData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_search_man_pages",
    error_code_prefix="MANUAL_MCP",
)
async def mcp_search_man_pages(
    request: ManPageSearchRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """MCP tool: Search the system documentation index.

    Delegates to `man -k <query>` and returns structured results.
    Gracefully returns an empty list when `man` is not available.

    Issue #3287.
    """
    try:
        results = await _query_doc_index(request.query, request.max_results)
        return {
            "success": True,
            "query": request.query,
            "count": len(results),
            "results": results,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("search_man_pages failed for query '%s': %s", request.query, exc)
        return {
            "success": False,
            "query": request.query,
            "count": 0,
            "results": [],
            "error": "Documentation index query unavailable",
        }


@router.post("/mcp/get_doc_index", response_model=DataResponse[ManPageSearchData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_get_doc_index",
    error_code_prefix="MANUAL_MCP",
)
async def mcp_get_doc_index(
    request: ManPageSearchRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """MCP tool: Query the cached documentation index.

    First checks Redis; falls back to man -k when cache is cold.

    Issue #3287.
    """
    try:
        results = await _query_doc_index(request.query, request.max_results)
        return {
            "success": True,
            "query": request.query,
            "count": len(results),
            "results": results,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("get_doc_index failed for query '%s': %s", request.query, exc)
        return {
            "success": False,
            "query": request.query,
            "count": 0,
            "results": [],
            "error": "Documentation index unavailable",
        }
