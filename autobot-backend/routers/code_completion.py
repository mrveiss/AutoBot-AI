# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Code Completion API Router (Issue #903)

Endpoints for pattern extraction and code completion.
"""

from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from models.code_pattern import CodePattern
from services.context_analyzer import ContextAnalyzer
from services.pattern_extractor import PatternExtractor
from user_management.database import db_session_context

logger = get_logger(__name__)

router = APIRouter(tags=["code-completion"])

get_context_analyzer = lazy_singleton(ContextAnalyzer)


# =============================================================================
# Request/Response Models
# =============================================================================


class ExtractionRequest(BaseModel):
    """Request to trigger pattern extraction."""

    languages: List[str] | None = Field(
        default=["python", "typescript", "vue"],
        description="Languages to extract patterns from",
    )
    cache_hot_patterns: bool = Field(default=True, description="Cache top patterns to Redis")


class ExtractionResponse(BaseModel):
    """Response from pattern extraction."""

    status: str
    patterns_extracted: int
    statistics: Dict[str, int]
    message: str


class PatternResponse(BaseModel):
    """Pattern data for API response."""

    id: int
    pattern_type: str
    language: str
    category: str | None
    signature: str
    body: str | None
    frequency: int
    acceptance_rate: float
    file_path: str | None
    line_number: int | None


class PatternListResponse(BaseModel):
    """List of patterns with pagination."""

    patterns: List[PatternResponse]
    total: int
    page: int
    page_size: int


class PatternSearchRequest(BaseModel):
    """Search patterns by context."""

    query: str = Field(..., description="Search query")
    language: str | None = Field(None, description="Filter by language")
    pattern_type: str | None = Field(None, description="Filter by pattern type")
    limit: int = Field(default=20, le=100)


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/extract", response_model=ExtractionResponse)
async def extract_patterns(request: ExtractionRequest):
    """
    Trigger pattern extraction from codebase.

    Scans AutoBot codebase and extracts code patterns for ML training
    and completion suggestions.

    - **languages**: List of languages to extract (python, typescript, vue)
    - **cache_hot_patterns**: Whether to cache frequent patterns to Redis
    """
    try:
        extractor = PatternExtractor()

        # Extract patterns
        patterns_dict = extractor.extract_from_codebase(languages=request.languages)

        # Store patterns in database
        async with db_session_context() as db:
            total_stored = 0
            for pattern_type, patterns in patterns_dict.items():
                for pattern_data in patterns:
                    # Check if pattern already exists
                    result = await db.execute(
                        select(CodePattern).where(
                            CodePattern.signature == pattern_data["signature"],
                            CodePattern.file_path == pattern_data["file_path"],
                            CodePattern.line_number == pattern_data["line_number"],
                        )
                    )
                    existing = result.scalars().first()

                    if existing:
                        # Update frequency and last_seen
                        existing.frequency += 1
                        existing.last_seen = func.now()
                    else:
                        # Create new pattern
                        pattern = CodePattern(**pattern_data)
                        db.add(pattern)
                        total_stored += 1
            # commit handled by db_session_context()

        # Cache hot patterns to Redis
        if request.cache_hot_patterns:
            extractor.cache_hot_patterns()

        stats = extractor.get_statistics()

        return ExtractionResponse(
            status="success",
            patterns_extracted=sum(stats.values()),
            statistics=stats,
            message=f"Extracted {sum(stats.values())} patterns, " f"stored {total_stored} new patterns",
        )

    except Exception as e:
        logger.error(f"Pattern extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/patterns", response_model=PatternListResponse)
async def list_patterns(
    language: str | None = Query(None),
    pattern_type: str | None = Query(None),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("frequency", pattern="^(frequency|acceptance_rate|created_at)$"),
):
    """
    List extracted patterns with filtering and pagination.

    - **language**: Filter by language (python, typescript, vue)
    - **pattern_type**: Filter by pattern type (function, error_handling, etc.)
    - **category**: Filter by category (fastapi, redis, vue_composable, etc.)
    - **page**: Page number (1-indexed)
    - **page_size**: Results per page (1-100)
    - **sort_by**: Sort field (frequency, acceptance_rate, created_at)
    """
    from sqlalchemy import func as sa_func

    async with db_session_context() as db:
        stmt = select(CodePattern)

        # Apply filters
        if language:
            stmt = stmt.where(CodePattern.language == language)
        if pattern_type:
            stmt = stmt.where(CodePattern.pattern_type == pattern_type)
        if category:
            stmt = stmt.where(CodePattern.category == category)

        # Get total count
        count_result = await db.execute(select(sa_func.count()).select_from(stmt.subquery()))
        total = count_result.scalar_one()

        # Apply sorting and pagination
        sort_column = getattr(CodePattern, sort_by)
        offset = (page - 1) * page_size
        paged_stmt = stmt.order_by(desc(sort_column)).offset(offset).limit(page_size)
        patterns_result = await db.execute(paged_stmt)
        patterns = patterns_result.scalars().all()

        return PatternListResponse(
            patterns=[
                PatternResponse(
                    id=p.id,
                    pattern_type=p.pattern_type,
                    language=p.language,
                    category=p.category,
                    signature=p.signature,
                    body=p.body[:200] if p.body else None,  # Truncate body
                    frequency=p.frequency,
                    acceptance_rate=p.acceptance_rate,
                    file_path=p.file_path,
                    line_number=p.line_number,
                )
                for p in patterns
            ],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/patterns/{category}", response_model=PatternListResponse)
async def get_patterns_by_category(
    category: str,
    language: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Get patterns by category.

    Categories include: fastapi, redis, vue_composable, pydantic, async, etc.
    """
    return await list_patterns(
        language=language,
        category=category,
        page=page,
        page_size=page_size,
    )


