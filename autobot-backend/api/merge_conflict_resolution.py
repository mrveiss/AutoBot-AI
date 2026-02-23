# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Merge Conflict Resolution API Endpoints

Provides REST API for intelligent merge conflict resolution:
- Parse and analyze merge conflicts
- Auto-resolve conflicts with multiple strategies
- Validate resolutions
- Repository-wide conflict analysis

Part of Issue #246 - Intelligent Merge Conflict Resolution
Parent Epic: #217 - Advanced Code Intelligence
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from auth_middleware import check_admin_permission
from backend.code_intelligence.merge_conflict_resolver import (
    ConflictBlock,
    ConflictParser,
    ConflictSeverity,
    MergeConflictResolver,
    ResolutionStrategy,
    analyze_repository,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class ConflictAnalysisRequest(BaseModel):
    """Request model for conflict analysis."""

    file_path: str = Field(
        ...,
        description="Path to file with merge conflicts",
    )


class ConflictResolutionRequest(BaseModel):
    """Request model for conflict resolution."""

    file_path: str = Field(
        ...,
        description="Path to file with merge conflicts",
    )
    strategy: Optional[str] = Field(
        default=None,
        description=(
            "Resolution strategy: semantic_merge, accept_both, pattern_based, "
            "accept_ours, accept_theirs, manual_review"
        ),
    )
    safe_mode: bool = Field(
        default=True,
        description="Enable safe mode (require review for complex conflicts)",
    )
    validate: bool = Field(
        default=True,
        description="Validate resolved code for syntax errors",
    )


class RepositoryAnalysisRequest(BaseModel):
    """Request model for repository-wide conflict analysis."""

    repo_path: str = Field(
        ...,
        description="Path to git repository",
    )


class ApplyResolutionRequest(BaseModel):
    """Request model for applying a resolution to file."""

    file_path: str = Field(..., description="Path to file")
    resolved_content: str = Field(..., description="Resolved file content")
    create_backup: bool = Field(
        default=True,
        description="Create backup before applying",
    )


# =============================================================================
# Helper Functions (Issue #246)
# =============================================================================


def _build_conflict_data(conflict: "ConflictBlock") -> dict:
    """Build conflict data dictionary for API response.

    Helper for analyze_conflicts (Issue #246).
    """
    return {
        "start_line": conflict.start_line,
        "end_line": conflict.end_line,
        "severity": conflict.severity.value,
        "conflict_type": (
            conflict.conflict_type.value if conflict.conflict_type else None
        ),
        "ours_lines": len(conflict.ours_content.split("\n")),
        "theirs_lines": len(conflict.theirs_content.split("\n")),
        "has_base": conflict.base_content is not None,
    }


def _calculate_severity_distribution(conflicts: list) -> dict:
    """Calculate severity distribution for conflicts.

    Helper for analyze_conflicts (Issue #246).
    """
    return {
        "trivial": sum(1 for c in conflicts if c.severity == ConflictSeverity.TRIVIAL),
        "simple": sum(1 for c in conflicts if c.severity == ConflictSeverity.SIMPLE),
        "moderate": sum(
            1 for c in conflicts if c.severity == ConflictSeverity.MODERATE
        ),
        "complex": sum(1 for c in conflicts if c.severity == ConflictSeverity.COMPLEX),
        "critical": sum(
            1 for c in conflicts if c.severity == ConflictSeverity.CRITICAL
        ),
    }


def _build_resolution_response(
    results: list, file_path: str, safe_mode: bool
) -> JSONResponse:
    """Build the JSONResponse for a successful conflict resolution.

    Helper for resolve_conflicts. Ref: #1088.
    """
    resolutions = [r.to_dict() for r in results]
    avg_confidence = sum(r.confidence_score for r in results) / len(results)
    all_validated = all(r.is_validated for r in results)
    any_require_review = any(r.requires_review for r in results)

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "file_path": file_path,
            "resolution_count": len(results),
            "resolutions": resolutions,
            "summary": {
                "average_confidence": round(avg_confidence, 2),
                "all_validated": all_validated,
                "requires_review": any_require_review,
            },
            "safe_mode": safe_mode,
            "timestamp": datetime.now().isoformat(),
        },
    )


