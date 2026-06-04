# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM configuration and model-listing endpoints.

Exposes GET/POST routes for querying available language models, reading
current LLM config, and selecting the active model.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.schemas_agent import (
    LLMConfigResponse,
    LLMConnectionTestResponse,
    LLMCurrentResponse,
    LLMEmbeddingModelsResponse,
    LLMModelsResponse,
)
from api.schemas_common import DataResponse
from api.schemas_workflows import (
    LLMCacheClearData,
    LLMComprehensiveStatusData,
    LLMDeprecatedData,
    LLMProviderHealthData,
    LLMProvidersHealthData,
    LLMQuickStatusData,
    LLMTieredMetricsResetData,
    LLMTieredRoutingConfigData,
    LLMTieredRoutingMetricsData,
    LLMTieredRoutingUpdateData,
)
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as ssot_config
from autobot_shared.time_utils import now_utc
from config.manager import get_config_manager

# Import unified configuration system - NO HARDCODED VALUES
from constants.model_constants import ModelConstants
from services.config_service import ConfigService
from services.llm_service import get_llm_service

# Import caching utilities from unified cache manager (P4 Cache Consolidation)
from utils.advanced_cache_manager import cache_response
from utils.connection_utils import ConnectionTester, ModelManager

config = get_config_manager()

router = APIRouter()

logger = get_logger(__name__)

# Performance optimization: O(1) lookup for embedding model detection (Issue #326)
EMBEDDING_MODEL_PATTERNS = {"embed", "nomic", "all-minilm", "sentence"}
TEXT_MODEL_SIZE_INDICATORS = {"small", "large", "medium"}


@router.get("/config", response_model=LLMConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_llm_config",
    error_code_prefix="LLM",
)
async def get_llm_config(
    current_user: dict = Depends(get_current_user),
):
    """Get current LLM configuration.

    Issue #744: Requires authenticated user.
    """
    try:
        return ConfigService.get_llm_config()
    except Exception as e:
        logger.error("Error getting LLM config: %s", str(e))
        raise HTTPException(status_code=500, detail="Error getting LLM config")


@router.post("/config", response_model=DataResponse[LLMDeprecatedData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_llm_config",
    error_code_prefix="LLM",
)
async def update_llm_config(
    config_data: dict,
    admin_check: bool = Depends(check_admin_permission),
):
    """LLM configuration writes are managed by the SLM server.

    Issue #2400: Deprecated — use SLM settings to modify LLM config.
    POST /api/llm/config is no longer accepted on the main backend to prevent
    config drift between the SLM authority and fleet nodes.
    """
    logger.warning(
        "Rejected POST /api/llm/config — write endpoint deprecated (#2400). "
        "Caller should use SLM settings interface."
    )
    return JSONResponse(
        status_code=410,
        content={
            "detail": (
                "LLM configuration is managed by the SLM server. "
                "Use the SLM settings interface at /api/slm/config to modify LLM settings."
            ),
            "redirect": "/api/slm/config",
        },
    )


@router.post("/test_connection", response_model=LLMConnectionTestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_llm_connection",
    error_code_prefix="LLM",
)
async def test_llm_connection(
    current_user: dict = Depends(get_current_user),
):
    """Test LLM connection with current configuration.

    Issue #744: Requires authenticated user.
    """
    try:
        result = await ConnectionTester.test_ollama_connection()
        return result
    except Exception:
        logger.error("LLM connection test failed: %s", "Internal server error")
        return {
            "status": "disconnected",
            "message": "Failed to test LLM connection",
        }


@router.get("/models", response_model=LLMModelsResponse)
@cache_response(cache_key="llm_models", ttl=180)  # Cache for 3 minutes - RESTORED
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_llm_models",
    error_code_prefix="LLM",
)
async def get_available_llm_models(
    current_user: dict = Depends(get_current_user),
):
    """Get list of available LLM models.

    Issue #744: Requires authenticated user.
    """
    try:
        result = await ModelManager.get_available_models()
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["error"])

        return {"models": result["models"], "total_count": result["total_count"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting available models: %s", str(e))
        raise HTTPException(status_code=500, detail="Error getting available models")


@router.get("/current", response_model=LLMCurrentResponse)
@cache_response(cache_key="current_llm", ttl=60)  # Cache for 1 minute
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_llm",
    error_code_prefix="LLM",
)
async def get_current_llm(
    current_user: dict = Depends(get_current_user),
):
    """Get current LLM model and configuration.

    Issue #744: Requires authenticated user.
    """
    try:
        config = ConfigService.get_llm_config()
        current_model = config.get("model", ModelConstants.DEFAULT_OLLAMA_MODEL)

        return {
            "model": current_model,
            "provider": config.get("provider", "ollama"),
            "config": config,
        }
    except Exception as e:
        logger.error("Error getting current LLM: %s", str(e))
        raise HTTPException(status_code=500, detail="Error getting current LLM")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_llm_provider",
    error_code_prefix="LLM",
)
async def _update_local_provider(model_name: str) -> None:
    """Update local Ollama provider configuration. Issue #620."""
    logger.info("UNIFIED CONFIG: Updating Ollama model to: %s", model_name)
    await asyncio.to_thread(config.update_llm_model, model_name)


