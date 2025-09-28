#!/usr/bin/env python3
"""
Unified Configuration Manager for AutoBot

Consolidates functionality from:
- src/config.py (global_config_manager)
- src/utils/config_manager.py (config_manager)
- src/async_config_manager.py (AsyncConfigManager)

Provides a single, comprehensive configuration system with:
- Synchronous and asynchronous operations
- YAML/JSON file management
- Environment variable overrides
- Redis caching
- File watching and change callbacks
- Model management for GUI integration
- Hardware acceleration configuration
- Backward compatibility
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable

import aiofiles
import yaml
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from tenacity import retry, stop_after_attempt, wait_exponential

# Import host configurations
from src.config_helper import cfg

logger = logging.getLogger(__name__)


class UnifiedConfigSettings(BaseSettings):
    """Configuration settings for the unified config manager"""

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
        extra = "allow"


class UnifiedConfigManager:
    """
    Unified configuration manager combining sync/async operations,
    file management, caching, and model management.
    """

    def __init__(self, config_dir: str = "config", settings: Optional[UnifiedConfigSettings] = None):
        # Find project root dynamically
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / config_dir
        self.base_config_file = self.config_dir / "config.yaml"
        self.settings_file = self.config_dir / "settings.json"

        # Async settings
        self.settings = settings or UnifiedConfigSettings()

        # Configuration cache
        self._config: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._sync_cache_timestamp: Optional[float] = None
        self.CACHE_DURATION = 30  # 30 seconds for sync cache

        # Async support
        self._async_lock = asyncio.Lock() if hasattr(asyncio, 'current_task') else None
        self._sync_lock = None  # Will be created when needed
        self._file_watchers: Dict[str, asyncio.Task] = {}
        self._callbacks: Dict[str, List[Callable]] = {}

        # Initialize
        self._load_configuration()

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _get_sync_lock(self):
        """Get or create synchronous lock"""
        if self._sync_lock is None:
            import threading
            self._sync_lock = threading.Lock()
        return self._sync_lock

    def _load_configuration(self) -> None:
        """Load and merge all configuration sources (synchronous)"""
        try:
            # Load base configuration from YAML
            base_config = self._load_yaml_config()

            # Load user settings from JSON (if exists)
            user_settings = self._load_json_settings()

            # Merge configurations (user settings override base config)
            self._config = self._deep_merge(base_config, user_settings)

            # Apply environment variable overrides
            self._apply_env_overrides()

            # Update cache timestamp
            self._sync_cache_timestamp = time.time()

            logger.info("Unified configuration loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def _load_yaml_config(self) -> Dict[str, Any]:
        """Load base configuration from YAML file"""
        if not self.base_config_file.exists():
            logger.info(f"Base configuration file not found: {self.base_config_file}, using defaults")
            return self._get_default_config()

        try:
            with open(self.base_config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            logger.info(f"Base configuration loaded from {self.base_config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load YAML configuration: {e}")
            return self._get_default_config()

    def _load_json_settings(self) -> Dict[str, Any]:
        """Load user settings from JSON file"""
        if not self.settings_file.exists():
            logger.debug(f"Settings file not found: {self.settings_file}")
            return {}

        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            logger.info(f"User settings loaded from {self.settings_file}")
            return settings
        except Exception as e:
            logger.warning(f"Failed to load JSON settings: {e}")
            return {}

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values"""
        try:
            # Use config helper for service IPs
            ollama_host = cfg.get_host('ollama')
            ollama_port = cfg.get_port('ollama')
            redis_host = cfg.get_host('redis')
            redis_port = cfg.get_port('redis')
        except Exception:
            # Fallback values
            ollama_host = "127.0.0.1"
            ollama_port = 11434
            redis_host = "127.0.0.1"
            redis_port = 6379

        return {
            "backend": {
                "llm": {
                    "provider_type": "local",
                    "local": {
                        "provider": "ollama",
                        "providers": {
                            "ollama": {
                                "endpoint": f"http://{ollama_host}:{ollama_port}/api/generate",
                                "host": f"http://{ollama_host}:{ollama_port}",
                                "models": [],
                                "selected_model": os.getenv("AUTOBOT_OLLAMA_MODEL", "llama3.2:3b"),
                            }
                        },
                    },
                    "embedding": {
                        "provider": "ollama",
                        "providers": {
                            "ollama": {
                                "endpoint": f"http://{ollama_host}:{ollama_port}/api/embeddings",
                                "host": f"http://{ollama_host}:{ollama_port}",
                                "models": [],
                                "selected_model": os.getenv("AUTOBOT_EMBEDDING_MODEL", "nomic-embed-text"),
                            }
                        },
                    },
                },
                "server_host": "0.0.0.0",
                "server_port": int(os.getenv("AUTOBOT_BACKEND_PORT", "8001")),
                "timeout": 60,
                "max_retries": 3,
                "streaming": False,
            },
            "memory": {
                "redis": {
                    "enabled": True,
                    "host": redis_host,
                    "port": redis_port,
                    "db": int(os.getenv("AUTOBOT_REDIS_DB", "1")),
                    "password": os.getenv("AUTOBOT_REDIS_PASSWORD"),
                }
            },
            "ui": {
                "theme": "light",
                "font_size": "medium",
                "language": "en",
                "animations": True,
            },
            "chat": {
                "auto_scroll": True,
                "max_messages": 100,
                "message_retention_days": 30,
            },
            "logging": {
                "log_level": "INFO",
                "log_to_file": True,
                "log_file_path": "logs/autobot.log",
            },
        }

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries, with override taking precedence"""
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides using AUTOBOT_ prefix"""
        env_overrides = {}

        # Environment variable mappings
        env_mappings = {
            # Backend configuration
            "AUTOBOT_BACKEND_HOST": ["backend", "server_host"],
            "AUTOBOT_BACKEND_PORT": ["backend", "server_port"],
            "AUTOBOT_BACKEND_TIMEOUT": ["backend", "timeout"],
            "AUTOBOT_BACKEND_MAX_RETRIES": ["backend", "max_retries"],
            "AUTOBOT_BACKEND_STREAMING": ["backend", "streaming"],

            # LLM configuration
            "AUTOBOT_OLLAMA_HOST": ["backend", "llm", "local", "providers", "ollama", "host"],
            "AUTOBOT_OLLAMA_MODEL": ["backend", "llm", "local", "providers", "ollama", "selected_model"],
            "AUTOBOT_OLLAMA_ENDPOINT": ["backend", "llm", "local", "providers", "ollama", "endpoint"],

            # Redis configuration
            "AUTOBOT_REDIS_HOST": ["memory", "redis", "host"],
            "AUTOBOT_REDIS_PORT": ["memory", "redis", "port"],
            "AUTOBOT_REDIS_DB": ["memory", "redis", "db"],
            "AUTOBOT_REDIS_PASSWORD": ["memory", "redis", "password"],
            "AUTOBOT_REDIS_ENABLED": ["memory", "redis", "enabled"],

            # UI configuration
            "AUTOBOT_UI_THEME": ["ui", "theme"],
            "AUTOBOT_UI_FONT_SIZE": ["ui", "font_size"],
            "AUTOBOT_UI_LANGUAGE": ["ui", "language"],
            "AUTOBOT_UI_ANIMATIONS": ["ui", "animations"],

            # Chat configuration
            "AUTOBOT_CHAT_MAX_MESSAGES": ["chat", "max_messages"],
            "AUTOBOT_CHAT_AUTO_SCROLL": ["chat", "auto_scroll"],
            "AUTOBOT_CHAT_RETENTION_DAYS": ["chat", "message_retention_days"],

            # Logging configuration
            "AUTOBOT_LOG_LEVEL": ["logging", "log_level"],
            "AUTOBOT_LOG_TO_FILE": ["logging", "log_to_file"],
            "AUTOBOT_LOG_FILE_PATH": ["logging", "log_file_path"],
        }

        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # Convert string values to appropriate types
                if env_value.lower() in ("true", "false"):
                    env_value = env_value.lower() == "true"
                elif env_value.isdigit():
                    env_value = int(env_value)

                # Set the value in the config
                self._set_nested_value(env_overrides, config_path, env_value)
                logger.info(f"Applied environment override: {env_var} = {env_value}")

        # Merge environment overrides
        if env_overrides:
            self._config = self._deep_merge(self._config, env_overrides)

    def _set_nested_value(self, config: Dict[str, Any], path: List[str], value: Any) -> None:
        """Set a nested value in a dictionary using a path list"""
        current = config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    def _should_refresh_sync_cache(self) -> bool:
        """Check if synchronous cache should be refreshed"""
        if self._sync_cache_timestamp is None:
            return True
        return (time.time() - self._sync_cache_timestamp) > self.CACHE_DURATION

    # SYNCHRONOUS METHODS (for backward compatibility)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key (synchronous)"""
        with self._get_sync_lock():
            if self._should_refresh_sync_cache():
                self._load_configuration()
            return self._config.get(key, default)

    def get_nested(self, path: str, default: Any = None) -> Any:
        """Get nested config value using dot notation (synchronous)"""
        with self._get_sync_lock():
            if self._should_refresh_sync_cache():
                self._load_configuration()

            keys = path.split(".")
            current = self._config

            try:
                for key in keys:
                    current = current[key]
                return current
            except (KeyError, TypeError):
                return default

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value (synchronous)"""
        with self._get_sync_lock():
            self._config[key] = value

    def set_nested(self, path: str, value: Any) -> None:
        """Set a nested configuration value using dot notation (synchronous)"""
        with self._get_sync_lock():
            keys = path.split(".")
            current = self._config

            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]

            current[keys[-1]] = value

    def save_settings(self) -> None:
        """Save current configuration to settings.json (synchronous)"""
        try:
            # Filter out prompts before saving
            import copy
            filtered_config = copy.deepcopy(self._config)
            if "prompts" in filtered_config:
                logger.info("Removing prompts section from settings save")
                del filtered_config["prompts"]

            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(filtered_config, f, indent=2, ensure_ascii=False)

            # Clear cache to force fresh load on next access
            self._sync_cache_timestamp = None
            logger.info(f"Settings saved to {self.settings_file} and cache cleared")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            raise

    def save_config_to_yaml(self) -> None:
        """Save configuration to config.yaml file (synchronous)"""
        try:
            # Filter out prompts and legacy fields before saving
            import copy
            filtered_config = copy.deepcopy(self._config)

            if "prompts" in filtered_config:
                logger.info("Removing prompts section from YAML save")
                del filtered_config["prompts"]

            self.base_config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.base_config_file, "w", encoding="utf-8") as f:
                yaml.dump(filtered_config, f, default_flow_style=False, indent=2)

            # Clear cache to force fresh load on next access
            self._sync_cache_timestamp = None
            logger.info(f"Configuration saved to {self.base_config_file} and cache cleared")
        except Exception as e:
            logger.error(f"Failed to save YAML configuration: {e}")
            raise

    def reload(self) -> None:
        """Reload configuration from files (synchronous)"""
        with self._get_sync_lock():
            self._load_configuration()

    def to_dict(self) -> Dict[str, Any]:
        """Return the complete configuration as a dictionary (synchronous)"""
        with self._get_sync_lock():
            if self._should_refresh_sync_cache():
                self._load_configuration()
            return self._config.copy()

    # MODEL MANAGEMENT METHODS (critical for GUI integration)

    def get_selected_model(self) -> str:
        """Get the currently selected model from config.yaml (CRITICAL FIX)"""
        # This is the key method that was broken in the original global_config_manager
        # It must read from config.yaml, NOT return hardcoded values

        selected_model = self.get_nested("backend.llm.local.providers.ollama.selected_model")

        if selected_model:
            logger.info(f"UNIFIED CONFIG: Selected model from config.yaml: {selected_model}")
            return selected_model

        # Only fall back to environment if config.yaml doesn't have the value
        env_model = os.getenv("AUTOBOT_OLLAMA_MODEL")
        if env_model:
            logger.info(f"UNIFIED CONFIG: Selected model from environment: {env_model}")
            return env_model

        # Final fallback
        fallback_model = "llama3.2:3b"
        logger.warning(f"UNIFIED CONFIG: No model configured, using fallback: {fallback_model}")
        return fallback_model

    def update_llm_model(self, model_name: str) -> None:
        """Update the selected LLM model in config.yaml (GUI integration)"""
        logger.info(f"UNIFIED CONFIG: Updating selected model to '{model_name}'")

        # Update the configuration in memory
        self.set_nested("backend.llm.local.providers.ollama.selected_model", model_name)

        # Save both settings.json and config.yaml
        self.save_settings()
        self.save_config_to_yaml()

        logger.info(f"Model updated to '{model_name}' in unified configuration")

    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration with correct model reading"""
        # Get the full backend.llm configuration
        backend_llm = self.get_nested("backend.llm", {})

        # Ensure we have proper structure
        if not backend_llm:
            # Create default structure
            backend_llm = {
                "provider_type": "local",
                "local": {
                    "provider": "ollama",
                    "providers": {
                        "ollama": {
                            "selected_model": self.get_selected_model(),
                            "models": [],
                            "endpoint": f"http://127.0.0.1:11434/api/generate",
                            "host": f"http://127.0.0.1:11434",
                        }
                    },
                },
            }
            self.set_nested("backend.llm", backend_llm)

        # CRITICAL: Always use the selected model from config, not hardcoded values
        selected_model = self.get_selected_model()
        if backend_llm.get("local", {}).get("providers", {}).get("ollama"):
            backend_llm["local"]["providers"]["ollama"]["selected_model"] = selected_model

        # Return legacy-compatible format for existing code
        return {
            "ollama": {
                "selected_model": selected_model,
                "models": backend_llm.get("local", {}).get("providers", {}).get("ollama", {}).get("models", []),
                "endpoint": backend_llm.get("local", {}).get("providers", {}).get("ollama", {}).get("endpoint", "http://172.16.168.20:11434")
            },
            "unified": backend_llm  # New unified format
        }

    # REDIS CONFIGURATION METHODS

    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration with fallback defaults"""
        redis_config = self.get_nested("memory.redis", {})

        try:
            default_host = cfg.get_host('redis')
            default_port = cfg.get_port('redis')
        except Exception:
            default_host = "127.0.0.1"
            default_port = 6379

        defaults = {
            "enabled": True,
            "host": default_host,
            "port": default_port,
            "db": 1,
            "password": None,
        }

        return self._deep_merge(defaults, redis_config)

    def get_ollama_url(self) -> str:
        """Get the Ollama service URL from configuration (backward compatibility)"""
        # First check environment variable
        env_url = os.getenv("AUTOBOT_OLLAMA_URL")
        if env_url:
            return env_url

        # Then check configuration
        endpoint = self.get_nested("backend.llm.local.providers.ollama.endpoint")
        if endpoint:
            return endpoint.replace("/api/generate", "")  # Get base URL

        host = self.get_nested("backend.llm.local.providers.ollama.host")
        if host:
            return host

        # Finally fall back to configured host
        try:
            ollama_host = cfg.get_host('ollama')
            ollama_port = cfg.get_port('ollama')
            return f"http://{ollama_host}:{ollama_port}"
        except Exception:
            return "http://127.0.0.1:11434"

    def get_redis_url(self) -> str:
        """Get the Redis service URL from configuration (backward compatibility)"""
        env_url = os.getenv("AUTOBOT_REDIS_URL")
        if env_url:
            return env_url

        host = self.get_nested("memory.redis.host", "127.0.0.1")
        port = self.get_nested("memory.redis.port", 6379)
        return f"redis://{host}:{port}"

    # ASYNC METHODS (from AsyncConfigManager)

    async def _get_async_lock(self):
        """Get async lock, creating if needed"""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
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
                    return yaml.safe_load(content)
                else:
                    return json.loads(content)

        except Exception as e:
            logger.error(f"Failed to read config file {file_path}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def _write_file_async(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Write config file asynchronously with retry"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
                if file_path.suffix.lower() == '.json':
                    await file.write(json.dumps(data, indent=2, ensure_ascii=False))
                elif file_path.suffix.lower() in ['.yaml', '.yml']:
                    await file.write(yaml.dump(data, default_flow_style=False))
                else:
                    await file.write(json.dumps(data, indent=2, ensure_ascii=False))

        except Exception as e:
            logger.error(f"Failed to write config file {file_path}: {e}")
            raise

    async def load_config_async(self, config_type: str = "main", use_cache: bool = True) -> Dict[str, Any]:
        """Load configuration asynchronously"""
        async with await self._get_async_lock():
            # For main config, return current config
            if config_type == "main":
                if self._should_refresh_sync_cache():
                    self._load_configuration()
                return self._config.copy()

            # For other config types, use file-based loading
            if config_type == "settings":
                file_path = self.settings_file
            else:
                file_path = self.config_dir / f"{config_type}.json"

            file_data = await self._read_file_async(file_path)
            return file_data or {}

    async def save_config_async(self, config_type: str, data: Dict[str, Any]) -> None:
        """Save configuration asynchronously"""
        async with await self._get_async_lock():
            # Filter out prompts
            import copy
            filtered_data = copy.deepcopy(data)
            if "prompts" in filtered_data:
                logger.info(f"Removing prompts section from async {config_type} save")
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

            logger.info(f"Saved {config_type} config asynchronously")

    async def get_config_value_async(self, config_type: str, key: str, default: Any = None) -> Any:
        """Get specific config value asynchronously with dot notation support"""
        config = await self.load_config_async(config_type)

        keys = key.split('.')
        value = config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    async def set_config_value_async(self, config_type: str, key: str, value: Any) -> None:
        """Set specific config value asynchronously with dot notation support"""
        config = await self.load_config_async(config_type)

        keys = key.split('.')
        current = config

        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value
        await self.save_config_async(config_type, config)

    # FILE WATCHING AND CALLBACKS

    def add_change_callback(self, config_type: str, callback: Callable) -> None:
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

    async def stop_file_watcher(self, config_type: str) -> None:
        """Stop watching config file"""
        if config_type in self._file_watchers:
            self._file_watchers[config_type].cancel()
            try:
                await self._file_watchers[config_type]
            except asyncio.CancelledError:
                pass
            del self._file_watchers[config_type]

    # VALIDATION AND UTILITIES

    def validate_config(self) -> Dict[str, Any]:
        """Validate configuration and return status"""
        status = {
            "config_loaded": True,
            "llm_config": self.get_llm_config(),
            "redis_config": self.get_redis_config(),
            "issues": [],
        }

        # Validate LLM configuration
        llm_config = status["llm_config"]
        if not llm_config.get("ollama", {}).get("selected_model"):
            status["issues"].append("No selected_model specified in LLM config")

        # Validate Redis configuration
        redis_config = status["redis_config"]
        if redis_config.get("enabled", True) and not redis_config.get("host"):
            status["issues"].append("Redis enabled but no host specified")

        return status


# SINGLETON INSTANCE AND BACKWARD COMPATIBILITY

# Create the unified manager instance
unified_config_manager = UnifiedConfigManager()

# Backward compatibility aliases
config_manager = unified_config_manager  # For utils/config_manager.py imports
global_config_manager = unified_config_manager  # For src/config.py imports
config = unified_config_manager  # General usage

# Legacy class wrapper for compatibility
class Config:
    """Backward compatibility wrapper"""

    def __init__(self):
        self._manager = unified_config_manager

    @property
    def config(self) -> Dict[str, Any]:
        return self._manager.to_dict()

    def get(self, key: str, default: Any = None) -> Any:
        return self._manager.get(key, default)


# Convenience functions for common operations
def get_config(key: str, default: Any = None) -> Any:
    """Get configuration value"""
    return unified_config_manager.get(key, default)

def get_config_section(section: str) -> Dict[str, Any]:
    """Get configuration section"""
    return unified_config_manager.get_nested(section, {})

def get_llm_config() -> Dict[str, Any]:
    """Get LLM configuration"""
    return unified_config_manager.get_llm_config()

def get_redis_config() -> Dict[str, Any]:
    """Get Redis configuration"""
    return unified_config_manager.get_redis_config()

def reload_config() -> None:
    """Reload configuration from files"""
    unified_config_manager.reload()

def validate_config() -> Dict[str, Any]:
    """Validate configuration and return status"""
    return unified_config_manager.validate_config()


# ASYNC CONVENIENCE FUNCTIONS

async def get_config_manager_async():
    """Get async config manager instance"""
    return unified_config_manager

async def load_config_async(config_type: str = "main") -> Dict[str, Any]:
    """Load configuration asynchronously"""
    return await unified_config_manager.load_config_async(config_type)

async def save_config_async(config_type: str, data: Dict[str, Any]) -> None:
    """Save configuration asynchronously"""
    await unified_config_manager.save_config_async(config_type, data)

async def get_config_value_async(config_type: str, key: str, default: Any = None) -> Any:
    """Get configuration value asynchronously"""
    return await unified_config_manager.get_config_value_async(config_type, key, default)

async def set_config_value_async(config_type: str, key: str, value: Any) -> None:
    """Set configuration value asynchronously"""
    await unified_config_manager.set_config_value_async(config_type, key, value)


logger.info("Unified Configuration Manager initialized successfully")