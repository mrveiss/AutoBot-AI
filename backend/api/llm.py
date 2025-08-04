from fastapi import APIRouter, HTTPException
import logging

from backend.utils.connection_utils import ConnectionTester, ModelManager
from backend.services.config_service import ConfigService

# Import caching utilities
from backend.utils.cache_manager import cache_response

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
    """Update LLM provider configuration"""
    try:
        logger.info(f"Received LLM provider update: {provider_data}")

        # Convert frontend provider data to backend config format
        llm_config_update = {
            "provider_type": provider_data.get("provider_type", "local"),
        }

        if provider_data.get("provider_type") == "local":
            llm_config_update["local"] = {
                "provider": provider_data.get("local_provider", "ollama"),
                "selected_model": provider_data.get("local_model", ""),
            }
        elif provider_data.get("provider_type") == "cloud":
            llm_config_update["cloud"] = {
                "provider": provider_data.get("cloud_provider", "openai"),
                "selected_model": provider_data.get("cloud_model", ""),
            }

        # Update the LLM configuration
        result = ConfigService.update_llm_config(llm_config_update)

        return {
            "status": "success",
            "message": "LLM provider configuration updated successfully",
            "updated_config": llm_config_update,
        }

    except Exception as e:
        logger.error(f"Error updating LLM provider: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating LLM provider: {str(e)}"
        )