def _update_cloud_provider(cloud_provider: str, cloud_model: str) -> None:
    """Update cloud provider configuration. Issue #620."""
    logger.info(
        "UNIFIED CONFIG: Updating cloud provider to: %s, model: %s",
        cloud_provider,
        cloud_model,
    )
    config.set("backend.llm.provider_type", "cloud")
    config.set("backend.llm.cloud.provider", cloud_provider)
    config.set(
        f"backend.llm.cloud.providers.{cloud_provider}.selected_model",
        cloud_model,
    )


def _build_llm_update_response() -> dict:
    """Build LLM provider update response. Issue #620."""
    current_llm_config = config.get("llm", {})
    return {
        "status": "success",
        "message": "LLM provider configuration updated successfully using unified config system",
        "current_config": {
            "provider_type": current_llm_config.get("unified", {}).get("provider_type", "local"),
            "selected_model": (
                current_llm_config.get("unified", {})
                .get("local", {})
                .get("providers", {})
                .get("ollama", {})
                .get("selected_model")
                or current_llm_config.get("ollama", {}).get("model", "unknown")
            ),
            "streaming": config.get("backend.streaming", False),
        },
    }


@router.post("/provider", response_model=DataResponse[LLMDeprecatedData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_llm_provider",
    error_code_prefix="LLM",
)
async def update_llm_provider(
    provider_data: dict,
    admin_check: bool = Depends(check_admin_permission),
):
    """LLM provider configuration writes are managed by the SLM server.

    Issue #2400: Deprecated — use SLM settings to modify LLM provider.
    POST /api/llm/provider is no longer accepted on the main backend to prevent
    config drift between the SLM authority and fleet nodes.
    """
    logger.warning(
        "Rejected POST /api/llm/provider — write endpoint deprecated (#2400). "
        "Caller should use SLM settings interface."
    )
    return JSONResponse(
        status_code=410,
        content={
            "detail": (
                "LLM configuration is managed by the SLM server. "
                "Use the SLM settings interface at /api/slm/config to modify LLM settings."
            ),
            "redirect": "/api/slm/config",
        },
    )


@router.get("/embedding/models", response_model=LLMEmbeddingModelsResponse)
@cache_response(cache_key="embedding_models", ttl=300)  # Cache for 5 minutes
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_embedding_models",
    error_code_prefix="LLM",
)
async def get_available_embedding_models(
    current_user: dict = Depends(get_current_user),
):
    """Get list of available embedding models.

    Issue #744: Requires authenticated user.
    """
    try:
        # For now, return Ollama models (embedding models are typically the same as LLM models)
        result = await ModelManager.get_available_models()
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["error"])

        # Filter to common embedding models if possible, otherwise return all
        embedding_models = []
        for model in result["models"]:
            model_name = model.get("name", "") if isinstance(model, dict) else str(model)
            # Cache model_name.lower() to avoid repeated computation (Issue #323)
            model_name_lower = model_name.lower()
            # Common embedding model patterns
            if any(pattern in model_name_lower for pattern in EMBEDDING_MODEL_PATTERNS):
                embedding_models.append(model)
            elif "text" in model_name_lower and any(size in model_name_lower for size in TEXT_MODEL_SIZE_INDICATORS):
                embedding_models.append(model)

        # If no specific embedding models found, include some common ones
        if not embedding_models:
            embedding_models = [
                {"name": "nomic-embed-text", "available": True, "type": "ollama"},
                {"name": "all-minilm:l6-v2", "available": True, "type": "ollama"},
            ]

        return {"models": embedding_models, "total_count": len(embedding_models)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting available embedding models: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail="Error getting available embedding models",
        )


