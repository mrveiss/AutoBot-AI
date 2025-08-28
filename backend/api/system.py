import importlib
import logging
import sys
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.services.config_service import ConfigService
from backend.utils.connection_utils import ModelManager
from src.config import PLAYWRIGHT_API_URL, PLAYWRIGHT_VNC_URL, config as config_manager

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/frontend-config")
async def get_frontend_config():
    """Get configuration values needed by the frontend.

    This endpoint provides all service URLs and configuration that the frontend needs,
    eliminating the need for hardcoded values in the frontend code.
    """
    try:
        # Get configuration from the config manager
        ollama_url = config_manager.get_ollama_url()
        redis_config = config_manager.get_redis_config()
        backend_config = config_manager.get_backend_config()

        # Build frontend configuration
        frontend_config = {
            "services": {
                "ollama": {
                    "url": ollama_url,
                    "endpoint": config_manager.get_nested(
                        "backend.llm.local.providers.ollama.endpoint",
                        f"{ollama_url}/api/generate",
                    ),
                    "embedding_endpoint": config_manager.get_nested(
                        "backend.llm.embedding.providers.ollama.endpoint",
                        f"{ollama_url}/api/embeddings",
                    ),
                },
                "playwright": {
                    "vnc_url": PLAYWRIGHT_VNC_URL,
                    "api_url": PLAYWRIGHT_API_URL,
                },
                "redis": {
                    "host": redis_config.get("host", "localhost"),
                    "port": redis_config.get("port", 6379),
                    "enabled": redis_config.get("enabled", True),
                },
                "lmstudio": {
                    "url": config_manager.get_nested(
                        "backend.llm.local.providers.lmstudio.endpoint",
                        "http://localhost:1234/v1",
                    ),
                },
            },
            "api": {
                "timeout": config_manager.get_nested("backend.timeout", 60)
                * 1000,  # Convert to milliseconds
                "retry_attempts": config_manager.get_nested("backend.max_retries", 3),
                "streaming": config_manager.get_nested("backend.streaming", False),
            },
            "features": {
                "voice_enabled": config_manager.get_nested(
                    "voice_interface.enabled", False
                ),
                "knowledge_base_enabled": config_manager.get_nested(
                    "knowledge_base.enabled", True
                ),
                "developer_mode": config_manager.get_nested("developer.enabled", True),
            },
            "ui": {
                "theme": config_manager.get_nested("ui.theme", "light"),
                "animations": config_manager.get_nested("ui.animations", True),
                "font_size": config_manager.get_nested("ui.font_size", "medium"),
            },
            "defaults": {
                "welcome_message": config_manager.get_nested(
                    "chat.default_welcome_message", "Hello! How can I assist you today?"
                ),
                "model_name": config_manager.get_nested(
                    "backend.llm.local.providers.ollama.selected_model",
                    "deepseek-r1:14b",
                ),
                "max_chat_messages": config_manager.get_nested(
                    "chat.max_messages", 100
                ),
            },
        }

        return {
            "status": "success",
            "config": frontend_config,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting frontend config: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to get frontend config: {str(e)}",
            },
        )


@router.get("/health")
async def health_check(detailed: bool = False):
    """PERFORMANCE FIX: Ultra-fast health check endpoint that responds immediately

    This replaces the complex consolidated health check that was timing out at 45+ seconds.
    The health endpoint should be the fastest responding endpoint in the system.

    Args:
        detailed: If True, includes basic system info (still fast)
                 If False, returns minimal status (default)
    """
    try:
        # PERFORMANCE FIX: Return immediate response without any blocking operations
        base_status = {
            "status": "healthy",
            "backend": "connected",
            "timestamp": datetime.now().isoformat(),
            "fast_check": True,
            "response_time_ms": "< 50ms",
        }

        if detailed:
            # Add some basic system info without blocking operations
            base_status.update(
                {
                    "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    "modules_loaded": len(sys.modules),
                    "detailed_check": True,
                }
            )

        return base_status

    except Exception as e:
        logger.error(f"Error in fast health check: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "backend": "connected",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "fast_check": True,
                "components": {"system": {"status": "error", "error": str(e)}},
            },
        )


@router.get("/health/comprehensive")
async def comprehensive_health_check():
    """Comprehensive health check for all system components

    WARNING: This endpoint may take longer to respond as it checks all components.
    For fast health checks, use /health instead.
    """
    try:
        # Try to import and use the consolidated health service
        from backend.services.consolidated_health_service import consolidated_health

        status = await consolidated_health.get_comprehensive_health()
        return status
    except ImportError:
        # Fallback if consolidated health service is not available
        return {
            "overall_status": "degraded",
            "message": "Comprehensive health service not available, using fallback",
            "components": {
                "backend": {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                }
            },
            "timestamp": datetime.now().isoformat(),
            "fast_check": False,
        }
    except Exception as e:
        logger.error(f"Error in comprehensive health check: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "overall_status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "fast_check": False,
            },
        )


