# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Search API

High-performance code search endpoints using NPU acceleration and Redis indexing.
Includes advanced codebase analytics for usage statistics and reusability detection.
"""

import asyncio
import logging
import re
from collections import defaultdict
from typing import List, Optional

from agents.npu_code_search_agent import (
    get_npu_code_search,
    index_project,
    search_codebase,
)
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.redis_client import get_redis_client

router = APIRouter()
logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for index status validation (Issue #326)
SUCCESSFUL_INDEX_STATUSES = {"success", "already_indexed"}

# Issue #380: Module-level frozenset for valid search types
_VALID_SEARCH_TYPES = frozenset({"semantic", "exact", "regex", "element"})

# Issue #281: Search examples extracted from get_search_examples for reuse
SEARCH_EXAMPLES_DATA = {
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
    "language_filters": (
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
    ),
    "usage_tips": (
        "Use semantic search for concept-based queries",
        "Use exact search for finding specific code patterns",
        "Use regex search for complex pattern matching",
        "Use element search for finding specific functions/classes by name",
        "Add language filters to narrow down results",
        "Results are cached for performance - clear cache if codebase changes",
    ),
}

# Lazy initialization for NPU code search agent (thread-safe)
import threading

_npu_code_search_instance = None
_npu_code_search_lock = threading.Lock()


def _get_code_search_agent():
    """Get or create the NPU code search agent instance (lazy initialization, thread-safe)"""
    global _npu_code_search_instance
    if _npu_code_search_instance is None:
        with _npu_code_search_lock:
            # Double-check after acquiring lock
            if _npu_code_search_instance is None:
                _npu_code_search_instance = get_npu_code_search()
    return _npu_code_search_instance


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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="index_codebase",
    error_code_prefix="CODE_SEARCH",
)
@router.post("/index")
async def index_codebase(request: IndexRequest):
    """
    Index a codebase for fast searching.

    This endpoint indexes all supported code files in the specified directory,
    creating optimized data structures for fast searching.
    """
    try:
        logger.info("Starting codebase indexing: %s", request.root_path)

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
        logger.error("Indexing endpoint error: %s", e)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_code",
    error_code_prefix="CODE_SEARCH",
)
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
        logger.info("Code search: '%s' (type: %s)", request.query, request.search_type)

        # Validate search type (Issue #380: use module-level constant)
        if request.search_type not in _VALID_SEARCH_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid search_type. Must be one of: {sorted(_VALID_SEARCH_TYPES)}",
            )

        # Perform search
        results = await search_codebase(
            query=request.query,
            search_type=request.search_type,
            language=request.language,
            max_results=request.max_results,
        )

        # Get search statistics
        stats = _get_code_search_agent().get_search_stats()

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
        logger.error("Search endpoint error: %s", e)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_code_get",
    error_code_prefix="CODE_SEARCH",
)
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_search_status",
    error_code_prefix="CODE_SEARCH",
)
@router.get("/status")
async def get_search_status():
    """
    Get code search system status.

    Returns information about indexed files, NPU availability,
    language distribution, and cache statistics.
    """
    try:
        status = await _get_code_search_agent().get_index_status()

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
        logger.error("Status endpoint error: %s", e)
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_search_cache",
    error_code_prefix="CODE_SEARCH",
)
@router.delete("/cache")
async def clear_search_cache():
    """
    Clear the search cache.

    This removes all cached search results to free memory
    and ensure fresh results on next search.
    """
    try:
        result = await _get_code_search_agent().clear_cache()

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
        logger.error("Cache clear endpoint error: %s", e)
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_search_examples",
    error_code_prefix="CODE_SEARCH",
)
@router.get("/examples")
async def get_search_examples():
    """
    Get example search queries and usage patterns.

    Issue #281: Refactored to use module-level SEARCH_EXAMPLES_DATA constant.
    Reduced from 111 lines to ~10 lines.
    """
    # Issue #281: Use module-level constant for search examples
    return JSONResponse(status_code=200, content=SEARCH_EXAMPLES_DATA)


# New Analytics Models
class AnalyticsRequest(BaseModel):
    root_path: str
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = ["*.pyc", "*.git*", "*__pycache__*"]
    languages: Optional[List[str]] = None


class CodeDeclaration(BaseModel):
    name: str
    type: str  # function, class, variable, import, etc.
    file_path: str
    line_number: int
    usage_count: int
    definition: str
    context: str
    complexity_score: Optional[float] = None


class ReusabilityReport(BaseModel):
    declaration: CodeDeclaration
    reusability_score: float
    usage_patterns: List[str]
    refactor_suggestions: List[str]
    similar_declarations: List[str]


# Advanced Codebase Analytics Endpoints

# Declaration patterns for analysis (Issue #315 - extracted)
DECLARATION_PATTERNS = {
    "functions": [
        r"def\s+(\w+)\s*\(",  # Python functions
        r"function\s+(\w+)\s*\(",  # JavaScript functions
        r"async\s+def\s+(\w+)\s*\(",  # Python async functions
        r"const\s+(\w+)\s*=\s*\(",  # JS arrow functions
        r"(\w+)\s*=\s*async\s*\(",  # JS async arrow functions
    ],
    "classes": [
        r"class\s+(\w+)",  # Python/JS classes
        r"interface\s+(\w+)",  # TypeScript interfaces
        r"type\s+(\w+)\s*=",  # Type definitions
    ],
    "imports": [
        r"from\s+[\w.]+\s+import\s+(\w+)",  # Python imports
        r"import\s+{([^}]+)}",  # JS destructured imports
        r"import\s+(\w+)",  # Simple imports
    ],
    "variables": [
        r"(\w+)\s*=\s*[^=]",  # Variable assignments
        r"const\s+(\w+)\s*=",  # JS constants
        r"let\s+(\w+)\s*=",  # JS variables
        r"var\s+(\w+)\s*=",  # JS variables
    ],
}


def _extract_declaration_names(match_text: str) -> List[str]:
    """Extract declaration names from match, handling destructured imports (Issue #315)."""
    if "," in match_text:
        return [name.strip() for name in match_text.split(",") if name.strip()]
    return [match_text.strip()] if match_text.strip() else []


def _update_declaration_stats(
    declaration_stats: dict,
    name: str,
    file_path: str,
    line_number: int,
    context_lines: str,
) -> None:
    """Update declaration statistics for a single name (Issue #315)."""
    if name and len(name) > 1:  # Filter out single characters
        declaration_stats[name]["definition_count"] += 1
        declaration_stats[name]["files"].add(file_path)
        declaration_stats[name]["lines"].append(line_number)
        declaration_stats[name]["contexts"].append(context_lines)


async def _process_pattern_matches(
    pattern: str,
    declaration_stats: dict,
) -> None:
    """Process matches for a single pattern (Issue #315).

    Issue #508: Optimized by precompiling regex pattern once instead of
    per-iteration compilation.
    """
    search_results = await search_codebase(
        query=pattern, search_type="regex", max_results=1000
    )

    # Issue #508: Precompile pattern once - O(1) instead of O(n) compilations
    compiled_pattern = re.compile(pattern, re.MULTILINE)

    for result in search_results:
        matches = compiled_pattern.finditer(result.content)
        for match in matches:
            match_text = match.group(1) if match.groups() else match.group(0)
            for name in _extract_declaration_names(match_text):
                _update_declaration_stats(
                    declaration_stats,
                    name,
                    result.file_path,
                    result.line_number,
                    result.context_lines,
                )


async def _count_usages(declaration_stats: dict) -> None:
    """Count usages for all declarations (Issue #315)."""
    for name in list(declaration_stats.keys()):
        usage_results = await search_codebase(
            query=name, search_type="exact", max_results=500
        )
        declaration_stats[name]["usage_count"] = len(usage_results)


def _build_type_results(declaration_stats: dict, pattern_type: str) -> List[dict]:
    """Build result list for a pattern type (Issue #315)."""
    results = []
    for name, stats in declaration_stats.items():
        if stats["definition_count"] > 0:
            results.append(
                {
                    "name": name,
                    "type": pattern_type[:-1],  # Remove 's' from end
                    "definition_count": stats["definition_count"],
                    "usage_count": stats["usage_count"],
                    "files": list(stats["files"]),
                    "reusability_score": min(
                        stats["usage_count"] / max(stats["definition_count"], 1),
                        10.0,
                    ),
                    "lines": stats["lines"][:10],  # Limit to first 10
                }
            )
    return sorted(results, key=lambda x: x["usage_count"], reverse=True)[:50]


def _build_reusability_insights(analysis_results: dict) -> dict:
    """Build reusability insights from analysis results (Issue #315)."""
    all_items = [item for results in analysis_results.values() for item in results]
    return {
        "highly_reusable": [
            item for item in all_items if item["reusability_score"] > 5
        ][:20],
        "underutilized": [
            item
            for item in all_items
            if item["definition_count"] > 1 and item["usage_count"] < 3
        ][:20],
        "potential_duplicates": [
            item for item in all_items if item["definition_count"] > 3
        ][:20],
    }


def _build_similar_block_entry(result) -> dict:
    """
    Build a single similar block entry from a search result.

    Issue #281: Extracted from find_code_duplicates to reduce function length
    and improve readability of result processing.

    Args:
        result: Search result with file_path, line_number, content, etc.

    Returns:
        Dict with formatted block entry for duplicate detection
    """
    return {
        "file_path": result.file_path,
        "line_number": result.line_number,
        "content": (
            result.content[:200] + "..."
            if len(result.content) > 200
            else result.content
        ),
        "confidence": result.confidence,
        "context": result.context_lines[:3],  # First 3 context lines
    }


# Issue #665: Module-level constant for refactoring suggestions
_REFACTOR_SUGGESTIONS = (
    {
        "type": "Extract Utility Functions",
        "priority": "high",
        "description": (
            "Functions with high usage but multiple definitions " "can be centralized"
        ),
        "impact": "Reduces code duplication and improves maintainability",
        "effort": "medium",
    },
    {
        "type": "Create Base Classes",
        "priority": "medium",
        "description": (
            "Similar classes can be refactored to use inheritance " "or composition"
        ),
        "impact": "Improves code organization and reduces repetition",
        "effort": "high",
    },
    {
        "type": "Standardize Error Handling",
        "priority": "high",
        "description": "Inconsistent error handling patterns detected",
        "impact": "Improves reliability and debugging experience",
        "effort": "medium",
    },
    {
        "type": "Configuration Centralization",
        "priority": "medium",
        "description": "Multiple configuration loading patterns found",
        "impact": "Simplifies configuration management",
        "effort": "low",
    },
)

# Issue #665: Module-level constant for next steps
_REFACTOR_NEXT_STEPS = (
    "Review high-priority suggestions first",
    "Use duplicate detection to identify specific refactoring targets",
    "Run declaration analysis to understand usage patterns",
    "Test thoroughly after any refactoring changes",
)

# Issue #380: Module-level tuple for common duplicate detection patterns
_DUPLICATE_DETECTION_PATTERNS = (
    "error handling",
    "validation logic",
    "database connection",
    "api request",
    "file processing",
    "configuration loading",
    "logging setup",
    "authentication",
    "data transformation",
    "utility function",
)


async def _search_pattern_for_duplicates(pattern: str) -> Optional[dict]:
    """
    Search for duplicates matching a pattern.

    Issue #665: Extracted from find_code_duplicates.

    Args:
        pattern: Pattern to search for

    Returns:
        Duplicate candidate dict if multiple similar blocks found, None otherwise
    """
    results = await search_codebase(
        query=pattern, search_type="semantic", max_results=20
    )

    if len(results) <= 1:
        return None

    similar_blocks = [_build_similar_block_entry(result) for result in results]

    if len(similar_blocks) > 1:
        return _build_duplicate_candidate(pattern, similar_blocks)

    return None


def _build_duplicates_response(patterns_count: int, duplicate_candidates: list) -> dict:
    """
    Build the response dictionary for duplicate detection.

    Issue #665: Extracted from find_code_duplicates.
    """
    return {
        "summary": {
            "patterns_analyzed": patterns_count,
            "duplicate_candidates_found": len(duplicate_candidates),
            "total_similar_blocks": sum(
                len(c["similar_blocks"]) for c in duplicate_candidates
            ),
            "highest_priority_pattern": (
                duplicate_candidates[0]["pattern"] if duplicate_candidates else None
            ),
        },
        "duplicate_candidates": duplicate_candidates[:10],
        "recommendations": [
            "Consider extracting common patterns into utility functions",
            "Look for opportunities to create base classes or mixins",
            "Evaluate if similar error handling can be centralized",
            "Check if configuration loading can be standardized",
            "Consider creating shared validation utilities",
        ],
    }


def _build_duplicate_candidate(pattern: str, similar_blocks: list) -> dict:
    """
    Build a duplicate candidate entry from similar blocks.

    Issue #281: Extracted from find_code_duplicates to reduce function length
    and centralize candidate building logic.

    Args:
        pattern: The pattern name that matched
        similar_blocks: List of similar block entries

    Returns:
        Dict with duplicate candidate info including refactor priority
    """
    return {
        "pattern": pattern,
        "similar_blocks": similar_blocks,
        "potential_savings": (f"Could refactor {len(similar_blocks)} similar blocks"),
        "refactor_priority": (
            len(similar_blocks) * max(block["confidence"] for block in similar_blocks)
        ),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_declarations",
    error_code_prefix="CODE_SEARCH",
)
@router.post("/analytics/declarations")
async def analyze_declarations(request: AnalyticsRequest):
    """
    Analyze codebase declarations for usage statistics and reusability potential.

    Returns detailed statistics about functions, classes, variables and their usage
    patterns across the codebase. Uses Redis caching for performance.
    """
    try:
        logger.info("Starting declaration analysis for: %s", request.root_path)

        # First ensure the codebase is indexed
        index_result = await index_project(request.root_path, force_reindex=False)
        if index_result["status"] not in SUCCESSFUL_INDEX_STATUSES:
            raise HTTPException(status_code=500, detail="Failed to index codebase")

        # Analyze each pattern type using extracted helpers (Issue #315)
        analysis_results = {}

        for pattern_type, pattern_list in DECLARATION_PATTERNS.items():
            logger.info("Analyzing %s patterns...", pattern_type)

            # Fresh stats for each pattern type
            declaration_stats = defaultdict(
                lambda: {
                    "definition_count": 0,
                    "usage_count": 0,
                    "files": set(),
                    "lines": [],
                    "contexts": [],
                }
            )

            # Process all patterns for this type
            for pattern in pattern_list:
                await _process_pattern_matches(pattern, declaration_stats)

            # Count usages after all patterns processed
            await _count_usages(declaration_stats)

            # Build results for this type
            analysis_results[pattern_type] = _build_type_results(
                declaration_stats, pattern_type
            )

        # Generate summary statistics
        total_declarations = sum(len(results) for results in analysis_results.values())
        most_reused = max(
            (item for results in analysis_results.values() for item in results),
            key=lambda x: x["usage_count"],
            default={"name": "None", "usage_count": 0},
        )

        return JSONResponse(
            status_code=200,
            content={
                "summary": {
                    "total_declarations": total_declarations,
                    "most_reused_declaration": most_reused["name"],
                    "max_usage_count": most_reused["usage_count"],
                    "analysis_root": request.root_path,
                    "pattern_types_analyzed": list(DECLARATION_PATTERNS.keys()),
                },
                "declarations_by_type": analysis_results,
                "reusability_insights": _build_reusability_insights(analysis_results),
            },
        )

    except Exception as e:
        logger.error("Declaration analysis error: %s", e)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_code_duplicates",
    error_code_prefix="CODE_SEARCH",
)
@router.post("/analytics/duplicates")
async def find_code_duplicates(request: AnalyticsRequest):
    """
    Find potential code duplicates and similar patterns for refactoring opportunities.

    Issue #665: Refactored from 85 lines to use extracted helper methods.
    Issue #380: Uses module-level constant for patterns.

    Uses semantic search to identify similar code blocks that could be refactored
    into reusable functions or modules.
    """
    try:
        logger.info("Starting duplicate detection for: %s", request.root_path)

        # Index codebase if needed
        index_result = await index_project(request.root_path, force_reindex=False)
        if index_result["status"] not in SUCCESSFUL_INDEX_STATUSES:
            raise HTTPException(status_code=500, detail="Failed to index codebase")

        # Search patterns for duplicates (Issue #665: uses helper)
        duplicate_candidates = []
        for pattern in _DUPLICATE_DETECTION_PATTERNS:
            candidate = await _search_pattern_for_duplicates(pattern)
            if candidate:
                duplicate_candidates.append(candidate)

        # Sort by refactor priority
        duplicate_candidates.sort(key=lambda x: x["refactor_priority"], reverse=True)

        # Build response (Issue #665: uses helper)
        return JSONResponse(
            status_code=200,
            content=_build_duplicates_response(
                len(_DUPLICATE_DETECTION_PATTERNS), duplicate_candidates
            ),
        )

    except Exception as e:
        logger.error("Duplicate detection error: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Duplicate detection failed: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_statistics",
    error_code_prefix="CODE_SEARCH",
)
@router.get("/analytics/stats")
async def get_codebase_statistics():
    """
    Get comprehensive codebase statistics from Redis index.

    Returns language distribution, file types, complexity metrics,
    and usage patterns across the indexed codebase.
    """
    try:
        # Get current index status
        index_status = await _get_code_search_agent().get_index_status()

        if not index_status.get("is_indexed", False):
            raise HTTPException(
                status_code=404,
                detail="No codebase currently indexed. Use /code_search/index first.",
            )

        # Get Redis statistics
        redis_client = get_redis_client()

        # Get all index keys
        # Issue #361 - avoid blocking
        index_pattern = "code_index:*"
        index_keys = await asyncio.to_thread(redis_client.keys, index_pattern)

        stats = {
            "index_statistics": index_status,
            "redis_keys": len(index_keys),
            "search_performance": {
                "npu_available": index_status.get("npu_available", False),
                "cache_efficiency": "Redis-powered indexing active",
                "supported_languages": index_status.get("language_distribution", {}),
            },
            "recommendations": [],
        }

        # Add performance recommendations
        total_files = index_status.get("total_files", 0)
        if total_files > 1000:
            stats["recommendations"].append(
                "Large codebase detected - NPU acceleration recommended"
            )
        if total_files > 5000:
            stats["recommendations"].append(
                "Very large codebase - consider incremental indexing"
            )

        language_dist = index_status.get("language_distribution", {})
        if len(language_dist) > 5:
            stats["recommendations"].append(
                "Multi-language codebase - use language filters for targeted searches"
            )

        return JSONResponse(status_code=200, content=stats)

    except Exception as e:
        logger.error("Statistics error: %s", e)
        raise HTTPException(status_code=500, detail=f"Statistics failed: {str(e)}")