def _parse_resolution_strategy(
    strategy_str: Optional[str],
) -> Optional[ResolutionStrategy]:
    """Parse a strategy string into a ResolutionStrategy enum value.

    Helper for resolve_conflicts. Ref: #1088.
    """
    if not strategy_str:
        return None
    try:
        return ResolutionStrategy(strategy_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution strategy: {strategy_str}",
        )


# =============================================================================
# API Endpoints
# =============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_conflicts",
    error_code_prefix="MERGE_CONFLICT",
)
@router.post("/analyze")
async def analyze_conflicts(
    request: ConflictAnalysisRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Analyze merge conflicts in a file.

    Parses git conflict markers and provides detailed analysis:
    - Number of conflicts
    - Conflict types
    - Severity levels
    - Recommended resolution strategies

    Issue #246: Intelligent Merge Conflict Resolution
    Issue #744: Requires admin authentication
    """
    # Validate file exists
    file_exists = await asyncio.to_thread(os.path.exists, request.file_path)
    if not file_exists:
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {request.file_path}",
        )

    # Validate it's a text file
    if not request.file_path.endswith((".py", ".js", ".ts", ".java", ".cpp", ".c")):
        raise HTTPException(
            status_code=400,
            detail="Only source code files are supported",
        )

    try:
        # Parse conflicts
        parser = ConflictParser()
        conflicts = await asyncio.to_thread(parser.parse_file, request.file_path)

        if not conflicts:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "No conflicts found in file",
                    "file_path": request.file_path,
                    "conflict_count": 0,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        # Build analysis response
        conflicts_data = [_build_conflict_data(c) for c in conflicts]
        severity_counts = _calculate_severity_distribution(conflicts)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "file_path": request.file_path,
                "conflict_count": len(conflicts),
                "conflicts": conflicts_data,
                "severity_distribution": severity_counts,
                "timestamp": datetime.now().isoformat(),
            },
        )

    except Exception as e:
        logger.error("Conflict analysis failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Conflict analysis failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resolve_conflicts",
    error_code_prefix="MERGE_CONFLICT",
)
@router.post("/resolve")
async def resolve_conflicts(
    request: ConflictResolutionRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Resolve merge conflicts in a file.

    Applies intelligent resolution strategies:
    - Semantic merge: AI combines both changes
    - Accept both: Preserves both sides (non-conflicting)
    - Pattern-based: Uses historical patterns
    - Accept ours/theirs: Takes one side

    Returns resolved content with confidence scores and validation results.

    Issue #246: Intelligent Merge Conflict Resolution
    Issue #744: Requires admin authentication
    """
    # Validate file exists
    file_exists = await asyncio.to_thread(os.path.exists, request.file_path)
    if not file_exists:
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {request.file_path}",
        )

    strategy = _parse_resolution_strategy(request.strategy)

    try:
        resolver = MergeConflictResolver(
            safe_mode=request.safe_mode,
            require_validation=request.validate,
        )

        results = await asyncio.to_thread(
            resolver.resolve_file,
            request.file_path,
            strategy,
        )

        if not results:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "No conflicts found in file",
                    "file_path": request.file_path,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        return _build_resolution_response(results, request.file_path, request.safe_mode)

    except Exception as e:
        logger.error("Conflict resolution failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Conflict resolution failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_repository",
    error_code_prefix="MERGE_CONFLICT",
)
@router.post("/analyze-repository")
async def analyze_repository_conflicts(
    request: RepositoryAnalysisRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Analyze entire repository for merge conflicts.

    Scans all source files and provides summary:
    - Total files with conflicts
    - Total conflict count
    - Severity distribution
    - Per-file breakdown

    Issue #246: Intelligent Merge Conflict Resolution
    Issue #744: Requires admin authentication
    """
    # Validate repository path
    repo_exists = await asyncio.to_thread(os.path.exists, request.repo_path)
    if not repo_exists:
        raise HTTPException(
            status_code=400,
            detail=f"Repository path does not exist: {request.repo_path}",
        )

    repo_is_dir = await asyncio.to_thread(os.path.isdir, request.repo_path)
    if not repo_is_dir:
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {request.repo_path}",
        )

    try:
        # Analyze repository
        analysis = await asyncio.to_thread(analyze_repository, request.repo_path)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "repository": request.repo_path,
                "total_files_with_conflicts": analysis["total_files"],
                "total_conflicts": analysis["total_conflicts"],
                "files": analysis["files"],
                "timestamp": datetime.now().isoformat(),
            },
        )

    except Exception as e:
        logger.error("Repository analysis failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Repository analysis failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="apply_resolution",
    error_code_prefix="MERGE_CONFLICT",
)
@router.post("/apply")
async def apply_resolution(
    request: ApplyResolutionRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Apply a resolved conflict to file.

    Writes the resolved content back to the original file.
    Optionally creates a backup before applying.

    Issue #246: Intelligent Merge Conflict Resolution
    Issue #744: Requires admin authentication
    """
    # Validate file exists
    file_exists = await asyncio.to_thread(os.path.exists, request.file_path)
    if not file_exists:
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {request.file_path}",
        )

    try:
        # Create backup if requested
        backup_path = None
        if request.create_backup:
            backup_path = (
                f"{request.file_path}.backup.{int(datetime.now().timestamp())}"
            )
            await asyncio.to_thread(
                lambda: __import__("shutil").copy2(request.file_path, backup_path)
            )
            logger.info("Created backup at %s", backup_path)

        # Write resolved content
        await asyncio.to_thread(
            lambda: open(request.file_path, "w", encoding="utf-8").write(
                request.resolved_content
            )
        )

        logger.info("Applied resolution to %s", request.file_path)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Resolution applied successfully",
                "file_path": request.file_path,
                "backup_path": backup_path,
                "timestamp": datetime.now().isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to apply resolution: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply resolution: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_resolution_strategies",
    error_code_prefix="MERGE_CONFLICT",
)
@router.get("/strategies")
async def get_resolution_strategies(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get available resolution strategies.

    Returns list of all resolution strategies with descriptions.

    Issue #246: Intelligent Merge Conflict Resolution
    Issue #744: Requires admin authentication
    """
    strategies = {
        "semantic_merge": {
            "name": "Semantic Merge",
            "description": "AI analyzes both changes and combines them intelligently",
            "use_case": "When both changes add valuable logic",
            "confidence": "medium",
        },
        "accept_both": {
            "name": "Accept Both",
            "description": "Keeps both changes (when non-conflicting)",
            "use_case": "Non-overlapping additions (imports, functions)",
            "confidence": "high",
        },
        "pattern_based": {
            "name": "Pattern-Based",
            "description": "Uses historical patterns for common conflicts",
            "use_case": "Recurring conflict patterns",
            "confidence": "medium-high",
        },
        "accept_ours": {
            "name": "Accept Ours",
            "description": "Keeps current branch changes",
            "use_case": "When current branch is correct",
            "confidence": "high",
        },
        "accept_theirs": {
            "name": "Accept Theirs",
            "description": "Keeps incoming branch changes",
            "use_case": "When incoming branch is correct",
            "confidence": "high",
        },
        "manual_review": {
            "name": "Manual Review",
            "description": "Requires human review and resolution",
            "use_case": "Complex or critical conflicts",
            "confidence": "n/a",
        },
    }

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "strategies": strategies,
            "default_strategy": "semantic_merge",
            "timestamp": datetime.now().isoformat(),
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_file_conflicts",
    error_code_prefix="MERGE_CONFLICT",
)
@router.get("/check")
async def check_file_conflicts(
    file_path: str = Query(..., description="Path to file to check"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Quick check if file has unresolved conflicts.

    Returns boolean indicating presence of conflict markers.

    Issue #246: Intelligent Merge Conflict Resolution
    Issue #744: Requires admin authentication
    """
    # Validate file exists
    file_exists = await asyncio.to_thread(os.path.exists, file_path)
    if not file_exists:
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {file_path}",
        )

    try:
        parser = ConflictParser()
        has_conflicts = await asyncio.to_thread(parser.has_conflicts, file_path)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "file_path": file_path,
                "has_conflicts": has_conflicts,
                "timestamp": datetime.now().isoformat(),
            },
        )

    except Exception as e:
        logger.error("Conflict check failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Conflict check failed: {str(e)}",
        )
