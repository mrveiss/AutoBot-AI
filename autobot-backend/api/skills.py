# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skills API Endpoints (Issue #731)

REST API for managing the Skills system: list, enable/disable,
configure, execute, and monitor skills.

Includes metrics and health tracking (Issue #4339).
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from skills.manager import SkillManager
from skills.registry import get_skill_registry
from api.schemas_common import DataResponse
from api.schemas_workflows import (
    SkillsListResponse,
    SkillsCategoriesResponse,
    SkillsAllHealthResponse,
    SkillsInitializeResponse,
    SkillDetailResponse,
    SkillHealthResponse,
    SkillActionsResponse,
    SkillMetricsResponse,
    SkillSuggestionsResponse,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)
router = APIRouter()

_manager: Optional[SkillManager] = None


def _get_manager() -> SkillManager:
    """Get or create the SkillManager singleton.

    Helper for API endpoints (Issue #731).
    """
    global _manager
    if _manager is None:
        _manager = SkillManager()
    return _manager


# --- Request/Response Models ---


class SkillConfigUpdate(BaseModel):
    """Request body for updating a skill's configuration."""

    config: Dict[str, Any] = Field(..., description="Configuration values")


class SkillActionRequest(BaseModel):
    """Request body for executing a skill action."""

    action: str = Field(..., description="Tool/action name to execute")
    params: Dict[str, Any] = Field(
        default_factory=dict, description="Action parameters"
    )


class UserSkillPreferences(BaseModel):
    """Request body for updating user skill preferences."""

    preferences: Dict[str, bool] = Field(
        ..., description="Mapping of skill_name -> enabled"
    )


class SkillFeedbackRequest(BaseModel):
    """Request body for submitting skill feedback."""

    rating: int = Field(..., description="User rating (1-5)", ge=1, le=5)
    feedback: Optional[str] = Field(None, description="Feedback text")


# --- Endpoints ---


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_skills",
    error_code_prefix="SKILLS",
)
@router.get("/", summary="List all skills", response_model=SkillsListResponse)
async def list_skills(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search query"),
    enabled_only: bool = Query(False, description="Only show enabled skills"),
) -> Dict[str, Any]:
    """List all registered skills with optional filtering."""
    manager = _get_manager()

    if search:
        skills = manager.search_skills(search)
    elif category:
        by_cat = manager.list_skills_by_category()
        skills = by_cat.get(category, [])
    else:
        skills = manager.registry.list_skills()

    if enabled_only:
        skills = [s for s in skills if s["enabled"]]

    return {
        "skills": skills,
        "total": len(skills),
        "categories": list(manager.registry.categories),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_categories",
    error_code_prefix="SKILLS",
)
@router.get("/categories", summary="List skill categories", response_model=SkillsCategoriesResponse)
async def list_categories() -> Dict[str, Any]:
    """List all available skill categories with counts."""
    manager = _get_manager()
    by_cat = manager.list_skills_by_category()
    return {"categories": {cat: len(skills) for cat, skills in by_cat.items()}}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_health",
    error_code_prefix="SKILLS",
)
@router.get("/health", summary="Get health of all skills", response_model=SkillsAllHealthResponse)
async def get_all_health() -> Dict[str, Any]:
    """Get health status for all registered skills."""
    registry = get_skill_registry()
    return {"skills": registry.get_all_health()}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="initialize_skills",
    error_code_prefix="SKILLS",
)
@router.post("/initialize", summary="Initialize skills system", response_model=SkillsInitializeResponse)
async def initialize_skills() -> Dict[str, Any]:
    """Discover and load all builtin skills."""
    manager = _get_manager()
    result = await manager.initialize()
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_skill",
    error_code_prefix="SKILLS",
)
@router.get("/{name}", summary="Get skill details", response_model=SkillDetailResponse)
async def get_skill(name: str) -> Dict[str, Any]:
    """Get detailed information about a specific skill."""
    registry = get_skill_registry()
    detail = registry.get_skill_detail(name)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return detail


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enable_skill",
    error_code_prefix="SKILLS",
)
@router.post("/{name}/enable", summary="Enable a skill", response_model=None)
async def enable_skill(name: str) -> Dict[str, Any]:
    """Enable a skill, checking dependencies. Persists state to Redis (Issue #993)."""
    registry = get_skill_registry()
    result = registry.enable_skill(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    manager = _get_manager()
    await manager.persist_skill_enabled(name, True)
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="disable_skill",
    error_code_prefix="SKILLS",
)
@router.post("/{name}/disable", summary="Disable a skill", response_model=None)
async def disable_skill(name: str) -> Dict[str, Any]:
    """Disable a skill. Persists state to Redis (Issue #993)."""
    registry = get_skill_registry()
    result = registry.disable_skill(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    manager = _get_manager()
    await manager.persist_skill_enabled(name, False)
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_config",
    error_code_prefix="SKILLS",
)
@router.put("/{name}/config", summary="Update skill config", response_model=None)
async def update_config(name: str, body: SkillConfigUpdate) -> Dict[str, Any]:
    """Update a skill's configuration values."""
    registry = get_skill_registry()
    result = registry.update_config(name, body.config)
    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("errors", result.get("error", "Validation failed")),
        )
    manager = _get_manager()
    await manager.persist_skill_config(name, body.config)
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_skill",
    error_code_prefix="SKILLS",
)
@router.post("/{name}/execute", summary="Execute a skill action", response_model=None)
async def execute_skill(name: str, body: SkillActionRequest) -> Dict[str, Any]:
    """Execute a specific action on a skill."""
    manager = _get_manager()
    result = await manager.execute_skill(name, body.action, body.params)
    if not result.get("success", False):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Execution failed"),
        )
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_skill_health",
    error_code_prefix="SKILLS",
)
@router.get("/{name}/health", summary="Get skill health", response_model=SkillHealthResponse)
async def get_skill_health(name: str) -> Dict[str, Any]:
    """Get health status for a specific skill."""
    registry = get_skill_registry()
    health = registry.get_health(name)
    if not health:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return health.model_dump()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_skill_actions",
    error_code_prefix="SKILLS",
)
@router.get("/{name}/actions", summary="List skill actions", response_model=SkillActionsResponse)
async def list_skill_actions(name: str) -> Dict[str, Any]:
    """List available actions for a skill."""
    registry = get_skill_registry()
    skill = registry.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {
        "skill": name,
        "actions": skill.get_available_actions(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_skill_metrics",
    error_code_prefix="SKILLS",
)
@router.get("/{name}/metrics", summary="Get skill metrics", response_model=SkillMetricsResponse)
async def get_skill_metrics(
    name: str,
    days: int = Query(30, description="Number of days to analyze"),
) -> Dict[str, Any]:
    """Get performance metrics for a skill (Issue #4339).

    Returns invocation count, success rate, error patterns, and duration stats.
    """
    try:
        from services.skill_management.skill_metrics import SkillMetrics

        metrics = SkillMetrics()
        data = await metrics.get_metrics(name, days)
        health_score = await metrics.get_health_score(name, days)
        data["health_score"] = health_score
        return data
    except Exception as e:
        logger.error("Failed to get metrics for %s: %s", name, e)
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="submit_skill_feedback",
    error_code_prefix="SKILLS",
)
@router.post("/{name}/feedback", summary="Submit skill feedback", response_model=DataResponse)
async def submit_skill_feedback(
    name: str,
    body: SkillFeedbackRequest,
    action: Optional[str] = Query(None, description="Action that was invoked"),
) -> Dict[str, Any]:
    """Submit user feedback for a skill (Issue #4339)."""
    try:
        from services.skill_management.skill_feedback import SkillFeedbackAnalyzer

        analyzer = SkillFeedbackAnalyzer()
        await analyzer.log_user_feedback(
            skill_id=name,
            action=action or "unknown",
            rating=body.rating,
            feedback_text=body.feedback,
        )
        return {
            "success": True,
            "message": f"Feedback submitted for skill '{name}'",
        }
    except Exception as e:
        logger.error("Failed to log feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to log feedback")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_refinement_suggestions",
    error_code_prefix="SKILLS",
)
@router.get("/{name}/suggestions", summary="Get skill refinement suggestions", response_model=SkillSuggestionsResponse)
async def get_refinement_suggestions(name: str) -> Dict[str, Any]:
    """Get suggestions for improving a skill (Issue #4339)."""
    try:
        from services.skill_management.skill_feedback import SkillFeedbackAnalyzer

        analyzer = SkillFeedbackAnalyzer()
        suggestions = await analyzer.get_refinement_suggestions(name)
        return suggestions
    except Exception as e:
        logger.error("Failed to get suggestions for %s: %s", name, e)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve suggestions",
        )
