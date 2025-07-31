from fastapi import APIRouter, HTTPException
import logging

from backend.utils.connection_utils import ConnectionTester, ModelManager
from backend.services.config_service import ConfigService

router = APIRouter()

logger = logging.getLogger(__name__)

@router.get("/config")
async def get_llm_config():
    """Get current LLM configuration"""
    try:
        return ConfigService.get_llm_config()
    except Exception as e:
        logger.error(f"Error getting LLM config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting LLM config: {str(e)}")

@router.post("/config")
async def update_llm_config(config_data: dict):
    """Update LLM configuration"""
    try:
        result = ConfigService.update_llm_config(config_data)
        return result
    except Exception as e:
        logger.error(f"Error updating LLM config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating LLM config: {str(e)}")

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
            "message": f"Failed to test LLM connection: {str(e)}"
        }

@router.get("/models")
async def get_available_llm_models():
    """Get list of available LLM models"""
    try:
        result = await ModelManager.get_available_models()
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["error"])
        
        return {
            "models": result["models"],
            "total_count": result["total_count"]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting available models: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting available models: {str(e)}")
