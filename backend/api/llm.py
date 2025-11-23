# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from backend.services.config_service import ConfigService
from backend.utils.connection_utils import ConnectionTester, ModelManager
from src.constants.network_constants import NetworkConstants

# Import unified configuration system - NO HARDCODED VALUES
from src.unified_config_manager import UnifiedConfigManager

# Import caching utilities from unified cache manager (P4 Cache Consolidation)
from src.utils.advanced_cache_manager import cache_response
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Create singleton config instance
config = UnifiedConfigManager()

router = APIRouter()

logger = logging.getLogger(__name__)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_llm_config",
    error_code_prefix="LLM",
)
@router.get("/config")
async def get_llm_config():
    """Get current LLM configuration"""
    try:
        return ConfigService.get_llm_config()
    except Exception as e:
        logger.error(f"Error getting LLM config: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting LLM config: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_llm_config",
    error_code_prefix="LLM",
)
@router.post("/config")
async def update_llm_config(config_data: dict):
    """Update LLM configuration"""
    try:
        result = ConfigService.update_llm_config(config_data)
        return result
    except Exception as e:
        logger.error(f"Error updating LLM config: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating LLM config: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_llm_connection",
    error_code_prefix="LLM",
)
@router.post("/test_connection")
async def test_llm_connection():
    """Test LLM connection with current configuration"""
    try:
        result = await ConnectionTester.test_ollama_connection()
        return result
    except Exception as e:
        logger.error(f"LLM connection test failed: {str(e)}")
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
async def get_available_llm_models():
    """Get list of available LLM models"""
    try:
        result = await ModelManager.get_available_models()
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["error"])

        return {"models": result["models"], "total_count": result["total_count"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting available models: {str(e)}")
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
async def get_current_llm():
    """Get current LLM model and configuration"""
    try:
        config = ConfigService.get_llm_config()
        current_model = config.get("model", "llama3.2")

        return {
            "model": current_model,
            "provider": config.get("provider", "ollama"),
            "config": config,
        }
    except Exception as e:
        logger.error(f"Error getting current LLM: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting current LLM: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_llm_provider",
    error_code_prefix="LLM",
)
@router.post("/provider")
async def update_llm_provider(provider_data: dict):
    """Update LLM provider configuration using unified config system"""
    try:
        logger.info(f"UNIFIED CONFIG: Received LLM provider update: {provider_data}")

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
            logger.info(f"UNIFIED CONFIG: Updating Ollama model to: {model_name}")

            # Use the unified model update method
            config.update_llm_model(model_name)

        # Handle cloud provider updates
        elif provider_data.get("provider_type") == "cloud":
            if provider_data.get("cloud_provider") and provider_data.get("cloud_model"):
                cloud_provider = provider_data.get("cloud_provider")
                cloud_model = provider_data.get("cloud_model")
                logger.info(
                    f"UNIFIED CONFIG: Updating cloud provider to: {cloud_provider}, model: {cloud_model}"
                )

                # Update provider type
                config.set("backend.llm.provider_type", "cloud")
                config.set("backend.llm.cloud.provider", cloud_provider)
                config.set(
                    f"backend.llm.cloud.providers.{cloud_provider}.selected_model",
                    cloud_model,
                )

        # Save all changes
        config.save()

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
        logger.error(f"Error updating LLM provider: {str(e)}")
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
async def get_available_embedding_models():
    """Get list of available embedding models"""
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
            # Common embedding model patterns
            if any(
                pattern in model_name.lower()
                for pattern in ["embed", "nomic", "all-minilm", "sentence"]
            ):
                embedding_models.append(model)
            elif "text" in model_name.lower() and any(
                size in model_name.lower() for size in ["small", "large", "medium"]
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
        logger.error(f"Error getting available embedding models: {str(e)}")
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
async def update_embedding_model(embedding_data: dict):
    """Update embedding model configuration"""
    try:
        logger.info(
            f"UNIFIED CONFIG: Received embedding model update: {embedding_data}"
        )

        # Use unified configuration system

        provider = embedding_data.get("provider", "ollama")
        model = embedding_data.get("model")

        if not model:
            raise HTTPException(status_code=400, detail="Model name is required")

        logger.info(f"UNIFIED CONFIG: Updating embedding model to: {provider}/{model}")

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

        # Use the dedicated embedding model update method
        config.update_embedding_model(model)

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
        logger.error(f"Error updating embedding model: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating embedding model: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_comprehensive_llm_status",
    error_code_prefix="LLM",
)
@router.get("/status/comprehensive")
@cache_response(cache_key="llm_status_comprehensive", ttl=30)  # Cache for 30 seconds
async def get_comprehensive_llm_status():
    """Get comprehensive LLM status for GUI settings panel"""
    try:
        # Use unified configuration system for all values

        llm_config = config.get("llm", {})
        provider_type = llm_config.get("provider_type", "local")

        # Get provider-specific configurations
        local_config = llm_config.get("local", {})
        cloud_config = llm_config.get("cloud", {})

        # Build comprehensive status using main AutoBot OS environment configuration
        status = {
            "provider_type": provider_type,
            "providers": {
                "local": {
                    "ollama": {
                        "configured": bool(
                            local_config.get("providers", {})
                            .get("ollama", {})
                            .get("selected_model")
                        ),
                        "status": "connected",  # Assume connected for now
                        "model": (
                            local_config.get("providers", {})
                            .get("ollama", {})
                            .get("selected_model", "")
                        ),
                        "endpoint": (
                            local_config.get("providers", {})
                            .get("ollama", {})
                            .get(
                                "host",
                                config.get_service_url("ollama"),
                            )
                        ),
                    },
                    "lmstudio": {
                        "configured": bool(
                            local_config.get("providers", {})
                            .get("lmstudio", {})
                            .get("selected_model")
                        ),
                        "status": "disconnected",  # Typically not running
                        "model": (
                            local_config.get("providers", {})
                            .get("lmstudio", {})
                            .get("selected_model", "")
                        ),
                        "endpoint": (
                            local_config.get("providers", {})
                            .get("lmstudio", {})
                            .get(
                                "endpoint",
                                f"{config.get_service_url('ollama')}/v1",
                            )
                        ),
                    },
                },
                "cloud": {
                    "openai": {
                        "configured": bool(
                            cloud_config.get("providers", {})
                            .get("openai", {})
                            .get("api_key")
                        ),
                        "status": (
                            "disconnected"
                            if not cloud_config.get("providers", {})
                            .get("openai", {})
                            .get("api_key")
                            else "connected"
                        ),
                        "model": (
                            cloud_config.get("providers", {})
                            .get("openai", {})
                            .get("selected_model", "")
                        ),
                        "endpoint": (
                            cloud_config.get("providers", {})
                            .get("openai", {})
                            .get("endpoint", "https://api.openai.com/v1")
                        ),
                    },
                    "anthropic": {
                        "configured": bool(
                            cloud_config.get("providers", {})
                            .get("anthropic", {})
                            .get("api_key")
                        ),
                        "status": (
                            "disconnected"
                            if not cloud_config.get("providers", {})
                            .get("anthropic", {})
                            .get("api_key")
                            else "connected"
                        ),
                        "model": (
                            cloud_config.get("providers", {})
                            .get("anthropic", {})
                            .get("selected_model", "")
                        ),
                        "endpoint": (
                            cloud_config.get("providers", {})
                            .get("anthropic", {})
                            .get("endpoint", "https://api.anthropic.com/v1")
                        ),
                    },
                },
            },
            "active_provider": {
                "type": provider_type,
                "name": (
                    local_config.get("provider", "ollama")
                    if provider_type == "local"
                    else cloud_config.get("provider", "openai")
                ),
                "model": (
                    local_config.get("providers", {})
                    .get("ollama", {})
                    .get("selected_model", "")
                    if provider_type == "local"
                    else cloud_config.get("providers", {})
                    .get(cloud_config.get("provider", "openai"), {})
                    .get("selected_model", "")
                ),
            },
            "settings": {
                "streaming": llm_config.get("streaming", False),
                "timeout": llm_config.get("timeout", 60),
                "max_retries": llm_config.get("max_retries", 3),
            },
        }

        return JSONResponse(status_code=200, content=status)

    except Exception as e:
        logger.error(f"Failed to get comprehensive LLM status: {e}")
        return JSONResponse(
            status_code=500, content={"error": f"Failed to get LLM status: {str(e)}"}
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_llm_status",
    error_code_prefix="LLM",
)
@router.get("/status")
async def get_llm_status():
    """Get current LLM status (alias for quick status)"""
    return await get_quick_llm_status()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quick_llm_status",
    error_code_prefix="LLM",
)
@router.get("/status/quick")
@cache_response(cache_key="llm_status_quick", ttl=15)  # Cache for 15 seconds
async def get_quick_llm_status():
    """Get quick LLM status check for dashboard"""
    try:
        # Use unified configuration system

        llm_config = config.get("llm", {})

        # Get provider type from unified config structure
        unified_config = llm_config.get("unified", {})
        provider_type = unified_config.get("provider_type", "local")

        if provider_type == "local":
            # Look in the correct path: unified.local.providers.ollama
            local_config = unified_config.get("local", {})
            model = (
                local_config.get("providers", {})
                .get("ollama", {})
                .get("selected_model", "")
            )
            status = "connected" if model else "disconnected"
        else:
            # Look in the correct path: unified.cloud.providers.[provider]
            cloud_config = unified_config.get("cloud", {})
            provider = cloud_config.get("provider", "openai")
            api_key = (
                cloud_config.get("providers", {}).get(provider, {}).get("api_key", "")
            )
            model = (
                cloud_config.get("providers", {})
                .get(provider, {})
                .get("selected_model", "")
            )
            status = "connected" if api_key and model else "disconnected"

        return JSONResponse(
            status_code=200,
            content={
                "status": status,
                "provider_type": provider_type,
                "model": model,
                "timestamp": "2025-08-18T10:31:00Z",
            },
        )

    except Exception as e:
        logger.error(f"Failed to get quick LLM status: {e}")
        return JSONResponse(
            status_code=200,
            content={
                "status": "error",
                "provider_type": "unknown",
                "model": "",
                "error": str(e),
            },
        )
