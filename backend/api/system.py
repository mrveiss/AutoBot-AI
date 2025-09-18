import importlib
import logging
import sys
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.services.config_service import ConfigService
from backend.utils.connection_utils import ModelManager
# Add caching support for performance improvement
from backend.utils.cache_manager import cache_response
from src.unified_config import config

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/frontend-config")
@cache_response(cache_key="frontend_config", ttl=60)  # Cache for 1 minute
async def get_frontend_config():
    """Get configuration values needed by the frontend.

    This endpoint provides all service URLs and configuration that the frontend needs,
    eliminating the need for hardcoded values in the frontend code.
    """
    try:
        # Get configuration from the config manager
        ollama_url = config.get_service_url('ollama')
        redis_config = config.get_redis_config()
        backend_config = config.get('backend', {})

        # Build frontend configuration
        frontend_config = {
            "services": {
                "ollama": {
                    "url": ollama_url,
                    "endpoint": config.get(
                        "backend.llm.local.providers.ollama.endpoint",
                        f"{ollama_url}/api/generate",
                    ),
                    "embedding_endpoint": config.get(
                        "backend.llm.embedding.providers.ollama.endpoint",
                        f"{ollama_url}/api/embeddings",
                    ),
                },
                "playwright": {
                    "vnc_url": config.get_service_url('playwright-vnc'),
                    "api_url": config.get_service_url('playwright'),
                },
                "redis": {
                    "host": redis_config.get("host", config.get_host('redis')),
                    "port": redis_config.get("port", config.get_port('redis')),
                    "enabled": redis_config.get("enabled", True),
                },
                "lmstudio": {
                    "url": config.get(
                        "backend.llm.local.providers.lmstudio.endpoint",
                        config.get_service_url('lmstudio'),
                    ),
                },
            },
            "api": {
                "timeout": config.get("backend.timeout", 60)
                * 1000,  # Convert to milliseconds
                "retry_attempts": config.get("backend.max_retries", 3),
                "streaming": config.get("backend.streaming", False),
            },
            "features": {
                "voice_enabled": config.get(
                    "voice_interface.enabled", False
                ),
                "knowledge_base_enabled": config.get(
                    "knowledge_base.enabled", True
                ),
                "developer_mode": config.get("developer.enabled", True),
            },
            "ui": {
                "theme": config.get("ui.theme", "light"),
                "animations": config.get("ui.animations", True),
                "font_size": config.get("ui.font_size", "medium"),
            },
            "defaults": {
                "welcome_message": config.get(
                    "chat.default_welcome_message", "Hello! How can I assist you today?"
                ),
                "model_name": config.get(
                    "backend.llm.local.providers.ollama.selected_model",
                    "deepseek-r1:14b",
                ),
                "max_chat_messages": config.get(
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
        logger.error(f"Failed to get frontend config: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get frontend config: {str(e)}"
        )


@router.get("/health")
@cache_response(cache_key="system_health", ttl=30)  # Cache for 30 seconds
async def get_system_health():
    """Get system health status"""
    try:
        # Check various system components
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "backend": "healthy",
                "config": "healthy",
                "logging": "healthy",
            },
        }

        # Test configuration access
        try:
            config.get_service_url('ollama')
            health_status["components"]["config"] = "healthy"
        except Exception as e:
            health_status["components"]["config"] = f"error: {str(e)}"
            health_status["status"] = "degraded"

        return health_status

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
        }


@router.get("/info")
@cache_response(cache_key="system_info", ttl=300)  # Cache for 5 minutes
async def get_system_info():
    """Get system information"""
    try:
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        system_info = {
            "name": "AutoBot Backend",
            "version": "Phase 9.0",
            "python_version": python_version,
            "timestamp": datetime.now().isoformat(),
            "features": {
                "llm_integration": True,
                "knowledge_base": True,
                "chat_system": True,
                "caching": True,  # Now enabled!
                "websockets": True,
            },
        }

        return system_info

    except Exception as e:
        logger.error(f"Failed to get system info: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get system info: {str(e)}"
        )


