# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Web Research Settings API

Provides endpoints for managing web research configuration and preferences.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_workflows import (
    WebResearchCacheClearData,
    WebResearchSettings,
    WebResearchSettingsData,
    WebResearchSettingsUpdateData,
    WebResearchStatusData,
    WebResearchTestData,
    WebResearchToggleData,
    WebResearchUsageStatsData,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/web-research", tags=["web-research"])


@router.get("/status", response_model=DataResponse[WebResearchStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_research_status",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def get_research_status():
    """Get current web research status and configuration"""
    try:
        from agents.web_researcher import get_web_researcher as get_web_research_integration

        # Get web research integration instance
        integration = get_web_research_integration()

        # Get health check
        health_status = await integration.health_check()

        # Get circuit breaker status
        circuit_status = integration.get_circuit_breaker_status()

        # Get cache stats
        cache_stats = integration.get_cache_stats()

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "enabled": health_status["enabled"],
                "preferred_method": "advanced",
                "health": health_status,
                "circuit_breakers": circuit_status,
                "cache_stats": cache_stats,
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


@router.post("/enable", response_model=DataResponse[WebResearchToggleData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enable_web_research",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def enable_web_research():
    """Enable web research functionality"""
    try:
        from unified_unified_config_manager import unified_unified_config_manager

        from agents.web_researcher import get_web_researcher as get_web_research_integration
        from services.config_service import ConfigService

        # Enable in integration
        integration = get_web_research_integration()
        success = await integration.enable_research(user_confirmed=True)

        if success:
            # Update configuration
            unified_unified_config_manager.set_nested("agents.research.enabled", True)
            unified_unified_config_manager.set_nested("web_research.enabled", True)
            unified_unified_config_manager.save_settings()
            ConfigService.clear_cache()

            logger.info("Web research enabled by user")

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Web research enabled successfully",
                    "enabled": True,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Failed to enable web research",
                    "enabled": False,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                },
            )

    except Exception as e:
        logger.error("Failed to enable web research: %s", e)
        raise HTTPException(status_code=500, detail="Failed to enable web research")


@router.post("/disable", response_model=DataResponse[WebResearchToggleData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="disable_web_research",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def disable_web_research():
    """Disable web research functionality"""
    try:
        from unified_unified_config_manager import unified_unified_config_manager

        from agents.web_researcher import get_web_researcher as get_web_research_integration
        from services.config_service import ConfigService

        # Disable in integration
        integration = get_web_research_integration()
        success = await integration.disable_research()

        if success:
            # Update configuration
            unified_unified_config_manager.set_nested("agents.research.enabled", False)
            unified_unified_config_manager.set_nested("web_research.enabled", False)
            unified_unified_config_manager.save_settings()
            ConfigService.clear_cache()

            logger.info("Web research disabled by user")

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Web research disabled successfully",
                    "enabled": False,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Failed to disable web research",
                    "enabled": True,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                },
            )

    except Exception as e:
        logger.error("Failed to disable web research: %s", e)
        raise HTTPException(status_code=500, detail="Failed to disable web research")


@router.get("/settings", response_model=DataResponse[WebResearchSettingsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_research_settings",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def get_research_settings():
    """Get current web research settings"""
    try:
        from config.manager import get_config_manager

        # Get settings from config
        unified_config_manager = get_config_manager()
        research_config = unified_config_manager.get_nested("agents.research", {})
        web_research_config = unified_config_manager.get_nested("web_research", {})

        settings = {
            "enabled": research_config.get("enabled", False),
            "require_user_confirmation": web_research_config.get("require_user_confirmation", True),
            "preferred_method": research_config.get("preferred_method", "basic"),
            "max_results": research_config.get("max_results", 5),
            "timeout_seconds": research_config.get("timeout_seconds", 30),
            "auto_research_threshold": web_research_config.get("auto_research_threshold", 0.3),
            "rate_limit_requests": research_config.get("rate_limit_requests", 5),
            "rate_limit_window": research_config.get("rate_limit_window", 60),
            "daily_limit": web_research_config.get("daily_research_limit", 50),
            "quality_threshold": web_research_config.get("min_result_quality", 0.5),
            "store_results_in_kb": web_research_config.get("store_results_in_kb", True),
            "filter_adult_content": web_research_config.get("filter_adult_content", True),
            "anonymize_requests": web_research_config.get("anonymize_requests", True),
        }

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "settings": settings,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to get research settings: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get research settings")


@router.put("/settings", response_model=DataResponse[WebResearchSettingsUpdateData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_research_settings",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def update_research_settings(settings: WebResearchSettings):
    """Update web research settings"""
    try:
        from config import unified_config_manager
        from services.config_service import ConfigService

        # Update research agent settings
        unified_config_manager.set_nested("agents.research.enabled", settings.enabled)
        unified_config_manager.set_nested("agents.research.preferred_method", settings.preferred_method)
        unified_config_manager.set_nested("agents.research.max_results", settings.max_results)
        unified_config_manager.set_nested("agents.research.timeout_seconds", settings.timeout_seconds)
        unified_config_manager.set_nested("agents.research.rate_limit_requests", settings.rate_limit_requests)
        unified_config_manager.set_nested("agents.research.rate_limit_window", settings.rate_limit_window)

        # Update web research settings
        unified_config_manager.set_nested("web_research.enabled", settings.enabled)
        unified_config_manager.set_nested("web_research.require_user_confirmation", settings.require_user_confirmation)
        unified_config_manager.set_nested("web_research.auto_research_threshold", settings.auto_research_threshold)

        # Save configuration and clear cache
        unified_config_manager.save_settings()
        ConfigService.clear_cache()

        logger.info("Web research settings updated")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Web research settings updated successfully",
                "settings": settings.dict(),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to update research settings: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update research settings")


@router.post("/test", response_model=DataResponse[WebResearchTestData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_web_research",
    error_code_prefix="WEB_RESEARCH_SETTINGS",
)
async def test_web_research(query: str = "test query"):
    """Test web research functionality"""
    try:
        from agents.web_researcher import conduct_web_research

        logger.info("Testing web research with query: %s", query)

        # Conduct test research
        result = await conduct_web_research(
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
async def clear_research_cache():
    """Clear web research cache"""
    try:
        from agents.web_researcher import get_web_researcher as get_web_research_integration

        integration = get_web_research_integration()

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
async def reset_circuit_breakers():
    """Reset all circuit breakers for web research"""
    try:
        from agents.web_researcher import get_web_researcher as get_web_research_integration

        integration = get_web_research_integration()

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
async def get_usage_stats():
    """Get web research usage statistics"""
    try:
        from agents.web_researcher import get_web_researcher as get_web_research_integration

        integration = get_web_research_integration()

        # Get basic stats
        cache_stats = integration.get_cache_stats()
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