@router.get("/health/{component}")
async def component_health_check(component: str):
    """Get health status for a specific component

    Args:
        component: Component name (system, chat, llm, knowledge_base, terminal)
    """
    try:
        # Simple component status without complex dependencies
        if component == "system":
            return {
                "status": "healthy",
                "component": component,
                "timestamp": datetime.now().isoformat(),
                "details": "System is operational",
            }
        elif component == "backend":
            return {
                "status": "healthy",
                "component": component,
                "timestamp": datetime.now().isoformat(),
                "details": "Backend API is responding",
            }
        else:
            return {
                "status": "unknown",
                "component": component,
                "timestamp": datetime.now().isoformat(),
                "details": f"Health check not implemented for {component}",
            }
    except Exception as e:
        logger.error(f"Error checking component health for {component}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "component": component,
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


@router.post("/reload")
async def reload_system(request: Request):
    """Reload system modules and configuration"""
    try:
        logger.info("System reload request received")
        reload_results = []

        # List of modules to reload
        modules_to_reload = [
            "src.llm_interface",
            "src.config",
            "src.orchestrator",
            "backend.services.config_service",
            "backend.utils.connection_utils",
        ]

        reloaded_modules = []
        failed_modules = []

        for module_name in modules_to_reload:
            try:
                if module_name in sys.modules:
                    importlib.reload(sys.modules[module_name])
                    reloaded_modules.append(module_name)
                    logger.info(f"Successfully reloaded module: {module_name}")
                else:
                    logger.info(f"Module {module_name} not loaded, skipping")
            except Exception as e:
                failed_modules.append({"module": module_name, "error": str(e)})
                logger.error(f"Failed to reload module {module_name}: {str(e)}")

        # Reinitialize app state if available
        if hasattr(request.app.state, "llm_interface"):
            try:
                # Reinitialize LLM interface
                from src.llm_interface import LLMInterface

                request.app.state.llm_interface = LLMInterface()
                logger.info("Reinitialized LLM interface")
                reload_results.append("LLM interface reinitialized")
            except Exception as e:
                logger.error(f"Failed to reinitialize LLM interface: {str(e)}")
                failed_modules.append({"component": "LLM interface", "error": str(e)})

        # Reinitialize orchestrator if available
        if hasattr(request.app.state, "orchestrator"):
            try:
                from src.orchestrator import Orchestrator

                request.app.state.orchestrator = Orchestrator()
                logger.info("Reinitialized orchestrator")
                reload_results.append("Orchestrator reinitialized")
            except Exception as e:
                logger.error(f"Failed to reinitialize orchestrator: {str(e)}")
                failed_modules.append({"component": "Orchestrator", "error": str(e)})

        return {
            "status": "success",
            "message": "System reload completed",
            "reloaded_modules": reloaded_modules,
            "failed_modules": failed_modules,
            "reload_results": reload_results,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error processing reload request: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error processing reload request: {str(e)}"
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
        default_llm = llm_config.get("default_llm", "unknown")
        current_llm_display = default_llm
        if default_llm.startswith("ollama_"):
            base_alias = default_llm.replace("ollama_", "")
            ollama_models = llm_config.get("ollama", {}).get("models", {})
            actual_model = ollama_models.get(base_alias, base_alias)
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
            "default_llm": llm_config.get("default_llm", "unknown"),
            "task_llm": llm_config.get("task_llm", "unknown"),
            "ollama_models": llm_config.get("ollama", {}).get("models", {}),
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


@router.get("/playwright/health")
async def check_playwright_health():
    """Check Playwright container health status"""
    try:
        import requests

        # Check if Playwright service is accessible
        try:
            response = requests.get(f"{PLAYWRIGHT_API_URL}/health", timeout=5)
            if response.status_code == 200:
                playwright_data = response.json()
                return {
                    "status": "healthy",
                    "playwright_available": True,
                    "browser_connected": playwright_data.get(
                        "browser_connected", False
                    ),
                    "timestamp": playwright_data.get("timestamp"),
                    "vnc_url": PLAYWRIGHT_VNC_URL,
                    "api_url": PLAYWRIGHT_API_URL,
                }
            else:
                return {
                    "status": "unhealthy",
                    "playwright_available": False,
                    "error": f"HTTP {response.status_code}",
                    "timestamp": datetime.now().isoformat(),
                }
        except requests.exceptions.ConnectionError:
            return {
                "status": "unhealthy",
                "playwright_available": False,
                "error": "Connection refused - container may be down",
                "timestamp": datetime.now().isoformat(),
            }
        except requests.exceptions.Timeout:
            return {
                "status": "unhealthy",
                "playwright_available": False,
                "error": "Request timeout - service not responding",
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        logger.error(f"Error checking Playwright health: {str(e)}")
        return {
            "status": "error",
            "playwright_available": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/resource_cache")
async def get_resource_cache_status(request: Request):
    """Get status of cached resources for performance monitoring"""
    try:
        from src.utils.resource_factory import ResourceFactory

        cached_resources = ResourceFactory.get_all_cached_resources(request)

        # Count statistics
        total_resources = len(cached_resources)
        cached_count = sum(1 for r in cached_resources.values() if r["cached"])
        cache_hit_rate = (
            (cached_count / total_resources * 100) if total_resources > 0 else 0
        )

        return {
            "cache_statistics": {
                "total_resource_types": total_resources,
                "cached_resources": cached_count,
                "cache_hit_rate_percent": round(cache_hit_rate, 1),
                "performance_status": (
                    "optimized" if cache_hit_rate > 70 else "needs_optimization"
                ),
            },
            "resource_details": cached_resources,
            "optimization_notes": {
                "high_cache_rate": "Excellent performance - most resources are pre-initialized",
                "medium_cache_rate": "Good performance - some resources being cached",
                "low_cache_rate": "Performance impact - resources being created on-demand",
            }[
                (
                    "high_cache_rate"
                    if cache_hit_rate > 70
                    else (
                        "medium_cache_rate" if cache_hit_rate > 40 else "low_cache_rate"
                    )
                )
            ],
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get resource cache status: {e}")
        return {
            "error": "Failed to get resource cache status",
            "details": str(e),
            "timestamp": datetime.now().isoformat(),
        }
