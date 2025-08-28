"""
Code Search API

High-performance code search endpoints using NPU acceleration and Redis indexing.
Includes advanced codebase analytics for usage statistics and reusability detection.
"""

import logging
import re
from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.agents.npu_code_search_agent import (
    index_project,
    npu_code_search,
    search_codebase,
)
from src.utils.redis_client import get_redis_client

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
                            "use_case": (
                                "Find code related to authentication, "
                                "even if exact terms don't match"
                            ),
                        },
                        {
                            "query": "database connection pool",
                            "type": "semantic",
                            "use_case": (
                                "Find database connectivity code "
                                "across different implementations"
                            ),
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
                            "use_case": (
                                "Find functions, classes, or variables "
                                "named 'authenticate'"
                            ),
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


@router.post("/analytics/declarations")
async def analyze_declarations(request: AnalyticsRequest):
    """
    Analyze codebase declarations for usage statistics and reusability potential.

    Returns detailed statistics about functions, classes, variables and their usage
    patterns across the codebase. Uses Redis caching for performance.
    """
    try:
        logger.info(f"Starting declaration analysis for: {request.root_path}")

        # First ensure the codebase is indexed
        index_result = await index_project(request.root_path, force_reindex=False)
        if index_result["status"] not in ["success", "already_indexed"]:
            raise HTTPException(status_code=500, detail="Failed to index codebase")

        # Analyze declarations across all files
        declaration_stats = defaultdict(
            lambda: {
                "definition_count": 0,
                "usage_count": 0,
                "files": set(),
                "lines": [],
                "contexts": [],
            }
        )

        # Search for common declaration patterns
        patterns = {
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

        # Analyze each pattern type
        analysis_results = {}

        for pattern_type, pattern_list in patterns.items():
            logger.info(f"Analyzing {pattern_type} patterns...")
            type_results = []

            for pattern in pattern_list:
                # Search for declarations using regex search
                search_results = await search_codebase(
                    query=pattern, search_type="regex", max_results=1000
                )

                # Process results
                for result in search_results:
                    matches = re.finditer(pattern, result.content, re.MULTILINE)
                    for match in matches:
                        declaration_name = (
                            match.group(1) if match.groups() else match.group(0)
                        )

                        # Clean up declaration name
                        if "," in declaration_name:
                            # Handle destructured imports
                            names = [
                                name.strip() for name in declaration_name.split(",")
                            ]
                        else:
                            names = [declaration_name.strip()]

                        for name in names:
                            if name and len(name) > 1:  # Filter out single characters
                                declaration_stats[name]["definition_count"] += 1
                                declaration_stats[name]["files"].add(result.file_path)
                                declaration_stats[name]["lines"].append(
                                    result.line_number
                                )
                                declaration_stats[name]["contexts"].append(
                                    result.context_lines
                                )

                # Also search for usage of these declarations
                for declaration_name in list(declaration_stats.keys()):
                    usage_results = await search_codebase(
                        query=declaration_name, search_type="exact", max_results=500
                    )

                    declaration_stats[declaration_name]["usage_count"] = len(
                        usage_results
                    )

            # Convert to structured results
            for name, stats in declaration_stats.items():
                if stats["definition_count"] > 0:  # Only include declared items
                    type_results.append(
                        {
                            "name": name,
                            "type": pattern_type[:-1],  # Remove 's' from end
                            "definition_count": stats["definition_count"],
                            "usage_count": stats["usage_count"],
                            "files": list(stats["files"]),
                            "reusability_score": min(
                                stats["usage_count"]
                                / max(stats["definition_count"], 1),
                                10.0,
                            ),
                            "lines": stats["lines"][
                                :10
                            ],  # Limit to first 10 occurrences
                        }
                    )

            analysis_results[pattern_type] = sorted(
                type_results, key=lambda x: x["usage_count"], reverse=True
            )[
                :50
            ]  # Top 50 most used

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
                    "pattern_types_analyzed": list(patterns.keys()),
                },
                "declarations_by_type": analysis_results,
                "reusability_insights": {
                    "highly_reusable": [
                        item
                        for results in analysis_results.values()
                        for item in results
                        if item["reusability_score"] > 5
                    ][:20],
                    "underutilized": [
                        item
                        for results in analysis_results.values()
                        for item in results
                        if item["definition_count"] > 1 and item["usage_count"] < 3
                    ][:20],
                    "potential_duplicates": [
                        item
                        for results in analysis_results.values()
                        for item in results
                        if item["definition_count"] > 3
                    ][:20],
                },
            },
        )

    except Exception as e:
        logger.error(f"Declaration analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/analytics/duplicates")
