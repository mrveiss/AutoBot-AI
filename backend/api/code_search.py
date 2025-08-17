"""
Code Search API

High-performance code search endpoints using NPU acceleration and Redis indexing.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.agents.npu_code_search_agent import (
    index_project,
    npu_code_search,
    search_codebase,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class IndexRequest(BaseModel):
    root_path: str
    force_reindex: bool = False


class SearchRequest(BaseModel):
    query: str
    search_type: str = "semantic"  # semantic, exact, regex, element
    language: Optional[str] = None
    max_results: int = 20


class SearchResponse(BaseModel):
    results: List[dict]
    stats: dict
    query: str
    search_type: str


@router.post("/index")
async def index_codebase(request: IndexRequest):
    """
    Index a codebase for fast searching.

    This endpoint indexes all supported code files in the specified directory,
    creating optimized data structures for fast searching.
    """
    try:
        logger.info(f"Starting codebase indexing: {request.root_path}")

        result = await index_project(request.root_path, request.force_reindex)

        if result["status"] == "success":
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Codebase indexed successfully",
                    "indexed_files": result["indexed_files"],
                    "execution_time": result["execution_time"],
                    "skipped_files": result.get("skipped_files", 0),
                    "errors": result.get("errors", []),
                },
            )
        elif result["status"] == "already_indexed":
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Codebase already indexed",
                    "index_key": result["index_key"],
                    "note": "Use force_reindex=true to re-index",
                },
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Indexing failed",
                    "details": result.get("error", "Unknown error"),
                },
            )

    except Exception as e:
        logger.error(f"Indexing endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.post("/search")
async def search_code(request: SearchRequest):
    """
    Search through indexed code.

    Supports multiple search types:
    - semantic: AI-powered semantic similarity search (NPU-accelerated when available)
    - exact: Exact string matching
    - regex: Regular expression search
    - element: Search for specific code elements (functions, classes, etc.)
    """
    try:
        logger.info(f"Code search: '{request.query}' (type: {request.search_type})")

        # Validate search type
        valid_types = ["semantic", "exact", "regex", "element"]
        if request.search_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid search_type. Must be one of: {valid_types}",
            )

        # Perform search
        results = await search_codebase(
            query=request.query,
            search_type=request.search_type,
            language=request.language,
            max_results=request.max_results,
        )

        # Get search statistics
        stats = npu_code_search.get_search_stats()

        # Convert results to serializable format
        serialized_results = []
        for result in results:
            serialized_results.append(
                {
                    "file_path": result.file_path,
                    "content": result.content,
                    "line_number": result.line_number,
                    "confidence": result.confidence,
                    "context_lines": result.context_lines,
                    "metadata": result.metadata,
                }
            )

        return JSONResponse(
            status_code=200,
            content={
                "results": serialized_results,
                "stats": {
                    "total_results": len(serialized_results),
                    "search_time_ms": stats.search_time_ms,
                    "npu_acceleration_used": stats.npu_acceleration_used,
                    "redis_cache_hit": stats.redis_cache_hit,
                },
                "query": request.query,
                "search_type": request.search_type,
                "language_filter": request.language,
            },
        )

    except Exception as e:
        logger.error(f"Search endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/search")
async def search_code_get(
    q: str = Query(..., description="Search query"),
    type: str = Query("semantic", description="Search type"),
    lang: Optional[str] = Query(None, description="Programming language filter"),
    max: int = Query(20, description="Maximum results", le=100),
):
    """
    GET endpoint for code search (convenience method).

    Query parameters:
    - q: Search query (required)
    - type: Search type (semantic, exact, regex, element)
    - lang: Language filter (python, javascript, etc.)
    - max: Maximum number of results (1-100)
    """
    request = SearchRequest(query=q, search_type=type, language=lang, max_results=max)
    return await search_code(request)


@router.get("/status")
async def get_search_status():
    """
    Get code search system status.

    Returns information about indexed files, NPU availability,
    language distribution, and cache statistics.
    """
    try:
        status = await npu_code_search.get_index_status()

        return JSONResponse(
            status_code=200,
            content={
                "status": "operational",
                "index_status": status,
                "capabilities": {
                    "npu_acceleration": status.get("npu_available", False),
                    "redis_indexing": True,
                    "supported_search_types": ["semantic", "exact", "regex", "element"],
                    "supported_languages": [
                        "python",
                        "javascript",
                        "typescript",
                        "java",
                        "cpp",
                        "c",
                        "csharp",
                        "ruby",
                        "go",
                        "rust",
                        "php",
                        "swift",
                        "kotlin",
                        "scala",
                        "bash",
                        "yaml",
                        "json",
                        "html",
                        "css",
                        "sql",
                        "markdown",
                    ],
                },
            },
        )

    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


@router.delete("/cache")
async def clear_search_cache():
    """
    Clear the search cache.

    This removes all cached search results to free memory
    and ensure fresh results on next search.
    """
    try:
        result = await npu_code_search.clear_cache()

        if result["status"] == "success":
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Search cache cleared successfully",
                    "keys_deleted": result["keys_deleted"],
                },
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to clear cache",
                    "details": result.get("error", "Unknown error"),
                },
            )

    except Exception as e:
        logger.error(f"Cache clear endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


@router.get("/examples")
async def get_search_examples():
    """
    Get example search queries and usage patterns.
    """
    return JSONResponse(
        status_code=200,
        content={
            "examples": {
                "semantic_search": {
                    "description": "AI-powered semantic similarity search",
                    "examples": [
                        {
                            "query": "authentication middleware",
                            "type": "semantic",
                            "use_case": "Find code related to authentication, even if exact terms don't match",
                        },
                        {
                            "query": "database connection pool",
                            "type": "semantic",
                            "use_case": "Find database connectivity code across different implementations",
                        },
                    ],
                },
                "exact_search": {
                    "description": "Find exact string matches",
                    "examples": [
                        {
                            "query": "def authenticate",
                            "type": "exact",
                            "use_case": "Find exact function definitions",
                        },
                        {
                            "query": "import redis",
                            "type": "exact",
                            "use_case": "Find specific imports",
                        },
                    ],
                },
                "regex_search": {
                    "description": "Pattern-based search using regular expressions",
                    "examples": [
                        {
                            "query": "def\\s+\\w+_test\\s*\\(",
                            "type": "regex",
                            "use_case": "Find all test functions",
                        },
                        {
                            "query": "class\\s+\\w+Exception",
                            "type": "regex",
                            "use_case": "Find exception classes",
                        },
                    ],
                },
                "element_search": {
                    "description": "Search for specific code elements by name",
                    "examples": [
                        {
                            "query": "authenticate",
                            "type": "element",
                            "use_case": "Find functions, classes, or variables named 'authenticate'",
                        },
                        {
                            "query": "UserModel",
                            "type": "element",
                            "use_case": "Find specific class definitions",
                        },
                    ],
                },
            },
            "language_filters": [
                "python",
                "javascript",
                "typescript",
                "java",
                "cpp",
                "c",
                "csharp",
                "ruby",
                "go",
                "rust",
                "php",
                "swift",
                "kotlin",
                "scala",
                "bash",
                "yaml",
                "json",
                "html",
                "css",
                "sql",
                "markdown",
            ],
            "usage_tips": [
                "Use semantic search for concept-based queries",
                "Use exact search for finding specific code patterns",
                "Use regex search for complex pattern matching",
                "Use element search for finding specific functions/classes by name",
                "Add language filters to narrow down results",
                "Results are cached for performance - clear cache if codebase changes",
            ],
        },
    )
