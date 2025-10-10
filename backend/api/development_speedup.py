"""
Development Speedup API

Advanced code analysis endpoints for development acceleration using NPU and Redis.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.constants.network_constants import NetworkConstants
from src.agents.development_speedup_agent import (
    analyze_codebase,
    get_development_speedup_agent,
    find_duplicates,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Lazy initialization for development speedup agent
_development_speedup_instance = None


def _get_dev_speedup_agent():
    """Get or create the development speedup agent instance (lazy initialization)"""
    global _development_speedup_instance
    if _development_speedup_instance is None:
        _development_speedup_instance = get_development_speedup_agent()
    return _development_speedup_instance


class AnalysisRequest(BaseModel):
    root_path: str
    analysis_type: str = (
        "comprehensive"  # comprehensive, duplicates, patterns, imports, dead_code, refactoring, quality
    )


@router.post("/analyze")
async def analyze_codebase_endpoint(request: AnalysisRequest):
    """
    Comprehensive codebase analysis for development speedup.

    Analysis types:
    - comprehensive: Full analysis including all categories
    - duplicates: Duplicate code detection only
    - patterns: Code pattern analysis only
    - imports: Import optimization analysis only
    - dead_code: Dead code detection only
    - refactoring: Refactoring opportunities only
    - quality: Code quality consistency only
    """
    try:
        logger.info(f"Starting {request.analysis_type} analysis: {request.root_path}")

        if request.analysis_type == "comprehensive":
            result = await analyze_codebase(request.root_path)
        elif request.analysis_type == "duplicates":
            result = await _get_dev_speedup_agent().find_duplicate_code(request.root_path)
        elif request.analysis_type == "patterns":
            result = await _get_dev_speedup_agent().identify_code_patterns(request.root_path)
        elif request.analysis_type == "imports":
            result = await _get_dev_speedup_agent().analyze_imports_and_dependencies(
                request.root_path
            )
        elif request.analysis_type == "dead_code":
            result = await _get_dev_speedup_agent().detect_dead_code(request.root_path)
        elif request.analysis_type == "refactoring":
            result = await _get_dev_speedup_agent().find_refactoring_opportunities(
                request.root_path
            )
        elif request.analysis_type == "quality":
            result = await _get_dev_speedup_agent().analyze_code_quality_consistency(
                request.root_path
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid analysis_type. Must be one of: comprehensive, duplicates, patterns, imports, dead_code, refactoring, quality",
            )

        return JSONResponse(
            status_code=200,
            content={
                "analysis_type": request.analysis_type,
                "root_path": request.root_path,
                "results": result,
                "status": "success",
            },
        )

    except Exception as e:
        logger.error(f"Analysis endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/analyze")
async def analyze_codebase_get(
    path: str = Query(..., description="Root path to analyze"),
    type: str = Query("comprehensive", description="Analysis type"),
):
    """
    GET endpoint for codebase analysis (convenience method).

    Query parameters:
    - path: Root directory path to analyze (required)
    - type: Analysis type (comprehensive, duplicates, patterns, imports, dead_code, refactoring, quality)
    """
    request = AnalysisRequest(root_path=path, analysis_type=type)
    return await analyze_codebase_endpoint(request)


@router.get("/duplicates")
async def find_duplicates_endpoint(
    path: str = Query(..., description="Root path to analyze"),
    min_lines: int = Query(
        5, description="Minimum lines for duplicate detection", ge=3, le=50
    ),
):
    """
    Find duplicate code blocks in the codebase.

    This endpoint specifically focuses on duplicate code detection
    and provides detailed analysis of code duplication.
    """
    try:
        logger.info(f"Finding duplicates in: {path}")

        # Temporarily adjust minimum lines threshold
        agent = _get_dev_speedup_agent()
        original_threshold = agent.min_duplicate_lines
        agent.min_duplicate_lines = min_lines

        try:
            result = await find_duplicates(path)
        finally:
            # Restore original threshold
            agent.min_duplicate_lines = original_threshold

        return JSONResponse(
            status_code=200,
            content={
                "analysis_type": "duplicates",
                "root_path": path,
                "min_lines_threshold": min_lines,
                "results": result,
                "status": "success",
            },
        )

    except Exception as e:
        logger.error(f"Duplicate detection error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Duplicate detection failed: {str(e)}"
        )


@router.get("/patterns")
async def analyze_patterns_endpoint(
    path: str = Query(..., description="Root path to analyze"),
    pattern_type: Optional[str] = Query(
        None, description="Specific pattern type to search for"
    ),
):
    """
    Analyze code patterns and anti-patterns.

    Identifies common code patterns, anti-patterns, and suggests improvements.
    """
    try:
        logger.info(f"Analyzing patterns in: {path}")

        result = await _get_dev_speedup_agent().identify_code_patterns(path)

        # Filter by pattern type if specified
        if pattern_type:
            filtered_patterns = [
                p
                for p in result.get("patterns", [])
                if pattern_type.lower() in p.get("pattern_type", "").lower()
            ]
            result["patterns"] = filtered_patterns
            result["total_patterns"] = len(filtered_patterns)

        return JSONResponse(
            status_code=200,
            content={
                "analysis_type": "patterns",
                "root_path": path,
                "pattern_filter": pattern_type,
                "results": result,
                "status": "success",
            },
        )

    except Exception as e:
        logger.error(f"Pattern analysis error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Pattern analysis failed: {str(e)}"
        )


@router.get("/imports")
async def analyze_imports_endpoint(
    path: str = Query(..., description="Root path to analyze"),
    show_unused: bool = Query(True, description="Include potentially unused imports"),
):
    """
    Analyze import patterns and dependencies.

    Provides insights into import usage, dependency patterns,
    and optimization opportunities.
    """
    try:
        logger.info(f"Analyzing imports in: {path}")

        result = await _get_dev_speedup_agent().analyze_imports_and_dependencies(path)

        if not show_unused:
            result.pop("potential_unused_imports", None)

        return JSONResponse(
            status_code=200,
            content={
                "analysis_type": "imports",
                "root_path": path,
                "show_unused": show_unused,
                "results": result,
                "status": "success",
            },
        )

    except Exception as e:
        logger.error(f"Import analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Import analysis failed: {str(e)}")


@router.get("/dead-code")
async def detect_dead_code_endpoint(
    path: str = Query(..., description="Root path to analyze")
):
    """
    Detect potentially dead or unreachable code.

    Identifies code that may be unreachable or no longer used.
    """
    try:
        logger.info(f"Detecting dead code in: {path}")

        result = await _get_dev_speedup_agent().detect_dead_code(path)

        return JSONResponse(
            status_code=200,
            content={
                "analysis_type": "dead_code",
                "root_path": path,
                "results": result,
                "status": "success",
            },
        )

    except Exception as e:
        logger.error(f"Dead code detection error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Dead code detection failed: {str(e)}"
        )


@router.get("/refactoring")
async def find_refactoring_opportunities_endpoint(
    path: str = Query(..., description="Root path to analyze"),
    min_complexity: float = Query(
        5.0, description="Minimum complexity score for opportunities", ge=1.0, le=10.0
    ),
):
    """
    Find refactoring opportunities to improve code quality.

    Identifies functions and code blocks that would benefit from refactoring.
    """
    try:
        logger.info(f"Finding refactoring opportunities in: {path}")

        result = await _get_dev_speedup_agent().find_refactoring_opportunities(path)

        # Filter by complexity if specified
        if min_complexity > 1.0:
            filtered_opportunities = [
                opp
                for opp in result.get("refactoring_opportunities", [])
                if opp.get("complexity_score", 0) >= min_complexity
            ]
            result["refactoring_opportunities"] = filtered_opportunities
            result["total_opportunities"] = len(filtered_opportunities)
            result["filtered_by_complexity"] = min_complexity

        return JSONResponse(
            status_code=200,
            content={
                "analysis_type": "refactoring",
                "root_path": path,
                "min_complexity": min_complexity,
                "results": result,
                "status": "success",
            },
        )

    except Exception as e:
        logger.error(f"Refactoring analysis error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Refactoring analysis failed: {str(e)}"
        )


@router.get("/quality")
async def analyze_quality_endpoint(
    path: str = Query(..., description="Root path to analyze"),
    severity: Optional[str] = Query(
        None, description="Filter by severity: low, medium, high, critical"
    ),
):
    """
    Analyze code quality and consistency.

    Checks for naming conventions, documentation consistency,
    and other code quality metrics.
    """
    try:
        logger.info(f"Analyzing code quality in: {path}")

        result = await _get_dev_speedup_agent().analyze_code_quality_consistency(path)

        # Filter by severity if specified
        if severity:
            valid_severities = ["low", "medium", "high", "critical"]
            if severity not in valid_severities:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid severity. Must be one of: {valid_severities}",
                )

            filtered_issues = [
                issue
                for issue in result.get("quality_issues", [])
                if issue.get("severity") == severity
            ]
            result["quality_issues"] = filtered_issues
            result["total_issues"] = len(filtered_issues)
            result["filtered_by_severity"] = severity

        return JSONResponse(
            status_code=200,
            content={
                "analysis_type": "quality",
                "root_path": path,
                "severity_filter": severity,
                "results": result,
                "status": "success",
            },
        )

    except Exception as e:
        logger.error(f"Quality analysis error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Quality analysis failed: {str(e)}"
        )


@router.get("/recommendations")
async def get_recommendations_endpoint(
    path: str = Query(..., description="Root path to analyze")
):
    """
    Get actionable recommendations for development speedup.

    Performs a quick analysis and provides prioritized recommendations
    for improving the codebase.
    """
    try:
        logger.info(f"Generating recommendations for: {path}")

        # Perform comprehensive analysis
        result = await analyze_codebase(path)

        # Extract recommendations and add priority scoring
        recommendations = result.get("recommendations", [])

        # Add some quick metrics for dashboard
        metrics = {
            "duplicate_savings": result.get("duplicate_code", {})
            .get("potential_savings", {})
            .get("lines_of_code", 0),
            "technical_debt_items": result.get("code_patterns", {}).get(
                "high_priority_issues", 0
            ),
            "unused_imports": len(
                result.get("import_analysis", {}).get("potential_unused_imports", [])
            ),
            "refactoring_opportunities": result.get(
                "refactoring_opportunities", {}
            ).get("total_opportunities", 0),
            "quality_issues": result.get("quality_issues", {}).get("total_issues", 0),
        }

        # Calculate overall health score
        total_issues = (
            result.get("duplicate_code", {}).get("total_duplicates", 0)
            + metrics["technical_debt_items"]
            + metrics["unused_imports"]
            + metrics["refactoring_opportunities"]
            + metrics["quality_issues"]
        )

        health_score = max(0, 100 - (total_issues * 2))  # Simple scoring

        return JSONResponse(
            status_code=200,
            content={
                "analysis_type": "recommendations",
                "root_path": path,
                "health_score": health_score,
                "recommendations": recommendations,
                "metrics": metrics,
                "priority_actions": recommendations[:3],  # Top 3 recommendations
                "status": "success",
            },
        )

    except Exception as e:
        logger.error(f"Recommendations error: {e}")
        raise HTTPException(status_code=500, detail=f"Recommendations failed: {str(e)}")


@router.get("/status")
async def get_development_speedup_status():
    """
    Get development speedup system status.

    Returns information about NPU availability, Redis connection,
    and analysis capabilities.
    """
    try:
        from src.agents.npu_code_search_agent import npu_code_search

        # Get NPU and search status
        search_status = await npu_code_search.get_index_status()

        return JSONResponse(
            status_code=200,
            content={
                "status": "operational",
                "capabilities": {
                    "npu_acceleration": search_status.get("npu_available", False),
                    "redis_indexing": True,
                    "analysis_types": [
                        "comprehensive",
                        "duplicates",
                        "patterns",
                        "imports",
                        "dead_code",
                        "refactoring",
                        "quality",
                    ],
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
                    ],
                },
                "search_index": search_status,
                "thresholds": {
                    "duplicate_similarity": _get_dev_speedup_agent().duplicate_threshold,
                    "min_duplicate_lines": _get_dev_speedup_agent().min_duplicate_lines,
                    "complexity_threshold": _get_dev_speedup_agent().complexity_threshold,
                },
            },
        )

    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


@router.get("/examples")
async def get_analysis_examples():
    """
    Get example analysis requests and usage patterns.
    """
    return JSONResponse(
        status_code=200,
        content={
            "examples": {
                "comprehensive_analysis": {
                    "description": "Full codebase analysis with all insights",
                    "endpoint": "/api/development_speedup/analyze",
                    "parameters": {
                        "root_path": "/path/to/project",
                        "analysis_type": "comprehensive",
                    },
                    "use_case": "Get complete overview of codebase health and improvement opportunities",
                },
                "duplicate_detection": {
                    "description": "Find duplicate code blocks",
                    "endpoint": "/api/development_speedup/duplicates",
                    "parameters": {"path": "/path/to/project", "min_lines": 5},
                    "use_case": "Identify and eliminate code duplication to reduce maintenance burden",
                },
                "pattern_analysis": {
                    "description": "Identify code patterns and anti-patterns",
                    "endpoint": "/api/development_speedup/patterns",
                    "parameters": {"path": "/path/to/project", "pattern_type": "TODO"},
                    "use_case": "Find technical debt items and code smells",
                },
                "quick_recommendations": {
                    "description": "Get prioritized improvement recommendations",
                    "endpoint": "/api/development_speedup/recommendations",
                    "parameters": {"path": "/path/to/project"},
                    "use_case": "Quick health check with actionable next steps",
                },
            },
            "typical_workflow": [
                "1. Index codebase: POST /api/code_search/index",
                "2. Get recommendations: GET /api/development_speedup/recommendations",
                "3. Analyze specific areas: GET /api/development_speedup/duplicates",
                "4. Address high-priority issues first",
                "5. Re-analyze to track progress",
            ],
            "performance_tips": [
                "Index your codebase first for optimal performance",
                "Use specific analysis types for faster results on large codebases",
                "Results are cached - clear cache if codebase changes significantly",
                "NPU acceleration improves semantic analysis when available",
            ],
        },
    )
