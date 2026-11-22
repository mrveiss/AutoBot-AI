# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Web Research Settings API

Provides endpoints for managing web research configuration and preferences.
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_web_research import (
    WebResearchCacheClearData,
    WebResearchSettingsData,
    WebResearchSettingsUpdate,
    WebResearchSettingsUpdateData,
    WebResearchStatusData,
    WebResearchTestData,
    WebResearchToggleData,
    WebResearchUsageStatsData,
)
from api.system_health import HEALTH_PROBE_TIMEOUT_S
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services import web_research_config

logger = get_logger(__name__)

# #16375: mounted with no auth dependency. Reading status, settings and usage
# needs a signed-in caller; enabling, disabling, changing the persisted settings,
# running a test search, clearing the cache and resetting the circuit breakers
# also need admin.
router = APIRouter(prefix="/web-research", tags=["web-research"], dependencies=[Depends(get_current_user)])

_RESEARCHER_UNAVAILABLE_DETAIL = (
    "web researcher unavailable — browser/Playwright initialization failed at startup; see logs"
)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _persist(changes: dict) -> dict:
    """Save setting changes to the one web research section; returns the full set (#19226)."""
    from config import config_manager
    from services.config_service import ConfigService

    settings = web_research_config.save_settings(config_manager, changes)
    ConfigService.clear_cache()
    return settings


def _saved_method() -> str:
    from config import config_manager

    return web_research_config.load_settings(config_manager)["preferred_method"]


def _require_web_researcher(request: Request):
    """Return the startup-initialized WebResearcher or raise 503 (#11665).

    Phase-2 init failure leaves ``app.state.web_researcher = None``
    (initialization/lifespan.py), so every endpoint that needs the researcher
    must fail actionably instead of touching an uninitialized instance.
    """
    researcher = getattr(request.app.state, "web_researcher", None)
    if researcher is None:
        raise HTTPException(status_code=503, detail=_RESEARCHER_UNAVAILABLE_DETAIL)
    return researcher


