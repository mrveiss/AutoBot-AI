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
@router.get("/system/health")  # Frontend compatibility alias
@cache_response(cache_key="system_health", ttl=30)  # Cache for 30 seconds
async def get_system_health(request: Request = None):
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

        # Check conversation files database if request is available
        if request:
            try:
                if hasattr(request.app.state, 'conversation_file_manager'):
                    conversation_file_manager = request.app.state.conversation_file_manager
                    # Verify database connectivity and schema
                    try:
                        version = await conversation_file_manager.get_schema_version()
                        if version == "unknown":
                            health_status["components"]["conversation_files_db"] = "not_initialized"
                            health_status["status"] = "degraded"
                        else:
                            health_status["components"]["conversation_files_db"] = "healthy"
                    except Exception as db_e:
                        logger.warning(f"Conversation files DB health check failed: {db_e}")
                        health_status["components"]["conversation_files_db"] = "unhealthy"
                        health_status["status"] = "degraded"
                else:
                    health_status["components"]["conversation_files_db"] = "not_configured"
                    health_status["status"] = "degraded"
            except Exception as e:
                health_status["components"]["conversation_files_db"] = f"error: {str(e)}"
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


@router.get("/health/detailed")
@cache_response(cache_key="system_health_detailed", ttl=30)  # Cache for 30 seconds
async def get_detailed_health(request: Request):
    """Get detailed system health status including all components"""
    try:
        # Get basic health status first
        basic_health = await get_system_health()

        # Add detailed component checks
        detailed_components = {}

        # Check Redis connection
        try:
            from backend.utils.cache_manager import cache_manager
            await cache_manager._ensure_redis_client()
            if cache_manager._redis_client:
                detailed_components["redis"] = "healthy"
            else:
                detailed_components["redis"] = "unavailable"
        except Exception as e:
            detailed_components["redis"] = f"error: {str(e)}"

        # Check LLM interface
        try:
            from src.llm_interface import LLMInterface
            detailed_components["llm"] = "available"
        except Exception as e:
            detailed_components["llm"] = f"import_error: {str(e)}"

        # Check knowledge base
        try:
            from src.knowledge_base import KnowledgeBase
            detailed_components["knowledge_base"] = "available"
        except Exception as e:
            detailed_components["knowledge_base"] = f"import_error: {str(e)}"

        # Check Conversation Files Database
        try:
            if hasattr(request.app.state, 'conversation_file_manager'):
                conversation_file_manager = request.app.state.conversation_file_manager
                # Verify database connectivity and schema
                try:
                    version = await conversation_file_manager.get_schema_version()
                    if version == "unknown":
                        detailed_components["conversation_files_db"] = "not_initialized"
                        detailed_components["conversation_files_schema"] = "none"
                    else:
                        detailed_components["conversation_files_db"] = "healthy"
                        detailed_components["conversation_files_schema"] = version
                except Exception as db_e:
                    logger.warning(f"Conversation files DB health check failed: {db_e}")
                    detailed_components["conversation_files_db"] = "unhealthy"
                    detailed_components["conversation_files_schema"] = "error"
                    detailed_components["conversation_files_error"] = str(db_e)
            else:
                detailed_components["conversation_files_db"] = "not_configured"
        except Exception as e:
            detailed_components["conversation_files_db"] = f"error: {str(e)}"

        # Add system resource info
        try:
            import psutil
            detailed_components["cpu_usage"] = f"{psutil.cpu_percent(interval=0.1)}%"
            memory = psutil.virtual_memory()
            detailed_components["memory_usage"] = f"{memory.percent}%"
            disk = psutil.disk_usage("/")
            detailed_components["disk_usage"] = f"{(disk.used / disk.total) * 100:.1f}%"
        except ImportError:
            detailed_components["system_monitoring"] = "psutil_unavailable"
        except Exception as e:
            detailed_components["system_monitoring"] = f"error: {str(e)}"

        # Combine basic and detailed status
        health_status = basic_health.copy()
        health_status["components"].update(detailed_components)
        health_status["detailed"] = True

        # Determine overall status
        error_components = [comp for comp, status in health_status["components"].items() if "error" in str(status).lower()]
        if error_components:
            health_status["status"] = "degraded"
            health_status["errors"] = error_components

        return health_status

    except Exception as e:
        logger.error(f"Detailed health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "detailed": True,
        }


