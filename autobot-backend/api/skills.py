# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skills API Endpoints (Issue #731)

REST API for managing the Skills system: list, enable/disable,
configure, execute, and monitor skills.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.skills.manager import SkillManager
from backend.skills.registry import get_skill_registry

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


# --- Endpoints ---


@router.get("/", summary="List all skills")
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


@router.get("/categories", summary="List skill categories")
async def list_categories() -> Dict[str, Any]:
    """List all available skill categories with counts."""
    manager = _get_manager()
    by_cat = manager.list_skills_by_category()
    return {"categories": {cat: len(skills) for cat, skills in by_cat.items()}}


@router.get("/health", summary="Get health of all skills")
async def get_all_health() -> Dict[str, Any]:
    """Get health status for all registered skills."""
    registry = get_skill_registry()
    return {"skills": registry.get_all_health()}


@router.post("/initialize", summary="Initialize skills system")
async def initialize_skills() -> Dict[str, Any]:
    """Discover and load all builtin skills."""
    manager = _get_manager()
    result = await manager.initialize()
    return result


@router.get("/{name}", summary="Get skill details")
async def get_skill(name: str) -> Dict[str, Any]:
    """Get detailed information about a specific skill."""
    registry = get_skill_registry()
    detail = registry.get_skill_detail(name)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return detail


@router.post("/{name}/enable", summary="Enable a skill")
async def enable_skill(name: str) -> Dict[str, Any]:
    """Enable a skill, checking dependencies. Persists state to Redis (Issue #993)."""
    registry = get_skill_registry()
    result = registry.enable_skill(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    manager = _get_manager()
    await manager.persist_skill_enabled(name, True)
    return result


@router.post("/{name}/disable", summary="Disable a skill")
async def disable_skill(name: str) -> Dict[str, Any]:
    """Disable a skill. Persists state to Redis (Issue #993)."""
    registry = get_skill_registry()
    result = registry.disable_skill(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    manager = _get_manager()
    await manager.persist_skill_enabled(name, False)
    return result


@router.put("/{name}/config", summary="Update skill config")
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


@router.post("/{name}/execute", summary="Execute a skill action")
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


@router.get("/{name}/health", summary="Get skill health")
async def get_skill_health(name: str) -> Dict[str, Any]:
    """Get health status for a specific skill."""
    registry = get_skill_registry()
    health = registry.get_health(name)
    if not health:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return health.model_dump()


@router.get("/{name}/actions", summary="List skill actions")
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