async def _apply_embedding_config(provider: str, model: str, embedding_data: dict) -> None:
    """Helper for update_embedding_model. Ref: #1088."""
    config.set("backend.llm.embedding.provider", provider)
    config.set(f"backend.llm.embedding.providers.{provider}.selected_model", model)
    if "endpoint" in embedding_data:
        config.set(
            f"backend.llm.embedding.providers.{provider}.endpoint",
            embedding_data["endpoint"],
        )
    if provider == "openai" and "api_key" in embedding_data:
        config.set(
            f"backend.llm.embedding.providers.{provider}.api_key",
            embedding_data["api_key"],
        )
    await asyncio.to_thread(config.save_settings)
    await asyncio.to_thread(config.save_config_to_yaml)


@router.post("/embedding", response_model=DataResponse[LLMDeprecatedData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_embedding_model",
    error_code_prefix="LLM",
)
async def update_embedding_model(
    embedding_data: dict,
    admin_check: bool = Depends(check_admin_permission),
):
    """Embedding model configuration writes are managed by the SLM server.

    Issue #2400: Deprecated — use SLM settings to modify embedding model config.
    POST /api/llm/embedding is no longer accepted on the main backend to prevent
    config drift between the SLM authority and fleet nodes.
    """
    logger.warning(
        "Rejected POST /api/llm/embedding — write endpoint deprecated (#2400). "
        "Caller should use SLM settings interface."
    )
    return JSONResponse(
        status_code=410,
        content={
            "detail": (
                "LLM configuration is managed by the SLM server. "
                "Use the SLM settings interface at /api/slm/config to modify LLM settings."
            ),
            "redirect": "/api/slm/config",
        },
    )


def _build_local_provider_status(local_config: dict, ollama_url: str) -> dict:
    """
    Build status dictionary for local LLM providers.

    Issue #281: Extracted helper for local provider status building.

    Args:
        local_config: Local provider configuration
        ollama_url: Default Ollama URL from config

    Returns:
        Dictionary with ollama and lmstudio provider status
    """
    providers = local_config.get("providers", {})

    return {
        "ollama": {
            "configured": bool(providers.get("ollama", {}).get("selected_model")),
            "status": "connected",  # Assume connected for now
            "model": providers.get("ollama", {}).get("selected_model", ""),
            "endpoint": providers.get("ollama", {}).get("host", ollama_url),
        },
        "lmstudio": {
            "configured": bool(providers.get("lmstudio", {}).get("selected_model")),
            "status": "disconnected",  # Typically not running
            "model": providers.get("lmstudio", {}).get("selected_model", ""),
            "endpoint": providers.get("lmstudio", {}).get("endpoint", f"{ollama_url}/v1"),
        },
    }


def _build_cloud_provider_status(cloud_config: dict) -> dict:
    """
    Build status dictionary for cloud LLM providers.

    Issue #281: Extracted helper for cloud provider status building.

    Args:
        cloud_config: Cloud provider configuration

    Returns:
        Dictionary with openai and anthropic provider status
    """
    providers = cloud_config.get("providers", {})

    openai_config = providers.get("openai", {})
    anthropic_config = providers.get("anthropic", {})

    return {
        "openai": {
            "configured": bool(openai_config.get("api_key")),
            "status": "connected" if openai_config.get("api_key") else "disconnected",
            "model": openai_config.get("selected_model", ""),
            "endpoint": openai_config.get("endpoint", "https://api.openai.com/v1"),
        },
        "anthropic": {
            "configured": bool(anthropic_config.get("api_key")),
            "status": ("connected" if anthropic_config.get("api_key") else "disconnected"),
            "model": anthropic_config.get("selected_model", ""),
            "endpoint": anthropic_config.get("endpoint", "https://api.anthropic.com/v1"),
        },
    }


def _build_active_provider_info(provider_type: str, local_config: dict, cloud_config: dict) -> dict:
    """
    Build active provider information dictionary.

    Issue #281: Extracted helper for active provider info building.

    Args:
        provider_type: Current provider type (local or cloud)
        local_config: Local provider configuration
        cloud_config: Cloud provider configuration

    Returns:
        Dictionary with active provider type, name, and model
    """
    if provider_type == "local":
        return {
            "type": provider_type,
            "name": local_config.get("provider", "ollama"),
            "model": (local_config.get("providers", {}).get("ollama", {}).get("selected_model", "")),
        }

    # Cloud provider
    cloud_provider = cloud_config.get("provider", "openai")
    return {
        "type": provider_type,
        "name": cloud_provider,
        "model": (cloud_config.get("providers", {}).get(cloud_provider, {}).get("selected_model", "")),
    }


@router.get("/status/comprehensive", response_model=DataResponse[LLMComprehensiveStatusData])
@cache_response(cache_key="llm_status_comprehensive", ttl=30)  # Cache for 30 seconds
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_comprehensive_llm_status",
    error_code_prefix="LLM",
)
async def get_comprehensive_llm_status(
    current_user: dict = Depends(get_current_user),
):
    """
    Get comprehensive LLM status for GUI settings panel.

    Issue #281: Refactored from 142 lines to use extracted helper methods.
    Issue #744: Requires authenticated user.
    """
    try:
        # Use unified configuration system for all values
        llm_config = config.get("llm", {})
        provider_type = llm_config.get("provider_type", "local")

        # Get provider-specific configurations
        local_config = llm_config.get("local", {})
        cloud_config = llm_config.get("cloud", {})
        ollama_url = ssot_config.ollama_url

        # Build comprehensive status using extracted helpers (Issue #281)
        status = {
            "provider_type": provider_type,
            "providers": {
                "local": _build_local_provider_status(local_config, ollama_url),
                "cloud": _build_cloud_provider_status(cloud_config),
            },
            "active_provider": _build_active_provider_info(provider_type, local_config, cloud_config),
            "settings": {
                "streaming": llm_config.get("streaming", False),
                "timeout": llm_config.get("timeout", 60),
                "max_retries": llm_config.get("max_retries", 3),
            },
        }

        return JSONResponse(status_code=200, content=status)

    except Exception as e:
        logger.error("Failed to get comprehensive LLM status: %s", e)
        return JSONResponse(status_code=500, content={"error": "Failed to get LLM status"})


