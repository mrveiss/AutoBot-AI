# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import asyncio
import importlib
import logging
import sys
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from auth_middleware import check_admin_permission
from config import UnifiedConfigManager
from backend.constants.model_constants import ModelConstants as ModelConsts

# Add caching support from unified cache manager (P4 Cache Consolidation)
from backend.utils.advanced_cache_manager import cache_manager, cache_response
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

# Create singleton config instance
config = UnifiedConfigManager()

router = APIRouter()

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for allowed dynamic import modules
_ALLOWED_IMPORT_MODULES = (
    "src.config",
    "src.llm_interface",
    "backend.services",
    "backend.utils",
)


async def _check_conversation_files_db(request: Request, health_status: dict) -> None:
    """Check conversation files database health (Issue #315 - extracted)."""
    if not hasattr(request.app.state, "conversation_file_manager"):
        health_status["components"]["conversation_files_db"] = "not_configured"
        health_status["status"] = "degraded"
        return

    conversation_file_manager = request.app.state.conversation_file_manager
    try:
        version = await conversation_file_manager.get_schema_version()
        if version == "unknown":
            health_status["components"]["conversation_files_db"] = "not_initialized"
            health_status["status"] = "degraded"
        else:
            health_status["components"]["conversation_files_db"] = "healthy"
    except Exception as db_e:
        logger.warning("Conversation files DB health check failed: %s", db_e)
        health_status["components"]["conversation_files_db"] = "unhealthy"
        health_status["status"] = "degraded"