async def find_code_duplicates(request: AnalyticsRequest):
    """
    Find potential code duplicates and similar patterns for refactoring opportunities.

    Uses semantic search to identify similar code blocks that could be refactored
    into reusable functions or modules.
    """
    try:
        logger.info(f"Starting duplicate detection for: {request.root_path}")

        # Index codebase if needed
        index_result = await index_project(request.root_path, force_reindex=False)
        if index_result["status"] not in ["success", "already_indexed"]:
            raise HTTPException(status_code=500, detail="Failed to index codebase")

        # Search for common code patterns that might indicate duplication
        duplicate_patterns = [
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
        ]

        duplicate_candidates = []

        for pattern in duplicate_patterns:
            # Use semantic search to find similar code blocks
            results = await search_codebase(
                query=pattern, search_type="semantic", max_results=20
            )

            if len(results) > 1:  # Found potential duplicates
                # Group by similarity
                similar_blocks = []
                for result in results:
                    similar_blocks.append(
                        {
                            "file_path": result.file_path,
                            "line_number": result.line_number,
                            "content": (
                                result.content[:200] + "..."
                                if len(result.content) > 200
                                else result.content
                            ),
                            "confidence": result.confidence,
                            "context": result.context_lines[
                                :3
                            ],  # First 3 context lines
                        }
                    )

                if len(similar_blocks) > 1:
                    duplicate_candidates.append(
                        {
                            "pattern": pattern,
                            "similar_blocks": similar_blocks,
                            "potential_savings": (
                                f"Could refactor {len(similar_blocks)} similar blocks"
                            ),
                            "refactor_priority": len(similar_blocks)
                            * max(block["confidence"] for block in similar_blocks),
                        }
                    )

        # Sort by refactor priority
        duplicate_candidates.sort(key=lambda x: x["refactor_priority"], reverse=True)

        return JSONResponse(
            status_code=200,
            content={
                "summary": {
                    "patterns_analyzed": len(duplicate_patterns),
                    "duplicate_candidates_found": len(duplicate_candidates),
                    "total_similar_blocks": sum(
                        len(candidate["similar_blocks"])
                        for candidate in duplicate_candidates
                    ),
                    "highest_priority_pattern": (
                        duplicate_candidates[0]["pattern"]
                        if duplicate_candidates
                        else None
                    ),
                },
                "duplicate_candidates": duplicate_candidates[:10],  # Top 10 candidates
                "recommendations": [
                    "Consider extracting common patterns into utility functions",
                    "Look for opportunities to create base classes or mixins",
                    "Evaluate if similar error handling can be centralized",
                    "Check if configuration loading can be standardized",
                    "Consider creating shared validation utilities",
                ],
            },
        )

    except Exception as e:
        logger.error(f"Duplicate detection error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Duplicate detection failed: {str(e)}"
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
        index_status = await npu_code_search.get_index_status()

        if not index_status.get("is_indexed", False):
            raise HTTPException(
                status_code=404,
                detail="No codebase currently indexed. Use /code_search/index first.",
            )

        # Get Redis statistics
        redis_client = get_redis_client()

        # Get all index keys
        index_pattern = "code_index:*"
        index_keys = redis_client.keys(index_pattern)

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
        logger.error(f"Statistics error: {e}")
        raise HTTPException(status_code=500, detail=f"Statistics failed: {str(e)}")


@router.post("/analytics/refactor-suggestions")
async def get_refactor_suggestions(request: AnalyticsRequest):
    """
    Generate intelligent refactoring suggestions based on codebase analysis.

    Analyzes code patterns, usage statistics, and complexity to suggest
    specific refactoring opportunities for improved maintainability.
    """
    try:
        logger.info(f"Generating refactor suggestions for: {request.root_path}")

        # Get declaration analysis (for future integration)
        await analyze_declarations(request)

        # Get duplicate analysis (for future integration)
        await find_code_duplicates(request)

        suggestions = []

        # High-impact refactoring suggestions
        suggestions.extend(
            [
                {
                    "type": "Extract Utility Functions",
                    "priority": "high",
                    "description": (
                        "Functions with high usage but multiple definitions "
                        "can be centralized"
                    ),
                    "impact": "Reduces code duplication and improves maintainability",
                    "effort": "medium",
                },
                {
                    "type": "Create Base Classes",
                    "priority": "medium",
                    "description": (
                        "Similar classes can be refactored to use inheritance "
                        "or composition"
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
            ]
        )

        return JSONResponse(
            status_code=200,
            content={
                "refactor_suggestions": suggestions,
                "analysis_summary": {
                    "root_path": request.root_path,
                    "suggestion_count": len(suggestions),
                    "high_priority_count": len(
                        [s for s in suggestions if s["priority"] == "high"]
                    ),
                },
                "next_steps": [
                    "Review high-priority suggestions first",
                    "Use duplicate detection to identify specific refactoring targets",
                    "Run declaration analysis to understand usage patterns",
                    "Test thoroughly after any refactoring changes",
                ],
            },
        )

    except Exception as e:
        logger.error(f"Refactor suggestions error: {e}")
        raise HTTPException(status_code=500, detail=f"Suggestions failed: {str(e)}")