@router.post("/patterns/search", response_model=PatternListResponse)
async def search_patterns(request: PatternSearchRequest):
    """
    Search patterns by signature or context.

    Searches in:
    - Pattern signatures
    - Function names
    - Categories
    """
    from sqlalchemy import func as sa_func

    async with db_session_context() as db:
        stmt = select(CodePattern)

        # Apply filters
        if request.language:
            stmt = stmt.where(CodePattern.language == request.language)
        if request.pattern_type:
            stmt = stmt.where(CodePattern.pattern_type == request.pattern_type)

        # Search in signature
        search_term = f"%{request.query}%"
        stmt = stmt.where(CodePattern.signature.ilike(search_term))

        # Count before limiting
        count_result = await db.execute(select(sa_func.count()).select_from(stmt.subquery()))
        total = count_result.scalar_one()

        # Order by relevance (frequency * acceptance_rate) and limit
        stmt = stmt.order_by(desc(CodePattern.frequency * CodePattern.acceptance_rate)).limit(request.limit)
        patterns_result = await db.execute(stmt)
        patterns = patterns_result.scalars().all()

        return PatternListResponse(
            patterns=[
                PatternResponse(
                    id=p.id,
                    pattern_type=p.pattern_type,
                    language=p.language,
                    category=p.category,
                    signature=p.signature,
                    body=p.body[:200] if p.body else None,
                    frequency=p.frequency,
                    acceptance_rate=p.acceptance_rate,
                    file_path=p.file_path,
                    line_number=p.line_number,
                )
                for p in patterns
            ],
            total=total,
            page=1,
            page_size=request.limit,
        )


@router.get("/statistics")
async def get_statistics():
    """Get pattern extraction statistics."""
    async with db_session_context() as db:
        total_result = await db.execute(select(func.count(CodePattern.id)))
        by_language_result = await db.execute(
            select(CodePattern.language, func.count(CodePattern.id)).group_by(CodePattern.language)
        )
        by_type_result = await db.execute(
            select(CodePattern.pattern_type, func.count(CodePattern.id)).group_by(CodePattern.pattern_type)
        )
        by_category_result = await db.execute(
            select(CodePattern.category, func.count(CodePattern.id)).group_by(CodePattern.category)
        )
        top_result = await db.execute(
            select(CodePattern.signature, CodePattern.frequency).order_by(desc(CodePattern.frequency)).limit(10)
        )
        return {
            "total_patterns": total_result.scalar_one(),
            "by_language": dict(by_language_result.all()),
            "by_type": dict(by_type_result.all()),
            "by_category": dict(by_category_result.all()),
            "top_patterns": [
                {"signature": sig, "frequency": freq} for sig, freq in top_result.all()
            ],
        }


# =============================================================================
# Context Analysis Endpoints (Issue #907)
# =============================================================================


class ContextAnalysisRequest(BaseModel):
    """Request for context analysis."""

    file_content: str = Field(..., description="Full file content")
    cursor_line: int = Field(..., ge=0, description="Cursor line (0-indexed)")
    cursor_position: int = Field(..., ge=0, description="Cursor column position")
    file_path: str | None = Field(None, description="Optional file path")


class ContextAnalysisResponse(BaseModel):
    """Response from context analysis."""

    context: Dict
    analysis_time_ms: float


@router.post("/context/analyze", response_model=ContextAnalysisResponse)
async def analyze_context(request: ContextAnalysisRequest):
    """
    Analyze code context for completion.

    Performs multi-level analysis:
    - File-level: imports, defined symbols
    - Function-level: parameters, return types, decorators
    - Block-level: variables in scope, control flow
    - Line-level: cursor position, partial statement
    - Semantic: detected frameworks, coding style
    - Dependencies: import usage, missing imports

    - **file_content**: Full source code
    - **cursor_line**: Line number (0-indexed)
    - **cursor_position**: Column position in line
    - **file_path**: Optional file path for context
    """
    import time

    start_time = time.time()

    try:
        context = get_context_analyzer().analyze(
            file_content=request.file_content,
            cursor_line=request.cursor_line,
            cursor_position=request.cursor_position,
            file_path=request.file_path or "",
        )

        analysis_time = (time.time() - start_time) * 1000  # Convert to ms

        return ContextAnalysisResponse(
            context=context.to_dict(),
            analysis_time_ms=round(analysis_time, 2),
        )

    except Exception as e:
        logger.error(f"Context analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/context/{context_id}")
async def get_context(context_id: str):
    """
    Retrieve cached context by ID.

    - **context_id**: Context identifier from previous analysis
    """
    try:
        cached = get_context_analyzer()._get_cached_context(context_id)

        if not cached:
            raise HTTPException(
                status_code=404,
                detail=f"Context {context_id} not found or expired",
            )

        return {"context": cached.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