@router.post("/reload_config")
async def reload_system_config():
    """Reload system configuration and clear caches"""
    try:
        logger.info("Reloading system configuration...")

        # Reload configuration
        config.reload()

        # Clear configuration-related caches
        from backend.utils.cache_manager import cache_manager

        await cache_manager.clear_pattern("frontend_config*")
        await cache_manager.clear_pattern("system_*")
        await cache_manager.clear_pattern("llm_*")

        logger.info("System configuration reloaded and caches cleared")

        return {
            "status": "success",
            "message": "System configuration reloaded successfully",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to reload config: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to reload config: {str(e)}"
        )


@router.get("/prompt_reload")
async def reload_prompts():
    """Reload prompt templates"""
    try:
        logger.info("Reloading prompt templates...")

        # Try to reload prompts if available
        try:
            from src.prompt_manager import prompt_manager

            prompt_manager.reload_prompts()
            message = "Prompts reloaded successfully"
        except ImportError:
            message = "Prompt manager not available"
        except Exception as e:
            message = f"Prompt reload error: {str(e)}"

        return {
            "status": "success",
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to reload prompts: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to reload prompts: {str(e)}"
        )


@router.get("/admin_check")
async def admin_check():
    """Check admin status and permissions"""
    try:
        import os

        admin_status = {
            "user": os.getenv("USER", "unknown"),
            "admin": os.getuid() == 0 if hasattr(os, "getuid") else False,
            "timestamp": datetime.now().isoformat(),
        }

        return admin_status

    except Exception as e:
        logger.error(f"Admin check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Admin check failed: {str(e)}")


@router.post("/dynamic_import")
async def dynamic_import(request: Request, module_name: str = Form(...)):
    """Dynamically import a module (admin only)"""
    try:
        logger.info(f"Dynamic import requested for module: {module_name}")

        # Security check - only allow specific modules
        allowed_modules = [
            "src.config",
            "src.llm_interface",
            "backend.services",
            "backend.utils",
        ]

        if not any(module_name.startswith(allowed) for allowed in allowed_modules):
            raise HTTPException(
                status_code=403, detail="Module import not allowed for security reasons"
            )

        # Attempt import
        imported_module = importlib.import_module(module_name)

        return {
            "status": "success",
            "message": f"Module {module_name} imported successfully",
            "module_info": {
                "name": getattr(imported_module, "__name__", "unknown"),
                "file": getattr(imported_module, "__file__", "unknown"),
                "doc": getattr(imported_module, "__doc__", "No documentation"),
            },
            "timestamp": datetime.now().isoformat(),
        }

    except ImportError as e:
        logger.error(f"Import failed for {module_name}: {str(e)}")
        raise HTTPException(
            status_code=400, detail=f"Failed to import module: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Dynamic import error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Import error: {str(e)}")


@router.get("/metrics")
@cache_response(cache_key="system_metrics", ttl=15)  # Cache for 15 seconds
async def get_system_metrics():
    """Get system performance metrics"""
    try:
        import psutil
        import time

        # Get system metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": cpu_percent,
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used,
                    "free": memory.free,
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": (disk.used / disk.total) * 100,
                },
            },
            "python": {
                "version": sys.version,
                "executable": sys.executable,
            },
        }

        # Add cache statistics if available
        try:
            from backend.utils.cache_manager import cache_manager

            cache_stats = await cache_manager.get_stats()
            metrics["cache"] = cache_stats
        except Exception:
            metrics["cache"] = {"status": "unavailable"}

        return metrics

    except ImportError:
        return {
            "timestamp": datetime.now().isoformat(),
            "error": "psutil not available",
            "basic_info": {
                "python_version": sys.version,
                "executable": sys.executable,
            },
        }
    except Exception as e:
        logger.error(f"Failed to get system metrics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get system metrics: {str(e)}"
        )