async def _check_detailed_conversation_db(
    request: Request, detailed_components: dict
) -> None:
    """Check conversation files database for detailed health (Issue #315 - extracted)."""
    if not hasattr(request.app.state, "conversation_file_manager"):
        detailed_components["conversation_files_db"] = "not_configured"
        return

    conversation_file_manager = request.app.state.conversation_file_manager
    try:
        version = await conversation_file_manager.get_schema_version()
        if version == "unknown":
            detailed_components["conversation_files_db"] = "not_initialized"
            detailed_components["conversation_files_schema"] = "none"
        else:
            detailed_components["conversation_files_db"] = "healthy"
            detailed_components["conversation_files_schema"] = version
    except Exception as db_e:
        logger.warning("Conversation files DB health check failed: %s", db_e)
        detailed_components["conversation_files_db"] = "unhealthy"
        detailed_components["conversation_files_schema"] = "error"
        detailed_components["conversation_files_error"] = str(db_e)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_frontend_config",
    error_code_prefix="SYSTEM",
)
@router.get("/frontend-config")
@cache_response(cache_key="frontend_config", ttl=60)  # Cache for 1 minute
async def get_frontend_config(admin_check: bool = Depends(check_admin_permission)):
    """Get configuration values needed by the frontend.

    This endpoint provides all service URLs and configuration that the frontend needs,
    eliminating the need for hardcoded values in the frontend code.

    Issue #744: Requires admin authentication.
    """
    # Get configuration from the config manager
    ollama_url = config.get_service_url("ollama")
    redis_config = config.get_redis_config()

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
                "vnc_url": config.get_service_url("playwright-vnc"),
                "api_url": config.get_service_url("playwright"),
            },
            "redis": {
                "host": redis_config.get("host", config.get_host("redis")),
                "port": redis_config.get("port", config.get_port("redis")),
                "enabled": redis_config.get("enabled", True),
            },
            "lmstudio": {
                "url": config.get(
                    "backend.llm.local.providers.lmstudio.endpoint",
                    config.get_service_url("lmstudio"),
                ),
            },
        },
        "api": {
            "timeout": (
                config.get("backend.timeout", 60) * 1000
            ),  # Convert to milliseconds
            "retry_attempts": config.get("backend.max_retries", 3),
            "streaming": config.get("backend.streaming", False),
        },
        "features": {
            "voice_enabled": config.get("voice_interface.enabled", False),
            "knowledge_base_enabled": config.get("knowledge_base.enabled", True),
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
                ModelConsts.DEFAULT_OLLAMA_MODEL,
            ),
            "max_chat_messages": config.get("chat.max_messages", 100),
        },
    }

    return {
        "status": "success",
        "config": frontend_config,
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_health",
    error_code_prefix="SYSTEM",
)
@router.get("/health")
@router.get("/system/health")  # Frontend compatibility alias
@cache_response(cache_key="system_health", ttl=30)  # Cache for 30 seconds
async def get_system_health(
    request: Request = None, admin_check: bool = Depends(check_admin_permission)
):
    """Get system health status

    Issue #744: Requires admin authentication.
    """
    try:
        # Import app_state to get initialization status
        from backend.initialization.lifespan import app_state

        # Check various system components
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "initialization": {
                "status": app_state.get("initialization_status", "unknown"),
                "message": app_state.get(
                    "initialization_message", "Status unavailable"
                ),
            },
            "components": {
                "backend": "healthy",
                "config": "healthy",
                "logging": "healthy",
            },
        }

        # Test configuration access
        try:
            config.get_service_url("ollama")
            health_status["components"]["config"] = "healthy"
        except Exception as e:
            health_status["components"]["config"] = f"error: {str(e)}"
            health_status["status"] = "degraded"

        # Check conversation files database if request is available (Issue #315 - use helper)
        if request:
            await _check_conversation_files_db(request, health_status)

        return health_status

    except Exception as e:
        logger.error("Health check failed: %s", str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_info",
    error_code_prefix="SYSTEM",
)
@router.get("/info")
@cache_response(cache_key="system_info", ttl=300)  # Cache for 5 minutes
async def get_system_info(admin_check: bool = Depends(check_admin_permission)):
    """Get system information

    Issue #744: Requires admin authentication.
    """
    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    system_info = {
        "name": "AutoBot Backend",
        "version": "1.0.0",
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reload_system_config",
    error_code_prefix="SYSTEM",
)
@router.post("/reload_config")
async def reload_system_config(admin_check: bool = Depends(check_admin_permission)):
    """Reload system configuration and clear caches

    Issue #744: Requires admin authentication.
    """
    logger.info("Reloading system configuration...")

    # Reload configuration
    config.reload()

    # Issue #379: Clear configuration-related caches in parallel
    # cache_manager already imported at top

    await asyncio.gather(
        cache_manager.clear_pattern("frontend_config*"),
        cache_manager.clear_pattern("system_*"),
        cache_manager.clear_pattern("llm_*"),
    )

    logger.info("System configuration reloaded and caches cleared")

    return {
        "status": "success",
        "message": "System configuration reloaded successfully",
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reload_prompts",
    error_code_prefix="SYSTEM",
)
@router.get("/prompt_reload")
async def reload_prompts(admin_check: bool = Depends(check_admin_permission)):
    """Reload prompt templates

    Issue #744: Requires admin authentication.
    """
    logger.info("Reloading prompt templates...")

    # Try to reload prompts if available
    try:
        from prompt_manager import prompt_manager

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="admin_check",
    error_code_prefix="SYSTEM",
)
@router.get("/admin_check")
async def admin_check(admin_check: bool = Depends(check_admin_permission)):
    """Check admin status and permissions

    Issue #744: Requires admin authentication.
    """
    import os

    admin_status = {
        "user": os.getenv("USER", "unknown"),
        "admin": os.getuid() == 0 if hasattr(os, "getuid") else False,
        "timestamp": datetime.now().isoformat(),
    }

    return admin_status


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="dynamic_import",
    error_code_prefix="SYSTEM",
)
@router.post("/dynamic_import")
async def dynamic_import(
    request: Request,
    module_name: str = Form(...),
    admin_check: bool = Depends(check_admin_permission),
):
    """Dynamically import a module (admin only)

    Issue #744: Requires admin authentication.
    """
    logger.info("Dynamic import requested for module: %s", module_name)

    # Security check - only allow specific modules (Issue #380: use module-level constant)
    if not any(module_name.startswith(allowed) for allowed in _ALLOWED_IMPORT_MODULES):
        raise HTTPException(
            status_code=403, detail="Module import not allowed for security reasons"
        )

    # Attempt import
    try:
        imported_module = importlib.import_module(module_name)
    except ImportError as e:
        logger.error("Import failed for %s: %s", module_name, str(e))
        raise HTTPException(
            status_code=400, detail=f"Failed to import module: {str(e)}"
        )

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_detailed_health",
    error_code_prefix="SYSTEM",
)
@router.get("/health/detailed")
@cache_response(cache_key="system_health_detailed", ttl=30)  # Cache for 30 seconds
async def get_detailed_health(
    request: Request, admin_check: bool = Depends(check_admin_permission)
):
    """Get detailed system health status including all components (Issue #665: refactored).

    Issue #744: Requires admin authentication.
    """
    try:
        basic_health = await get_system_health()
        detailed_components = {}

        # Check components
        await _check_redis_health(detailed_components)
        _check_llm_availability(detailed_components)
        _check_knowledge_base_availability(detailed_components)
        await _check_detailed_conversation_db(request, detailed_components)
        _check_system_resources(detailed_components)

        # Build final status
        health_status = basic_health.copy()
        health_status["components"].update(detailed_components)
        health_status["detailed"] = True

        _determine_overall_health_status(health_status)

        return health_status

    except Exception as e:
        logger.error("Detailed health check failed: %s", str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "detailed": True,
        }


