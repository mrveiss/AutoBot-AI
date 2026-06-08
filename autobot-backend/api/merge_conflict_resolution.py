# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas_code import (
    ApplyResolutionRequest,
    ConflictAnalysisRequest,
    ConflictResolutionRequest,
    MergeConflictAnalyzeResponse,
    MergeConflictApplyResponse,
    MergeConflictCheckResponse,
    MergeConflictRepositoryAnalyzeResponse,
    MergeConflictResolveResponse,
    MergeConflictStrategiesResponse,
    RepositoryAnalysisRequest,
)
from api.schemas_common import DataResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_path
from autobot_shared.time_utils import utc_timestamp
from code_intelligence.merge_conflict_resolver import (
    ConflictBlock,
    ConflictParser,
    ConflictSeverity,
    MergeConflictResolver,
    ResolutionStrategy,
    analyze_repository,
)
from utils.response_helpers import create_success_response

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


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
        "conflict_type": (conflict.conflict_type.value if conflict.conflict_type else None),
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
        "moderate": sum(1 for c in conflicts if c.severity == ConflictSeverity.MODERATE),
        "complex": sum(1 for c in conflicts if c.severity == ConflictSeverity.COMPLEX),
        "critical": sum(1 for c in conflicts if c.severity == ConflictSeverity.CRITICAL),
    }


def _build_resolution_response(
    results: list, file_path: str, safe_mode: bool
) -> DataResponse[MergeConflictResolveResponse]:
    """Build the DataResponse for a successful conflict resolution.

    Helper for resolve_conflicts. Ref: #1088.
    """
    resolutions = [r.to_dict() for r in results]
    avg_confidence = sum(r.confidence_score for r in results) / len(results)
    all_validated = all(r.is_validated for r in results)
    any_require_review = any(r.requires_review for r in results)

    return create_success_response(
        data=MergeConflictResolveResponse(
            status="success",
            file_path=file_path,
            resolved_count=len(results),
            results=resolutions,
            summary={
                "average_confidence": round(avg_confidence, 2),
                "all_validated": all_validated,
                "requires_review": any_require_review,
            },
            safe_mode=safe_mode,
            timestamp=utc_timestamp(),
        )
    )


def _parse_resolution_strategy(
    strategy_str: str | None,
) -> ResolutionStrategy | None:
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


_CONFLICT_ALLOWED_EXTENSIONS = (".py", ".js", ".ts", ".java", ".cpp", ".c")


def _assert_safe_path(user_path: str) -> Path:
    """Resolve and validate *user_path* against allowed roots.

    Raises HTTPException(400) when the path escapes the allowed
    directories, contains null bytes, or is otherwise invalid.
    Prevents path traversal attacks on all merge-conflict endpoints.

    Issue #2848.
    """
    try:
        return validate_path(user_path, must_exist=False)
    except ValueError as exc:
        logger.warning("Path traversal attempt blocked: %s — %s", user_path, exc)
        raise HTTPException(status_code=400, detail="Invalid or disallowed path")


async def _validate_conflict_file(file_path: str) -> Path:
    """Validate *file_path* is safe, exists, and is a supported source file.

    Helper for analyze_conflicts. Ref: #1088, #2848.
    """
    safe = _assert_safe_path(file_path)
    file_exists = await asyncio.to_thread(safe.exists)
    if not file_exists:
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {file_path}",
        )
    if not file_path.endswith(_CONFLICT_ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Only source code files are supported",
        )
    return safe


def _build_no_conflicts_response(file_path: str) -> DataResponse[MergeConflictAnalyzeResponse]:
    """Helper for analyze_conflicts. Ref: #1088."""
    return create_success_response(
        data=MergeConflictAnalyzeResponse(
            status="success",
            file_path=file_path,
            conflict_count=0,
            timestamp=utc_timestamp(),
        ),
        message="No conflicts found in file",
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/analyze", response_model=DataResponse[MergeConflictAnalyzeResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_conflicts",
    error_code_prefix="MERGE_CONFLICT_RESOLUTION",
)
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
    Issue #2848: Path traversal prevention
    """
    safe_path = await _validate_conflict_file(request.file_path)

    try:
        parser = ConflictParser()
        conflicts = await asyncio.to_thread(parser.parse_file, str(safe_path))

        if not conflicts:
            return _build_no_conflicts_response(str(safe_path))

        conflicts_data = [_build_conflict_data(c) for c in conflicts]
        severity_counts = _calculate_severity_distribution(conflicts)

        return create_success_response(
            data=MergeConflictAnalyzeResponse(
                status="success",
                file_path=str(safe_path),
                conflict_count=len(conflicts),
                conflicts=conflicts_data,
                severity_distribution=severity_counts,
                timestamp=utc_timestamp(),
            )
        )

    except Exception as e:
        logger.error("Conflict analysis failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Conflict analysis failed",
        )


@router.post("/resolve", response_model=DataResponse[MergeConflictResolveResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resolve_conflicts",
    error_code_prefix="MERGE_CONFLICT_RESOLUTION",
)
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
    Issue #2848: Path traversal prevention
    """
    safe_path = _assert_safe_path(request.file_path)
    file_exists = await asyncio.to_thread(safe_path.exists)
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
            str(safe_path),
            strategy,
        )

        if not results:
            return create_success_response(
                data=MergeConflictResolveResponse(
                    status="success",
                    file_path=request.file_path,
                    timestamp=utc_timestamp(),
                ),
                message="No conflicts found in file",
            )

        return _build_resolution_response(results, request.file_path, request.safe_mode)

    except Exception as e:
        logger.error("Conflict resolution failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Conflict resolution failed",
        )


