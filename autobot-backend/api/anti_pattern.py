# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Detection API

REST API endpoints for code anti-pattern detection and analysis.
Provides comprehensive detection of code smells including God classes,
feature envy, circular dependencies, and more.

Issue: #221
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for refactoring recommendation keywords (Issue #326)
REFACTORING_KEYWORDS = {"method", "parameter", "lazy", "clump"}

# Issue #380: Module-level frozenset for code smell pattern types
_CODE_SMELL_TYPES = frozenset(
    {"long_method", "long_parameter_list", "lazy_class", "data_clump"}
)

# Issue #281: Anti-pattern type definitions extracted from list_anti_pattern_types
# Tuple of 8 anti-pattern type definitions with thresholds and severity
ANTI_PATTERN_TYPE_DEFINITIONS = (
    {
        "type": "god_class",
        "name": "God Class",
        "description": "Classes with too many responsibilities",
        "thresholds": {
            "method_count": ">20",
            "attribute_count": ">15",
            "lines_of_code": ">500",
        },
        "severity_range": ["medium", "critical"],
        "principle_violated": "Single Responsibility Principle",
    },
    {
        "type": "feature_envy",
        "name": "Feature Envy",
        "description": "Methods that use other classes more than their own",
        "thresholds": {"external_ref_ratio": ">3x self references"},
        "severity_range": ["medium", "high"],
        "principle_violated": "Encapsulation",
    },
    {
        "type": "circular_dependency",
        "name": "Circular Dependency",
        "description": "Modules that depend on each other in a cycle",
        "thresholds": {"cycle_detection": "DFS graph traversal"},
        "severity_range": ["medium", "high"],
        "principle_violated": "Acyclic Dependencies Principle",
    },
    {
        "type": "long_method",
        "name": "Long Method",
        "description": "Methods that are too long to easily understand",
        "thresholds": {"lines": ">50"},
        "severity_range": ["medium", "high"],
        "principle_violated": "Single Responsibility Principle",
    },
    {
        "type": "long_parameter_list",
        "name": "Long Parameter List",
        "description": "Methods with too many parameters",
        "thresholds": {"parameter_count": ">5"},
        "severity_range": ["medium", "high"],
        "principle_violated": "Interface Segregation",
    },
    {
        "type": "lazy_class",
        "name": "Lazy Class",
        "description": "Classes that don't do enough to justify existence",
        "thresholds": {"method_count": "<=2", "lines_of_code": "<=20"},
        "severity_range": ["low"],
        "principle_violated": "None (code smell)",
    },
    {
        "type": "dead_code",
        "name": "Dead Code",
        "description": "Unreferenced classes or functions",
        "thresholds": {"reference_count": "0"},
        "severity_range": ["low"],
        "principle_violated": "None (housekeeping)",
    },
    {
        "type": "data_clump",
        "name": "Data Clump",
        "description": "Groups of parameters that appear together frequently",
        "thresholds": {"group_size": ">=3 parameters", "occurrences": ">=3 methods"},
        "severity_range": ["low", "medium"],
        "principle_violated": "Don't Repeat Yourself (DRY)",
    },
)

# Lazy initialization for detector (thread-safe)
import asyncio

_detector_instance = None
_detector_lock = asyncio.Lock()


async def _get_detector():
    """Get or create the anti-pattern detector instance (lazy initialization, thread-safe)"""
    global _detector_instance
    if _detector_instance is None:
        async with _detector_lock:
            # Double-check after acquiring lock
            if _detector_instance is None:
                import importlib.util
                import os

                # Import using file path since directory has dashes
                module_path = os.path.join(
                    os.path.dirname(__file__),
                    "../../tools/code-analysis-suite/src/anti_pattern_detector.py",
                )
                spec = importlib.util.spec_from_file_location(
                    "anti_pattern_detector", module_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                _detector_instance = module.AntiPatternDetector()
    return _detector_instance


# ============ Health Score Helpers (Issue #315) ============


def _get_health_grade(score: float) -> tuple:
    """Get health grade and status from score. (Issue #315 - extracted to reduce nesting)"""
    if score >= 90:
        return "A", "Excellent"
    if score >= 70:
        return "B", "Good"
    if score >= 50:
        return "C", "Fair"
    if score >= 30:
        return "D", "Poor"
    return "F", "Critical"


# ============ Request/Response Models ============


class AnalysisRequest(BaseModel):
    """Request model for anti-pattern analysis"""

    root_path: str = Field(default=".", description="Root path to analyze")
    patterns: List[str] = Field(
        default=["**/*.py"], description="Glob patterns for files to include"
    )
    exclude_patterns: List[str] = Field(
        default=[
            "__pycache__",
            ".git",
            "node_modules",
            ".venv",
            "venv",
            "test_",
            "_test.py",
        ],
        description="Patterns to exclude from analysis",
    )


class SeveritySummary(BaseModel):
    """Summary of issues by severity"""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class AntiPatternSummary(BaseModel):
    """Summary information about detected anti-patterns"""

    total_issues: int
    severity_counts: SeveritySummary
    health_score: float
    summary_by_type: dict
    analysis_time_seconds: float


class AnalysisResponse(BaseModel):
    """Response model for anti-pattern analysis"""

    success: bool
    summary: AntiPatternSummary
    anti_patterns: List[dict]
    recommendations: List[str]


# ============ API Endpoints ============


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_anti_patterns",
    error_code_prefix="ANTI_PATTERN",
)
@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_anti_patterns(request: AnalysisRequest):
    """
    Analyze codebase for anti-patterns.

    Performs comprehensive detection of code smells including:
    - God Classes (>20 methods, high complexity)
    - Feature Envy (methods using other classes more than their own)
    - Circular Dependencies (module/class level cycles)
    - Long Methods (>50 lines)
    - Long Parameter Lists (>5 parameters)
    - Lazy Classes (too few methods)
    - Dead Code (unreferenced entities)
    - Data Clumps (recurring parameter groups)

    Returns severity-scored issues with actionable refactoring suggestions.
    """
    try:
        logger.info("Starting anti-pattern analysis: %s", request.root_path)

        detector = await _get_detector()
        report = await detector.analyze(
            root_path=request.root_path,
            patterns=request.patterns,
            exclude_patterns=request.exclude_patterns,
        )

        # Issue #372: Use model method to get severity counts (reduces feature envy)
        severity_counts = report.get_severity_counts()
        response = AnalysisResponse(
            success=True,
            summary=AntiPatternSummary(
                total_issues=report.total_issues,
                severity_counts=SeveritySummary(**severity_counts),
                health_score=report.health_score,
                summary_by_type=report.summary_by_type,
                analysis_time_seconds=report.analysis_time_seconds,
            ),
            anti_patterns=[ap.to_dict() for ap in report.anti_patterns],
            recommendations=report.recommendations,
        )

        # Issue #372: Use model method for log summary
        logger.info("Anti-pattern analysis complete: %s", report.get_log_summary())

        return response

    except Exception as e:
        logger.error("Anti-pattern analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cached_analysis",
    error_code_prefix="ANTI_PATTERN",
)
@router.get("/cached")
async def get_cached_analysis():
    """
    Get the most recent cached analysis results.

    Returns the last analysis if available, or 404 if no cached results exist.
    """
    try:
        detector = await _get_detector()
        cached = await detector.get_cached_report()

        if cached:
            return JSONResponse(
                content={"success": True, "cached": True, "data": cached}
            )
        else:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "No cached analysis available. Run /analyze first.",
                },
            )

    except Exception as e:
        logger.error("Failed to retrieve cached analysis: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve cache: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_god_classes",
    error_code_prefix="ANTI_PATTERN",
)
@router.post("/god-classes")
async def detect_god_classes(request: AnalysisRequest):
    """
    Detect only God Class anti-patterns.

    God Classes are classes that:
    - Have too many methods (>20)
    - Have too many attributes (>15)
    - Have excessive lines of code (>500)
    - Have high cyclomatic complexity

    These classes typically violate the Single Responsibility Principle.
    """
    try:
        detector = await _get_detector()
        report = await detector.analyze(
            root_path=request.root_path,
            patterns=request.patterns,
            exclude_patterns=request.exclude_patterns,
        )

        # Filter to only god_class issues
        god_classes = [
            ap.to_dict()
            for ap in report.anti_patterns
            if ap.pattern_type.value == "god_class"
        ]

        return JSONResponse(
            content={
                "success": True,
                "count": len(god_classes),
                "god_classes": god_classes,
                "recommendation": (
                    "Break down large classes using Single Responsibility Principle. "
                    "Extract cohesive groups of methods into separate classes."
                ),
            }
        )

    except Exception as e:
        logger.error("God class detection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_circular_dependencies",
    error_code_prefix="ANTI_PATTERN",
)
@router.post("/circular-dependencies")
async def detect_circular_dependencies(request: AnalysisRequest):
    """
    Detect circular dependencies in the codebase.

    Circular dependencies create tight coupling and make the codebase
    difficult to maintain, test, and reason about.
    """
    try:
        detector = await _get_detector()
        report = await detector.analyze(
            root_path=request.root_path,
            patterns=request.patterns,
            exclude_patterns=request.exclude_patterns,
        )

        # Filter to only circular_dependency issues
        circular_deps = [
            ap.to_dict()
            for ap in report.anti_patterns
            if ap.pattern_type.value == "circular_dependency"
        ]

        return JSONResponse(
            content={
                "success": True,
                "count": len(circular_deps),
                "circular_dependencies": circular_deps,
                "recommendation": (
                    "Break cycles by: (1) Extract shared code into common module, "
                    "(2) Use dependency injection, (3) Apply Dependency Inversion Principle"
                ),
            }
        )

    except Exception as e:
        logger.error("Circular dependency detection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_feature_envy",
    error_code_prefix="ANTI_PATTERN",
)
@router.post("/feature-envy")
async def detect_feature_envy(request: AnalysisRequest):
    """
    Detect Feature Envy anti-pattern.

    Feature Envy occurs when a method uses features (methods/attributes)
    of another class more than its own class. This suggests the method
    might belong in the other class.
    """
    try:
        detector = await _get_detector()
        report = await detector.analyze(
            root_path=request.root_path,
            patterns=request.patterns,
            exclude_patterns=request.exclude_patterns,
        )

        # Filter to only feature_envy issues
        feature_envy = [
            ap.to_dict()
            for ap in report.anti_patterns
            if ap.pattern_type.value == "feature_envy"
        ]

        return JSONResponse(
            content={
                "success": True,
                "count": len(feature_envy),
                "feature_envy": feature_envy,
                "recommendation": (
                    "Move methods to the class they reference most, "
                    "or extract shared logic into a common service."
                ),
            }
        )

    except Exception as e:
        logger.error("Feature envy detection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_smells",
    error_code_prefix="ANTI_PATTERN",
)
@router.post("/code-smells")
async def detect_code_smells(request: AnalysisRequest):
    """
    Detect general code smells.

    Includes:
    - Long Methods (>50 lines)
    - Long Parameter Lists (>5 parameters)
    - Lazy Classes (too few methods)
    - Data Clumps (recurring parameter groups)
    """
    try:
        detector = await _get_detector()
        report = await detector.analyze(
            root_path=request.root_path,
            patterns=request.patterns,
            exclude_patterns=request.exclude_patterns,
        )

        # Filter to code smell types (Issue #380: use module-level constant)
        code_smells = [
            ap.to_dict()
            for ap in report.anti_patterns
            if ap.pattern_type.value in _CODE_SMELL_TYPES
        ]

        # Group by type
        by_type = {}
        for smell in code_smells:
            ptype = smell["pattern_type"]
            if ptype not in by_type:
                by_type[ptype] = []
            by_type[ptype].append(smell)

        return JSONResponse(
            content={
                "success": True,
                "total_count": len(code_smells),
                "by_type": by_type,
                "recommendations": [
                    rec
                    for rec in report.recommendations
                    if any(t in rec.lower() for t in REFACTORING_KEYWORDS)
                ],
            }
        )

    except Exception as e:
        logger.error("Code smell detection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dead_code",
    error_code_prefix="ANTI_PATTERN",
)
@router.post("/dead-code")
async def detect_dead_code(request: AnalysisRequest):
    """
    Detect potentially dead (unreferenced) code.

    Identifies classes and functions that don't appear to be referenced
    anywhere in the analyzed codebase.
    """
    try:
        detector = await _get_detector()
        report = await detector.analyze(
            root_path=request.root_path,
            patterns=request.patterns,
            exclude_patterns=request.exclude_patterns,
        )

        # Filter to only dead_code issues
        dead_code = [
            ap.to_dict()
            for ap in report.anti_patterns
            if ap.pattern_type.value == "dead_code"
        ]

        return JSONResponse(
            content={
                "success": True,
                "count": len(dead_code),
                "dead_code": dead_code,
                "recommendation": (
                    "Verify if code is used: check tests, external imports, dynamic loading. "
                    "Remove if confirmed unused."
                ),
            }
        )

    except Exception as e:
        logger.error("Dead code detection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_health_score",
    error_code_prefix="ANTI_PATTERN",
)
@router.post("/health-score")
async def get_health_score(request: AnalysisRequest):
    """
    Get codebase health score based on anti-pattern analysis.

    Returns a score from 0-100 where:
    - 90-100: Excellent - minimal anti-patterns
    - 70-89: Good - some minor issues
    - 50-69: Fair - several issues need attention
    - 30-49: Poor - significant refactoring needed
    - 0-29: Critical - major architectural issues
    """
    try:
        detector = await _get_detector()
        report = await detector.analyze(
            root_path=request.root_path,
            patterns=request.patterns,
            exclude_patterns=request.exclude_patterns,
        )

        # Determine grade using helper (Issue #315 - reduces nesting from chained if/elif)
        score = report.health_score
        grade, status = _get_health_grade(score)

        return JSONResponse(
            content={
                "success": True,
                "health_score": round(score, 2),
                "grade": grade,
                "status": status,
                "issue_counts": {
                    "critical": report.critical_count,
                    "high": report.high_count,
                    "medium": report.medium_count,
                    "low": report.low_count,
                    "total": report.total_issues,
                },
                "top_recommendations": report.recommendations[:3],
                "analysis_time_seconds": round(report.analysis_time_seconds, 3),
            }
        )

    except Exception as e:
        logger.error("Health score calculation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types")
async def list_anti_pattern_types():
    """
    List all anti-pattern types that can be detected.

    Issue #281: Refactored to use module-level ANTI_PATTERN_TYPE_DEFINITIONS.
    Reduced from 96 to ~10 lines (90% reduction).

    Returns descriptions and thresholds for each type.
    """
    return JSONResponse(
        content={"anti_pattern_types": list(ANTI_PATTERN_TYPE_DEFINITIONS)}
    )
