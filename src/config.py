"""
Centralized Configuration Management Module

This module provides a unified configuration system that:
- Loads base configuration from config/config.yaml
- Allows overrides from config/settings.json
- Supports environment variable overrides
- Provides a single source of truth for all configuration
"""

import os
import yaml
import json
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigManager:
    """Centralized configuration manager"""

    def __init__(self, config_dir: str = "config"):
        # Find project root dynamically (directory containing this file is
        # src/, parent is project root)
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / config_dir
        self.base_config_file = self.config_dir / "config.yaml"
        self.settings_file = self.config_dir / "settings.json"
        self._config: Dict[str, Any] = {}
        self._load_configuration()

    def _load_configuration(self) -> None:
        """Load and merge all configuration sources"""
        try:
            # Load base configuration from YAML
            base_config = self._load_yaml_config()

            # Load user settings from JSON (if exists)
            user_settings = self._load_json_settings()

            # Merge configurations (user settings override base config)
            self._config = self._deep_merge(base_config, user_settings)

            # Apply environment variable overrides
            self._apply_env_overrides()

            logger.info("Configuration loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def _load_yaml_config(self) -> Dict[str, Any]:
        """Load base configuration from YAML file"""
        if not self.base_config_file.exists():
            raise FileNotFoundError(
                f"Base configuration file not found: {self.base_config_file}"
            )

        try:
            with open(self.base_config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            logger.info(f"Base configuration loaded from {self.base_config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load YAML configuration: {e}")
            raise

    def _load_json_settings(self) -> Dict[str, Any]:
        """Load user settings from JSON file"""
        if not self.settings_file.exists():
            logger.info(
                f"Settings file not found: {self.settings_file}, "
                "using base configuration only"
            )
            return {}

        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            logger.info(f"User settings loaded from {self.settings_file}")
            return settings
        except Exception as e:
            logger.warning(
                f"Failed to load JSON settings: {e}, using base configuration only"
            )
            return {}

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

        # Comprehensive environment variable mappings
        env_mappings = {
            # Backend configuration
            "AUTOBOT_BACKEND_HOST": ["backend", "server_host"],
            "AUTOBOT_BACKEND_PORT": ["backend", "server_port"],
            "AUTOBOT_BACKEND_API_ENDPOINT": ["backend", "api_endpoint"],
            "AUTOBOT_BACKEND_TIMEOUT": ["backend", "timeout"],
            "AUTOBOT_BACKEND_MAX_RETRIES": ["backend", "max_retries"],
            "AUTOBOT_BACKEND_STREAMING": ["backend", "streaming"],
            # LLM configuration
            "AUTOBOT_OLLAMA_HOST": ["backend", "ollama_endpoint"],
            "AUTOBOT_OLLAMA_MODEL": ["backend", "ollama_model"],
            "AUTOBOT_OLLAMA_ENDPOINT": [
                "backend",
                "llm",
                "local",
                "providers",
                "ollama",
                "endpoint",
            ],
            "AUTOBOT_OLLAMA_SELECTED_MODEL": [
                "backend",
                "llm",
                "local",
                "providers",
                "ollama",
                "selected_model",
            ],
            "AUTOBOT_ORCHESTRATOR_LLM": ["llm_config", "orchestrator_llm"],
            "AUTOBOT_DEFAULT_LLM": ["llm_config", "default_llm"],
            "AUTOBOT_TASK_LLM": ["llm_config", "task_llm"],
            "AUTOBOT_LLM_PROVIDER_TYPE": ["backend", "llm", "provider_type"],
            # Redis configuration
            "AUTOBOT_REDIS_HOST": ["memory", "redis", "host"],
            "AUTOBOT_REDIS_PORT": ["memory", "redis", "port"],
            "AUTOBOT_REDIS_ENABLED": ["memory", "redis", "enabled"],
            # Chat configuration
            "AUTOBOT_CHAT_MAX_MESSAGES": ["chat", "max_messages"],
            "AUTOBOT_CHAT_WELCOME_MESSAGE": ["chat", "default_welcome_message"],
            "AUTOBOT_CHAT_AUTO_SCROLL": ["chat", "auto_scroll"],
            "AUTOBOT_CHAT_RETENTION_DAYS": ["chat", "message_retention_days"],
            # Knowledge base configuration
            "AUTOBOT_KB_ENABLED": ["knowledge_base", "enabled"],
            "AUTOBOT_KB_UPDATE_FREQUENCY": [
                "knowledge_base",
                "update_frequency_days",
            ],
            "AUTOBOT_KB_DB_PATH": ["backend", "knowledge_base_db"],
            # Logging configuration
            "AUTOBOT_LOG_LEVEL": ["logging", "log_level"],
            "AUTOBOT_LOG_TO_FILE": ["logging", "log_to_file"],
            "AUTOBOT_LOG_FILE_PATH": ["logging", "log_file_path"],
            # Developer configuration
            "AUTOBOT_DEVELOPER_MODE": ["developer", "enabled"],
            "AUTOBOT_DEBUG_LOGGING": ["developer", "debug_logging"],
            "AUTOBOT_ENHANCED_ERRORS": ["developer", "enhanced_errors"],
            # UI configuration
            "AUTOBOT_UI_THEME": ["ui", "theme"],
            "AUTOBOT_UI_FONT_SIZE": ["ui", "font_size"],
            "AUTOBOT_UI_LANGUAGE": ["ui", "language"],
            "AUTOBOT_UI_ANIMATIONS": ["ui", "animations"],
            # Message display configuration
            "AUTOBOT_SHOW_THOUGHTS": ["message_display", "show_thoughts"],
            "AUTOBOT_SHOW_JSON": ["message_display", "show_json"],
            "AUTOBOT_SHOW_DEBUG": ["message_display", "show_debug"],
            "AUTOBOT_SHOW_PLANNING": ["message_display", "show_planning"],
            "AUTOBOT_SHOW_UTILITY": ["message_display", "show_utility"],
            # Security configuration
            "AUTOBOT_ENABLE_ENCRYPTION": ["security", "enable_encryption"],
            "AUTOBOT_SESSION_TIMEOUT": ["security", "session_timeout_minutes"],
            # Voice interface configuration
            "AUTOBOT_VOICE_ENABLED": ["voice_interface", "enabled"],
            "AUTOBOT_VOICE_RATE": ["voice_interface", "speech_rate"],
            "AUTOBOT_VOICE": ["voice_interface", "voice"],
            # Legacy support
            "AUTOBOT_USE_LANGCHAIN": ["orchestrator", "use_langchain"],
            "AUTOBOT_USE_PHI2": ["backend", "use_phi2"],
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
                logger.info(
                    f"Applied environment override: {env_var} = {env_value}"
                )

        # Merge environment overrides
        if env_overrides:
            self._config = self._deep_merge(self._config, env_overrides)

    def _set_nested_value(
        self, config: Dict[str, Any], path: list, value: Any
    ) -> None:
        """Set a nested value in a dictionary using a path list"""
        current = config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key"""
        return self._config.get(key, default)

    def get_nested(self, path: str, default: Any = None) -> Any:
        """Get nested config value using dot notation.
        (e.g., 'llm_config.ollama.model')
        """
        keys = path.split(".")
        current = self._config

        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value"""
        self._config[key] = value

    def set_nested(self, path: str, value: Any) -> None:
        """Set a nested configuration value using dot notation"""
        keys = path.split(".")
        current = self._config

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    def save_settings(self) -> None:
        """Save current configuration to settings.json"""
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logger.info(f"Settings saved to {self.settings_file}")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            raise

    def reload(self) -> None:
        """Reload configuration from files"""
        self._load_configuration()

    def to_dict(self) -> Dict[str, Any]:
        """Return the complete configuration as a dictionary"""
        return self._config.copy()

    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration with fallback defaults"""
        llm_config = self.get("llm_config", {})

        # Ensure we have sensible defaults
        defaults = {
            "default_llm": "ollama",
            "orchestrator_llm": os.getenv(
                "AUTOBOT_ORCHESTRATOR_LLM", "deepseek-r1:14b"
            ),
            "task_llm": os.getenv("AUTOBOT_TASK_LLM", "ollama"),
            "ollama": {
                "host": os.getenv("AUTOBOT_OLLAMA_HOST", "http://localhost:11434"),
                "port": int(os.getenv("AUTOBOT_OLLAMA_PORT", "11434")),
                "model": os.getenv("AUTOBOT_OLLAMA_MODEL", "deepseek-r1:14b"),
                "base_url": os.getenv(
                    "AUTOBOT_OLLAMA_BASE_URL", "http://localhost:11434"
                ),
            },
        }

        return self._deep_merge(defaults, llm_config)

    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration with fallback defaults"""
        redis_config = self.get_nested("memory.redis", {})

        defaults = {
            "enabled": os.getenv("AUTOBOT_REDIS_ENABLED", "true").lower() == "true",
            "host": os.getenv("AUTOBOT_REDIS_HOST", "localhost"),
            "port": int(os.getenv("AUTOBOT_REDIS_PORT", "6379")),
            "db": int(os.getenv("AUTOBOT_REDIS_DB", "1")),
        }

        return self._deep_merge(defaults, redis_config)

    def get_backend_config(self) -> Dict[str, Any]:
        """Get backend configuration with fallback defaults"""
        backend_config = self.get("backend", {})

        defaults = {
            "server_host": os.getenv("AUTOBOT_BACKEND_HOST", "0.0.0.0"),
            "server_port": int(os.getenv("AUTOBOT_BACKEND_PORT", "8001")),
            "api_endpoint": os.getenv(
                "AUTOBOT_BACKEND_API_ENDPOINT", "http://localhost:8001"
            ),
            "cors_origins": [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ],  # Vue frontend only
        }

        return self._deep_merge(defaults, backend_config)

    def validate_config(self) -> Dict[str, Any]:
        """Validate configuration and return status of dependencies"""
        status = {
            "config_loaded": True,
            "llm_config": self.get_llm_config(),
            "redis_config": self.get_redis_config(),
            "backend_config": self.get_backend_config(),
            "issues": [],
        }

        # Validate LLM configuration
        llm_config = status["llm_config"]
        if not llm_config.get("orchestrator_llm"):
            status["issues"].append("No orchestrator_llm specified")

        # Validate Redis configuration
        redis_config = status["redis_config"]
        if redis_config.get("enabled", True) and not redis_config.get("host"):
            status["issues"].append("Redis enabled but no host specified")

        return status


# Global configuration instance
config = ConfigManager()

# Alias for backward compatibility and consistent naming
global_config_manager = config


# Convenience functions for backward compatibility
def get_config() -> Dict[str, Any]:
    """Get the complete configuration dictionary"""
    return config.to_dict()


def get_llm_config() -> Dict[str, Any]:
    """Get LLM configuration"""
    return config.get_llm_config()


def get_redis_config() -> Dict[str, Any]:
    """Get Redis configuration"""
    return config.get_redis_config()


def get_backend_config() -> Dict[str, Any]:
    """Get backend configuration"""
    return config.get_backend_config()


def reload_config() -> None:
    """Reload configuration from files"""
    config.reload()


def validate_config() -> Dict[str, Any]:
    """Validate configuration and return status"""
    return config.validate_config()
