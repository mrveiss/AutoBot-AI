import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from backend.services.config_service import ConfigService
from backend.utils.connection_utils import ConnectionTester, ModelManager

# Import caching utilities (cache_response temporarily disabled)
# from backend.utils.cache_manager import cache_response

router = APIRouter()

logger = logging.getLogger(__name__)


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


@router.get("/models")
# TODO: Re-enable caching after fixing compatibility with FastAPI 0.115.9
# @cache_response(cache_key="llm_models", ttl=180)  # Cache for 3 minutes
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


@router.get("/current")
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


@router.post("/provider")
async def update_llm_provider(provider_data: dict):
    """Update LLM provider configuration using unified config system"""
    try:
        logger.info(f"UNIFIED CONFIG: Received LLM provider update: {provider_data}")

        from src.config import global_config_manager

        # Handle streaming setting
        if "streaming" in provider_data:
            logger.info(
                f"UNIFIED CONFIG: Updating streaming setting to: {provider_data['streaming']}"
            )
            global_config_manager.set_nested(
                "backend.streaming", provider_data["streaming"]
            )

        # Handle local provider updates (Ollama)
        if provider_data.get("provider_type") == "local" and provider_data.get(
            "local_model"
        ):
            model_name = provider_data.get("local_model")
            logger.info(f"UNIFIED CONFIG: Updating Ollama model to: {model_name}")

            # Use the unified model update method
            global_config_manager.update_llm_model(model_name)

        # Handle cloud provider updates
        elif provider_data.get("provider_type") == "cloud":
            if provider_data.get("cloud_provider") and provider_data.get("cloud_model"):
                cloud_provider = provider_data.get("cloud_provider")
                cloud_model = provider_data.get("cloud_model")
                logger.info(
                    f"UNIFIED CONFIG: Updating cloud provider to: {cloud_provider}, model: {cloud_model}"
                )

                # Update provider type
                global_config_manager.set_nested("backend.llm.provider_type", "cloud")
                global_config_manager.set_nested(
                    "backend.llm.cloud.provider", cloud_provider
                )
                global_config_manager.set_nested(
                    f"backend.llm.cloud.providers.{cloud_provider}.selected_model",
                    cloud_model,
                )

        # Save all changes
        global_config_manager.save_settings()

        # Return current configuration
        current_llm_config = global_config_manager.get_llm_config()

        return {
            "status": "success",
            "message": "LLM provider configuration updated successfully using unified config system",
            "current_config": {
                "provider_type": current_llm_config.get("unified", {}).get(
                    "provider_type", "local"
                ),
                "selected_model": (
                    current_llm_config.get("unified", {})
                    .get("local", {})
                    .get("providers", {})
                    .get("ollama", {})
                    .get("selected_model")
                    or current_llm_config.get("ollama", {}).get("model", "unknown")
                ),
                "streaming": global_config_manager.get_nested(
                    "backend.streaming", False
                ),
            },
        }

    except Exception as e:
        logger.error(f"Error updating LLM provider: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating LLM provider: {str(e)}"
        )


@router.get("/embedding/models")
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


@router.post("/embedding")
async def update_embedding_model(embedding_data: dict):
    """Update embedding model configuration"""
    try:
        logger.info(
            f"UNIFIED CONFIG: Received embedding model update: {embedding_data}"
        )

        from src.config import global_config_manager

        provider = embedding_data.get("provider", "ollama")
        model = embedding_data.get("model")

        if not model:
            raise HTTPException(status_code=400, detail="Model name is required")

        logger.info(f"UNIFIED CONFIG: Updating embedding model to: {provider}/{model}")

        # Update embedding configuration in unified config
        global_config_manager.set_nested("backend.llm.embedding.provider", provider)
        global_config_manager.set_nested(
            f"backend.llm.embedding.providers.{provider}.selected_model", model
        )

        if "endpoint" in embedding_data:
            global_config_manager.set_nested(
                f"backend.llm.embedding.providers.{provider}.endpoint",
                embedding_data["endpoint"],
            )

        if provider == "openai" and "api_key" in embedding_data:
            global_config_manager.set_nested(
                f"backend.llm.embedding.providers.{provider}.api_key",
                embedding_data["api_key"],
            )

        # Use the dedicated embedding model update method
        global_config_manager.update_embedding_model(model)

        # Get current configuration for response
        current_config = global_config_manager.get_llm_config()
        embedding_config = current_config.get("unified", {}).get("embedding", {})

        return {
            "status": "success",
            "message": f"Embedding model updated to {provider}/{model}",
            "current_config": {
                "provider": embedding_config.get("provider", provider),
                "selected_model": embedding_config.get("providers", {})
                .get(provider, {})
                .get("selected_model", model),
            },
        }

    except Exception as e:
        logger.error(f"Error updating embedding model: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating embedding model: {str(e)}"
        )


