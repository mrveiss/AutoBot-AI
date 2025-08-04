from fastapi import APIRouter, HTTPException, Request, Form
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
                "timestamp": datetime.now().isoformat(),
            },
        )


@router.post("/restart")
async def restart():
    try:
        logger.info("Restart request received")
        return {"status": "success", "message": "Restart initiated."}
    except Exception as e:
        logger.error(f"Error processing restart request: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error processing restart request: {str(e)}"
        )


@router.get("/models")
async def get_models():
    """Get available LLM models"""
    try:
        result = await ModelManager.get_available_models()
        if result["status"] == "error":
            return JSONResponse(status_code=500, content={"error": result["error"]})

        # Format for backward compatibility
        available_models = [
            model["name"] for model in result["models"] if model.get("available", False)
        ]
        configured_models = {
            model["name"]: model["name"]
            for model in result["models"]
            if model.get("configured", False)
        }

        return {
            "status": "success",
            "models": available_models,
            "configured_models": configured_models,
            "detailed_models": result["models"],
        }
    except Exception as e:
        logger.error(f"Error getting models: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Error getting models: {str(e)}"}
        )


@router.get("/status")
async def get_system_status(request: Request):
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

        # Check for background tasks status
        background_tasks_status = "disabled"
        background_tasks_count = 0

        if hasattr(request.app.state, "background_tasks"):
            background_tasks_count = len(request.app.state.background_tasks)
            if background_tasks_count > 0:
                background_tasks_status = "active"

        return {
            "status": "success",
            "current_llm": current_llm_display,
            "default_llm": llm_config["default_llm"],
            "task_llm": llm_config["task_llm"],
            "ollama_models": llm_config["ollama"]["models"],
            "background_tasks": {
                "status": background_tasks_status,
                "count": background_tasks_count,
            },
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Error getting system status: {str(e)}"}
        )


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """User authentication endpoint"""
    security_layer = request.app.state.security_layer
    user_role = security_layer.authenticate_user(username, password)
    if user_role:
        security_layer.audit_log("login", username, "success", {"ip": "N/A"})
        return {"message": "Login successful", "role": user_role}
    else:
        security_layer.audit_log(
            "login", username, "failure", {"reason": "invalid_credentials"}
        )
        return JSONResponse(status_code=401, content={"message": "Invalid credentials"})


@router.get("/ctx_window")
async def get_context_window():
    """
    Retrieves the content of the LLM's context window.
    For now, this is a placeholder. In a real implementation, this would fetch
    the actual context provided to the LLM in the last interaction.
    """
    mock_context = """
System Prompt: You are an AI assistant.
Conversation History:
User: Hello, how are you?
Agent: I am an AI assistant, functioning as expected. How can I help you today?
Relevant Knowledge:
- AutoBot is an autonomous agent.
- It uses Ollama for local LLM interactions.
"""
    mock_tokens = len(mock_context.split())
    return {"content": mock_context, "tokens": mock_tokens}