@router.get("/cache/stats")
@cache_response(cache_key="cache_stats", ttl=15)  # Cache for 15 seconds
async def get_cache_stats():
    """Get cache statistics and performance metrics"""
    try:
        from backend.utils.cache_manager import cache_manager

        # Get cache statistics
        cache_stats = await cache_manager.get_stats()

        # Add timestamp and additional metadata
        stats_response = {
            "timestamp": datetime.now().isoformat(),
            "cache": cache_stats,
            "performance": {
                "ttl_default": cache_manager.default_ttl,
                "prefix": cache_manager.cache_prefix,
            }
        }

        # Add Redis info if available
        if cache_manager._redis_client:
            try:
                await cache_manager._ensure_redis_client()
                info = await cache_manager._redis_client.info()
                stats_response["redis_info"] = {
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory_human": info.get("used_memory_human", "N/A"),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                }

                # Calculate hit rate
                hits = info.get("keyspace_hits", 0)
                misses = info.get("keyspace_misses", 0)
                total = hits + misses
                hit_rate = (hits / total * 100) if total > 0 else 0
                stats_response["performance"]["hit_rate"] = f"{hit_rate:.2f}%"

            except Exception as e:
                stats_response["redis_info"] = {"error": str(e)}

        return stats_response

    except Exception as e:
        logger.error(f"Failed to get cache stats: {str(e)}")
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "cache": {"status": "error"},
        }


@router.get("/cache/activity")
@cache_response(cache_key="cache_activity", ttl=10)  # Cache for 10 seconds
async def get_cache_activity():
    """Get recent cache activity and key information"""
    try:
        from backend.utils.cache_manager import cache_manager

        activity_response = {
            "timestamp": datetime.now().isoformat(),
            "activity": {
                "recent_keys": [],
                "key_patterns": {},
                "total_keys": 0,
            }
        }

        if cache_manager._redis_client:
            try:
                await cache_manager._ensure_redis_client()

                # Get all cache keys
                cache_keys = await cache_manager._redis_client.keys(f"{cache_manager.cache_prefix}*")
                activity_response["activity"]["total_keys"] = len(cache_keys)

                # Get recent keys (limit to 20 for performance)
                recent_keys = []
                for key in cache_keys[:20]:
                    try:
                        # Remove prefix for cleaner display
                        clean_key = key.replace(cache_manager.cache_prefix, "")
                        ttl = await cache_manager._redis_client.ttl(key)
                        recent_keys.append({
                            "key": clean_key,
                            "ttl": ttl if ttl > 0 else "no_expiry",
                        })
                    except Exception:
                        recent_keys.append({"key": clean_key, "ttl": "unknown"})

                activity_response["activity"]["recent_keys"] = recent_keys

                # Analyze key patterns
                key_patterns = {}
                for key in cache_keys:
                    clean_key = key.replace(cache_manager.cache_prefix, "")
                    pattern = clean_key.split(":")[0] if ":" in clean_key else "other"
                    key_patterns[pattern] = key_patterns.get(pattern, 0) + 1

                activity_response["activity"]["key_patterns"] = key_patterns

            except Exception as e:
                activity_response["activity"]["error"] = str(e)
        else:
            activity_response["activity"]["error"] = "Redis client not available"

        return activity_response

    except Exception as e:
        logger.error(f"Failed to get cache activity: {str(e)}")
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "activity": {"error": "Failed to retrieve activity"},
        }


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