@router.get("/status", response_model=DataResponse[WebResearchStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_research_status",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def get_research_status(request: Request):
    """Get current web research status and configuration"""
    integration = _require_web_researcher(request)
    try:
        # #12751: bound every dependency call. A status endpoint that HANGS is
        # worse than one reporting an error — the UI health panel and monitoring
        # block instead of getting a clear degraded signal, and `except
        # Exception` below catches failures but never a hang. Same budget as the
        # health aggregator so probes cannot disagree about what "too slow"
        # means. (#6918 caveat: wait_for only cancels at await points.)
        health_status = await asyncio.wait_for(integration.health_check(), timeout=HEALTH_PROBE_TIMEOUT_S)

        # Get circuit breaker status (sync, no I/O)
        circuit_status = integration.get_circuit_breaker_status()

        cache_stats = await asyncio.wait_for(integration.get_cache_stats(), timeout=HEALTH_PROBE_TIMEOUT_S)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "enabled": health_status["enabled"],
                "preferred_method": _saved_method(),
                "health": health_status,
                "circuit_breakers": circuit_status,
                "cache_stats": cache_stats,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except asyncio.TimeoutError:
        logger.warning(
            "Web research status probe exceeded %ss — returning degraded (#12751)",
            HEALTH_PROBE_TIMEOUT_S,
        )
        return JSONResponse(
            status_code=200,  # graceful degradation, same contract as the error path
            content={
                "status": "degraded",
                "enabled": False,
                "error": f"health probe timed out after {HEALTH_PROBE_TIMEOUT_S}s",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to get research status: %s", e)
        return JSONResponse(
            status_code=200,  # Return 200 even on error for graceful degradation
            content={
                "status": "error",
                "enabled": False,
                "message": "Web research not available",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )


# A save that reached the config but not the running researcher is not rolled back: the saved
# value is what the admin asked for, and startup applies it (#19226). The response says so.
SAVED_NOT_APPLIED = "saved_not_applied"
_SAVED_NOT_APPLIED_MESSAGE = "{what} saved; the running researcher did not take it and will after a restart"


async def _set_enabled(request: Request, enabled: bool) -> JSONResponse:
    """Save the switch, then flip the live researcher; a failed save changes neither (#19226)."""
    researcher = _require_web_researcher(request)
    word = "enabled" if enabled else "disabled"
    try:
        _persist({"enabled": enabled})
    except Exception as e:
        logger.error("Failed to save web research as %s: %s", word, e)
        raise HTTPException(status_code=500, detail=f"Failed to switch web research to {word}")
    try:
        applied = await (researcher.enable_research(user_confirmed=True) if enabled else researcher.disable_research())
    except Exception as e:
        logger.error("Web research saved as %s but not applied live: %s", word, e)
        applied = False
    logger.info("Web research %s by an admin (applied live: %s)", word, applied)
    content = {"status": "success", "message": f"Web research {word}", "enabled": researcher.enabled}
    if not applied:
        content.update(status=SAVED_NOT_APPLIED, message=_SAVED_NOT_APPLIED_MESSAGE.format(what=f"Web research {word}"))
    return JSONResponse(status_code=200, content={**content, "timestamp": _now()})


@router.post("/enable", response_model=DataResponse[WebResearchToggleData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enable_web_research",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def enable_web_research(request: Request, _: bool = Depends(check_admin_permission)):
    """Enable web research, saved across restarts."""
    return await _set_enabled(request, True)


@router.post("/disable", response_model=DataResponse[WebResearchToggleData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="disable_web_research",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def disable_web_research(request: Request, _: bool = Depends(check_admin_permission)):
    """Disable web research, saved across restarts."""
    return await _set_enabled(request, False)


@router.get("/settings", response_model=DataResponse[WebResearchSettingsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_research_settings",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def get_research_settings():
    """Every web research setting, read from the one section the researcher uses (#19226)."""
    from config import config_manager

    settings = web_research_config.load_settings(config_manager)
    return JSONResponse(status_code=200, content={"status": "success", "settings": settings, "timestamp": _now()})


@router.put("/settings", response_model=DataResponse[WebResearchSettingsUpdateData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_research_settings",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def update_research_settings(
    request: Request, changes: WebResearchSettingsUpdate, _: bool = Depends(check_admin_permission)
):
    """Save the sent settings and apply them to the running researcher, no restart (#19226)."""
    from config import config_manager

    try:
        settings = _persist(changes.model_dump(exclude_unset=True, exclude_none=True))
    except Exception as e:
        logger.error("Failed to update research settings: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update research settings")
    content = {"status": "success", "message": "Web research settings updated", "settings": settings}
    researcher = getattr(request.app.state, "web_researcher", None)
    try:
        if researcher is not None:
            researcher.apply_settings(web_research_config.researcher_config(config_manager))
    except Exception as e:
        logger.error("Web research settings saved but not applied live: %s", e)
        content.update(
            status=SAVED_NOT_APPLIED, message=_SAVED_NOT_APPLIED_MESSAGE.format(what="Web research settings")
        )
    return JSONResponse(status_code=200, content={**content, "timestamp": _now()})


@router.post("/test", response_model=DataResponse[WebResearchTestData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_web_research",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def test_web_research(request: Request, query: str = "test query", _: bool = Depends(check_admin_permission)):
    """Test web research functionality"""
    integration = _require_web_researcher(request)
    try:
        logger.info("Testing web research with query: %s", query)

        # Conduct test research
        result = await integration.conduct_research(
            query=query,
            max_results=3,
            # Remove timeout - let research complete naturally
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "test_query": query,
                "result": result,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Web research test failed: %s", e)
        return JSONResponse(
            status_code=200,
            content={
                "status": "error",
                "test_query": query,
                "error": "Internal server error",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )


@router.post("/clear-cache", response_model=DataResponse[WebResearchCacheClearData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_research_cache",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def clear_research_cache(request: Request, _: bool = Depends(check_admin_permission)):
    """Clear web research cache"""
    integration = _require_web_researcher(request)
    try:
        # Clear cache
        integration._cache.clear()

        logger.info("Web research cache cleared")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Research cache cleared successfully",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to clear research cache: %s", e)
        raise HTTPException(status_code=500, detail="Failed to clear research cache")


@router.post("/reset-circuit-breakers", response_model=DataResponse[WebResearchCacheClearData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_circuit_breakers",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def reset_circuit_breakers(request: Request, _: bool = Depends(check_admin_permission)):
    """Reset all circuit breakers for web research"""
    integration = _require_web_researcher(request)
    try:
        # Reset circuit breakers
        integration.reset_circuit_breakers()

        logger.info("Web research circuit breakers reset")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Circuit breakers reset successfully",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to reset circuit breakers: %s", e)
        raise HTTPException(status_code=500, detail="Failed to reset circuit breakers")


@router.get("/usage-stats", response_model=DataResponse[WebResearchUsageStatsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_usage_stats",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def get_usage_stats(request: Request):
    """Get web research usage statistics"""
    integration = _require_web_researcher(request)
    try:
        # Get basic stats
        cache_stats = await integration.get_cache_stats()
        circuit_status = integration.get_circuit_breaker_status()

        stats = {
            "cache_size": cache_stats["cache_size"],
            "cache_ttl": cache_stats["cache_ttl"],
            "rate_limiter": cache_stats["rate_limiter"],
            "circuit_breakers": circuit_status,
            "enabled": integration.enabled,
            "preferred_method": "advanced",
        }

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "stats": stats,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to get usage stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get usage stats")