@router.get("/status", response_model=DataResponse[LLMQuickStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_llm_status",
    error_code_prefix="LLM",
)
async def get_llm_status(
    current_user: dict = Depends(get_current_user),
):
    """Get current LLM status (alias for quick status).

    Issue #744: Requires authenticated user.
    """
    return await get_quick_llm_status()


def _get_model_from_llm_config(llm_config: dict) -> tuple[str, str]:
    """
    Extract model and provider type from LLM config with fallbacks.

    Issue #620: Extracted from get_quick_llm_status for readability.

    Returns:
        Tuple of (model, provider_type)
    """
    # First, try direct ollama config path (most common)
    ollama_config = llm_config.get("ollama", {})
    if ollama_config.get("selected_model"):
        return ollama_config.get("selected_model", ""), "local"

    # Fall back to unified config structure
    unified_config = llm_config.get("unified", {})
    provider_type = unified_config.get("provider_type", "local")

    if provider_type == "local":
        model = _get_model_from_local_config(unified_config)
    else:
        model = _get_model_from_cloud_config(unified_config)

    return model, provider_type


def _get_model_from_local_config(unified_config: dict) -> str:
    """Extract model from local/ollama config paths. Issue #620."""
    local_config = unified_config.get("local", {})
    model = local_config.get("providers", {}).get("ollama", {}).get("selected_model", "")
    if not model:
        nested_local = unified_config.get("unified", {}).get("local", {})
        model = nested_local.get("providers", {}).get("ollama", {}).get("selected_model", "")
    return model


def _get_model_from_cloud_config(unified_config: dict) -> str:
    """Extract model from cloud provider config. Issue #620."""
    cloud_config = unified_config.get("cloud", {})
    provider = cloud_config.get("provider", "openai")
    provider_config = cloud_config.get("providers", {}).get(provider, {})
    api_key = provider_config.get("api_key", "")
    model = provider_config.get("selected_model", "")
    return model if (api_key and model) else ""


@router.get("/status/quick", response_model=DataResponse[LLMQuickStatusData])
@cache_response(cache_key="llm_status_quick", ttl=15)  # Cache for 15 seconds
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quick_llm_status",
    error_code_prefix="LLM",
)
async def get_quick_llm_status(
    current_user: dict = Depends(get_current_user),
):
    """Get quick LLM status check for dashboard.

    Issue #620: Refactored to use helper functions.
    Issue #744: Requires authenticated user.
    """

    try:
        llm_config = ConfigService.get_llm_config()
        model, provider_type = _get_model_from_llm_config(llm_config)
        status = "connected" if model else "disconnected"

        return JSONResponse(
            status_code=200,
            content={
                "status": status,
                "provider_type": provider_type,
                "model": model,
                "timestamp": now_utc().isoformat().replace("+00:00", "Z"),
            },
        )

    except Exception as e:
        logger.error("Failed to get quick LLM status: %s", e)

        return JSONResponse(
            status_code=200,
            content={
                "status": "error",
                "provider_type": "unknown",
                "model": "",
                "error": "Internal server error",
                "timestamp": now_utc().isoformat().replace("+00:00", "Z"),
            },
        )