def _build_refactor_response(root_path: str, suggestions: list) -> dict:
    """
    Build refactor suggestions response.

    Issue #665: Extracted from get_refactor_suggestions to reduce function length.

    Args:
        root_path: The analyzed codebase path
        suggestions: List of suggestion dicts

    Returns:
        Response content dictionary
    """
    return {
        "refactor_suggestions": suggestions,
        "analysis_summary": {
            "root_path": root_path,
            "suggestion_count": len(suggestions),
            "high_priority_count": sum(
                1 for s in suggestions if s["priority"] == "high"
            ),
        },
        "next_steps": list(_REFACTOR_NEXT_STEPS),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_refactor_suggestions",
    error_code_prefix="CODE_SEARCH",
)
@router.post("/analytics/refactor-suggestions")
async def get_refactor_suggestions(request: AnalyticsRequest):
    """
    Generate intelligent refactoring suggestions based on codebase analysis.

    Issue #665: Refactored to use module-level constants for suggestions.

    Analyzes code patterns, usage statistics, and complexity to suggest
    specific refactoring opportunities for improved maintainability.
    """
    try:
        logger.info("Generating refactor suggestions for: %s", request.root_path)

        # Get declaration analysis (for future integration)
        await analyze_declarations(request)

        # Get duplicate analysis (for future integration)
        await find_code_duplicates(request)

        # Issue #665: Use module-level constant for suggestions
        suggestions = list(_REFACTOR_SUGGESTIONS)

        # Issue #665: Use helper to build response
        return JSONResponse(
            status_code=200,
            content=_build_refactor_response(request.root_path, suggestions),
        )

    except Exception as e:
        logger.error("Refactor suggestions error: %s", e)
        raise HTTPException(status_code=500, detail=f"Suggestions failed: {str(e)}")
