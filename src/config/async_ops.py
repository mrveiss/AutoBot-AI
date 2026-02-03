#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Asynchronous operations for unified config manager.
"""

import asyncio
import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
import yaml
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Module-level constants for O(1) lookups (Issue #326)
YAML_FILE_EXTENSIONS = {".yaml", ".yml"}

# Issue #380: Module-level tuple for container type checks
_CONTAINER_TYPES = (dict, list)


class AsyncOperationsMixin:
    """Mixin providing asynchronous config operations"""

    # Class-level lock for safe async lock initialization (Issue #378)
    _lock_init_lock = asyncio.Lock()

    async def _get_async_lock(self):
        """Get async lock, creating if needed.

        Issue #378: Uses double-checked locking pattern to prevent race condition
        when multiple coroutines try to create the lock simultaneously.
        """
        if self._async_lock is None:
            async with AsyncOperationsMixin._lock_init_lock:
                # Double-check after acquiring lock
                if self._async_lock is None:
                    self._async_lock = asyncio.Lock()
        return self._async_lock

    def _filter_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter sensitive data before caching to Redis.
        Redacts passwords, credentials, API keys, and other secrets.
        """
        filtered = copy.deepcopy(data)

        # List of sensitive field patterns to redact
        sensitive_patterns = [
            "password",
            "passwd",
            "pwd",
            "secret",
            "api_key",
            "apikey",
            "token",
            "credential",
            "auth",
        ]

        def redact_sensitive_fields(obj: Any, path: str = "") -> Any:
            """Recursively redact sensitive fields"""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    key_lower = key.lower()
                    current_path = f"{path}.{key}" if path else key

                    # Check if field name contains sensitive pattern
                    if any(pattern in key_lower for pattern in sensitive_patterns):
                        obj[key] = "***REDACTED***"
                        logger.debug("Redacted sensitive field: %s", current_path)
                    elif isinstance(value, _CONTAINER_TYPES):  # Issue #380
                        obj[key] = redact_sensitive_fields(value, current_path)

            elif isinstance(obj, list):
                return [
                    redact_sensitive_fields(item, f"{path}[{i}]")
                    for i, item in enumerate(obj)
                ]

            return obj

        return redact_sensitive_fields(filtered)

    def _get_redis_cache_key(self, config_type: str) -> str:
        """Get Redis cache key for config type"""
        return f"{self.settings.redis_key_prefix}{config_type}"

    async def _load_from_redis_cache(
        self, config_type: str
    ) -> Optional[Dict[str, Any]]:
        """Load config from Redis cache"""
        if not self.settings.use_redis_cache:
            return None

        try:
            from src.utils.redis_client import get_redis_client

            cache_key = self._get_redis_cache_key(config_type)
            redis_client = await get_redis_client(async_client=True, database="main")

            if redis_client:
                cached_data = await redis_client.get(cache_key)
                if cached_data:
                    data = json.loads(cached_data.decode())
                    logger.debug("Loaded %s config from Redis cache", config_type)
                    return data

        except Exception as e:
            logger.debug("Failed to load %s from Redis cache: %s", config_type, e)

        return None

    async def _save_to_redis_cache(
        self, config_type: str, data: Dict[str, Any]
    ) -> None:
        """Save config to Redis cache (with sensitive data filtering)"""
        if not self.settings.use_redis_cache:
            return

        try:
            from src.utils.redis_client import get_redis_client

            # Filter sensitive data before caching
            filtered_data = self._filter_sensitive_data(data)

            cache_key = self._get_redis_cache_key(config_type)
            redis_client = await get_redis_client(async_client=True, database="main")

            if redis_client:
                await redis_client.set(
                    cache_key,
                    json.dumps(filtered_data, default=str),
                    ex=self.settings.cache_ttl,
                )
                logger.debug(
                    "Saved %s config to Redis cache (sensitive data filtered)",
                    config_type,
                )

        except Exception as e:
            logger.debug("Failed to save %s to Redis cache: %s", config_type, e)

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def _read_file_async(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Read config file asynchronously with retry"""
        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(file_path.exists):
            return None

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as file:
                content = await file.read()

                if file_path.suffix.lower() == ".json":
                    return json.loads(content)
                elif (
                    file_path.suffix.lower() in YAML_FILE_EXTENSIONS
                ):  # O(1) lookup (Issue #326)
                    return yaml.safe_load(content)
                else:
                    return json.loads(content)

        except OSError as e:
            logger.error("Failed to read config file %s: %s", file_path, e)
            raise
        except Exception as e:
            logger.error("Failed to parse config file %s: %s", file_path, e)
            raise

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def _write_file_async(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Write config file asynchronously with retry"""
        try:
            # Issue #358 - avoid blocking
            await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)

            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                if file_path.suffix.lower() == ".json":
                    await file.write(json.dumps(data, indent=2, ensure_ascii=False))
                elif (
                    file_path.suffix.lower() in YAML_FILE_EXTENSIONS
                ):  # O(1) lookup (Issue #326)
                    await file.write(yaml.dump(data, default_flow_style=False))
                else:
                    await file.write(json.dumps(data, indent=2, ensure_ascii=False))

        except OSError as e:
            logger.error("Failed to write config file %s: %s", file_path, e)
            raise
        except Exception as e:
            logger.error("Failed to serialize config for %s: %s", file_path, e)
            raise

    async def load_config_async(
        self, config_type: str = "main", use_cache: bool = True
    ) -> Dict[str, Any]:
        """Load configuration asynchronously with Redis caching"""
        async with await self._get_async_lock():
            # For main config, return current config
            if config_type == "main":
                if self._should_refresh_sync_cache():
                    self._reload_config()
                return self._config.copy()

            # Try Redis cache first for other config types
            if use_cache:
                redis_data = await self._load_from_redis_cache(config_type)
                if redis_data:
                    return redis_data

            # For other config types, use file-based loading
            if config_type == "settings":
                file_path = self.settings_file
            else:
                file_path = self.config_dir / f"{config_type}.json"

            file_data = await self._read_file_async(file_path)

            # Save to Redis cache if loaded from file
            if file_data and use_cache:
                await self._save_to_redis_cache(config_type, file_data)

            return file_data or {}

    async def save_config_async(self, config_type: str, data: Dict[str, Any]) -> None:
        """Save configuration asynchronously with Redis caching"""
        import time

        async with await self._get_async_lock():
            # Filter out prompts
            filtered_data = copy.deepcopy(data)
            if "prompts" in filtered_data:
                logger.info("Removing prompts section from async %s save", config_type)
                del filtered_data["prompts"]

            # Determine file path
            if config_type == "main":
                file_path = self.base_config_file
            elif config_type == "settings":
                file_path = self.settings_file
            else:
                file_path = self.config_dir / f"{config_type}.json"

            await self._write_file_async(file_path, filtered_data)

            # Update cache if main config
            if config_type == "main":
                self._config = filtered_data
                self._sync_cache_timestamp = time.time()

            # Save to Redis cache
            await self._save_to_redis_cache(config_type, filtered_data)

            logger.info("Saved %s config asynchronously", config_type)

    async def get_config_value_async(
        self, config_type: str, key: str, default: Any = None
    ) -> Any:
        """Get specific config value asynchronously with dot notation support"""
        config = await self.load_config_async(config_type)

        keys = key.split(".")
        value = config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    async def set_config_value_async(
        self, config_type: str, key: str, value: Any
    ) -> None:
        """Set specific config value asynchronously with dot notation support"""
        config = await self.load_config_async(config_type)

        keys = key.split(".")
        current = config

        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value
        await self.save_config_async(config_type, config)

    async def close(self) -> None:
        """Clean up async resources"""
        # Stop all file watchers
        for config_type in list(self._file_watchers.keys()):
            await self.stop_file_watcher(config_type)

        # Clear caches
        self._config.clear()
        self._cache_timestamps.clear()
        self._callbacks.clear()

        logger.info("Unified config manager closed")