async def _check_redis_health(components: dict) -> None:
    """Check Redis connection health (Issue #665: extracted helper)."""
    try:
        await cache_manager._ensure_redis_client()
        if cache_manager._redis_client:
            components["redis"] = "healthy"
        else:
            components["redis"] = "unavailable"
    except Exception as e:
        components["redis"] = f"error: {str(e)}"


def _check_llm_availability(components: dict) -> None:
    """Check LLM interface availability (Issue #665: extracted helper)."""
    try:
        pass  # Import check placeholder
        components["llm"] = "available"
    except Exception as e:
        components["llm"] = f"import_error: {str(e)}"


def _check_knowledge_base_availability(components: dict) -> None:
    """Check knowledge base availability (Issue #665: extracted helper)."""
    try:
        pass  # Import check placeholder
        components["knowledge_base"] = "available"
    except Exception as e:
        components["knowledge_base"] = f"import_error: {str(e)}"


def _check_system_resources(components: dict) -> None:
    """Check system resources via psutil (Issue #665: extracted helper)."""
    try:
        import psutil

        components["cpu_usage"] = f"{psutil.cpu_percent(interval=0.1)}%"
        memory = psutil.virtual_memory()
        components["memory_usage"] = f"{memory.percent}%"
        disk = psutil.disk_usage("/")
        components["disk_usage"] = f"{(disk.used / disk.total) * 100:.1f}%"
    except ImportError:
        components["system_monitoring"] = "psutil_unavailable"
    except Exception as e:
        components["system_monitoring"] = f"error: {str(e)}"


def _determine_overall_health_status(health_status: dict) -> None:
    """Determine overall health status from components (Issue #665: extracted helper)."""
    error_components = [
        comp
        for comp, status in health_status["components"].items()
        if "error" in str(status).lower()
    ]
    if error_components:
        health_status["status"] = "degraded"
        health_status["errors"] = error_components


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_stats",
    error_code_prefix="SYSTEM",
)
@router.get("/cache/stats")
@cache_response(cache_key="cache_stats", ttl=15)  # Cache for 15 seconds
async def get_cache_stats(admin_check: bool = Depends(check_admin_permission)):
    """Get cache statistics and performance metrics

    Issue #744: Requires admin authentication.
    """
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
            },
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
        logger.error("Failed to get cache stats: %s", str(e))
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "cache": {"status": "error"},
        }


async def _get_key_info(redis_client, key: str, cache_prefix: str) -> dict:
    """Get TTL info for a single cache key (Issue #315: extracted).

    Returns:
        Dict with key and ttl info
    """
    clean_key = key.replace(cache_prefix, "")
    try:
        ttl = await redis_client.ttl(key)
        return {"key": clean_key, "ttl": ttl if ttl > 0 else "no_expiry"}
    except Exception:
        return {"key": clean_key, "ttl": "unknown"}


async def _get_recent_keys(redis_client, cache_keys: list, cache_prefix: str) -> list:
    """Get recent keys with TTL info (Issue #315: extracted).

    Issue #370: Fetch TTL info in parallel instead of sequentially.

    Returns:
        List of key info dicts
    """
    # Issue #370: Fetch all key info in parallel
    key_infos = await asyncio.gather(
        *[_get_key_info(redis_client, key, cache_prefix) for key in cache_keys[:20]],
        return_exceptions=True,
    )
    # Filter out exceptions
    return [info for info in key_infos if not isinstance(info, Exception)]