# =============================================================================
# Provider Health Endpoints (Issue #746)
# =============================================================================


def _build_providers_health_dict(results: dict) -> tuple:
    """Helper for get_all_providers_health. Ref: #1088."""
    providers_health = {}
    available_count = 0
    for provider_name, result in results.items():
        is_available = result.available
        if is_available:
            available_count += 1
        providers_health[provider_name] = {
            "status": result.status.value,
            "available": is_available,
            "message": result.message,
            "response_time_ms": round(result.response_time * 1000, 2),
            "details": result.details or {},
        }
    return providers_health, available_count


@router.get("/health/providers", response_model=DataResponse[LLMProvidersHealthData])
@cache_response(cache_key="llm_providers_health", ttl=30)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_providers_health",
    error_code_prefix="LLM",
)
async def get_all_providers_health():
    """
    Get health status of all configured LLM providers.

    Issue #746: Unified endpoint for frontend to check provider availability.
    Frontend cannot directly contact Ollama (localhost-only), so this backend
    endpoint proxies the health check.

    Returns:
        JSON with health status for all providers (ollama, openai, anthropic, google)
    """

    from services.provider_health import ProviderHealthManager

    try:
        results = await ProviderHealthManager.check_all_providers(timeout=5.0, use_cache=True)
        providers_health, available_count = _build_providers_health_dict(results)
        total_count = len(results)
        if available_count == total_count:
            overall_status = "healthy"
        elif available_count > 0:
            overall_status = "degraded"
        else:
            overall_status = "unavailable"
        return JSONResponse(
            status_code=200,
            content={
                "overall_status": overall_status,
                "available_providers": available_count,
                "total_providers": total_count,
                "providers": providers_health,
                "cache_stats": ProviderHealthManager.get_cache_stats(),
                "timestamp": now_utc().isoformat().replace("+00:00", "Z"),
            },
        )
    except Exception as e:
        logger.error("Failed to check providers health: %s", e)
        return JSONResponse(
            status_code=500,
            content={
                "overall_status": "error",
                "error": "Internal server error",
                "timestamp": now_utc().isoformat().replace("+00:00", "Z"),
            },
        )


