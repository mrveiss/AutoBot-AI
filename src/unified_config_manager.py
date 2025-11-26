#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
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
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

import aiofiles
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings
from tenacity import retry, stop_after_attempt, wait_exponential

# Import host configurations
# NOTE: Removed config_helper dependency (Issue #63 - Config Consolidation)
# Convenience methods (get_host, get_port, etc.) are now built into this module
from src.constants.network_constants import NetworkConstants

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

    def __init__(
        self,
        config_dir: str = "config",
        settings: Optional[UnifiedConfigSettings] = None,
    ):
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
        self._async_lock = asyncio.Lock() if hasattr(asyncio, "current_task") else None
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
        """Load and merge all configuration sources (synchronous)

        IMPORTANT: Configuration precedence order:
        1. config.yaml (base configuration)
        2. settings.json (user settings override base config)
        3. Environment variables (override both)

        WARNING: settings.json completely overrides matching sections from config.yaml.
        For example, if config.yaml has 10 CORS origins and settings.json has 4,
        only the 4 from settings.json will be used.
        """
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
            logger.info(
                f"Base configuration file not found: {self.base_config_file}, using defaults"
            )
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
        # Use NetworkConstants directly for defaults (no circular dependency)
        ollama_host = NetworkConstants.AI_STACK_HOST
        ollama_port = NetworkConstants.OLLAMA_PORT
        redis_host = NetworkConstants.REDIS_HOST
        redis_port = NetworkConstants.REDIS_PORT

        return {
            "backend": {
                "llm": {
                    "provider_type": "local",
                    "local": {
                        "provider": "ollama",
                        "providers": {
                            "ollama": {
                                "endpoint": (
                                    f"http://{ollama_host}:{ollama_port}/api/generate"
                                ),
                                "host": f"http://{ollama_host}:{ollama_port}",
                                "models": [],
                                "selected_model": os.getenv(
                                    "AUTOBOT_OLLAMA_MODEL", "gemma3:270m"
                                ),
                            }
                        },
                    },
                    "embedding": {
                        "provider": "ollama",
                        "providers": {
                            "ollama": {
                                "endpoint": (
                                    f"http://{ollama_host}:{ollama_port}/api/embeddings"
                                ),
                                "host": f"http://{ollama_host}:{ollama_port}",
                                "models": [],
                                "selected_model": os.getenv(
                                    "AUTOBOT_EMBEDDING_MODEL", "nomic-embed-text"
                                ),
                            }
                        },
                    },
                },
                "server_host": NetworkConstants.BIND_ALL_INTERFACES,
                "server_port": int(
                    os.getenv(
                        "AUTOBOT_BACKEND_PORT", str(NetworkConstants.BACKEND_PORT)
                    )
                ),
                "timeout": 60,
                "max_retries": 3,
                "streaming": False,
            },
            "deployment": {
                "mode": "local",
                "host": redis_host,
                "port": int(
                    os.getenv(
                        "AUTOBOT_BACKEND_PORT", str(NetworkConstants.BACKEND_PORT)
                    )
                ),
            },
            "data": {
                "reliability_stats_file": "data/reliability_stats.json",
                "long_term_db_path": "data/agent_memory.db",
                "chat_history_file": "data/chat_history.json",
                "chats_directory": "data/chats",
            },
            "redis": {
                "host": redis_host,
                "port": redis_port,
                "db": int(os.getenv("AUTOBOT_REDIS_DB", "0")),
                "password": os.getenv("AUTOBOT_REDIS_PASSWORD"),
            },
            "memory": {
                "redis": {
                    "enabled": True,
                    "host": redis_host,
                    "port": redis_port,
                    "db": int(os.getenv("AUTOBOT_REDIS_MEMORY_DB", "1")),
                    "password": os.getenv("AUTOBOT_REDIS_PASSWORD"),
                }
            },
            "multimodal": {
                "vision": {
                    "enabled": True,
                    "confidence_threshold": 0.7,
                    "processing_timeout": 30,
                },
                "voice": {
                    "enabled": True,
                    "confidence_threshold": 0.8,
                    "processing_timeout": 15,
                },
                "context": {
                    "enabled": True,
                    "decision_threshold": 0.9,
                    "processing_timeout": 10,
                },
            },
            "npu": {
                "enabled": False,
                "device": "CPU",
                "model_path": None,
                "optimization_level": "PERFORMANCE",
            },
            "hardware": {
                "environment_variables": {
                    "cuda_device_order": "PCI_BUS_ID",
                    "gpu_max_heap_size": "100",
                    "gpu_use_sync_objects": "1",
                    "openvino_device_priorities": "NPU,GPU,CPU",
                    "intel_npu_enabled": "1",
                    "omp_num_threads": "4",
                    "mkl_num_threads": "4",
                    "openblas_num_threads": "4",
                },
                "acceleration": {
                    "enabled": True,
                    "priority_order": ["npu", "gpu", "cpu"],
                    "cpu_reserved_cores": 2,
                    "memory_optimization": "enabled",
                },
            },
            "system": {
                "environment": {"DISPLAY": ":0", "USER": "unknown", "SHELL": "unknown"},
                "desktop_streaming": {
                    "default_resolution": os.getenv(
                        "AUTOBOT_DESKTOP_RESOLUTION", "1024x768"
                    ),
                    "default_depth": int(os.getenv("AUTOBOT_DESKTOP_DEPTH", "24")),
                    "max_sessions": int(
                        os.getenv("AUTOBOT_DESKTOP_MAX_SESSIONS", "10")
                    ),
                },
            },
            "network": {"share": {"username": None, "password": None}},
            "task_transport": {
                "type": "redis",
                "redis": {
                    "host": redis_host,
                    "port": redis_port,
                    "password": os.getenv("AUTOBOT_REDIS_PASSWORD"),
                    "db": int(os.getenv("AUTOBOT_REDIS_TASK_DB", "0")),
                },
            },
            "security": {
                "enable_sandboxing": True,
                "allowed_commands": [],
                "blocked_commands": ["rm -rf", "format", "delete"],
                "secrets_key": None,
                "audit_log_file": "data/audit.log",
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

    def _deep_merge(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
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
            "AUTOBOT_OLLAMA_HOST": [
                "backend",
                "llm",
                "local",
                "providers",
                "ollama",
                "host",
            ],
            "AUTOBOT_OLLAMA_MODEL": [
                "backend",
                "llm",
                "local",
                "providers",
                "ollama",
                "selected_model",
            ],
            "AUTOBOT_OLLAMA_ENDPOINT": [
                "backend",
                "llm",
                "local",
                "providers",
                "ollama",
                "endpoint",
            ],
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

    def _set_nested_value(
        self, config: Dict[str, Any], path: List[str], value: Any
    ) -> None:
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
            logger.info(
                f"Configuration saved to {self.base_config_file} and cache cleared"
            )
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

        selected_model = self.get_nested(
            "backend.llm.local.providers.ollama.selected_model"
        )

        if selected_model:
            logger.info(
                f"UNIFIED CONFIG: Selected model from config.yaml: {selected_model}"
            )
            return selected_model

        # Only fall back to environment if config.yaml doesn't have the value
        env_model = os.getenv("AUTOBOT_OLLAMA_MODEL")
        if env_model:
            logger.info(f"UNIFIED CONFIG: Selected model from environment: {env_model}")
            return env_model

        # Final fallback
        fallback_model = "mistral:7b"
        logger.warning(
            f"UNIFIED CONFIG: No model configured, using fallback: {fallback_model}"
        )
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
                            "endpoint": (
                                f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.OLLAMA_PORT}/api/generate"
                            ),
                            "host": (
                                f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.OLLAMA_PORT}"
                            ),
                        }
                    },
                },
            }
            self.set_nested("backend.llm", backend_llm)

        # CRITICAL: Always use the selected model from config, not hardcoded values
        selected_model = self.get_selected_model()
        if backend_llm.get("local", {}).get("providers", {}).get("ollama"):
            backend_llm["local"]["providers"]["ollama"][
                "selected_model"
            ] = selected_model

        # Build Ollama endpoint from config instead of hardcoded IP
        ollama_endpoint = (
            backend_llm.get("local", {})
            .get("providers", {})
            .get("ollama", {})
            .get("endpoint")
        )

        # If not explicitly configured, construct from infrastructure config
        if not ollama_endpoint:
            ollama_host = self.get_host("ollama")
            ollama_port = self.get_port("ollama")
            ollama_endpoint = f"http://{ollama_host}:{ollama_port}"

        # Return legacy-compatible format for existing code
        return {
            "ollama": {
                "selected_model": selected_model,
                "models": (
                    backend_llm.get("local", {})
                    .get("providers", {})
                    .get("ollama", {})
                    .get("models", [])
                ),
                "endpoint": ollama_endpoint,
            },
            "unified": backend_llm,  # New unified format
        }

    # BACKEND CONFIGURATION METHODS

    def get_backend_config(self) -> Dict[str, Any]:
        """Get backend configuration with fallback defaults"""
        backend_config = self.get_nested("backend", {})

        defaults = {
            "server_host": NetworkConstants.BIND_ALL_INTERFACES,
            "server_port": int(
                os.getenv("AUTOBOT_BACKEND_PORT", str(NetworkConstants.BACKEND_PORT))
            ),
            "api_endpoint": (
                f"http://localhost:{os.getenv('AUTOBOT_BACKEND_PORT', str(NetworkConstants.BACKEND_PORT))}"
            ),
            "timeout": 60,
            "max_retries": 3,
            "streaming": False,
            "cors_origins": [],
            "allowed_hosts": ["*"],
            "max_request_size": 10485760,  # 10MB
        }

        return self._deep_merge(defaults, backend_config)

    def get_config_section(self, section: str) -> Dict[str, Any]:
        """Get configuration section with fallback defaults"""
        return self.get_nested(section, {})

    # CONVENIENCE METHODS (from config_helper for consolidation)

    def get_host(self, service: str) -> str:
        """
        Get host address for a service.

        Provides compatibility with config_helper.cfg.get_host()
        for config consolidation (Issue #63).

        Args:
            service: Service name (e.g., 'backend', 'redis', 'frontend')

        Returns:
            Host address string
        """
        # Try infrastructure.hosts first
        host = self.get_nested(f"infrastructure.hosts.{service}")
        if host:
            return host

        # Fallback to NetworkConstants
        service_map = {
            "backend": NetworkConstants.BACKEND_HOST,
            "redis": NetworkConstants.REDIS_HOST,
            "frontend": NetworkConstants.FRONTEND_HOST,
            "npu_worker": NetworkConstants.NPU_WORKER_HOST,
            "ai_stack": NetworkConstants.AI_STACK_HOST,
            "browser": NetworkConstants.BROWSER_HOST,
        }
        return service_map.get(service, "localhost")

    def get_port(self, service: str) -> int:
        """
        Get port number for a service.

        Provides compatibility with config_helper.cfg.get_port()
        for config consolidation (Issue #63).

        Args:
            service: Service name (e.g., 'backend', 'redis', 'frontend')

        Returns:
            Port number
        """
        # Try infrastructure.ports first
        port = self.get_nested(f"infrastructure.ports.{service}")
        if port:
            return int(port)

        # Fallback to NetworkConstants
        service_map = {
            "backend": NetworkConstants.BACKEND_PORT,
            "redis": NetworkConstants.REDIS_PORT,
            "frontend": NetworkConstants.FRONTEND_PORT,
            "npu_worker": NetworkConstants.NPU_WORKER_PORT,
            "ai_stack": NetworkConstants.AI_STACK_PORT,
            "browser": NetworkConstants.BROWSER_PORT,
        }
        return service_map.get(service, 8000)

    def get_timeout(self, category: str, timeout_type: str = "default") -> float:
        """
        Get timeout value for a category.

        Provides compatibility with config_helper.cfg.get_timeout()
        for config consolidation (Issue #63).

        Args:
            category: Timeout category (e.g., 'llm', 'http', 'redis')
            timeout_type: Type of timeout (default: 'default')

        Returns:
            Timeout in seconds
        """
        timeout = self.get_nested(f"timeouts.{category}.{timeout_type}")
        if timeout is not None:
            return float(timeout)

        # Fallback defaults
        defaults = {
            "llm": {"default": 120.0, "streaming": 180.0},
            "http": {"default": 30.0, "long": 60.0},
            "redis": {"default": 5.0, "connection": 10.0},
            "database": {"default": 30.0, "query": 60.0},
        }
        return defaults.get(category, {}).get(timeout_type, 30.0)

    def get_service_url(self, service: str, endpoint: str = None) -> str:
        """
        Get full URL for a service with optional endpoint.

        Provides compatibility with config_helper.cfg.get_service_url()
        for config consolidation (Issue #63).

        Args:
            service: Service name (e.g., 'backend', 'redis', 'frontend')
            endpoint: Optional endpoint path to append

        Returns:
            Full service URL string
        """
        host = self.get_host(service)
        port = self.get_port(service)
        url = f"http://{host}:{port}"
        if endpoint:
            url = f"{url}/{endpoint.lstrip('/')}"
        return url

    def get_path(self, category: str, name: str = None) -> str:
        """
        Get filesystem path from configuration.

        Provides compatibility with config_helper.cfg.get_path()
        for config consolidation (Issue #63).

        Args:
            category: Path category (e.g., 'logs', 'data', 'config')
            name: Optional specific path name within category

        Returns:
            Filesystem path string
        """
        if name:
            path = self.get_nested(f"paths.{category}.{name}")
        else:
            path = self.get_nested(f"paths.{category}")

        if path:
            return str(path)

        # Fallback defaults
        from pathlib import Path

        project_root = Path(__file__).parent.parent
        defaults = {
            "logs": str(project_root / "logs"),
            "data": str(project_root / "data"),
            "config": str(project_root / "config"),
            "reports": str(project_root / "reports"),
        }
        return defaults.get(category, str(project_root))

    # REDIS CONFIGURATION METHODS

    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration with fallback defaults"""
        redis_config = self.get_nested("memory.redis", {})

        # Use self.get_host/get_port for consistency (Issue #63 consolidation)
        default_host = self.get_host("redis")
        default_port = self.get_port("redis")

        # FIX: Don't override password with None - let it come from redis_config
        defaults = {
            "enabled": True,
            "host": default_host,
            "port": default_port,
            "db": 1,
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

        # Finally fall back to configured host (Issue #63 consolidation)
        ollama_host = self.get_host("ollama")
        ollama_port = self.get_port("ollama")
        if ollama_host and ollama_port:
            return f"http://{ollama_host}:{ollama_port}"
        return (
            f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.OLLAMA_PORT}"
        )

    def get_redis_url(self) -> str:
        """Get the Redis service URL from configuration (backward compatibility)"""
        env_url = os.getenv("AUTOBOT_REDIS_URL")
        if env_url:
            return env_url

        host = self.get_nested("memory.redis.host", NetworkConstants.LOCALHOST_IP)
        port = self.get_nested("memory.redis.port", 6379)
        return f"redis://{host}:{port}"

    def get_distributed_services_config(self) -> Dict[str, Any]:
        """Get distributed services configuration from NetworkConstants"""
        from src.constants.network_constants import NetworkConstants

        return {
            "frontend": {
                "host": str(NetworkConstants.FRONTEND_HOST),
                "port": NetworkConstants.FRONTEND_PORT,
            },
            "npu_worker": {
                "host": str(NetworkConstants.NPU_WORKER_HOST),
                "port": NetworkConstants.NPU_WORKER_PORT,
            },
            "redis": {
                "host": str(NetworkConstants.REDIS_HOST),
                "port": NetworkConstants.REDIS_PORT,
            },
            "ai_stack": {
                "host": str(NetworkConstants.AI_STACK_HOST),
                "port": NetworkConstants.AI_STACK_PORT,
            },
            "browser": {
                "host": str(NetworkConstants.BROWSER_HOST),
                "port": NetworkConstants.BROWSER_PORT,
            },
        }

    # CORS AND SECURITY METHODS (ported from unified_config.py for consolidation)

    def get_cors_origins(self) -> list:
        """Generate CORS allowed origins from infrastructure configuration

        Returns a list of allowed origins including:
        - Localhost variants for development
        - Frontend service (Vite dev server)
        - Browser service (Playwright)
        - Backend service (for WebSocket/CORS testing)
        """
        # Check if explicitly configured in security.cors_origins
        explicit_origins = self.get_nested("security.cors_origins", [])
        if explicit_origins:
            return explicit_origins

        # Otherwise, generate from infrastructure config
        frontend_host = self.get_host("frontend")
        frontend_port = self.get_port("frontend")
        browser_host = self.get_host("browser_service")
        browser_port = self.get_port("browser_service")
        backend_host = self.get_host("backend")
        backend_port = self.get_port("backend")

        origins = [
            # Localhost variants for development
            # Vite dev server default
            f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.FRONTEND_PORT}",
            f"http://{NetworkConstants.LOCALHOST_IP}:{NetworkConstants.FRONTEND_PORT}",
            # Browser/other dev tools
            f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.BROWSER_SERVICE_PORT}",
            f"http://{NetworkConstants.LOCALHOST_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}",
            # Frontend service
            f"http://{frontend_host}:{frontend_port}",
            # Browser service (Playwright)
            f"http://{browser_host}:{browser_port}",
            # Backend service (for testing/debugging)
            f"http://{backend_host}:{backend_port}",
        ]

        # Remove duplicates while preserving order
        seen = set()
        unique_origins = []
        for origin in origins:
            if origin not in seen:
                seen.add(origin)
                unique_origins.append(origin)

        return unique_origins

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self.get_nested(f"features.{feature}", False)

    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration"""
        return self.get_nested(
            "security",
            {"session": {"timeout_minutes": 30}, "encryption": {"enabled": False}},
        )

    # TIMEOUT METHODS (ported from unified_config.py for consolidation)

    def get_timeout_for_env(
        self,
        category: str,
        timeout_type: str,
        environment: str = None,
        default: float = 60.0,
    ) -> float:
        """
        Get environment-aware timeout value.

        Args:
            category: Category path (e.g., 'redis.operations')
            timeout_type: Specific timeout type (e.g., 'get')
            environment: Environment name ('development', 'production')
            default: Fallback value if not found

        Returns:
            Timeout value in seconds
        """
        if environment is None:
            environment = os.getenv("AUTOBOT_ENVIRONMENT", "production")

        # Try environment-specific override first
        env_path = f"environments.{environment}.timeouts.{category}.{timeout_type}"
        env_timeout = self.get_nested(env_path)
        if env_timeout is not None:
            return float(env_timeout)

        # Fall back to base configuration
        base_path = f"timeouts.{category}.{timeout_type}"
        base_timeout = self.get_nested(base_path, default)
        return float(base_timeout)

    def get_timeout_group(
        self, category: str, environment: str = None
    ) -> Dict[str, float]:
        """
        Get all timeouts for a category as a dictionary.

        Args:
            category: Category path (e.g., 'redis.operations')
            environment: Environment name (optional)

        Returns:
            Dictionary of timeout names to values
        """
        base_path = f"timeouts.{category}"
        base_config = self.get_nested(base_path, {})

        if not isinstance(base_config, dict):
            return {}

        # Apply environment overrides if specified
        if environment:
            env_path = f"environments.{environment}.timeouts.{category}"
            env_overrides = self.get_nested(env_path, {})
            if isinstance(env_overrides, dict):
                base_config = {**base_config, **env_overrides}

        # Convert all values to float
        result = {}
        for k, v in base_config.items():
            if isinstance(v, (int, float)):
                result[k] = float(v)

        return result

    def validate_timeouts(self) -> Dict[str, Any]:
        """
        Validate all timeout configurations.

        Returns:
            Validation report with issues and warnings
        """
        issues = []
        warnings = []

        # Check required timeout categories
        required_categories = ["redis", "llamaindex", "documents", "http", "llm"]
        for category in required_categories:
            timeout_config = self.get_nested(f"timeouts.{category}")
            if timeout_config is None:
                issues.append(f"Missing timeout configuration for '{category}'")

        # Validate timeout ranges
        all_timeouts = self.get_nested("timeouts", {})

        def check_timeout_values(config, path=""):
            for key, value in config.items():
                current_path = f"{path}.{key}" if path else key
                if isinstance(value, dict):
                    check_timeout_values(value, current_path)
                elif isinstance(value, (int, float)):
                    if value <= 0:
                        issues.append(
                            f"Invalid timeout '{current_path}': {value} (must be > 0)"
                        )
                    elif value > 600:
                        warnings.append(
                            f"Very long timeout '{current_path}': {value}s (> 10 minutes)"
                        )

        check_timeout_values(all_timeouts)

        return {"valid": len(issues) == 0, "issues": issues, "warnings": warnings}

    # ASYNC METHODS (from AsyncConfigManager)

    async def _get_async_lock(self):
        """Get async lock, creating if needed"""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def _filter_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter sensitive data before caching to Redis.
        Redacts passwords, credentials, API keys, and other secrets.
        """
        import copy

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
                        logger.debug(f"Redacted sensitive field: {current_path}")
                    elif isinstance(value, (dict, list)):
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
                    logger.debug(f"Loaded {config_type} config from Redis cache")
                    return data

        except Exception as e:
            logger.debug(f"Failed to load {config_type} from Redis cache: {e}")

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
                    f"Saved {config_type} config to Redis cache (sensitive data filtered)"
                )

        except Exception as e:
            logger.debug(f"Failed to save {config_type} to Redis cache: {e}")

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def _read_file_async(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Read config file asynchronously with retry"""
        if not file_path.exists():
            return None

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as file:
                content = await file.read()

                if file_path.suffix.lower() == ".json":
                    return json.loads(content)
                elif file_path.suffix.lower() in [".yaml", ".yml"]:
                    return yaml.safe_load(content)
                else:
                    return json.loads(content)

        except Exception as e:
            logger.error(f"Failed to read config file {file_path}: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def _write_file_async(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Write config file asynchronously with retry"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                if file_path.suffix.lower() == ".json":
                    await file.write(json.dumps(data, indent=2, ensure_ascii=False))
                elif file_path.suffix.lower() in [".yaml", ".yml"]:
                    await file.write(yaml.dump(data, default_flow_style=False))
                else:
                    await file.write(json.dumps(data, indent=2, ensure_ascii=False))

        except Exception as e:
            logger.error(f"Failed to write config file {file_path}: {e}")
            raise

    async def load_config_async(
        self, config_type: str = "main", use_cache: bool = True
    ) -> Dict[str, Any]:
        """Load configuration asynchronously with Redis caching"""
        async with await self._get_async_lock():
            # For main config, return current config
            if config_type == "main":
                if self._should_refresh_sync_cache():
                    self._load_configuration()
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

            # Save to Redis cache
            await self._save_to_redis_cache(config_type, filtered_data)

            logger.info(f"Saved {config_type} config asynchronously")

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

    async def start_file_watcher(self, config_type: str) -> None:
        """Start watching config file for changes"""
        if not self.settings.auto_reload:
            return

        if config_type in self._file_watchers:
            return  # Already watching

        # Determine file path
        if config_type == "settings":
            file_path = self.settings_file
        elif config_type == "main":
            file_path = self.base_config_file
        else:
            file_path = self.config_dir / f"{config_type}.json"

        async def watch_file():
            last_modified = None

            while True:
                try:
                    if file_path.exists():
                        current_modified = file_path.stat().st_mtime

                        if (
                            last_modified is not None
                            and current_modified != last_modified
                        ):
                            logger.info(f"Config file {file_path} changed, reloading")

                            # Reload config
                            new_data = await self._read_file_async(file_path)
                            if new_data:
                                # Update cache
                                if config_type == "main":
                                    self._config = new_data
                                    self._sync_cache_timestamp = time.time()

                                # Save to Redis cache
                                await self._save_to_redis_cache(config_type, new_data)

                                # Notify callbacks
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
cfg = unified_config_manager  # Short alias for ai_hardware_accelerator.py


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


async def get_config_value_async(
    config_type: str, key: str, default: Any = None
) -> Any:
    """Get configuration value asynchronously"""
    return await unified_config_manager.get_config_value_async(
        config_type, key, default
    )


async def set_config_value_async(config_type: str, key: str, value: Any) -> None:
    """Set configuration value asynchronously"""
    await unified_config_manager.set_config_value_async(config_type, key, value)


# Export host and service constants for backward compatibility
# Using NetworkConstants directly to avoid circular import (Issue #63)
HTTP_PROTOCOL = "http"
OLLAMA_HOST_IP = NetworkConstants.AI_STACK_HOST
OLLAMA_PORT = NetworkConstants.OLLAMA_PORT
REDIS_HOST_IP = NetworkConstants.REDIS_VM_IP
OLLAMA_URL = f"http://{OLLAMA_HOST_IP}:{OLLAMA_PORT}"

# Backend/API service constants
BACKEND_HOST_IP = NetworkConstants.MAIN_MACHINE_IP
BACKEND_PORT = NetworkConstants.BACKEND_PORT
API_BASE_URL = f"http://{BACKEND_HOST_IP}:{BACKEND_PORT}"

# Playwright/Browser service constants
PLAYWRIGHT_HOST_IP = NetworkConstants.BROWSER_VM_IP
PLAYWRIGHT_VNC_PORT = NetworkConstants.VNC_PORT
PLAYWRIGHT_VNC_URL = f"http://{PLAYWRIGHT_HOST_IP}:{PLAYWRIGHT_VNC_PORT}/vnc.html"


# VNC Direct URL function
def get_vnc_direct_url():
    """Get the direct VNC connection URL with appropriate port"""
    return f"http://{PLAYWRIGHT_HOST_IP}:{PLAYWRIGHT_VNC_PORT}/vnc.html"


# Export cfg for compatibility
# This is already imported at the top, now we export it

logger.info("Unified Configuration Manager initialized successfully")
