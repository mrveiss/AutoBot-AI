#!/usr/bin/env python3
"""
Async Configuration Manager using pydantic-settings
Replaces blocking config operations with async file I/O and caching
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from datetime import datetime, timezone

import aiofiles
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.async_redis_manager import redis_get, redis_set
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class AsyncConfigSettings(BaseSettings):
    """Base configuration settings with async support"""
    
    # File paths
    config_dir: Path = Field(default=Path("config"), env="CONFIG_DIR")
    config_file: str = Field(default="config.yaml", env="CONFIG_FILE")
    settings_file: str = Field(default="settings.json", env="SETTINGS_FILE")
    
    # Cache settings
    cache_ttl: int = Field(default=300, env="CONFIG_CACHE_TTL")  # 5 minutes
    auto_reload: bool = Field(default=True, env="CONFIG_AUTO_RELOAD")
    
    # Redis settings for distributed config
    use_redis_cache: bool = Field(default=True, env="USE_REDIS_CONFIG_CACHE")
    redis_key_prefix: str = Field(default="config:", env="CONFIG_REDIS_PREFIX")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"  # Allow extra environment variables


class AsyncConfigManager:
    """
    Async configuration manager with file watching, caching, and validation
    """
    
    def __init__(self, settings: Optional[AsyncConfigSettings] = None):
        self.settings = settings or AsyncConfigSettings()
        self._config_cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._file_watchers: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._callbacks: Dict[str, List[callable]] = {}
        
        # Ensure config directory exists
        self.settings.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_key(self, config_type: str) -> str:
        """Get Redis cache key for config type"""
        return f"{self.settings.redis_key_prefix}{config_type}"
    
    async def _get_file_path(self, config_type: str) -> Path:
        """Get file path for config type"""
        if config_type == "settings":
            return self.settings.config_dir / self.settings.settings_file
        elif config_type == "config":
            return self.settings.config_dir / self.settings.config_file
        else:
            return self.settings.config_dir / f"{config_type}.json"
    
    async def _is_cache_valid(self, config_type: str) -> bool:
        """Check if cached config is still valid"""
        if config_type not in self._cache_timestamps:
            return False
        
        cache_time = self._cache_timestamps[config_type]
        age = (datetime.now(timezone.utc) - cache_time).total_seconds()
        return age < self.settings.cache_ttl
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def _read_file_async(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Read config file asynchronously with retry"""
        if not file_path.exists():
            return None
        
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
                content = await file.read()
                
                if file_path.suffix.lower() == '.json':
                    return json.loads(content)
                elif file_path.suffix.lower() in ['.yaml', '.yml']:
                    import yaml
                    return yaml.safe_load(content)
                else:
                    # Assume JSON for unknown extensions
                    return json.loads(content)
        
        except Exception as e:
            logger.error(f"Failed to read config file {file_path}: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def _write_file_async(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Write config file asynchronously with retry"""
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
                if file_path.suffix.lower() == '.json':
                    await file.write(json.dumps(data, indent=2, ensure_ascii=False))
                elif file_path.suffix.lower() in ['.yaml', '.yml']:
                    import yaml
                    await file.write(yaml.dump(data, default_flow_style=False))
                else:
                    # Default to JSON
                    await file.write(json.dumps(data, indent=2, ensure_ascii=False))
        
        except Exception as e:
            logger.error(f"Failed to write config file {file_path}: {e}")
            raise
    
    async def _load_from_redis_cache(self, config_type: str) -> Optional[Dict[str, Any]]:
        """Load config from Redis cache"""
        if not self.settings.use_redis_cache:
            return None
        
        try:
            cache_key = self._get_cache_key(config_type)
            cached_data = await redis_get(cache_key)
            
            if cached_data:
                data = json.loads(cached_data.decode())
                logger.debug(f"Loaded {config_type} config from Redis cache")
                return data
        
        except Exception as e:
            logger.debug(f"Failed to load {config_type} from Redis cache: {e}")
        
        return None
    
    async def _save_to_redis_cache(self, config_type: str, data: Dict[str, Any]) -> None:
        """Save config to Redis cache"""
        if not self.settings.use_redis_cache:
            return
        
        try:
            cache_key = self._get_cache_key(config_type)
            await redis_set(
                cache_key,
                json.dumps(data, default=str),
                ex=self.settings.cache_ttl
            )
            logger.debug(f"Saved {config_type} config to Redis cache")
        
        except Exception as e:
            logger.debug(f"Failed to save {config_type} to Redis cache: {e}")
    
    async def load_config(self, config_type: str, use_cache: bool = True) -> Dict[str, Any]:
        """Load configuration with caching and fallback mechanisms"""
        async with self._lock:
            # Check memory cache first
            if use_cache and await self._is_cache_valid(config_type):
                logger.debug(f"Using memory cache for {config_type} config")
                return self._config_cache.get(config_type, {})
            
            # Try Redis cache
            if use_cache:
                redis_data = await self._load_from_redis_cache(config_type)
                if redis_data:
                    self._config_cache[config_type] = redis_data
                    self._cache_timestamps[config_type] = datetime.now(timezone.utc)
                    return redis_data
            
            # Load from file
            file_path = await self._get_file_path(config_type)
            file_data = await self._read_file_async(file_path)
            
            if file_data is None:
                # Return empty config if file doesn't exist
                file_data = {}
                logger.info(f"Config file {file_path} not found, using empty config")
            
            # Update caches
            self._config_cache[config_type] = file_data
            self._cache_timestamps[config_type] = datetime.now(timezone.utc)
            
            # Save to Redis cache
            if file_data:
                await self._save_to_redis_cache(config_type, file_data)
            
            logger.info(f"Loaded {config_type} config from file: {len(file_data)} keys")
            return file_data
    
    async def save_config(self, config_type: str, data: Dict[str, Any]) -> None:
        """Save configuration with validation and caching"""
        async with self._lock:
            # Validate data structure
            if not isinstance(data, dict):
                raise ValueError(f"Config data must be a dictionary, got {type(data)}")
            
            # Save to file
            file_path = await self._get_file_path(config_type)
            await self._write_file_async(file_path, data)
            
            # Update caches
            self._config_cache[config_type] = data
            self._cache_timestamps[config_type] = datetime.now(timezone.utc)
            
            # Save to Redis cache
            await self._save_to_redis_cache(config_type, data)
            
            # Notify callbacks
            await self._notify_callbacks(config_type, data)
            
            logger.info(f"Saved {config_type} config: {len(data)} keys")
    
    async def get_config_value(
        self, 
        config_type: str, 
        key: str, 
        default: Any = None
    ) -> Any:
        """Get specific config value with dot notation support"""
        config = await self.load_config(config_type)
        
        # Support dot notation (e.g., "database.host")
        keys = key.split('.')
        value = config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    async def set_config_value(
        self, 
        config_type: str, 
        key: str, 
        value: Any
    ) -> None:
        """Set specific config value with dot notation support"""
        config = await self.load_config(config_type)
        
        # Support dot notation for nested keys
        keys = key.split('.')
        current = config
        
        # Navigate to parent of target key
        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        
        # Set the value
        current[keys[-1]] = value
        
        # Save updated config
        await self.save_config(config_type, config)
    
    def add_change_callback(self, config_type: str, callback: callable) -> None:
        """Add callback for config changes"""
        if config_type not in self._callbacks:
            self._callbacks[config_type] = []
        
        self._callbacks[config_type].append(callback)
    
    async def _notify_callbacks(self, config_type: str, data: Dict[str, Any]) -> None:
        """Notify callbacks of config changes"""
        if config_type in self._callbacks:
            for callback in self._callbacks[config_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(config_type, data)
                    else:
                        callback(config_type, data)
                except Exception as e:
                    logger.error(f"Config callback error for {config_type}: {e}")
    
    async def start_file_watcher(self, config_type: str) -> None:
        """Start watching config file for changes"""
        if not self.settings.auto_reload:
            return
        
        if config_type in self._file_watchers:
            return  # Already watching
        
        file_path = await self._get_file_path(config_type)
        
        async def watch_file():
            last_modified = None
            
            while True:
                try:
                    if file_path.exists():
                        current_modified = file_path.stat().st_mtime
                        
                        if last_modified is not None and current_modified != last_modified:
                            logger.info(f"Config file {file_path} changed, reloading")
                            
                            # Reload config
                            new_data = await self._read_file_async(file_path)
                            if new_data:
                                self._config_cache[config_type] = new_data
                                self._cache_timestamps[config_type] = datetime.now(timezone.utc)
                                await self._save_to_redis_cache(config_type, new_data)
                                await self._notify_callbacks(config_type, new_data)
                        
                        last_modified = current_modified
                    
                    await asyncio.sleep(1.0)  # Check every second
                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"File watcher error for {config_type}: {e}")
                    await asyncio.sleep(5.0)  # Wait before retrying
        
        self._file_watchers[config_type] = asyncio.create_task(watch_file())
        logger.info(f"Started file watcher for {config_type} config")
    
    async def stop_file_watcher(self, config_type: str) -> None:
        """Stop watching config file"""
        if config_type in self._file_watchers:
            self._file_watchers[config_type].cancel()
            try:
                await self._file_watchers[config_type]
            except asyncio.CancelledError:
                pass
            
            del self._file_watchers[config_type]
            logger.info(f"Stopped file watcher for {config_type} config")
    
    async def reload_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """Reload all cached configurations"""
        reloaded = {}
        
        for config_type in list(self._config_cache.keys()):
            try:
                reloaded[config_type] = await self.load_config(config_type, use_cache=False)
            except Exception as e:
                logger.error(f"Failed to reload {config_type} config: {e}")
        
        logger.info(f"Reloaded {len(reloaded)} configurations")
        return reloaded
    
    async def get_config_stats(self) -> Dict[str, Any]:
        """Get configuration statistics"""
        stats = {
            "cached_configs": list(self._config_cache.keys()),
            "cache_timestamps": {
                k: v.isoformat() for k, v in self._cache_timestamps.items()
            },
            "active_watchers": list(self._file_watchers.keys()),
            "settings": {
                "cache_ttl": self.settings.cache_ttl,
                "auto_reload": self.settings.auto_reload,
                "use_redis_cache": self.settings.use_redis_cache,
                "config_dir": str(self.settings.config_dir)
            }
        }
        
        return stats
    
    async def close(self) -> None:
        """Clean up resources"""
        # Stop all file watchers
        for config_type in list(self._file_watchers.keys()):
            await self.stop_file_watcher(config_type)
        
        # Clear caches
        self._config_cache.clear()
        self._cache_timestamps.clear()
        self._callbacks.clear()
        
        logger.info("Async config manager closed")


# Dependency injection pattern - global instance
class ConfigManagerContainer:
    """Container for config manager with lazy initialization"""
    
    def __init__(self):
        self._instance: Optional[AsyncConfigManager] = None
        self._lock = asyncio.Lock()
    
    async def get_manager(self) -> AsyncConfigManager:
        """Get or create config manager instance"""
        if self._instance is None:
            async with self._lock:
                if self._instance is None:
                    self._instance = AsyncConfigManager()
                    logger.info("Async config manager initialized")
        
        return self._instance
    
    async def close(self) -> None:
        """Close config manager"""
        if self._instance:
            await self._instance.close()
            self._instance = None


# DEPRECATED: This file now imports from unified_config_manager for backward compatibility
# All new code should import directly from src.unified_config_manager

from src.unified_config_manager import (
    unified_config_manager,
    get_config_manager_async,
    load_config_async,
    save_config_async,
    get_config_value_async,
    set_config_value_async
)

logger.warning("DEPRECATED: src.async_config_manager is deprecated. Use src.unified_config_manager instead.")

# Backward compatibility aliases
config_container = None  # No longer needed


# Convenience functions for backward compatibility
async def get_config_manager() -> 'UnifiedConfigManager':
    """Get config manager instance"""
    return await get_config_manager_async()


async def load_config(config_type: str) -> Dict[str, Any]:
    """Load configuration"""
    return await load_config_async(config_type)


async def save_config(config_type: str, data: Dict[str, Any]) -> None:
    """Save configuration"""
    await save_config_async(config_type, data)


async def get_config_value(config_type: str, key: str, default: Any = None) -> Any:
    """Get configuration value"""
    return await get_config_value_async(config_type, key, default)


async def set_config_value(config_type: str, key: str, value: Any) -> None:
    """Set configuration value"""
    await set_config_value_async(config_type, key, value)