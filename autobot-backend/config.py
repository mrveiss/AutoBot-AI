"""
Centralized Configuration Management Module

This module provides a unified configuration system that:
- Loads base configuration from config/config.yaml
- Allows overrides from config/settings.json
- Supports environment variable overrides
- Provides a single source of truth for all configuration
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml


# SSOT config for Ollama defaults - Issue #694
def _get_ssot_ollama_url() -> str:
    """Get Ollama URL from SSOT config with fallback."""
    try:
        from autobot_shared.ssot_config import get_config

        return get_config().ollama_url
    except Exception:
        return os.getenv("AUTOBOT_OLLAMA_HOST", "http://127.0.0.1:11434")


def _get_ssot_ollama_endpoint() -> str:
    """Get Ollama API endpoint from SSOT config with fallback."""
    return f"{_get_ssot_ollama_url()}/api/generate"


def _get_ssot_ollama_embedding_endpoint() -> str:
    """Get Ollama embedding endpoint from SSOT config with fallback."""
    return f"{_get_ssot_ollama_url()}/api/embeddings"


# GLOBAL PROTECTION: Monkey-patch yaml.dump to always filter prompts when
# writing config files
_original_yaml_dump = yaml.dump
_original_yaml_safe_dump = yaml.safe_dump


def _filtered_yaml_dump(data, stream=None, **kwargs):
    """Wrapper that filters prompts from any YAML dump operation"""
    if isinstance(data, dict) and stream is not None:
        # Check if this looks like a config file write (stream is a file-like object)
        if hasattr(stream, "name") and "config" in str(stream.name):
            # Filter out prompts for config files
            import copy

            filtered_data = copy.deepcopy(data)
            if "prompts" in filtered_data:
                logging.getLogger(__name__).info(
                    f"GLOBAL YAML PROTECTION: Filtering prompts from {stream.name}"
                )
                del filtered_data["prompts"]
            return _original_yaml_dump(filtered_data, stream, **kwargs)
    return _original_yaml_dump(data, stream, **kwargs)


def _filtered_yaml_safe_dump(data, stream=None, **kwargs):
    """Wrapper that filters prompts from any YAML safe_dump operation"""
    if isinstance(data, dict) and stream is not None:
        # Check if this looks like a config file write
        if hasattr(stream, "name") and "config" in str(stream.name):
            # Filter out prompts for config files
            import copy

            filtered_data = copy.deepcopy(data)
            if "prompts" in filtered_data:
                logging.getLogger(__name__).info(
                    f"GLOBAL YAML PROTECTION: Filtering prompts from {stream.name}"
                )
                del filtered_data["prompts"]
            return _original_yaml_safe_dump(filtered_data, stream, **kwargs)
    return _original_yaml_safe_dump(data, stream, **kwargs)


# Apply the monkey patches
yaml.dump = _filtered_yaml_dump
yaml.safe_dump = _filtered_yaml_safe_dump

logger = logging.getLogger(__name__)


class ConfigManager:
    """Centralized configuration manager"""

    # Issue #620: Extracted from get_ollama_runtime_config for clarity
    OLLAMA_TASK_OPTIMIZATIONS = {
        "chat": {"temperature": 0.8, "num_predict": 256, "top_p": 0.9},
        "system_commands": {"temperature": 0.3, "num_predict": 128, "top_p": 0.7},
        "knowledge_retrieval": {"temperature": 0.4, "num_predict": 200, "top_p": 0.8},
        "rag": {"temperature": 0.6, "num_predict": 512, "top_p": 0.85},
        "research": {"temperature": 0.7, "num_predict": 600, "top_p": 0.9},
        "orchestrator": {"temperature": 0.5, "num_predict": 400, "top_p": 0.8},
    }

    # Issue #620: Environment variable mappings extracted as class constant
    # to reduce _apply_env_overrides function length
    ENV_VAR_MAPPINGS = {
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
        "AUTOBOT_KB_UPDATE_FREQUENCY": ["knowledge_base", "update_frequency_days"],
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

    # Issue #620: Agent model configuration extracted as class constant
    AGENT_MODEL_DEFAULTS = {
        # Core Orchestration - use available model for flexible reasoning
        "orchestrator": "llama3.2:3b",
        "default": "llama3.2:3b",
        # Specialized Agents - optimized for task complexity
        "chat": "llama3.2:1b",
        "system_commands": "llama3.2:1b",
        "rag": "dolphin-llama3:8b",
        "knowledge_retrieval": "llama3.2:1b",
        "research": "dolphin-llama3:8b",
        # Legacy compatibility
        "search": "llama3.2:1b",
        "code": "llama3.2:1b",
        "analysis": "dolphin-llama3:8b",
        "planning": "dolphin-llama3:8b",
        # Fallback models
        "orchestrator_fallback": "llama3.2:3b",
        "chat_fallback": "llama3.2:1b",
        "fallback": "dolphin-llama3:8b",
    }

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

    def _convert_env_value(self, env_value: str) -> Any:
        """Convert environment variable string to appropriate Python type.

        Issue #620: Extracted from _apply_env_overrides to reduce function length.
        Issue #620.

        Args:
            env_value: Raw string value from environment variable

        Returns:
            Converted value (bool, int, or original string)
        """
        if env_value.lower() in ("true", "false"):
            return env_value.lower() == "true"
        elif env_value.isdigit():
            return int(env_value)
        return env_value

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides using AUTOBOT_ prefix.

        Issue #620: Refactored to use ENV_VAR_MAPPINGS class constant and
        _convert_env_value helper method for reduced function length.
        """
        env_overrides = {}

        for env_var, config_path in self.ENV_VAR_MAPPINGS.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                converted_value = self._convert_env_value(env_value)
                self._set_nested_value(env_overrides, config_path, converted_value)
                logger.info(
                    f"Applied environment override: {env_var} = {converted_value}"
                )

        if env_overrides:
            self._config = self._deep_merge(self._config, env_overrides)

    def _set_nested_value(self, config: Dict[str, Any], path: list, value: Any) -> None:
        """Set a nested value in a dictionary using a path list"""
        current = config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    def _get_default_ollama_model(self) -> str:
        """Get the first available Ollama model or fallback to environment/
        hardcoded default"""
        # First check environment variable
        env_model = os.getenv("AUTOBOT_OLLAMA_MODEL")
        if env_model:
            return env_model

        # URGENT FIX: Skip auto-detection during startup to prevent blocking
        # Auto-detection will be handled asynchronously after startup
        logger.info(
            "UNIFIED CONFIG: Skipping Ollama auto-detection during startup to prevent blocking"
        )

        # Fallback to hardcoded default - use available model
        return "llama3.2:3b"

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
            # Filter out prompts before saving (prompts are managed separately
            # in prompts/ directory)
            import copy

            filtered_config = copy.deepcopy(self._config)
            if "prompts" in filtered_config:
                logger.info(
                    "GLOBAL CONFIG MANAGER: Removing prompts section from "
                    "settings save - prompts are managed in prompts/ directory"
                )
                del filtered_config["prompts"]

            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(filtered_config, f, indent=2, ensure_ascii=False)
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

    def _migrate_legacy_llm_config(self) -> Dict[str, Any]:
        """Migrate legacy LLM configuration to new unified structure.

        Issue #620: Extracted from get_llm_config to reduce function length.
        Issue #620.

        Returns:
            Migrated backend_llm configuration dict
        """
        legacy_ollama_model = self.get_nested("backend.ollama_model")
        if not legacy_ollama_model:
            return {}

        logger.info(
            f"MIGRATION: Moving legacy ollama_model '{legacy_ollama_model}' to new structure"
        )
        backend_llm = {
            "provider_type": "local",
            "local": {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": self.get_nested(
                            "backend.ollama_endpoint",
                            _get_ssot_ollama_endpoint(),
                        ),
                        "host": _get_ssot_ollama_url(),
                        "models": [],
                        "selected_model": legacy_ollama_model,
                    }
                },
            },
        }
        self.set_nested("backend.llm", backend_llm)
        return backend_llm

    def _get_llm_config_defaults(self) -> Dict[str, Any]:
        """Get default LLM configuration structure.

        Issue #620: Extracted from get_llm_config to reduce function length.
        Issue #620.

        Returns:
            Default LLM configuration dict
        """
        return {
            "provider_type": "local",
            "local": {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": os.getenv(
                            "AUTOBOT_OLLAMA_ENDPOINT",
                            _get_ssot_ollama_endpoint(),
                        ),
                        "host": _get_ssot_ollama_url(),
                        "models": [],
                        "selected_model": self._get_default_ollama_model(),
                    }
                },
            },
            "embedding": {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": os.getenv(
                            "AUTOBOT_EMBEDDING_ENDPOINT",
                            _get_ssot_ollama_embedding_endpoint(),
                        ),
                        "host": _get_ssot_ollama_url(),
                        "models": [],
                        "selected_model": os.getenv(
                            "AUTOBOT_EMBEDDING_MODEL", "nomic-embed-text"
                        ),
                    }
                },
            },
        }

    def _build_legacy_llm_format(
        self, unified_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build legacy LLM format for backward compatibility.

        Issue #620: Extracted from get_llm_config to reduce function length.
        Issue #620.

        Args:
            unified_config: Unified LLM configuration

        Returns:
            Legacy format configuration dict
        """
        ollama_config = unified_config["local"]["providers"]["ollama"]
        selected_model = ollama_config["selected_model"]

        return {
            "default_llm": (
                f"ollama_{selected_model}"
                if unified_config.get("provider_type") == "local"
                else "ollama"
            ),
            "orchestrator_llm": os.getenv("AUTOBOT_ORCHESTRATOR_LLM", selected_model),
            "task_llm": os.getenv("AUTOBOT_TASK_LLM", f"ollama_{selected_model}"),
            "ollama": {
                "host": ollama_config["host"],
                "port": int(os.getenv("AUTOBOT_OLLAMA_PORT", "11434")),
                "model": selected_model,
                "base_url": ollama_config["host"],
            },
        }

    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration with fallback defaults.

        Issue #620: Refactored to use helper methods for reduced function length.

        Returns:
            Unified LLM configuration with legacy format for backward compatibility
        """
        # Get or migrate backend.llm configuration
        backend_llm = self.get_nested("backend.llm", {})
        if not backend_llm:
            backend_llm = self._migrate_legacy_llm_config()

        # Merge with defaults
        defaults = self._get_llm_config_defaults()
        unified_config = self._deep_merge(defaults, backend_llm)

        # Build legacy format for backward compatibility
        legacy_format = self._build_legacy_llm_format(unified_config)

        return self._deep_merge(legacy_format, {"unified": unified_config})

    def get_task_specific_model(self, task_type: str = "default") -> str:
        """Get model for specific task types to optimize performance and resource usage.

        Issue #620: Refactored to use AGENT_MODEL_DEFAULTS class constant.

        Args:
            task_type: Agent type (orchestrator, chat, system_commands, rag, etc.)

        Returns:
            Model name for the specified agent
        """
        # Check environment override first
        env_key = f"AUTOBOT_MODEL_{task_type.upper()}"
        env_model = os.getenv(env_key)
        if env_model:
            logger.info(f"Using environment override for {task_type}: {env_model}")
            return env_model

        # Check config file
        config_key = f"backend.llm.task_models.{task_type}"
        configured_model = self.get_nested(config_key)
        if configured_model:
            return configured_model

        # Use class constant defaults
        return self.AGENT_MODEL_DEFAULTS.get(
            task_type, self.AGENT_MODEL_DEFAULTS["default"]
        )

    def _build_hardware_acceleration_base_config(
        self, device_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build base hardware acceleration configuration dict. Issue #620.

        Args:
            device_config: Device configuration from hardware manager

        Returns:
            Dict containing base hardware acceleration settings
        """
        return {
            "hardware_acceleration": {
                "enabled": os.getenv("AUTOBOT_HARDWARE_ACCELERATION", "true").lower()
                == "true",
                "priority_order": ["npu", "gpu", "cpu"],
                "device_assignments": device_config,
                "cpu_reserved_cores": int(os.getenv("AUTOBOT_CPU_RESERVED_CORES", "2")),
                "memory_optimization": os.getenv(
                    "AUTOBOT_MEMORY_OPTIMIZATION", "enabled"
                )
                == "enabled",
            }
        }

    def _get_hardware_fallback_config(self, error: Exception) -> Dict[str, Any]:
        """Get fallback CPU-only configuration when hardware detection fails. Issue #620.

        Args:
            error: The exception that caused the fallback

        Returns:
            Dict containing fallback CPU-only configuration
        """
        return {
            "hardware_acceleration": {
                "enabled": False,
                "device_type": "cpu",
                "fallback_reason": str(error),
            }
        }

    def get_hardware_acceleration_config(
        self, task_type: str = "default"
    ) -> Dict[str, Any]:
        """Get hardware acceleration configuration for a specific task type.

        Args:
            task_type: Agent type (orchestrator, chat, system_commands, etc.)

        Returns:
            Dict containing hardware acceleration settings
        """
        try:
            from hardware_acceleration import get_hardware_acceleration_manager

            hw_manager = get_hardware_acceleration_manager()
            device_config = hw_manager.get_ollama_device_config(task_type)
            base_config = self._build_hardware_acceleration_base_config(device_config)

            # Allow per-task overrides
            task_override_key = f"AUTOBOT_DEVICE_{task_type.upper()}"
            if os.getenv(task_override_key):
                base_config["hardware_acceleration"]["device_assignments"][
                    "device_type"
                ] = os.getenv(task_override_key)

            return base_config

        except Exception as e:
            logger.warning(f"Failed to get hardware acceleration config: {e}")
            return self._get_hardware_fallback_config(e)

    def _apply_ollama_env_overrides(self, config: Dict[str, Any]) -> None:
        """
        Apply environment variable overrides to Ollama config.

        Issue #620: Extracted from get_ollama_runtime_config to reduce function length.

        Args:
            config: Ollama configuration dict to modify in-place
        """
        env_overrides = {
            "AUTOBOT_LLM_TEMPERATURE": "temperature",
            "AUTOBOT_LLM_TOP_P": "top_p",
            "AUTOBOT_LLM_NUM_PREDICT": "num_predict",
        }

        for env_var, config_key in env_overrides.items():
            env_value = os.getenv(env_var)
            if env_value:
                try:
                    if config_key in ["temperature", "top_p"]:
                        config[config_key] = float(env_value)
                    elif config_key == "num_predict":
                        config[config_key] = int(env_value)
                except ValueError:
                    logger.warning(f"Invalid value for {env_var}: {env_value}")

    def get_ollama_runtime_config(self, task_type: str = "default") -> Dict[str, Any]:
        """Get Ollama runtime configuration with hardware optimization.

        Issue #620: Refactored to use class constant and helper method.

        Args:
            task_type: Agent type for task-specific optimization

        Returns:
            Dict containing Ollama runtime configuration
        """
        # Get hardware acceleration config
        hw_config = self.get_hardware_acceleration_config(task_type)
        device_config = hw_config["hardware_acceleration"]["device_assignments"]

        # Base Ollama configuration
        ollama_config = {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 512,
            "stop": ["</s>", "<|end|>", "<|eot_id|>"],
        }

        # Add device-specific options
        if device_config.get("ollama_options"):
            ollama_config.update(device_config["ollama_options"])

        # Apply task-specific optimizations from class constant
        if task_type in self.OLLAMA_TASK_OPTIMIZATIONS:
            ollama_config.update(self.OLLAMA_TASK_OPTIMIZATIONS[task_type])

        # Apply environment variable overrides
        self._apply_ollama_env_overrides(ollama_config)

        return ollama_config

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

    def _generate_cors_origins(self) -> list:
        """Generate CORS origins from all AutoBot VMs (#815)."""
        from constants.network_constants import NetworkConstants

        origins: set = set()
        for port in (5173, 8001, 3000):
            origins.add(f"http://localhost:{port}")
            origins.add(f"http://127.0.0.1:{port}")
        for host in NetworkConstants.get_host_configs():
            origins.add(f"http://{host['ip']}:{host['port']}")
        return sorted(origins)

    def get_backend_config(self) -> Dict[str, Any]:
        """Get backend configuration with fallback defaults"""
        backend_config = self.get("backend", {})

        defaults = {
            "server_host": os.getenv("AUTOBOT_BACKEND_HOST", "0.0.0.0"),  # nosec B104
            "server_port": int(os.getenv("AUTOBOT_BACKEND_PORT", "8001")),
            "api_endpoint": os.getenv(
                "AUTOBOT_BACKEND_API_ENDPOINT", "http://localhost:8001"
            ),
            "cors_origins": self._generate_cors_origins(),
        }

        return self._deep_merge(defaults, backend_config)

    def update_llm_model(self, model_name: str) -> None:
        """Update the selected LLM model using unified configuration"""
        logger.info(f"UNIFIED CONFIG: Updating selected model to '{model_name}'")

        # Update the unified structure
        self.set_nested("backend.llm.local.providers.ollama.selected_model", model_name)

        # Save the changes immediately
        self.save_settings()
        self._save_config_to_yaml()

        logger.info(f"Model updated to '{model_name}' in unified configuration")

    def _save_config_to_yaml(self) -> None:
        """Save configuration to config.yaml file (PROTECTED AGAINST PROMPTS)"""
        try:
            # Filter out prompts and legacy fields before saving
            import copy

            filtered_config = copy.deepcopy(self._config)

            if "prompts" in filtered_config:
                logger.info(
                    "YAML CONFIG SAVE: Removing prompts section - prompts are managed in prompts/ directory"
                )
                del filtered_config["prompts"]

            # Remove legacy fields that are now handled by backend.llm
            if "backend" in filtered_config:
                backend = filtered_config["backend"]

                # Only remove legacy fields if backend.llm is properly configured
                if (
                    backend.get("llm", {})
                    .get("local", {})
                    .get("providers", {})
                    .get("ollama", {})
                    .get("selected_model")
                ):
                    if "ollama_model" in backend:
                        logger.info(
                            "YAML CONFIG SAVE: Removing legacy ollama_model field - "
                            "now managed by backend.llm.local.providers.ollama.selected_model"
                        )
                        del backend["ollama_model"]
                    if "ollama_endpoint" in backend:
                        logger.info(
                            "YAML CONFIG SAVE: Removing legacy ollama_endpoint field - "
                            "now managed by backend.llm.local.providers.ollama.endpoint"
                        )
                        del backend["ollama_endpoint"]

            self.base_config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.base_config_file, "w", encoding="utf-8") as f:
                yaml.dump(filtered_config, f, default_flow_style=False, indent=2)
            logger.info(f"Configuration saved to {self.base_config_file}")
        except Exception as e:
            logger.error(f"Failed to save YAML configuration: {e}")
            raise

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

    def update_embedding_model(self, model_name: str) -> None:
        """Update the selected embedding model using unified configuration"""
        logger.info(f"UNIFIED CONFIG: Updating embedding model to '{model_name}'")

        # Update the unified structure
        self.set_nested(
            "backend.llm.embedding.providers.ollama.selected_model", model_name
        )

        # Save the changes immediately
        self.save_settings()
        self._save_config_to_yaml()

        logger.info(
            f"Embedding model updated to '{model_name}' in unified configuration"
        )


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
