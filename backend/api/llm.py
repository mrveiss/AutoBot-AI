# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from backend.services.config_service import ConfigService
from backend.utils.connection_utils import ConnectionTester, ModelManager
from src.auth_middleware import check_admin_permission, get_current_user
from src.config import UnifiedConfigManager

# Import unified configuration system - NO HARDCODED VALUES
from src.constants.model_constants import ModelConstants

# Import caching utilities from unified cache manager (P4 Cache Consolidation)
from src.utils.advanced_cache_manager import cache_response
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Create singleton config instance
config = UnifiedConfigManager()

router = APIRouter()

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for embedding model detection (Issue #326)
EMBEDDING_MODEL_PATTERNS = {"embed", "nomic", "all-minilm", "sentence"}
TEXT_MODEL_SIZE_INDICATORS = {"small", "large", "medium"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_llm_config",
    error_code_prefix="LLM",
)
@router.get("/config")
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
        raise HTTPException(
            status_code=500, detail=f"Error getting LLM config: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_llm_config",
    error_code_prefix="LLM",
)
@router.post("/config")
async def update_llm_config(
    config_data: dict,
    admin_check: bool = Depends(check_admin_permission),
):
    """Update LLM configuration.

    Issue #744: Requires admin authentication.
    """
    try:
        result = ConfigService.update_llm_config(config_data)
        return result
    except Exception as e:
        logger.error("Error updating LLM config: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error updating LLM config: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_llm_connection",
    error_code_prefix="LLM",
)
@router.post("/test_connection")
async def test_llm_connection(
    current_user: dict = Depends(get_current_user),
):
    """Test LLM connection with current configuration.

    Issue #744: Requires authenticated user.
    """
    try:
        result = await ConnectionTester.test_ollama_connection()
        return result
    except Exception as e:
        logger.error("LLM connection test failed: %s", str(e))
        return {
            "status": "disconnected",
            "message": f"Failed to test LLM connection: {str(e)}",
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_llm_models",
    error_code_prefix="LLM",
)
@router.get("/models")
@cache_response(cache_key="llm_models", ttl=180)  # Cache for 3 minutes - RESTORED
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
        raise HTTPException(
            status_code=500, detail=f"Error getting available models: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_llm",
    error_code_prefix="LLM",
)
@router.get("/current")
@cache_response(cache_key="current_llm", ttl=60)  # Cache for 1 minute
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
        raise HTTPException(
            status_code=500, detail=f"Error getting current LLM: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_llm_provider",
    error_code_prefix="LLM",
)
@router.post("/provider")
async def update_llm_provider(
    provider_data: dict,
    admin_check: bool = Depends(check_admin_permission),
):
    """Update LLM provider configuration using unified config system.

    Issue #744: Requires admin authentication.
    """
    try:
        logger.info("UNIFIED CONFIG: Received LLM provider update: %s", provider_data)

        # Use unified configuration system

        # Handle streaming setting
        if "streaming" in provider_data:
            logger.info(
                f"UNIFIED CONFIG: Updating streaming setting to: {provider_data['streaming']}"
            )
            config.set("backend.streaming", provider_data["streaming"])

        # Handle local provider updates (Ollama)
        if provider_data.get("provider_type") == "local" and provider_data.get(
            "local_model"
        ):
            model_name = provider_data.get("local_model")
            logger.info("UNIFIED CONFIG: Updating Ollama model to: %s", model_name)

            # Use the unified model update method (wrapped for async - Issue #362)
            await asyncio.to_thread(config.update_llm_model, model_name)

        # Handle cloud provider updates
        elif provider_data.get("provider_type") == "cloud":
            if provider_data.get("cloud_provider") and provider_data.get("cloud_model"):
                cloud_provider = provider_data.get("cloud_provider")
                cloud_model = provider_data.get("cloud_model")
                logger.info(
                    "UNIFIED CONFIG: Updating cloud provider to: %s, model: %s",
                    cloud_provider,
                    cloud_model,
                )

                # Update provider type
                config.set("backend.llm.provider_type", "cloud")
                config.set("backend.llm.cloud.provider", cloud_provider)
                config.set(
                    f"backend.llm.cloud.providers.{cloud_provider}.selected_model",
                    cloud_model,
                )

        # Save all changes (wrapped for async - Issue #362)
        await asyncio.to_thread(config.save_settings)
        await asyncio.to_thread(config.save_config_to_yaml)

        # Return current configuration
        current_llm_config = config.get("llm", {})

        return {
            "status": "success",
            "message": (
                "LLM provider configuration updated successfully using unified config system"
            ),
            "current_config": {
                "provider_type": (
                    current_llm_config.get("unified", {}).get("provider_type", "local")
                ),
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

    except Exception as e:
        logger.error("Error updating LLM provider: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error updating LLM provider: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_embedding_models",
    error_code_prefix="LLM",
)
@router.get("/embedding/models")
@cache_response(cache_key="embedding_models", ttl=300)  # Cache for 5 minutes
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
            model_name = (
                model.get("name", "") if isinstance(model, dict) else str(model)
            )
            # Cache model_name.lower() to avoid repeated computation (Issue #323)
            model_name_lower = model_name.lower()
            # Common embedding model patterns
            if any(pattern in model_name_lower for pattern in EMBEDDING_MODEL_PATTERNS):
                embedding_models.append(model)
            elif "text" in model_name_lower and any(
                size in model_name_lower for size in TEXT_MODEL_SIZE_INDICATORS
            ):
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
            detail=f"Error getting available embedding models: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_embedding_model",
    error_code_prefix="LLM",
)
@router.post("/embedding")
async def update_embedding_model(
    embedding_data: dict,
    admin_check: bool = Depends(check_admin_permission),
):
    """Update embedding model configuration.

    Issue #744: Requires admin authentication.
    """
    try:
        logger.info(
            f"UNIFIED CONFIG: Received embedding model update: {embedding_data}"
        )

        # Use unified configuration system

        provider = embedding_data.get("provider", "ollama")
        model = embedding_data.get("model")

        if not model:
            raise HTTPException(status_code=400, detail="Model name is required")

        logger.info(
            "UNIFIED CONFIG: Updating embedding model to: %s/%s", provider, model
        )

        # Update embedding configuration in unified config
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

        # Save configuration changes (wrapped for async - Issue #362)
        await asyncio.to_thread(config.save_settings)
        await asyncio.to_thread(config.save_config_to_yaml)

        # Get current configuration for response
        current_config = config.get("llm", {})
        embedding_config = current_config.get("unified", {}).get("embedding", {})

        return {
            "status": "success",
            "message": f"Embedding model updated to {provider}/{model}",
            "current_config": {
                "provider": embedding_config.get("provider", provider),
                "selected_model": (
                    embedding_config.get("providers", {})
                    .get(provider, {})
                    .get("selected_model", model)
                ),
            },
        }

    except Exception as e:
        logger.error("Error updating embedding model: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error updating embedding model: {str(e)}"
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
            "endpoint": providers.get("lmstudio", {}).get(
                "endpoint", f"{ollama_url}/v1"
            ),
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
            "status": "connected"
            if anthropic_config.get("api_key")
            else "disconnected",
            "model": anthropic_config.get("selected_model", ""),
            "endpoint": anthropic_config.get(
                "endpoint", "https://api.anthropic.com/v1"
            ),
        },
    }


def _build_active_provider_info(
    provider_type: str, local_config: dict, cloud_config: dict
) -> dict:
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
            "model": (
                local_config.get("providers", {})
                .get("ollama", {})
                .get("selected_model", "")
            ),
        }

    # Cloud provider
    cloud_provider = cloud_config.get("provider", "openai")
    return {
        "type": provider_type,
        "name": cloud_provider,
        "model": (
            cloud_config.get("providers", {})
            .get(cloud_provider, {})
            .get("selected_model", "")
        ),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_comprehensive_llm_status",
    error_code_prefix="LLM",
)
@router.get("/status/comprehensive")
@cache_response(cache_key="llm_status_comprehensive", ttl=30)  # Cache for 30 seconds
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
        ollama_url = config.get_service_url("ollama")

        # Build comprehensive status using extracted helpers (Issue #281)
        status = {
            "provider_type": provider_type,
            "providers": {
                "local": _build_local_provider_status(local_config, ollama_url),
                "cloud": _build_cloud_provider_status(cloud_config),
            },
            "active_provider": _build_active_provider_info(
                provider_type, local_config, cloud_config
            ),
            "settings": {
                "streaming": llm_config.get("streaming", False),
                "timeout": llm_config.get("timeout", 60),
                "max_retries": llm_config.get("max_retries", 3),
            },
        }

        return JSONResponse(status_code=200, content=status)

    except Exception as e:
        logger.error("Failed to get comprehensive LLM status: %s", e)
        return JSONResponse(
            status_code=500, content={"error": f"Failed to get LLM status: {str(e)}"}
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_llm_status",
    error_code_prefix="LLM",
)
@router.get("/status")
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
    model = (
        local_config.get("providers", {}).get("ollama", {}).get("selected_model", "")
    )
    if not model:
        nested_local = unified_config.get("unified", {}).get("local", {})
        model = (
            nested_local.get("providers", {})
            .get("ollama", {})
            .get("selected_model", "")
        )
    return model


