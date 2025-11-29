# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Intelligence API Endpoints

Provides REST API for code analysis features including:
- Anti-pattern detection
- Code smell identification
- Codebase health metrics

Part of Issue #221 - Anti-Pattern Detection System
Parent Epic: #217 - Advanced Code Intelligence
"""

import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.code_intelligence.anti_pattern_detector import (
    AntiPatternDetector,
    AntiPatternSeverity,
)
from src.code_intelligence.redis_optimizer import (
    OptimizationSeverity,
    RedisOptimizer,
)
from src.code_intelligence.security_analyzer import (
    SecurityAnalyzer,
    SecuritySeverity,
    get_vulnerability_types,
)
from src.code_intelligence.performance_analyzer import (
    PerformanceAnalyzer,
    PerformanceSeverity,
    get_performance_issue_types,
)
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter()


class AnalysisRequest(BaseModel):
    """Request model for code analysis."""

    path: str = Field(
        ...,
        description="Directory path to analyze",
    )
    exclude_dirs: Optional[list] = Field(
        default=None,
        description="Directories to exclude from analysis",
    )
    min_severity: Optional[str] = Field(
        default=None,
        description="Minimum severity level to include (info, low, medium, high, critical)",
    )


class QuickScanRequest(BaseModel):
    """Request for quick single-file scan."""

    file_path: str = Field(..., description="Path to Python file to analyze")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_codebase",
    error_code_prefix="CODE_INTEL",
)
@router.post("/analyze")
async def analyze_codebase(request: AnalysisRequest):
    """
    Analyze a codebase for anti-patterns and code smells.

    Scans all Python files in the specified directory and returns
    a comprehensive report of detected anti-patterns.
    """
    # Validate path exists
    if not os.path.exists(request.path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {request.path}",
        )

    if not os.path.isdir(request.path):
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {request.path}",
        )

    try:
        detector = AntiPatternDetector(exclude_dirs=request.exclude_dirs)
        report = detector.analyze_directory(request.path)

        # Filter by severity if specified
        if request.min_severity:
            severity_order = ["info", "low", "medium", "high", "critical"]
            try:
                min_idx = severity_order.index(request.min_severity.lower())
                filtered_patterns = [
                    p
                    for p in report.anti_patterns
                    if severity_order.index(p.severity.value) >= min_idx
                ]
                report.anti_patterns = filtered_patterns
            except ValueError:
                logger.warning(f"Invalid severity filter: {request.min_severity}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "report": report.to_dict(),
            },
        )

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="quick_scan",
    error_code_prefix="CODE_INTEL",
)
@router.post("/scan-file")
async def quick_scan_file(request: QuickScanRequest):
    """
    Quick scan a single Python file for anti-patterns.

    Faster than full codebase analysis when you only need
    to check one file.
    """
    if not os.path.exists(request.file_path):
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {request.file_path}",
        )

    if not request.file_path.endswith(".py"):
        raise HTTPException(
            status_code=400,
            detail="Only Python (.py) files are supported",
        )

    try:
        detector = AntiPatternDetector()
        results = detector.analyze_file(request.file_path)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "file_path": request.file_path,
                "patterns": [p.to_dict() for p in results["patterns"]],
                "statistics": {
                    "class_count": results["class_count"],
                    "function_count": results["function_count"],
                    "issues_found": len(results["patterns"]),
                },
            },
        )

    except Exception as e:
        logger.error(f"File scan failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Scan failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_health_score",
    error_code_prefix="CODE_INTEL",
)
@router.get("/health-score")
async def get_codebase_health_score(
    path: str = Query(..., description="Directory path to analyze"),
):
    """
    Get a simple health score for a codebase.

    Returns a score from 0-100 based on the number and severity
    of anti-patterns detected.
    """
    if not os.path.exists(path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {path}",
        )

    try:
        detector = AntiPatternDetector()
        report = detector.analyze_directory(path)

        # Calculate health score
        # Start with 100 and subtract based on issues
        score = 100.0

        severity_penalties = {
            AntiPatternSeverity.INFO: 0.5,
            AntiPatternSeverity.LOW: 1,
            AntiPatternSeverity.MEDIUM: 2,
            AntiPatternSeverity.HIGH: 4,
            AntiPatternSeverity.CRITICAL: 8,
        }

        for pattern in report.anti_patterns:
            penalty = severity_penalties.get(pattern.severity, 1)
            score -= penalty

        # Normalize to 0-100
        score = max(0, min(100, score))

        # Determine grade
        if score >= 90:
            grade = "A"
        elif score >= 80:
            grade = "B"
        elif score >= 70:
            grade = "C"
        elif score >= 60:
            grade = "D"
        else:
            grade = "F"

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "path": path,
                "health_score": round(score, 1),
                "grade": grade,
                "total_issues": len(report.anti_patterns),
                "files_analyzed": report.total_files,
                "severity_breakdown": report.severity_distribution,
            },
        )

    except Exception as e:
        logger.error(f"Health score calculation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pattern_types",
    error_code_prefix="CODE_INTEL",
)
@router.get("/pattern-types")
async def get_supported_pattern_types():
    """
    Get list of supported anti-pattern types.

    Returns all pattern types that the detector can identify,
    along with their descriptions and thresholds.
    """
    pattern_info = {
        # Bloaters
        "god_class": {
            "name": "God Class",
            "category": "bloater",
            "description": "Class with too many methods or responsibilities",
            "threshold": f">{AntiPatternDetector.GOD_CLASS_METHOD_THRESHOLD} methods "
            f"or >{AntiPatternDetector.GOD_CLASS_LINE_THRESHOLD} lines",
        },
        "long_method": {
            "name": "Long Method",
            "category": "bloater",
            "description": "Function with too many lines",
            "threshold": f">{AntiPatternDetector.LONG_METHOD_THRESHOLD} lines",
        },
        "long_parameter_list": {
            "name": "Long Parameter List",
            "category": "bloater",
            "description": "Function with too many parameters",
            "threshold": f">{AntiPatternDetector.LONG_PARAMETER_THRESHOLD} parameters",
        },
        "large_file": {
            "name": "Large File",
            "category": "bloater",
            "description": "File with excessive lines of code",
            "threshold": f">{AntiPatternDetector.LARGE_FILE_THRESHOLD} lines",
        },
        "deep_nesting": {
            "name": "Deep Nesting",
            "category": "bloater",
            "description": "Code with excessive nesting levels",
            "threshold": f">{AntiPatternDetector.DEEP_NESTING_THRESHOLD} levels",
        },
        "data_clumps": {
            "name": "Data Clumps",
            "category": "bloater",
            "description": "Groups of parameters that always appear together",
            "threshold": "3+ common parameters across functions",
        },
        # Couplers
        "circular_dependency": {
            "name": "Circular Dependency",
            "category": "coupler",
            "description": "Modules that import each other in a cycle",
            "threshold": "Any cycle detected",
        },
        "feature_envy": {
            "name": "Feature Envy",
            "category": "coupler",
            "description": "Method uses another object's data more than its own",
            "threshold": "More external accesses than self accesses",
        },
        "message_chains": {
            "name": "Message Chains",
            "category": "coupler",
            "description": "Long chains of method calls (a.b().c().d())",
            "threshold": f">{AntiPatternDetector.MESSAGE_CHAIN_THRESHOLD} chained calls",
        },
        # Dispensables
        "dead_code": {
            "name": "Dead Code",
            "category": "dispensable",
            "description": "Unreachable or unused code",
            "threshold": "Code after return/raise, empty except blocks",
        },
        "lazy_class": {
            "name": "Lazy Class",
            "category": "dispensable",
            "description": "Class that does too little",
            "threshold": f"<={AntiPatternDetector.LAZY_CLASS_METHOD_THRESHOLD} methods",
        },
        # Naming Issues
        "inconsistent_naming": {
            "name": "Inconsistent Naming",
            "category": "naming",
            "description": "Mixed naming conventions (snake_case vs camelCase)",
            "threshold": ">20% mixing of styles",
        },
        "single_letter_variable": {
            "name": "Single Letter Variable",
            "category": "naming",
            "description": "Non-descriptive single-letter variable names",
            "threshold": "Single letter (except i,j,k,n,x,y,z in loops)",
        },
        "magic_number": {
            "name": "Magic Number",
            "category": "naming",
            "description": "Unexplained numeric literals repeated in code",
            "threshold": f"Same number appears >{AntiPatternDetector.MAGIC_NUMBER_THRESHOLD} times",
        },
        # Other
        "complex_conditional": {
            "name": "Complex Conditional",
            "category": "other",
            "description": "Overly complex boolean expressions",
            "threshold": f">{AntiPatternDetector.COMPLEX_CONDITIONAL_THRESHOLD} conditions",
        },
        "missing_docstring": {
            "name": "Missing Docstring",
            "category": "other",
            "description": "Public function or class without documentation",
            "threshold": "No docstring on public entity",
        },
    }

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "pattern_types": pattern_info,
            "total_types": len(pattern_info),
        },
    )


# =============================================================================
# Redis Optimization Endpoints (Issue #220)
# =============================================================================


class RedisAnalysisRequest(BaseModel):
    """Request model for Redis optimization analysis."""

    path: str = Field(
        ...,
        description="Directory or file path to analyze for Redis optimizations",
    )
    exclude_patterns: Optional[list] = Field(
        default=None,
        description="Glob patterns to exclude from analysis",
    )
    min_severity: Optional[str] = Field(
        default=None,
        description="Minimum severity level to include (info, low, medium, high, critical)",
    )


class RedisFileScanRequest(BaseModel):
    """Request for scanning a single file for Redis optimizations."""

    file_path: str = Field(..., description="Path to Python file to analyze")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_redis_usage",
    error_code_prefix="CODE_INTEL",
)
@router.post("/redis/analyze")
async def analyze_redis_usage_endpoint(request: RedisAnalysisRequest):
    """
    Analyze Redis usage patterns in a codebase.

    Identifies optimization opportunities including:
    - Pipeline opportunities (sequential operations that can be batched)
    - Lua script candidates (complex atomic operations)
    - Data structure improvements
    - Connection management patterns
    - Cache invalidation strategies

    Part of Issue #220 - Redis Operation Optimizer
    """
    if not os.path.exists(request.path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {request.path}",
        )

    try:
        optimizer = RedisOptimizer(project_root=request.path)

        if os.path.isfile(request.path):
            results = optimizer.analyze_file(request.path)
        else:
            results = optimizer.analyze_directory(
                request.path,
                exclude_patterns=request.exclude_patterns,
            )

        # Filter by severity if specified
        if request.min_severity:
            severity_order = ["info", "low", "medium", "high", "critical"]
            try:
                min_idx = severity_order.index(request.min_severity.lower())
                results = [
                    r
                    for r in results
                    if severity_order.index(r.severity.value) >= min_idx
                ]
            except ValueError:
                logger.warning(f"Invalid severity filter: {request.min_severity}")

        # Get summary
        optimizer.results = results
        summary = optimizer.get_summary()

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "path": request.path,
                "optimizations": [r.to_dict() for r in results],
                "summary": summary,
            },
        )

    except Exception as e:
        logger.error(f"Redis analysis failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Redis analysis failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_redis_file",
    error_code_prefix="CODE_INTEL",
)
@router.post("/redis/scan-file")
async def scan_redis_file(request: RedisFileScanRequest):
    """
    Quick scan a single Python file for Redis optimization opportunities.

    Faster than full codebase analysis when you only need
    to check one file's Redis usage.
    """
    if not os.path.exists(request.file_path):
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {request.file_path}",
        )

    if not request.file_path.endswith(".py"):
        raise HTTPException(
            status_code=400,
            detail="Only Python (.py) files are supported",
        )

    try:
        optimizer = RedisOptimizer()
        results = optimizer.analyze_file(request.file_path)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "file_path": request.file_path,
                "optimizations": [r.to_dict() for r in results],
                "total_findings": len(results),
                "severity_breakdown": {
                    sev.value: len([r for r in results if r.severity == sev])
                    for sev in OptimizationSeverity
                },
            },
        )

    except Exception as e:
        logger.error(f"Redis file scan failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Scan failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_optimization_types",
    error_code_prefix="CODE_INTEL",
)
@router.get("/redis/optimization-types")
async def get_redis_optimization_types():
    """
    Get list of supported Redis optimization types.

    Returns all optimization types that the analyzer can identify,
    along with their descriptions and recommendations.
    """
    optimization_info = {
        # Pipeline opportunities
        "sequential_gets": {
            "name": "Sequential GETs",
            "category": "pipeline",
            "description": "Multiple GET operations that can be batched with MGET or pipeline",
            "recommendation": "Use redis.mget(keys) or pipeline() for batching",
        },
        "sequential_sets": {
            "name": "Sequential SETs",
            "category": "pipeline",
            "description": "Multiple SET operations that can be batched with MSET or pipeline",
            "recommendation": "Use redis.mset(mapping) or pipeline() for batching",
        },
        "loop_operations": {
            "name": "Loop Operations",
            "category": "pipeline",
            "description": "Redis operations inside loops causing O(N) network round-trips",
            "recommendation": "Collect keys first, then batch with pipeline()",
        },
        # Lua script candidates
        "read_modify_write": {
            "name": "Read-Modify-Write",
            "category": "lua_script",
            "description": "GET followed by SET - race condition risk",
            "recommendation": "Use Lua script or WATCH/MULTI/EXEC for atomicity",
        },
        "conditional_set": {
            "name": "Conditional SET",
            "category": "lua_script",
            "description": "SET based on condition - potential race",
            "recommendation": "Use SETNX, SET NX, or Lua script",
        },
        # Data structure optimizations
        "string_to_hash": {
            "name": "String to Hash",
            "category": "data_structure",
            "description": "Multiple related string keys could be a Hash",
            "recommendation": "Use HSET/HGET with single key for related data",
        },
        "inefficient_scan": {
            "name": "Inefficient Scan",
            "category": "data_structure",
            "description": "KEYS command blocks Redis - use SCAN instead",
            "recommendation": "Replace KEYS with SCAN for non-blocking iteration",
        },
        "missing_expiry": {
            "name": "Missing Expiry",
            "category": "data_structure",
            "description": "SET without TTL - potential memory leak",
            "recommendation": "Add ex=<seconds> parameter to SET operations",
        },
        # Connection patterns
        "connection_per_request": {
            "name": "Connection Per Request",
            "category": "connection",
            "description": "Direct redis.Redis() instantiation - should use pool",
            "recommendation": "Use get_redis_client() from src.utils.redis_client",
        },
        "blocking_in_async": {
            "name": "Blocking in Async",
            "category": "connection",
            "description": "Sync Redis calls in async function - blocks event loop",
            "recommendation": "Use async Redis client with await",
        },
        # Cache patterns
        "cache_stampede_risk": {
            "name": "Cache Stampede Risk",
            "category": "cache",
            "description": "Cache miss pattern without lock protection",
            "recommendation": "Use distributed lock or probabilistic early expiration",
        },
    }

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "optimization_types": optimization_info,
            "total_types": len(optimization_info),
            "categories": [
                "pipeline",
                "lua_script",
                "data_structure",
                "connection",
                "cache",
            ],
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_health",
    error_code_prefix="CODE_INTEL",
)
@router.get("/redis/health-score")
async def get_redis_usage_health_score(
    path: str = Query(..., description="Directory path to analyze"),
):
    """
    Get a Redis usage health score for a codebase.

    Returns a score from 0-100 based on the number and severity
    of optimization opportunities detected. Lower scores indicate
    more room for optimization.
    """
    if not os.path.exists(path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {path}",
        )

    try:
        optimizer = RedisOptimizer(project_root=path)
        results = optimizer.analyze_directory(path)

        # Calculate health score
        # Start with 100 and subtract based on issues
        score = 100.0

        severity_penalties = {
            OptimizationSeverity.INFO: 0.5,
            OptimizationSeverity.LOW: 1,
            OptimizationSeverity.MEDIUM: 2,
            OptimizationSeverity.HIGH: 4,
            OptimizationSeverity.CRITICAL: 8,
        }

        for result in results:
            penalty = severity_penalties.get(result.severity, 1)
            score -= penalty

        # Normalize to 0-100
        score = max(0, min(100, score))

        # Determine grade
        if score >= 90:
            grade = "A"
            status = "Excellent Redis usage patterns"
        elif score >= 80:
            grade = "B"
            status = "Good Redis usage with minor improvements possible"
        elif score >= 70:
            grade = "C"
            status = "Fair Redis usage - several optimizations recommended"
        elif score >= 60:
            grade = "D"
            status = "Poor Redis usage - significant optimization needed"
        else:
            grade = "F"
            status = "Critical Redis usage issues - immediate attention required"

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "path": path,
                "health_score": round(score, 1),
                "grade": grade,
                "status_message": status,
                "total_optimizations": len(results),
                "files_with_issues": len(set(r.file_path for r in results)),
                "severity_breakdown": {
                    sev.value: len([r for r in results if r.severity == sev])
                    for sev in OptimizationSeverity
                },
                "category_breakdown": optimizer.get_summary().get("by_type", {}),
            },
        )

    except Exception as e:
        logger.error(f"Redis health score calculation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}",
        )


# ============================================================================
# Security Analysis Endpoints (Issue #219)
# ============================================================================


class SecurityAnalysisRequest(BaseModel):
    """Request model for security analysis."""

    path: str = Field(
        ...,
        description="Directory path to analyze for security vulnerabilities",
    )
    exclude_patterns: Optional[list] = Field(
        default=None,
        description="Patterns to exclude from analysis (e.g., ['test_*', 'venv'])",
    )
    min_severity: Optional[str] = Field(
        default=None,
        description="Minimum severity level to include (info, low, medium, high, critical)",
    )


class SecurityFileScanRequest(BaseModel):
    """Request for single file security scan."""

    file_path: str = Field(..., description="Path to Python file to analyze")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="security_analyze",
    error_code_prefix="SECURITY",
)
@router.post("/security/analyze")
async def security_analyze(request: SecurityAnalysisRequest):
    """
    Analyze a codebase for security vulnerabilities.

    Scans all Python files in the specified directory for:
    - SQL injection patterns
    - Hardcoded secrets and credentials
    - Weak cryptography usage
    - Command injection risks
    - Insecure deserialization
    - Missing input validation
    - And more (OWASP Top 10 mapping)
    """
    if not os.path.exists(request.path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {request.path}",
        )

    if not os.path.isdir(request.path):
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {request.path}",
        )

    try:
        analyzer = SecurityAnalyzer(
            project_root=request.path,
            exclude_patterns=request.exclude_patterns,
        )
        results = analyzer.analyze_directory()

        # Filter by severity if specified
        if request.min_severity:
            severity_order = ["info", "low", "medium", "high", "critical"]
            try:
                min_idx = severity_order.index(request.min_severity.lower())
                results = [
                    r
                    for r in results
                    if severity_order.index(r.severity.value) >= min_idx
                ]
            except ValueError:
                pass

        summary = analyzer.get_summary()

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "path": request.path,
                "summary": summary,
                "findings": [r.to_dict() for r in results],
                "total_findings": len(results),
            },
        )

    except Exception as e:
        logger.error(f"Security analysis failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Security analysis failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="security_scan_file",
    error_code_prefix="SECURITY",
)
@router.post("/security/scan-file")
async def security_scan_file(request: SecurityFileScanRequest):
    """
    Scan a single file for security vulnerabilities.

    Quick scan of a single Python file for security issues.
    """
    if not os.path.exists(request.file_path):
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {request.file_path}",
        )

    if not request.file_path.endswith(".py"):
        raise HTTPException(
            status_code=400,
            detail="Only Python files (.py) are supported",
        )

    try:
        analyzer = SecurityAnalyzer()
        results = analyzer.analyze_file(request.file_path)

        # Group by vulnerability type
        by_type = {}
        for result in results:
            vtype = result.vulnerability_type.value
            if vtype not in by_type:
                by_type[vtype] = []
            by_type[vtype].append(result.to_dict())

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "file": request.file_path,
                "findings": [r.to_dict() for r in results],
                "total_findings": len(results),
                "by_type": by_type,
                "severity_counts": {
                    sev.value: len([r for r in results if r.severity == sev])
                    for sev in SecuritySeverity
                },
            },
        )

    except Exception as e:
        logger.error(f"Security file scan failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"File scan failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vulnerability_types",
    error_code_prefix="SECURITY",
)
@router.get("/security/vulnerability-types")
async def list_vulnerability_types():
    """
    Get all supported vulnerability types with OWASP mappings.

    Returns list of all vulnerability types that can be detected,
    along with their OWASP Top 10 2021 category mappings.
    """
    vuln_types = get_vulnerability_types()

    # Group by OWASP category
    by_owasp = {}
    for vt in vuln_types:
        owasp = vt["owasp"]
        if owasp not in by_owasp:
            by_owasp[owasp] = []
        by_owasp[owasp].append(vt["type"])

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "vulnerability_types": vuln_types,
            "total_types": len(vuln_types),
            "by_owasp_category": by_owasp,
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="security_score",
    error_code_prefix="SECURITY",
)
@router.get("/security/score")
async def get_security_score(
    path: str = Query(..., description="Directory path to analyze"),
):
    """
    Get security health score for a codebase.

    Returns a score from 0-100 based on the number and severity
    of security vulnerabilities detected. Higher scores indicate
    better security posture.
    """
    if not os.path.exists(path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {path}",
        )

    try:
        analyzer = SecurityAnalyzer(project_root=path)
        analyzer.analyze_directory()
        summary = analyzer.get_summary()

        # Generate grade
        score = summary["security_score"]
        if score >= 90:
            grade = "A"
            status = "Excellent security posture"
        elif score >= 80:
            grade = "B"
            status = "Good security with minor issues"
        elif score >= 70:
            grade = "C"
            status = "Fair security - several vulnerabilities to address"
        elif score >= 50:
            grade = "D"
            status = "Poor security - significant vulnerabilities present"
        else:
            grade = "F"
            status = "Critical security issues - immediate attention required"

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "path": path,
                "security_score": score,
                "grade": grade,
                "risk_level": summary["risk_level"],
                "status_message": status,
                "total_findings": summary["total_findings"],
                "critical_issues": summary["critical_issues"],
                "high_issues": summary["high_issues"],
                "files_analyzed": summary["files_analyzed"],
                "severity_breakdown": summary["by_severity"],
                "owasp_breakdown": summary["by_owasp_category"],
            },
        )

    except Exception as e:
        logger.error(f"Security score calculation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Security score calculation failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="security_report",
    error_code_prefix="SECURITY",
)
@router.get("/security/report")
async def get_security_report(
    path: str = Query(..., description="Directory path to analyze"),
    format: str = Query(default="json", description="Report format: json or markdown"),
):
    """
    Generate a comprehensive security report.

    Returns a detailed security analysis report including:
    - Executive summary
    - All findings with remediation advice
    - OWASP Top 10 mapping
    - Top recommendations
    """
    if not os.path.exists(path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {path}",
        )

    try:
        analyzer = SecurityAnalyzer(project_root=path)
        analyzer.analyze_directory()
        report = analyzer.generate_report(format=format)

        if format == "markdown":
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "timestamp": datetime.now().isoformat(),
                    "path": path,
                    "format": "markdown",
                    "report": report,
                },
            )
        else:
            import json

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "timestamp": datetime.now().isoformat(),
                    "path": path,
                    "format": "json",
                    "report": json.loads(report),
                },
            )

    except Exception as e:
        logger.error(f"Security report generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {str(e)}",
        )


# ============================================================================
# Performance Analysis Endpoints (Issue #222)
# ============================================================================


class PerformanceAnalysisRequest(BaseModel):
    """Request model for performance analysis."""

    path: str = Field(
        ...,
        description="Directory path to analyze for performance issues",
    )
    exclude_patterns: Optional[list] = Field(
        default=None,
        description="Patterns to exclude from analysis",
    )
    min_severity: Optional[str] = Field(
        default=None,
        description="Minimum severity level to include",
    )


class PerformanceFileScanRequest(BaseModel):
    """Request for single file performance scan."""

    file_path: str = Field(..., description="Path to Python file to analyze")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="performance_analyze",
    error_code_prefix="PERFORMANCE",
)
@router.post("/performance/analyze")
async def performance_analyze(request: PerformanceAnalysisRequest):
    """
    Analyze a codebase for performance issues.

    Detects:
    - N+1 query patterns
    - Nested loop complexity
    - Sync operations in async context
    - Sequential awaits (should be parallel)
    - String concatenation in loops
    - Inefficient data structures
    """
    if not os.path.exists(request.path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {request.path}",
        )

    if not os.path.isdir(request.path):
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {request.path}",
        )

    try:
        analyzer = PerformanceAnalyzer(
            project_root=request.path,
            exclude_patterns=request.exclude_patterns,
        )
        results = analyzer.analyze_directory()

        # Filter by severity if specified
        if request.min_severity:
            severity_order = ["info", "low", "medium", "high", "critical"]
            try:
                min_idx = severity_order.index(request.min_severity.lower())
                results = [
                    r
                    for r in results
                    if severity_order.index(r.severity.value) >= min_idx
                ]
            except ValueError:
                pass

        summary = analyzer.get_summary()

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "path": request.path,
                "summary": summary,
                "findings": [r.to_dict() for r in results],
                "total_findings": len(results),
            },
        )

    except Exception as e:
        logger.error(f"Performance analysis failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Performance analysis failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="performance_scan_file",
    error_code_prefix="PERFORMANCE",
)
@router.post("/performance/scan-file")
async def performance_scan_file(request: PerformanceFileScanRequest):
    """
    Scan a single file for performance issues.

    Quick scan of a single Python file for performance bottlenecks.
    """
    if not os.path.exists(request.file_path):
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {request.file_path}",
        )

    if not request.file_path.endswith(".py"):
        raise HTTPException(
            status_code=400,
            detail="Only Python files (.py) are supported",
        )

    try:
        analyzer = PerformanceAnalyzer()
        results = analyzer.analyze_file(request.file_path)

        # Group by issue type
        by_type = {}
        for result in results:
            itype = result.issue_type.value
            if itype not in by_type:
                by_type[itype] = []
            by_type[itype].append(result.to_dict())

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "file": request.file_path,
                "findings": [r.to_dict() for r in results],
                "total_findings": len(results),
                "by_type": by_type,
                "severity_counts": {
                    sev.value: len([r for r in results if r.severity == sev])
                    for sev in PerformanceSeverity
                },
            },
        )

    except Exception as e:
        logger.error(f"Performance file scan failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"File scan failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_issue_types",
    error_code_prefix="PERFORMANCE",
)
@router.get("/performance/issue-types")
async def list_performance_issue_types():
    """
    Get all supported performance issue types.

    Returns list of all performance issues that can be detected,
    along with their categories.
    """
    issue_types = get_performance_issue_types()

    # Group by category
    by_category = {}
    for it in issue_types:
        cat = it["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(it["type"])

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "issue_types": issue_types,
            "total_types": len(issue_types),
            "by_category": by_category,
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="performance_score",
    error_code_prefix="PERFORMANCE",
)
@router.get("/performance/score")
async def get_performance_score(
    path: str = Query(..., description="Directory path to analyze"),
):
    """
    Get performance health score for a codebase.

    Returns a score from 0-100 based on the number and severity
    of performance issues detected. Higher scores indicate
    better performance.
    """
    if not os.path.exists(path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {path}",
        )

    try:
        analyzer = PerformanceAnalyzer(project_root=path)
        analyzer.analyze_directory()
        summary = analyzer.get_summary()

        score = summary["performance_score"]
        grade = summary["grade"]

        if score >= 90:
            status = "Excellent performance - minimal issues"
        elif score >= 80:
            status = "Good performance with minor optimizations possible"
        elif score >= 70:
            status = "Fair performance - several optimizations recommended"
        elif score >= 50:
            status = "Performance issues detected - optimization needed"
        else:
            status = "Critical performance problems - immediate action required"

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "path": path,
                "performance_score": score,
                "grade": grade,
                "status_message": status,
                "total_issues": summary["total_issues"],
                "critical_issues": summary["critical_issues"],
                "high_issues": summary["high_issues"],
                "files_analyzed": summary["files_analyzed"],
                "severity_breakdown": summary["by_severity"],
                "top_issues": summary["top_issues"],
            },
        )

    except Exception as e:
        logger.error(f"Performance score calculation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Performance score calculation failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="performance_report",
    error_code_prefix="PERFORMANCE",
)
@router.get("/performance/report")
async def get_performance_report(
    path: str = Query(..., description="Directory path to analyze"),
    format: str = Query(default="json", description="Report format: json or markdown"),
):
    """
    Generate a comprehensive performance report.

    Returns a detailed performance analysis report including:
    - Summary with score and grade
    - All findings with optimization recommendations
    - Complexity analysis
    - Top recommendations
    """
    if not os.path.exists(path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {path}",
        )

    try:
        analyzer = PerformanceAnalyzer(project_root=path)
        analyzer.analyze_directory()
        report = analyzer.generate_report(format=format)

        if format == "markdown":
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "timestamp": datetime.now().isoformat(),
                    "path": path,
                    "format": "markdown",
                    "report": report,
                },
            )
        else:
            import json

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "timestamp": datetime.now().isoformat(),
                    "path": path,
                    "format": "json",
                    "report": json.loads(report),
                },
            )

    except Exception as e:
        logger.error(f"Performance report generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {str(e)}",
        )