@router.get("/health/providers/{provider_name}", response_model=DataResponse[LLMProviderHealthData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_provider_health",
    error_code_prefix="LLM",
)
async def get_provider_health(provider_name: str, use_cache: bool = True):
    """
    Get health status of a specific LLM provider.

    Issue #746: Per-provider health check endpoint.

    Args:
        provider_name: Provider to check (ollama, openai, anthropic, google)
        use_cache: Whether to use cached result (default True)

    Returns:
        JSON with health status for the specific provider
    """

    from services.provider_health import ProviderHealthManager

    try:
        result = await ProviderHealthManager.check_provider_health(
            provider=provider_name.lower(),
            timeout=5.0,
            use_cache=use_cache,
        )

        return JSONResponse(
            status_code=200,
            content={
                "provider": provider_name,
                "status": result.status.value,
                "available": result.available,
                "message": result.message,
                "response_time_ms": round(result.response_time * 1000, 2),
                "details": result.details or {},
                "timestamp": now_utc().isoformat().replace("+00:00", "Z"),
            },
        )

    except Exception as e:
        logger.error("Failed to check %s health: %s", provider_name, e)
        return JSONResponse(
            status_code=500,
            content={
                "provider": provider_name,
                "status": "error",
                "available": False,
                "error": "Internal server error",
                "timestamp": now_utc().isoformat().replace("+00:00", "Z"),
            },
        )


@router.post("/health/providers/clear-cache", response_model=DataResponse[LLMCacheClearData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_provider_health_cache",
    error_code_prefix="LLM",
)
async def clear_provider_health_cache(
    provider_name: str = None,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Clear provider health cache.

    Issue #746: Allows forcing fresh health checks.
    Issue #744: Requires admin authentication.

    Args:
        provider_name: Specific provider to clear, or None to clear all

    Returns:
        Confirmation of cache clear operation
    """
    from services.provider_health import ProviderHealthManager

    try:
        await ProviderHealthManager.clear_cache(provider_name)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"Cache cleared for: {provider_name or 'all providers'}",
                "cache_stats": ProviderHealthManager.get_cache_stats(),
            },
        )

    except Exception as e:
        logger.error("Failed to clear provider health cache: %s", e)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
            },
        )


# ============================================================================
# Tiered Model Routing Endpoints (Issue #696)
# ============================================================================


@router.get("/tiered-routing/metrics", response_model=DataResponse[LLMTieredRoutingMetricsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_tiered_routing_metrics",
    error_code_prefix="LLM",
)
async def get_tiered_routing_metrics(
    current_user: dict = Depends(get_current_user),
):
    """
    Get tiered model routing metrics.

    Issue #696: Provides statistics on model tier usage, complexity scores,
    and fallback frequency for monitoring and optimization.

    Returns:
        Dictionary with routing metrics including:
        - simple_tier_requests: Count of requests routed to simple models
        - complex_tier_requests: Count of requests routed to complex models
        - total_requests: Total routed requests
        - simple_tier_percentage: Percentage using simple tier
        - avg_simple_score: Average complexity score for simple tier
        - avg_complex_score: Average complexity score for complex tier
        - fallback_count: Times simple tier failed and escalated
    """
    try:
        llm_interface = get_llm_service()

        if not hasattr(llm_interface, "_tier_router") or not llm_interface._tier_router:
            return JSONResponse(
                status_code=200,
                content={
                    "enabled": False,
                    "message": "Tiered routing is not enabled",
                },
            )

        metrics = llm_interface._tier_router.get_metrics()

        return JSONResponse(
            status_code=200,
            content={
                "enabled": True,
                "metrics": metrics,
            },
        )

    except Exception as e:
        logger.error("Error getting tiered routing metrics: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Error getting tiered routing metrics",
        )


@router.get("/tiered-routing/config", response_model=DataResponse[LLMTieredRoutingConfigData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_tiered_routing_config",
    error_code_prefix="LLM",
)
async def get_tiered_routing_config(
    current_user: dict = Depends(get_current_user),
):
    """
    Get current tiered routing configuration.

    Issue #696: Returns the active configuration including model assignments,
    threshold values, and feature flags.

    Returns:
        Dictionary with configuration:
        - enabled: Whether tiered routing is active
        - complexity_threshold: Score threshold (0-10) for tier selection
        - models: Model assignments per tier
        - fallback_to_complex: Whether to escalate on simple tier failure
        - logging: Logging configuration
    """
    try:
        llm_interface = get_llm_service()

        if not hasattr(llm_interface, "_tier_router") or not llm_interface._tier_router:
            return JSONResponse(
                status_code=200,
                content={
                    "enabled": False,
                    "message": "Tiered routing is not initialized",
                },
            )

        router = llm_interface._tier_router
        tier_config = router.config

        return JSONResponse(
            status_code=200,
            content={
                "enabled": tier_config.enabled,
                "complexity_threshold": tier_config.complexity_threshold,
                "models": {
                    "simple": tier_config.models.simple,
                    "complex": tier_config.models.complex,
                },
                "fallback_to_complex": tier_config.fallback_to_complex,
                "logging": {
                    "log_scores": tier_config.logging.log_scores,
                    "log_routing_decisions": tier_config.logging.log_routing_decisions,
                },
            },
        )

    except Exception as e:
        logger.error("Error getting tiered routing config: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Error getting tiered routing config",
        )


def _get_tier_router(llm_interface):
    """Helper for update_tiered_routing_config. Ref: #1088.

    Returns the tier router from llm_interface, or raises HTTPException if absent.
    """
    if not hasattr(llm_interface, "_tier_router") or not llm_interface._tier_router:
        raise HTTPException(
            status_code=400,
            detail="Tiered routing is not initialized",
        )
    return llm_interface._tier_router


def _apply_tiered_routing_updates(tier_router, config_data: dict) -> None:
    """Helper for update_tiered_routing_config. Ref: #1088.

    Applies each field from config_data onto tier_router.config in-place.
    Raises HTTPException for out-of-range complexity_threshold.
    """
    if "enabled" in config_data:
        tier_router.config.enabled = bool(config_data["enabled"])

    if "complexity_threshold" in config_data:
        threshold = float(config_data["complexity_threshold"])
        if not 0 <= threshold <= 10:
            raise HTTPException(
                status_code=400,
                detail="complexity_threshold must be between 0 and 10",
            )
        tier_router.config.complexity_threshold = threshold

    if "models" in config_data:
        if "simple" in config_data["models"]:
            tier_router.config.models.simple = str(config_data["models"]["simple"])
        if "complex" in config_data["models"]:
            tier_router.config.models.complex = str(config_data["models"]["complex"])

    if "fallback_to_complex" in config_data:
        tier_router.config.fallback_to_complex = bool(config_data["fallback_to_complex"])


def _build_tiered_routing_response(tier_router) -> dict:
    """Helper for update_tiered_routing_config. Ref: #1088.

    Builds the JSON-serializable response dict from the current tier_router config.
    """
    return {
        "success": True,
        "message": "Tiered routing configuration updated successfully",
        "config": {
            "enabled": tier_router.config.enabled,
            "complexity_threshold": tier_router.config.complexity_threshold,
            "models": {
                "simple": tier_router.config.models.simple,
                "complex": tier_router.config.models.complex,
            },
            "fallback_to_complex": tier_router.config.fallback_to_complex,
        },
    }


@router.post("/tiered-routing/config", response_model=DataResponse[LLMTieredRoutingUpdateData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_tiered_routing_config",
    error_code_prefix="LLM",
)
async def update_tiered_routing_config(
    config_data: dict,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Update tiered routing configuration.

    Issue #696: Allows runtime adjustment of thresholds and model assignments.
    Requires admin authentication.

    Args:
        config_data: Configuration updates with optional fields:
            - enabled: bool
            - complexity_threshold: float (0-10)
            - models.simple: str
            - models.complex: str
            - fallback_to_complex: bool

    Returns:
        Updated configuration and confirmation message
    """
    try:
        llm_interface = get_llm_service()
        tier_router = _get_tier_router(llm_interface)
        _apply_tiered_routing_updates(tier_router, config_data)
        logger.info("Tiered routing configuration updated: %s", config_data)
        return JSONResponse(
            status_code=200,
            content=_build_tiered_routing_response(tier_router),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating tiered routing config: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Error updating tiered routing config",
        )


@router.post("/tiered-routing/metrics/reset", response_model=DataResponse[LLMTieredMetricsResetData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_tiered_routing_metrics",
    error_code_prefix="LLM",
)
async def reset_tiered_routing_metrics(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Reset tiered routing metrics to zero.

    Issue #696: Useful for starting fresh monitoring periods or after
    configuration changes. Requires admin authentication.

    Returns:
        Confirmation of metrics reset
    """
    try:
        llm_interface = get_llm_service()

        if not hasattr(llm_interface, "_tier_router") or not llm_interface._tier_router:
            raise HTTPException(
                status_code=400,
                detail="Tiered routing is not initialized",
            )

        llm_interface._tier_router.reset_metrics()

        logger.info("Tiered routing metrics reset by admin")

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Tiered routing metrics reset successfully",
                "metrics": llm_interface._tier_router.get_metrics(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resetting tiered routing metrics: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Error resetting tiered routing metrics",
        )