def _get_model_from_cloud_config(unified_config: dict) -> str:
    """Extract model from cloud provider config. Issue #620."""
    cloud_config = unified_config.get("cloud", {})
    provider = cloud_config.get("provider", "openai")
    provider_config = cloud_config.get("providers", {}).get(provider, {})
    api_key = provider_config.get("api_key", "")
    model = provider_config.get("selected_model", "")
    return model if (api_key and model) else ""


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quick_llm_status",
    error_code_prefix="LLM",
)
@router.get("/status/quick")
@cache_response(cache_key="llm_status_quick", ttl=15)  # Cache for 15 seconds
async def get_quick_llm_status(
    current_user: dict = Depends(get_current_user),
):
    """Get quick LLM status check for dashboard.

    Issue #620: Refactored to use helper functions.
    Issue #744: Requires authenticated user.
    """
    from datetime import datetime, timezone

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
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )

    except Exception as e:
        logger.error("Failed to get quick LLM status: %s", e)
        from datetime import datetime, timezone

        return JSONResponse(
            status_code=200,
            content={
                "status": "error",
                "provider_type": "unknown",
                "model": "",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )


# =============================================================================
# Provider Health Endpoints (Issue #746)
# =============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_providers_health",
    error_code_prefix="LLM",
)
@router.get("/health/providers")
@cache_response(cache_key="llm_providers_health", ttl=30)
async def get_all_providers_health():
    """
    Get health status of all configured LLM providers.

    Issue #746: Unified endpoint for frontend to check provider availability.
    Frontend cannot directly contact Ollama (localhost-only), so this backend
    endpoint proxies the health check.

    Returns:
        JSON with health status for all providers (ollama, openai, anthropic, google)
    """
    from datetime import datetime, timezone

    from backend.services.provider_health import ProviderHealthManager

    try:
        # Check all providers in parallel (uses 30s cache internally)
        results = await ProviderHealthManager.check_all_providers(
            timeout=5.0, use_cache=True
        )

        # Convert results to JSON-serializable format
        providers_health = {}
        available_count = 0
        total_count = len(results)

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

        # Determine overall status
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
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )

    except Exception as e:
        logger.error("Failed to check providers health: %s", e)
        return JSONResponse(
            status_code=500,
            content={
                "overall_status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_provider_health",
    error_code_prefix="LLM",
)
@router.get("/health/providers/{provider_name}")
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
    from datetime import datetime, timezone

    from backend.services.provider_health import ProviderHealthManager

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
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
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
                "error": str(e),
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_provider_health_cache",
    error_code_prefix="LLM",
)
@router.post("/health/providers/clear-cache")
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
    from backend.services.provider_health import ProviderHealthManager

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
                "error": str(e),
            },
        )