@router.post("/analyze-repository", response_model=DataResponse[MergeConflictRepositoryAnalyzeResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_repository_conflicts",
    error_code_prefix="MERGE_CONFLICT_RESOLUTION",
)
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
    Issue #2848: Path traversal prevention
    """
    safe_repo = _assert_safe_path(request.repo_path)
    repo_exists = await asyncio.to_thread(safe_repo.exists)
    if not repo_exists:
        raise HTTPException(
            status_code=400,
            detail=f"Repository path does not exist: {request.repo_path}",
        )

    repo_is_dir = await asyncio.to_thread(safe_repo.is_dir)
    if not repo_is_dir:
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {request.repo_path}",
        )

    try:
        # Analyze repository
        analysis = await asyncio.to_thread(analyze_repository, str(safe_repo))

        return create_success_response(
            data=MergeConflictRepositoryAnalyzeResponse(
                status="success",
                repository=request.repo_path,
                total_files_with_conflicts=analysis["total_files"],
                total_conflicts=analysis["total_conflicts"],
                files=analysis["files"],
                timestamp=utc_timestamp(),
            )
        )

    except Exception as e:
        logger.error("Repository analysis failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Repository analysis failed",
        )


@router.post("/apply", response_model=DataResponse[MergeConflictApplyResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="apply_resolution",
    error_code_prefix="MERGE_CONFLICT_RESOLUTION",
)
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
    Issue #2848: Path traversal prevention
    """
    safe_path = _assert_safe_path(request.file_path)
    file_exists = await asyncio.to_thread(safe_path.exists)
    if not file_exists:
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {request.file_path}",
        )

    try:
        # Create backup if requested
        backup_path = None
        if request.create_backup:
            backup_str = f"{safe_path}.backup.{int(datetime.now(tz=timezone.utc).timestamp())}"
            backup_safe = _assert_safe_path(backup_str)
            await asyncio.to_thread(lambda: __import__("shutil").copy2(str(safe_path), str(backup_safe)))
            backup_path = str(backup_safe)
            logger.info("Created backup at %s", backup_path)

        # Write resolved content
        await asyncio.to_thread(lambda: open(str(safe_path), "w", encoding="utf-8").write(request.resolved_content))

        logger.info("Applied resolution to %s", safe_path)

        return create_success_response(
            data=MergeConflictApplyResponse(
                status="success",
                message="Resolution applied successfully",
                file_path=str(safe_path),
                backup_path=backup_path,
                timestamp=utc_timestamp(),
            )
        )

    except Exception as e:
        logger.error("Failed to apply resolution: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to apply resolution",
        )


@router.get("/strategies", response_model=DataResponse[MergeConflictStrategiesResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_resolution_strategies",
    error_code_prefix="MERGE_CONFLICT_RESOLUTION",
)
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

    return create_success_response(
        data=MergeConflictStrategiesResponse(
            status="success",
            strategies=strategies,
            default_strategy="semantic_merge",
            timestamp=utc_timestamp(),
        )
    )


@router.get("/check", response_model=DataResponse[MergeConflictCheckResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_file_conflicts",
    error_code_prefix="MERGE_CONFLICT_RESOLUTION",
)
async def check_file_conflicts(
    file_path: str = Query(..., description="Path to file to check"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Quick check if file has unresolved conflicts.

    Returns boolean indicating presence of conflict markers.

    Issue #246: Intelligent Merge Conflict Resolution
    Issue #744: Requires admin authentication
    Issue #2848: Path traversal prevention
    """
    safe_path = _assert_safe_path(file_path)
    file_exists = await asyncio.to_thread(safe_path.exists)
    if not file_exists:
        raise HTTPException(
            status_code=400,
            detail=f"File does not exist: {file_path}",
        )

    try:
        parser = ConflictParser()
        has_conflicts = await asyncio.to_thread(parser.has_conflicts, str(safe_path))

        return create_success_response(
            data=MergeConflictCheckResponse(
                status="success",
                file_path=str(safe_path),
                has_conflicts=has_conflicts,
                timestamp=utc_timestamp(),
            )
        )

    except Exception as e:
        logger.error("Conflict check failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Conflict check failed",
        )