def _analyze_key_patterns(cache_keys: list, cache_prefix: str) -> dict:
    """Analyze cache key patterns (Issue #315: extracted).

    Returns:
        Dict of pattern counts
    """
    key_patterns = {}
    for key in cache_keys:
        clean_key = key.replace(cache_prefix, "")
        pattern = clean_key.split(":")[0] if ":" in clean_key else "other"
        key_patterns[pattern] = key_patterns.get(pattern, 0) + 1
    return key_patterns


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_activity",
    error_code_prefix="SYSTEM",
)
@router.get("/cache/activity")
@cache_response(cache_key="cache_activity", ttl=10)  # Cache for 10 seconds
async def get_cache_activity(admin_check: bool = Depends(check_admin_permission)):
    """Get recent cache activity and key information.

    Issue #315: Refactored to use helper functions for reduced nesting depth.
    Issue #744: Requires admin authentication.
    """
    try:
        from backend.utils.cache_manager import cache_manager

        activity_response = {
            "timestamp": datetime.now().isoformat(),
            "activity": {
                "recent_keys": [],
                "key_patterns": {},
                "total_keys": 0,
            },
        }

        if not cache_manager._redis_client:
            activity_response["activity"]["error"] = "Redis client not available"
            return activity_response

        try:
            await cache_manager._ensure_redis_client()

            # Get all cache keys
            cache_keys = await cache_manager._redis_client.keys(
                f"{cache_manager.cache_prefix}*"
            )
            activity_response["activity"]["total_keys"] = len(cache_keys)

            # Get recent keys using helper (Issue #315)
            activity_response["activity"]["recent_keys"] = await _get_recent_keys(
                cache_manager._redis_client, cache_keys, cache_manager.cache_prefix
            )

            # Analyze key patterns using helper (Issue #315)
            activity_response["activity"]["key_patterns"] = _analyze_key_patterns(
                cache_keys, cache_manager.cache_prefix
            )

        except Exception as e:
            activity_response["activity"]["error"] = str(e)

        return activity_response

    except Exception as e:
        logger.error("Failed to get cache activity: %s", str(e))
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "activity": {"error": "Failed to retrieve activity"},
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_metrics",
    error_code_prefix="SYSTEM",
)
@router.get("/metrics")
@cache_response(cache_key="system_metrics", ttl=15)  # Cache for 15 seconds
async def get_system_metrics(admin_check: bool = Depends(check_admin_permission)):
    """Get system performance metrics

    Issue #744: Requires admin authentication.
    """
    try:
        pass

        import psutil

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
            # cache_manager already imported at top

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


# Issue #743: Cache coordinator endpoints for memory optimization (Phase 3.2)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_coordinator_stats",
    error_code_prefix="SYSTEM",
)
@router.get("/api/cache/stats")
async def get_cache_coordinator_stats(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get unified cache statistics from the cache coordinator.

    Returns stats for all registered caches including:
    - Individual cache metrics (size, hits, misses, hit_rate)
    - Total items across all caches
    - System memory percentage
    - Pressure trigger count

    Issue #744: Requires admin authentication.
    """
    try:
        from cache import get_cache_coordinator

        coordinator = get_cache_coordinator()
        return coordinator.get_unified_stats()
    except Exception as e:
        logger.error("Error getting cache coordinator stats: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error getting cache coordinator stats: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="trigger_cache_eviction",
    error_code_prefix="SYSTEM",
)
@router.post("/api/cache/evict")
async def trigger_cache_eviction(admin_check: bool = Depends(check_admin_permission)):
    """
    Manually trigger coordinated cache eviction.

    Evicts items from all registered caches according to eviction_ratio.

    Issue #744: Requires admin authentication.
    """
    try:
        from cache import get_cache_coordinator

        coordinator = get_cache_coordinator()
        evicted = await coordinator._coordinated_evict()

        return {
            "status": "eviction_complete",
            "evicted": evicted,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error triggering cache eviction: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error triggering cache eviction: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cache",
    error_code_prefix="SYSTEM",
)
@router.post("/api/cache/clear/{cache_name}")
async def clear_cache(
    cache_name: str, admin_check: bool = Depends(check_admin_permission)
):
    """
    Clear a specific cache by name.

    Args:
        cache_name: Name of the cache to clear (e.g., 'lru_memory', 'embedding')

    Issue #744: Requires admin authentication.
    """
    try:
        from cache import get_cache_coordinator

        coordinator = get_cache_coordinator()
        if cache_name in coordinator._caches:
            coordinator._caches[cache_name].clear()
            return {
                "status": "cleared",
                "cache": cache_name,
                "timestamp": datetime.now().isoformat(),
            }

        raise HTTPException(status_code=404, detail=f"Cache '{cache_name}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing cache %s: %s", cache_name, str(e))
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")
