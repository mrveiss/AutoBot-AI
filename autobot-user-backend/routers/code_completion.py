# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Completion API Router (Issue #903)

Endpoints for pattern extraction and code completion.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, desc, func
from sqlalchemy.orm import sessionmaker

from autobot_shared.ssot_config import config
from backend.models.code_pattern import CodePattern
from backend.services.pattern_extractor import PatternExtractor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/code-completion", tags=["code-completion"])

# Database setup
DATABASE_URL = (
    f"postgresql://{config.database.user}:{config.database.password}"
    f"@{config.database.host}:{config.database.port}/{config.database.name}"
)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


# =============================================================================
# Request/Response Models
# =============================================================================


class ExtractionRequest(BaseModel):
    """Request to trigger pattern extraction."""

    languages: Optional[List[str]] = Field(
        default=["python", "typescript", "vue"],
        description="Languages to extract patterns from",
    )
    cache_hot_patterns: bool = Field(
        default=True, description="Cache top patterns to Redis"
    )


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
    category: Optional[str]
    signature: str
    body: Optional[str]
    frequency: int
    acceptance_rate: float
    file_path: Optional[str]
    line_number: Optional[int]


class PatternListResponse(BaseModel):
    """List of patterns with pagination."""

    patterns: List[PatternResponse]
    total: int
    page: int
    page_size: int


class PatternSearchRequest(BaseModel):
    """Search patterns by context."""

    query: str = Field(..., description="Search query")
    language: Optional[str] = Field(None, description="Filter by language")
    pattern_type: Optional[str] = Field(None, description="Filter by pattern type")
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
        patterns_dict = extractor.extract_from_codebase(
            languages=request.languages
        )

        # Store patterns in database
        db = SessionLocal()
        try:
            total_stored = 0
            for pattern_type, patterns in patterns_dict.items():
                for pattern_data in patterns:
                    # Check if pattern already exists
                    existing = (
                        db.query(CodePattern)
                        .filter_by(
                            signature=pattern_data["signature"],
                            file_path=pattern_data["file_path"],
                            line_number=pattern_data["line_number"],
                        )
                        .first()
                    )

                    if existing:
                        # Update frequency and last_seen
                        existing.frequency += 1
                        existing.last_seen = func.now()
                    else:
                        # Create new pattern
                        pattern = CodePattern(**pattern_data)
                        db.add(pattern)
                        total_stored += 1

            db.commit()
        finally:
            db.close()

        # Cache hot patterns to Redis
        if request.cache_hot_patterns:
            extractor.cache_hot_patterns()

        stats = extractor.get_statistics()

        return ExtractionResponse(
            status="success",
            patterns_extracted=sum(stats.values()),
            statistics=stats,
            message=f"Extracted {sum(stats.values())} patterns, "
            f"stored {total_stored} new patterns",
        )

    except Exception as e:
        logger.error(f"Pattern extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns", response_model=PatternListResponse)
async def list_patterns(
    language: Optional[str] = Query(None),
    pattern_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("frequency", regex="^(frequency|acceptance_rate|created_at)$"),
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
    db = SessionLocal()
    try:
        query = db.query(CodePattern)

        # Apply filters
        if language:
            query = query.filter(CodePattern.language == language)
        if pattern_type:
            query = query.filter(CodePattern.pattern_type == pattern_type)
        if category:
            query = query.filter(CodePattern.category == category)

        # Get total count
        total = query.count()

        # Apply sorting
        sort_column = getattr(CodePattern, sort_by)
        query = query.order_by(desc(sort_column))

        # Apply pagination
        offset = (page - 1) * page_size
        patterns = query.offset(offset).limit(page_size).all()

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
    finally:
        db.close()


@router.get("/patterns/{category}", response_model=PatternListResponse)
async def get_patterns_by_category(
    category: str,
    language: Optional[str] = Query(None),
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
    db = SessionLocal()
    try:
        query = db.query(CodePattern)

        # Apply filters
        if request.language:
            query = query.filter(CodePattern.language == request.language)
        if request.pattern_type:
            query = query.filter(CodePattern.pattern_type == request.pattern_type)

        # Search in signature
        search_term = f"%{request.query}%"
        query = query.filter(CodePattern.signature.ilike(search_term))

        # Order by relevance (frequency * acceptance_rate)
        query = query.order_by(
            desc(CodePattern.frequency * CodePattern.acceptance_rate)
        )

        total = query.count()
        patterns = query.limit(request.limit).all()

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
    finally:
        db.close()


@router.get("/statistics")
async def get_statistics():
    """Get pattern extraction statistics."""
    db = SessionLocal()
    try:
        stats = {
            "total_patterns": db.query(CodePattern).count(),
            "by_language": dict(
                db.query(CodePattern.language, func.count(CodePattern.id))
                .group_by(CodePattern.language)
                .all()
            ),
            "by_type": dict(
                db.query(
                    CodePattern.pattern_type, func.count(CodePattern.id)
                )
                .group_by(CodePattern.pattern_type)
                .all()
            ),
            "by_category": dict(
                db.query(CodePattern.category, func.count(CodePattern.id))
                .group_by(CodePattern.category)
                .all()
            ),
            "top_patterns": [
                {"signature": p.signature, "frequency": p.frequency}
                for p in db.query(CodePattern)
                .order_by(desc(CodePattern.frequency))
                .limit(10)
                .all()
            ],
        }
        return stats
    finally:
        db.close()
