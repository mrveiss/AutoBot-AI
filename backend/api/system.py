from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import logging
from datetime import datetime

from backend.utils.connection_utils import ConnectionTester, ModelManager
from backend.services.config_service import ConfigService
from src.config import global_config_manager

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """Health check endpoint for connection status monitoring"""
    try:
        status = await ConnectionTester.get_comprehensive_health_status()
        return status
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "backend": "connected",
                "ollama": "unknown",
                "redis_status": "unknown",
                "redis_search_module_loaded": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@router.post("/restart")
async def restart():
    try:
        logger.info("Restart request received")
        return {"status": "success", "message": "Restart initiated."}
    except Exception as e:
        logger.error(f"Error processing restart request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing restart request: {str(e)}")

@router.get("/models")
async def get_models():
    """Get available LLM models"""
    try:
        result = await ModelManager.get_available_models()
        if result["status"] == "error":
            return JSONResponse(status_code=500, content={"error": result["error"]})
        
        # Format for backward compatibility
        available_models = [model['name'] for model in result['models'] if model.get('available', False)]
        configured_models = {model['name']: model['name'] for model in result['models'] if model.get('configured', False)}
        
        return {
            "status": "success",
            "models": available_models,
            "configured_models": configured_models,
            "detailed_models": result['models']
        }
    except Exception as e:
        logger.error(f"Error getting models: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error getting models: {str(e)}"})

@router.get("/status")
async def get_system_status():
    """Get current system status including LLM configuration"""
    try:
        llm_config = ConfigService.get_llm_config()
        
        # Resolve actual model names for display
        default_llm = llm_config["default_llm"]
        current_llm_display = default_llm
        if default_llm.startswith("ollama_"):
            base_alias = default_llm.replace("ollama_", "")
            actual_model = llm_config["ollama"]["models"].get(base_alias, base_alias)
            current_llm_display = f"Ollama: {actual_model}"
        elif default_llm.startswith("openai_"):
            current_llm_display = f"OpenAI: {default_llm.replace('openai_', '')}"
        
        return {
            "status": "success",
            "current_llm": current_llm_display,
            "default_llm": llm_config["default_llm"],
            "task_llm": llm_config["task_llm"],
            "ollama_models": llm_config["ollama"]["models"],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error getting system status: {str(e)}"})

@router.get("/files")
async def list_files():
    """List files in the project directory"""
    try:
        import os
        base_dir = os.getcwd()
        files_list = []
        
        for item_name in os.listdir(base_dir):
            if item_name.startswith('.'):  # Skip hidden files
                continue
            item_path = os.path.join(base_dir, item_name)
            is_dir = os.path.isdir(item_path)
            files_list.append({
                "name": item_name,
                "path": item_name,
                "is_dir": is_dir,
                "size": os.path.getsize(item_path) if not is_dir else None,
                "last_modified": os.path.getmtime(item_path)
            })
        
        files_list.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return {"files": files_list}
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error listing files: {str(e)}"})