@router.get("/status/comprehensive")
async def get_comprehensive_llm_status():
    """Get comprehensive LLM status for GUI settings panel"""
    try:
        from src.config import (
            BACKEND_HOST_IP,
            BACKEND_PORT,
            HTTP_PROTOCOL,
        )
        from src.config import config as global_config_manager

        llm_config = global_config_manager.get_llm_config()
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
                        "model": local_config.get("providers", {})
                        .get("ollama", {})
                        .get("selected_model", ""),
                        "endpoint": local_config.get("providers", {})
                        .get("ollama", {})
                        .get(
                            "host",
                            f"{HTTP_PROTOCOL}://{BACKEND_HOST_IP}:{BACKEND_PORT}",
                        ),
                    },
                    "lmstudio": {
                        "configured": bool(
                            local_config.get("providers", {})
                            .get("lmstudio", {})
                            .get("selected_model")
                        ),
                        "status": "disconnected",  # Typically not running
                        "model": local_config.get("providers", {})
                        .get("lmstudio", {})
                        .get("selected_model", ""),
                        "endpoint": local_config.get("providers", {})
                        .get("lmstudio", {})
                        .get(
                            "endpoint",
                            f"{HTTP_PROTOCOL}://{BACKEND_HOST_IP}:{BACKEND_PORT}/v1",
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
                        "status": "disconnected"
                        if not cloud_config.get("providers", {})
                        .get("openai", {})
                        .get("api_key")
                        else "connected",
                        "model": cloud_config.get("providers", {})
                        .get("openai", {})
                        .get("selected_model", ""),
                        "endpoint": cloud_config.get("providers", {})
                        .get("openai", {})
                        .get("endpoint", "https://api.openai.com/v1"),
                    },
                    "anthropic": {
                        "configured": bool(
                            cloud_config.get("providers", {})
                            .get("anthropic", {})
                            .get("api_key")
                        ),
                        "status": "disconnected"
                        if not cloud_config.get("providers", {})
                        .get("anthropic", {})
                        .get("api_key")
                        else "connected",
                        "model": cloud_config.get("providers", {})
                        .get("anthropic", {})
                        .get("selected_model", ""),
                        "endpoint": cloud_config.get("providers", {})
                        .get("anthropic", {})
                        .get("endpoint", "https://api.anthropic.com/v1"),
                    },
                },
            },
            "active_provider": {
                "type": provider_type,
                "name": local_config.get("provider", "ollama")
                if provider_type == "local"
                else cloud_config.get("provider", "openai"),
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


@router.get("/status")
async def get_llm_status():
    """Get current LLM status (alias for quick status)"""
    return await get_quick_llm_status()


@router.get("/status/quick")
async def get_quick_llm_status():
    """Get quick LLM status check for dashboard"""
    try:
        from src.config import config as global_config_manager

        llm_config = global_config_manager.get_llm_config()
        provider_type = llm_config.get("provider_type", "local")

        if provider_type == "local":
            local_config = llm_config.get("local", {})
            model = (
                local_config.get("providers", {})
                .get("ollama", {})
                .get("selected_model", "")
            )
            status = "connected" if model else "disconnected"
        else:
            cloud_config = llm_config.get("cloud", {})
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
