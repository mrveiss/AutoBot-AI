# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skills API Endpoints (Issue #731)

REST API for managing the Skills system: list, enable/disable,
configure, execute, and monitor skills.

Includes metrics and health tracking (Issue #4339).
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request

from api.schemas_agent import (
    SkillActionRequest,
    SkillCatalogInstallData,
    SkillConfigUpdate,
    SkillFeedbackData,
    SkillFeedbackRequest,
    SkillInstallRequest,
)
from api.schemas_code import (
    SkillConfigUpdateResponse,
    SkillExecuteResponse,
    SkillToggleResponse,
)
from api.schemas_common import DataResponse
from api.schemas_workflows import (
    MCPSpanResponse,
    SkillActionsResponse,
    SkillDetailResponse,
    SkillHealthResponse,
    SkillMetricsResponse,
    SkillsCategoriesResponse,
    SkillsInitializeResponse,
    SkillsListResponse,
    SkillSuggestionsResponse,
    SkillTracesResponse,
)
from api.system_health import ComponentHealth, register_health_probe
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from skills.manager import SkillManager
from skills.registry import get_skill_registry

logger = get_logger(__name__)

logger = get_logger(__name__)
router = APIRouter()

_manager: SkillManager | None = None


def _get_manager() -> SkillManager:
    """Get or create the SkillManager singleton.

    Helper for API endpoints (Issue #731).
    """
    global _manager
    if _manager is None:
        _manager = SkillManager()
    return _manager


# --- Endpoints ---


@router.get("/", summary="List all skills", response_model=SkillsListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_skills",
    error_code_prefix="SKILLS",
)
async def list_skills(
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search query"),
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


@router.get("/categories", summary="List skill categories", response_model=SkillsCategoriesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_categories",
    error_code_prefix="SKILLS",
)
async def list_categories() -> Dict[str, Any]:
    """List all available skill categories with counts."""
    manager = _get_manager()
    by_cat = manager.list_skills_by_category()
    return {"categories": {cat: len(skills) for cat, skills in by_cat.items()}}


@register_health_probe("skills")
async def probe_skills(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for skills module."""
    try:
        registry = get_skill_registry()
        skill_count = len(registry.list_skills()) if registry else 0
        return ComponentHealth(
            name="skills",
            status="ok" if skill_count > 0 else "degraded",
            detail=f"{skill_count} skills loaded",
            data={"skill_count": skill_count},
        )
    except Exception as exc:
        return ComponentHealth(
            name="skills",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


@router.post("/initialize", summary="Initialize skills system", response_model=SkillsInitializeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="initialize_skills",
    error_code_prefix="SKILLS",
)
async def initialize_skills() -> Dict[str, Any]:
    """Discover and load all builtin skills."""
    manager = _get_manager()
    result = await manager.initialize()
    return result


@router.get("/traces", summary="Get recent MCP tool-call traces", response_model=SkillTracesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_skill_traces",
    error_code_prefix="SKILLS",
)
async def get_skill_traces(
    skill: str | None = Query(None, description="Filter by skill name"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of traces to return"),
) -> Dict[str, Any]:
    """Return recent MCP tool-call spans from Redis (Issue #4413).

    Queries ``mcp_trace_idx:{skill}`` (sorted set, newest first) when a skill
    name is provided, or iterates all ``mcp_trace_idx:*`` keys otherwise.
    """
    import json as _json

    from autobot_shared.redis_client import get_async_redis_client

    redis = await get_async_redis_client(database="main")
    if redis is None:
        return {"skill": skill, "traces": [], "total": 0}

    if skill:
        idx_keys = [f"mcp_trace_idx:{skill}"]
    else:
        idx_keys = [k.decode() if isinstance(k, bytes) else k async for k in redis.scan_iter("mcp_trace_idx:*")]

    trace_ids: list = []
    for idx_key in idx_keys:
        ids = await redis.zrevrange(idx_key, 0, limit - 1)
        trace_ids.extend(ids)

    # Deduplicate while preserving insertion order
    seen: set = set()
    unique_ids = []
    for tid in trace_ids:
        tid_str = tid.decode() if isinstance(tid, bytes) else tid
        if tid_str not in seen:
            seen.add(tid_str)
            unique_ids.append(tid_str)
    unique_ids = unique_ids[:limit]

    traces: list = []
    keys = [f"mcp_trace:{tid}" for tid in unique_ids]
    raws = await redis.mget(*keys)
    for raw in raws:
        if raw is None:
            continue
        try:
            traces.append(MCPSpanResponse(**_json.loads(raw)))
        except Exception as exc:
            logger.debug("mcp_trace: failed to deserialise span: %s", exc)

    return {"skill": skill, "traces": traces, "total": len(traces)}


@router.get("/catalog", summary="List external skill catalog entries", response_model=Dict[str, Any])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_catalog",
    error_code_prefix="SKILLS",
)
async def list_catalog(
    catalog_url: str = Query(..., description="HTTP URL of the remote skill catalog"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> Dict[str, Any]:
    """Fetch paginated skill entries from an HTTP catalog and return them with install actions.

    Each returned entry includes an ``install_action`` field describing the
    ``POST /skills/catalog/{name}/install`` endpoint to materialize the skill.
    """
    from skills.external_importer import ExternalSkillImporter

    importer = ExternalSkillImporter()
    try:
        entries = await importer.import_http_catalog(catalog_url, page=page, page_size=page_size)
    except RuntimeError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Internal server error")

    # Annotate each entry with an install action hint
    for entry in entries:
        name = entry.get("name", "")
        entry["install_action"] = f"POST /api/skills/catalog/{name}/install"

    return {"catalog_url": catalog_url, "page": page, "page_size": page_size, "skills": entries, "total": len(entries)}


@router.post(
    "/catalog/{name}/install",
    summary="Install a skill from an HTTP catalog",
    response_model=DataResponse[SkillCatalogInstallData],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="install_catalog_skill",
    error_code_prefix="SKILLS",
)
async def install_catalog_skill(name: str, body: SkillInstallRequest) -> Dict[str, Any]:
    """Fetch a skill from a remote catalog and persist it as a SANDBOXED SkillPackage.

    The catalog must expose a ``/skills/{name}`` endpoint (or equivalent) that
    returns the catalog entry dict containing at minimum a ``skill_md`` field.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from skills.db import get_skills_engine
    from skills.external_importer import ExternalSkillImporter
    from skills.models import SkillPackage

    importer = ExternalSkillImporter()
    # Fetch the single-entry detail URL: catalog_url/name
    detail_url = body.catalog_url.rstrip("/") + f"/{name}"
    try:
        entries = await importer.import_http_catalog(detail_url, page=1, page_size=1)
    except RuntimeError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Internal server error")

    if not entries:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found in catalog at {body.catalog_url}")

    entry = entries[0]
    try:
        pkg = await importer.install_from_catalog(name, entry, repo_id=body.repo_id)
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=422, detail="Internal server error")

    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        existing = await session.scalar(select(SkillPackage).where(SkillPackage.name == pkg.name))
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"Skill '{name}' is already installed")
        session.add(pkg)
        await session.commit()
        await session.refresh(pkg)

    logger.info("Installed catalog skill '%s' (id=%s)", pkg.name, pkg.id)
    return {"success": True, "id": pkg.id, "name": pkg.name, "version": pkg.version, "trust_level": pkg.trust_level}


@router.get("/{name}", summary="Get skill details", response_model=SkillDetailResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_skill",
    error_code_prefix="SKILLS",
)
async def get_skill(name: str) -> Dict[str, Any]:
    """Get detailed information about a specific skill."""
    registry = get_skill_registry()
    detail = registry.get_skill_detail(name)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return detail


@router.post("/{name}/enable", summary="Enable a skill", response_model=SkillToggleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enable_skill",
    error_code_prefix="SKILLS",
)
async def enable_skill(name: str) -> Dict[str, Any]:
    """Enable a skill, checking dependencies. Persists state to Redis (Issue #993)."""
    registry = get_skill_registry()
    result = registry.enable_skill(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    manager = _get_manager()
    await manager.persist_skill_enabled(name, True)
    return result


@router.post("/{name}/disable", summary="Disable a skill", response_model=SkillToggleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="disable_skill",
    error_code_prefix="SKILLS",
)
async def disable_skill(name: str) -> Dict[str, Any]:
    """Disable a skill. Persists state to Redis (Issue #993)."""
    registry = get_skill_registry()
    result = registry.disable_skill(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    manager = _get_manager()
    await manager.persist_skill_enabled(name, False)
    return result


@router.put("/{name}/config", summary="Update skill config", response_model=SkillConfigUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_config",
    error_code_prefix="SKILLS",
)
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


@router.post("/{name}/execute", summary="Execute a skill action", response_model=SkillExecuteResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_skill",
    error_code_prefix="SKILLS",
)
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


@router.get("/{name}/health", summary="Get skill health", response_model=SkillHealthResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_skill_health",
    error_code_prefix="SKILLS",
)
async def get_skill_health(name: str) -> Dict[str, Any]:
    """Get health status for a specific skill."""
    registry = get_skill_registry()
    health = registry.get_health(name)
    if not health:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return health.model_dump()


@router.get("/{name}/actions", summary="List skill actions", response_model=SkillActionsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_skill_actions",
    error_code_prefix="SKILLS",
)
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


@router.get("/{name}/metrics", summary="Get skill metrics", response_model=SkillMetricsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_skill_metrics",
    error_code_prefix="SKILLS",
)
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


@router.post("/{name}/feedback", summary="Submit skill feedback", response_model=DataResponse[SkillFeedbackData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="submit_skill_feedback",
    error_code_prefix="SKILLS",
)
async def submit_skill_feedback(
    name: str,
    body: SkillFeedbackRequest,
    action: str | None = Query(None, description="Action that was invoked"),
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


@router.get("/{name}/suggestions", summary="Get skill refinement suggestions", response_model=SkillSuggestionsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_refinement_suggestions",
    error_code_prefix="SKILLS",
)
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
