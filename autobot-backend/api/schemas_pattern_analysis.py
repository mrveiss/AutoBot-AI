# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request and response models for the pattern-analysis routes.

Split out of ``codebase_analytics/endpoints/pattern_analysis.py`` (#20513), a grandfathered file that may
not grow. ``pattern_analysis`` imports these names, so ``from ...pattern_analysis import PatternAnalysisRequest``
keeps working for the Celery task that builds one from a dict.
"""

from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator

from api.codebase_analytics.source_scope import require_source_id


class PatternAnalysisRequest(BaseModel):
    """Request model for pattern analysis."""

    path: str | None = Field(
        default=None,
        description="Optional sub-path to analyze, relative to the source root (default: the whole source)",
    )
    source_id: str = Field(description="Required (#20513): the code source to analyze")
    enable_clone_detection: bool = Field(default=True, description="Enable clone/duplicate detection")
    enable_anti_pattern_detection: bool = Field(default=True, description="Enable anti-pattern detection")
    enable_regex_detection: bool = Field(default=True, description="Enable regex optimization detection")
    enable_complexity_analysis: bool = Field(default=True, description="Enable complexity analysis")
    similarity_threshold: float = Field(default=0.8, ge=0.0, le=1.0, description="Similarity threshold for clustering")

    @field_validator("source_id")
    @classmethod
    def _source_id_required(cls, value: str) -> str:
        """The body counterpart of ``SourceIdQuery``: same rule, same shape check (#20513)."""
        return require_source_id(value, "pattern analysis")


class PatternAnalysisStatus(BaseModel):
    """Status model for pattern analysis task."""

    task_id: str
    status: str  # pending, running, completed, failed
    progress: float = 0.0
    current_step: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    reason: str | None = None  # orphaned, timeout, manual (#1250)
    result: Dict[str, Any] | None = None
    partial_results: Dict[str, Any] | None = None


class PatternSummary(BaseModel):
    """Summary of detected patterns."""

    total_patterns: int
    duplicates: int
    regex_opportunities: int
    complexity_hotspots: int
    modularization_suggestions: int
    potential_loc_reduction: int
    complexity_score: str
