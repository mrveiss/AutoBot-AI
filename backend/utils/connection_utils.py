# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared utilities for testing connections to various services.
Eliminates duplication across system.py, llm.py, and redis.py
"""

import asyncio
import logging
import os
import time
from datetime import datetime

import aiohttp

from backend.type_defs.common import Metadata

from src.constants.model_constants import ModelConstants
from src.constants.network_constants import NetworkConstants
from src.unified_config_manager import (
    HTTP_PROTOCOL,
    OLLAMA_HOST_IP,
    OLLAMA_PORT,
)
from src.unified_config_manager import config as global_config_manager
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Cache for health status with 30-second TTL
_health_cache = {"data": None, "timestamp": 0, "ttl": 30}

# Lock for thread-safe access to _health_cache
_health_cache_lock = asyncio.Lock()


class ConnectionTester:
    """Centralized connection testing for all backend services"""

    @staticmethod
    async def get_fast_health_status() -> Metadata:
        """Fast health check without expensive operations (< 1 second)"""
        try:
            # Check cache first (thread-safe)
            current_time = time.time()
            async with _health_cache_lock:
                if (
                    _health_cache["data"]
                    and current_time - _health_cache["timestamp"] < _health_cache["ttl"]
                ):
                    return _health_cache["data"]

            # Quick Redis check
            redis_client = get_redis_client()
            redis_status = "disconnected"
            try:
                if redis_client:
                    # Issue #361 - avoid blocking
                    await asyncio.to_thread(redis_client.ping)
                    redis_status = "connected"
            except Exception as e:
                logger.debug("Redis health check failed: %s", e)

            # Quick Ollama availability check (no generation test)
            ollama_status = "disconnected"
            try:
                ollama_endpoint = os.getenv(
                    "AUTOBOT_OLLAMA_HOST",
                    f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}",
                )
                ollama_check_url = f"{ollama_endpoint}/api/tags"
                timeout = aiohttp.ClientTimeout(total=3)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(ollama_check_url) as response:
                        if response.status == 200:
                            ollama_status = "connected"
            except Exception as e:
                logger.debug("Ollama health check failed: %s", e)

            health_data = {
                "status": "healthy",
                "backend": "connected",
                "ollama": ollama_status,
                "redis_status": redis_status,
                "timestamp": datetime.now().isoformat(),
                "fast_check": True,
            }

            # Cache the result (thread-safe)
            async with _health_cache_lock:
                _health_cache["data"] = health_data
                _health_cache["timestamp"] = current_time

            return health_data

        except Exception as e:
            logger.error("Error in fast health check: %s", str(e))
            return {
                "status": "unhealthy",
                "backend": "connected",
                "ollama": "unknown",
                "redis_status": "unknown",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "fast_check": True,
            }

    @staticmethod
    def _is_search_module(module) -> bool:
        """Check if a module entry represents the RediSearch module."""
        if isinstance(module, dict):
            return module.get("name") == "search" or module.get(b"name") == b"search"
        if hasattr(module, "__getitem__"):
            return module.get("name") == "search" or module.get(b"name") == b"search"
        return False

    @staticmethod
    def _check_redis_search_module(redis_client) -> bool:
        """Check if RediSearch module is loaded in Redis."""
        try:
            modules = redis_client.module_list()
            if not modules or not isinstance(modules, list):
                return False
            return any(
                ConnectionTester._is_search_module(module) for module in modules
            )
        except Exception:
            # If we can't check modules, assume it's not loaded
            return False

    @staticmethod
    def _get_ollama_config_from_new_structure() -> tuple:
        """Get Ollama config from new structure (Issue #336 - extracted helper)."""
        endpoint = None
        model = None
        llm_config = global_config_manager.get("backend", {}).get("llm", {})
        is_local_ollama = (
            llm_config.get("provider_type") == "local"
            and llm_config.get("local", {}).get("provider") == "ollama"
        )
        if is_local_ollama:
            ollama_providers = llm_config.get("local", {}).get("providers", {})
            ollama_config = ollama_providers.get("ollama", {})
            endpoint = ollama_config.get("endpoint")
            model = ollama_config.get("selected_model")
        return endpoint, model

    @staticmethod
    def _get_ollama_config_fallback(endpoint: str, model: str) -> tuple:
        """Get Ollama config from legacy/env (Issue #336 - extracted helper)."""
        if not endpoint:
            endpoint = global_config_manager.get_nested(
                "backend.ollama_endpoint",
                os.getenv(
                    "AUTOBOT_OLLAMA_HOST",
                    f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}/api/generate",
                ),
            )
        if not model:
            model = global_config_manager.get_nested(
                "backend.ollama_model",
                os.getenv(
                    "AUTOBOT_DEFAULT_LLM_MODEL", ModelConstants.DEFAULT_OLLAMA_MODEL
                ),
            )
        # Final fallbacks
        if not endpoint:
            from src.unified_config_manager import OLLAMA_URL
            endpoint = f"{OLLAMA_URL}/api/generate"
        if not model:
            model = os.getenv(
                "AUTOBOT_DEFAULT_LLM_MODEL", ModelConstants.DEFAULT_OLLAMA_MODEL
            )
        return endpoint, model

    @staticmethod
    async def _test_ollama_model(endpoint: str, model: str) -> Metadata:
        """Test Ollama model generation (Issue #336 - extracted helper)."""
        test_payload = {
            "model": model,
            "prompt": "Test connection - respond with 'OK'",
            "stream": False,
        }
        gen_timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=gen_timeout) as session:
            async with session.post(endpoint, json=test_payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    response_text = result.get("response", "No response text")
                    test_response = (
                        response_text[:100] + "..."
                        if response_text and response_text != "No response text"
                        else "No response"
                    )
                    return {
                        "status": "connected",
                        "message": f"Successfully connected to Ollama with model '{model}'",
                        "endpoint": endpoint,
                        "model": model,
                        "current_model": model,
                        "test_response": test_response,
                    }
                error_text = await resp.text()
                return {
                    "status": "partial",
                    "message": f"Connected to Ollama but model '{model}' failed to respond",
                    "endpoint": endpoint,
                    "model": model,
                    "current_model": model,
                    "error": error_text,
                }

    @staticmethod
    async def test_ollama_connection() -> Metadata:
        """Test Ollama LLM connection with current configuration"""
        try:
            endpoint, model = ConnectionTester._get_ollama_config_from_new_structure()
            endpoint, model = ConnectionTester._get_ollama_config_fallback(endpoint, model)

            check_url = endpoint.replace("/api/generate", "/api/tags")
            timeout = aiohttp.ClientTimeout(total=10)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(check_url) as response:
                    if response.status != 200:
                        return {
                            "status": "disconnected",
                            "message": f"Failed to connect to Ollama at {check_url}",
                            "endpoint": endpoint,
                            "status_code": response.status,
                        }
                    return await ConnectionTester._test_ollama_model(endpoint, model)

        except Exception as e:
            logger.error("Ollama connection test failed: %s", str(e))
            return {
                "status": "disconnected",
                "message": f"Failed to test Ollama connection: {str(e)}",
            }

    @staticmethod
    def _get_redis_config_values() -> tuple:
        """
        Load Redis host and port from configuration.

        Issue #665: Extracted from test_redis_connection to reduce function length.

        Returns:
            Tuple of (redis_host, redis_port, error_response or None)
        """
        # Check task_transport config (backwards compatibility)
        task_transport_config = global_config_manager.get("task_transport", {})

        if task_transport_config.get("type") == "redis":
            redis_config = task_transport_config.get("redis", {})
            host = redis_config.get(
                "host", os.getenv("AUTOBOT_REDIS_HOST", "localhost")
            )
            port = redis_config.get(
                "port",
                int(os.getenv("AUTOBOT_REDIS_PORT", str(NetworkConstants.REDIS_PORT))),
            )
            return host, port, None

        # Check memory.redis config (current structure)
        memory_config = global_config_manager.get("memory", {})
        redis_config = memory_config.get("redis", {})

        if not redis_config.get("enabled", False):
            return None, None, {
                "status": "not_configured",
                "message": "Redis is not enabled in memory configuration",
            }

        host = redis_config.get("host", os.getenv("AUTOBOT_REDIS_HOST", "localhost"))
        port = redis_config.get(
            "port",
            int(os.getenv("AUTOBOT_REDIS_PORT", str(NetworkConstants.REDIS_PORT))),
        )
        return host, port, None

    @staticmethod
    def test_redis_connection() -> Metadata:
        """
        Test Redis connection with current configuration.

        Issue #665: Refactored to use _get_redis_config_values helper.
        """
        try:
            # Issue #665: Use helper for config loading
            redis_host, redis_port, error = ConnectionTester._get_redis_config_values()
            if error:
                return error

            if not redis_host or not redis_port:
                return {
                    "status": "not_configured",
                    "message": "Redis configuration is incomplete (missing host or port)",
                }

            redis_client = get_redis_client()
            if redis_client is None:
                return {
                    "status": "not_configured",
                    "message": "Redis client could not be initialized",
                }
            redis_client.ping()

            # Check if RediSearch module is loaded
            redis_search_module_loaded = ConnectionTester._check_redis_search_module(
                redis_client
            )

            return {
                "status": "connected",
                "message": f"Successfully connected to Redis at {redis_host}:{redis_port}",
                "host": redis_host,
                "port": redis_port,
                "redis_search_module_loaded": redis_search_module_loaded,
            }
        except Exception as e:
            logger.error("Redis connection test failed: %s", str(e))
            return {
                "status": "disconnected",
                "message": f"Failed to connect to Redis: {str(e)}",
            }

    @staticmethod
    async def _check_ollama_embedding(
        provider_config: dict, current_model: str, provider: str
    ) -> Metadata:
        """Check Ollama embedding model availability (reduces nesting in _get_embedding_status)."""
        from src.unified_config_manager import OLLAMA_URL

        ollama_host = provider_config.get("host", OLLAMA_URL)
        tags_url = f"{ollama_host}/api/tags"
        timeout = aiohttp.ClientTimeout(total=5)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(tags_url) as response:
                if response.status != 200:
                    return {
                        "connected": False,
                        "current_model": current_model,
                        "provider": provider,
                        "message": f"Cannot connect to Ollama at {ollama_host}",
                    }
                data = await response.json()
                available_models = [
                    model["name"] for model in data.get("models", [])
                ]
                model_available = current_model in available_models if current_model else False
                return {
                    "connected": True,
                    "current_model": current_model,
                    "model_available": model_available,
                    "provider": provider,
                    "message": (
                        f"Embedding model '{current_model}' "
                        f"{'available' if model_available else 'not found'}"
                    ),
                }

    @staticmethod
    async def _get_embedding_status() -> Metadata:
        """Get current embedding model status"""
        try:
            # Get embedding configuration from unified config
            llm_config = global_config_manager.get_llm_config()
            embedding_config = llm_config.get("unified", {}).get("embedding", {})

            if not embedding_config:
                return {
                    "connected": False,
                    "current_model": None,
                    "message": "No embedding configuration found",
                }

            provider = embedding_config.get("provider", "ollama")
            provider_config = embedding_config.get("providers", {}).get(provider, {})
            current_model = provider_config.get("selected_model")

            if provider == "ollama":
                return await ConnectionTester._check_ollama_embedding(
                    provider_config, current_model, provider
                )

            if provider == "openai":
                # For OpenAI, just return configured status
                return {
                    "connected": True,  # Assume connected if API key is configured
                    "current_model": current_model,
                    "provider": provider,
                    "message": f"OpenAI embedding model '{current_model}' configured",
                }

            else:
                return {
                    "connected": False,
                    "current_model": current_model,
                    "provider": provider,
                    "message": f"Unknown embedding provider: {provider}",
                }

        except Exception as e:
            logger.error("Error getting embedding status: %s", str(e))
            return {
                "connected": False,
                "current_model": None,
                "message": f"Error checking embedding status: {str(e)}",
            }

    @staticmethod
    async def get_comprehensive_health_status() -> Metadata:
        """Get comprehensive health status for all services"""
        try:
            # Test Ollama
            ollama_status = await ConnectionTester.test_ollama_connection()
            ollama_healthy = ollama_status["status"] == "connected"

            # Test Redis
            redis_result = ConnectionTester.test_redis_connection()

            # Get current embedding model status
            embedding_status = await ConnectionTester._get_embedding_status()

            return {
                "status": "healthy",
                "backend": "connected",
                "ollama": "connected" if ollama_healthy else "disconnected",
                "llm_status": ollama_healthy,
                "current_model": ollama_status.get("current_model"),
                "embedding_status": embedding_status.get("connected", False),
                "current_embedding_model": embedding_status.get("current_model"),
                "redis_status": redis_result["status"],
                "redis_search_module_loaded": redis_result.get(
                    "redis_search_module_loaded", False
                ),
                "timestamp": datetime.now().isoformat(),
                "details": {
                    "ollama": ollama_status,
                    "redis": redis_result,
                    "embedding": embedding_status,
                },
            }
        except Exception as e:
            logger.error("Error in comprehensive health check: %s", str(e))
            return {
                "status": "unhealthy",
                "backend": "connected",
                "ollama": "unknown",
                "redis_status": "unknown",
                "redis_search_module_loaded": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


class ModelManager:
    """Centralized model management for LLM services"""

    # Rate limiting for warnings to prevent log spam
    _last_ollama_warning = 0
    _warning_interval = 60  # Only warn once per minute

    @staticmethod
    async def get_available_models() -> Metadata:
        """Get list of available LLM models from all configured providers"""
        models = []

        try:
            # Get Ollama models
            ollama_models = await ModelManager._get_ollama_models()
            models.extend(ollama_models)

            # Add configured models from config
            llm_config = global_config_manager.get("llm_config", {})
            ollama_config_models = llm_config.get("ollama", {}).get("models", {})
            for key, model_name in ollama_config_models.items():
                if not any(m["name"] == model_name for m in models):
                    models.append(
                        {
                            "name": model_name,
                            "type": "ollama",
                            "configured": True,
                            "available": False,
                        }
                    )

            return {"status": "success", "models": models, "total_count": len(models)}
        except Exception as e:
            logger.error("Error getting available models: %s", str(e))
            return {"status": "error", "error": str(e), "models": [], "total_count": 0}

    @staticmethod
    def _parse_ollama_model(model: dict) -> dict:
        """Parse a single Ollama model entry into standardized format."""
        return {
            "name": model.get("name", "Unknown"),
            "type": "ollama",
            "size": model.get("size", 0),
            "modified_at": model.get("modified_at", ""),
            "available": True,
        }

    @staticmethod
    def _log_ollama_warning_if_needed(error: Exception) -> None:
        """Log Ollama warning with rate limiting to prevent spam."""
        current_time = time.time()
        time_since_last = current_time - ModelManager._last_ollama_warning
        if time_since_last >= ModelManager._warning_interval:
            logger.warning("Failed to get Ollama models: %s", str(error))
            ModelManager._last_ollama_warning = current_time

    @staticmethod
    async def _get_ollama_models() -> list:
        """Get models from Ollama service"""
        try:
            ollama_config = global_config_manager.get_nested("llm_config.ollama", {})
            from src.unified_config_manager import OLLAMA_URL

            ollama_host = ollama_config.get("host", OLLAMA_URL)
            ollama_url = f"{ollama_host}/api/tags"

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(ollama_url) as response:
                    if response.status != 200:
                        return []
                    ollama_data = await response.json()
                    raw_models = ollama_data.get("models", [])
                    return [
                        ModelManager._parse_ollama_model(model)
                        for model in raw_models
                    ]
        except Exception as e:
            ModelManager._log_ollama_warning_if_needed(e)
            return []
