"""
Centralized Configuration Management Module - UNIFIED VERSION

This module provides a unified configuration system using ConfigHelper:
- All configuration values come from config/complete.yaml  
- No more hardcoded values or os.getenv calls
- Single source of truth for all configuration
- Backward compatibility maintained through legacy variable exports

USAGE: 
  from src.config_helper import cfg
  ollama_host = cfg.get_host('ollama')
  backend_url = cfg.get_service_url('backend') 
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

from .utils.service_registry import get_service_url
from .config_helper import cfg

logger = logging.getLogger(__name__)

# UNIFIED CONFIGURATION: All values now come from ConfigHelper
# Legacy variables exported for backward compatibility

# Service Host IP Addresses - FROM CONFIG
OLLAMA_HOST_IP = cfg.get_host('ollama')
LM_STUDIO_HOST_IP = cfg.get_host('ollama')  # LM Studio uses same host as Ollama  
BACKEND_HOST_IP = cfg.get_host('backend')
FRONTEND_HOST_IP = cfg.get_host('frontend')
PLAYWRIGHT_HOST_IP = cfg.get_host('browser_service')
NPU_WORKER_HOST_IP = cfg.get_host('npu_worker')
AI_STACK_HOST_IP = cfg.get_host('ai_stack')
REDIS_HOST_IP = cfg.get_host('redis')
LOG_VIEWER_HOST_IP = cfg.get_host('redis')  # Seq logs run on same host as Redis

# Service Ports - FROM CONFIG
BACKEND_PORT = cfg.get_port('backend')
FRONTEND_PORT = cfg.get_port('frontend')
OLLAMA_PORT = cfg.get_port('ollama')
LM_STUDIO_PORT = 1234  # LM Studio default port
REDIS_PORT = cfg.get_port('redis')
PLAYWRIGHT_API_PORT = cfg.get_port('browser_service')
PLAYWRIGHT_VNC_PORT = cfg.get_port('vnc')
NPU_WORKER_PORT = cfg.get_port('npu_worker')
AI_STACK_PORT = cfg.get_port('ai_stack')
LOG_VIEWER_PORT = 5341  # Seq default port
FLUENTD_PORT = 24224  # Fluentd default port
CHROME_DEBUG_PORT = 9222  # Chrome debug default port
VNC_DISPLAY_PORT = cfg.get_port('vnc')
VNC_CONTAINER_PORT = 5901  # Container VNC port

# Protocols - FROM CONFIG
HTTP_PROTOCOL = "http"
WS_PROTOCOL = "ws"
REDIS_PROTOCOL = "redis"

# Service URLs - FROM CONFIG
API_BASE_URL = cfg.get_service_url('backend')
REDIS_URL = cfg.get_service_url('redis')
OLLAMA_URL = cfg.get_service_url('ollama')
API_TIMEOUT = cfg.get_timeout('http', 'standard') * 1000  # Convert to milliseconds

# AI Services
LM_STUDIO_URL = f"http://{LM_STUDIO_HOST_IP}:{LM_STUDIO_PORT}"

# WebSocket URLs
WS_BASE_URL = f"{WS_PROTOCOL}://{BACKEND_HOST_IP}:{BACKEND_PORT}/ws"

# Container Services
PLAYWRIGHT_API_URL = cfg.get_service_url('browser_service')
PLAYWRIGHT_VNC_URL = f"http://{PLAYWRIGHT_HOST_IP}:{PLAYWRIGHT_VNC_PORT}/vnc.html"
NPU_WORKER_URL = cfg.get_service_url('npu_worker')
AI_STACK_URL = cfg.get_service_url('ai_stack')

# Logging and Monitoring
LOG_VIEWER_URL = f"http://{LOG_VIEWER_HOST_IP}:{LOG_VIEWER_PORT}"
FLUENTD_ADDRESS = f"{LOG_VIEWER_HOST_IP}:{FLUENTD_PORT}"

# Development Settings
CHROME_DEBUG_PORT = 9222

# VNC Display Port - FROM CONFIG
VNC_DISPLAY_PORT = cfg.get_port('vnc')
VNC_CONTAINER_PORT = 5901


# Service Registry Integration
def get_service_urls():
    """Get service URLs using service registry with fallbacks"""
    try:
        urls = {
            "backend": get_service_url("backend"),
            "redis": get_service_url("redis"),
            "ai_stack": get_service_url("ai-stack"),
            "npu_worker": get_service_url("npu-worker"),
            "playwright_vnc": get_service_url("playwright-vnc"),
        }
        return urls
    except Exception as e:
        logging.warning(f"Service registry failed, using static URLs: {e}")
        return {
            "backend": API_BASE_URL,
            "redis": REDIS_URL,
            "ai_stack": AI_STACK_URL,
            "npu_worker": NPU_WORKER_URL,
            "playwright_vnc": PLAYWRIGHT_API_URL,
        }


FRONTEND_URL = os.getenv(
    "AUTOBOT_FRONTEND_URL", f"{HTTP_PROTOCOL}://{FRONTEND_HOST_IP}:{FRONTEND_PORT}"
)


def get_vnc_display_port():
    """
    Get the appropriate VNC display port based on environment

    Returns:
        int: VNC port number (5900 for host, 5901 for container by default)
    """
    # Check if running in Docker container
    if os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER"):
        return VNC_CONTAINER_PORT

    # Check if VNC service is already running on 5900 (typical Kali setup)
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.1)
        vnc_host = os.getenv("AUTOBOT_VNC_HOST", "127.0.0.1")
        result = sock.connect_ex((vnc_host, 5900))
        sock.close()

        if result == 0:
            # Port 5900 is in use (likely host VNC), use container port
            return VNC_CONTAINER_PORT
        else:
            # Port 5900 is free, use it
            return VNC_DISPLAY_PORT
    except Exception:
        # Default to host port if detection fails
        return VNC_DISPLAY_PORT


def get_vnc_direct_url():
    """
    Get the direct VNC connection URL with appropriate port

    Returns:
        str: VNC connection URL
    """
    port = get_vnc_display_port()
    host = os.getenv("AUTOBOT_VNC_HOST", "127.0.0.1")
    return f"vnc://{host}:{port}"


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
                logger.info(f"Applied environment override: {env_var} = {env_value}")

        # Merge environment overrides
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

        # Fallback to environment or config default
        return os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", "llama3.2:3b")

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

    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration with fallback defaults - UNIFIED VERSION WITH MULTI-MODEL SUPPORT"""

        # SINGLE SOURCE: Use backend.llm as the authoritative config
        backend_llm = self.get_nested("backend.llm", {})

        # Legacy migration: if backend.llm is empty but legacy fields exist, migrate them
        if not backend_llm:
            legacy_ollama_model = self.get_nested("backend.ollama_model")
            if legacy_ollama_model:
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
                                    f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}/api/generate",
                                ),
                                "host": os.getenv(
                                    "AUTOBOT_OLLAMA_HOST",
                                    f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}",
                                ),
                                "models": [],
                                "selected_model": legacy_ollama_model,
                            }
                        },
                    },
                }
                # Update the config with migrated structure
                self.set_nested("backend.llm", backend_llm)

        # Sensible defaults for the new structure
        defaults = {
            "provider_type": "local",
            "local": {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": os.getenv(
                            "AUTOBOT_OLLAMA_ENDPOINT",
                            f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}/api/generate",
                        ),
                        "host": os.getenv(
                            "AUTOBOT_OLLAMA_HOST",
                            f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}",
                        ),
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
                            f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}/api/embeddings",
                        ),
                        "host": os.getenv(
                            "AUTOBOT_EMBEDDING_HOST",
                            f"{HTTP_PROTOCOL}://{OLLAMA_HOST_IP}:{OLLAMA_PORT}",
                        ),
                        "models": [],
                        "selected_model": os.getenv(
                            "AUTOBOT_EMBEDDING_MODEL", "nomic-embed-text"
                        ),
                    }
                },
            },
        }

        # Return the unified config
        unified_config = self._deep_merge(defaults, backend_llm)

        # BACKWARD COMPATIBILITY: Also expose legacy format for old code
        legacy_format = {
            "default_llm": (
                f"ollama_{unified_config['local']['providers']['ollama']['selected_model']}"
                if unified_config.get("provider_type") == "local"
                else "ollama"
            ),
            "orchestrator_llm": os.getenv(
                "AUTOBOT_ORCHESTRATOR_LLM",
                unified_config["local"]["providers"]["ollama"]["selected_model"],
            ),
            "task_llm": os.getenv(
                "AUTOBOT_TASK_LLM",
                f"ollama_{unified_config['local']['providers']['ollama']['selected_model']}",
            ),
            "ollama": {
                "host": unified_config["local"]["providers"]["ollama"]["host"],
                "port": int(os.getenv("AUTOBOT_OLLAMA_PORT", "11434")),
                "model": unified_config["local"]["providers"]["ollama"][
                    "selected_model"
                ],
                "base_url": unified_config["local"]["providers"]["ollama"]["host"],
            },
        }

        return self._deep_merge(legacy_format, {"unified": unified_config})

    def get_task_specific_model(self, task_type: str = "default") -> str:
        """Get model for specific task types to optimize performance and resource usage.

        Args:
            task_type: Agent type (orchestrator, chat, system_commands, rag, knowledge_retrieval, research)

        Returns:
            Model name for the specified agent
        """
        # Multi-agent model configuration - configurable via environment or LLM detection
        agent_models = self.get_nested(
            "llm.agent_models",
            {
                # Core Orchestration - use available model for flexible reasoning
                "orchestrator": os.getenv("AUTOBOT_ORCHESTRATOR_MODEL", "llama3.2:3b"),
                "default": os.getenv("AUTOBOT_DEFAULT_AGENT_MODEL", "llama3.2:3b"),
                # Specialized Agents - optimized for task complexity
                "chat": os.getenv("AUTOBOT_CHAT_MODEL", "llama3.2:1b"),
                "system_commands": os.getenv("AUTOBOT_SYSTEM_CMD_MODEL", "llama3.2:1b"),
                "rag": os.getenv("AUTOBOT_RAG_MODEL", "dolphin-llama3:8b"),
                "knowledge_retrieval": os.getenv(
                    "AUTOBOT_KNOWLEDGE_MODEL", "llama3.2:1b"
                ),
                "research": os.getenv("AUTOBOT_RESEARCH_MODEL", "dolphin-llama3:8b"),
                # Legacy compatibility - use available models
                "search": os.getenv("AUTOBOT_SEARCH_MODEL", "llama3.2:1b"),
                "code": os.getenv("AUTOBOT_CODE_MODEL", "llama3.2:1b"),
                "analysis": os.getenv("AUTOBOT_ANALYSIS_MODEL", "dolphin-llama3:8b"),
                "planning": os.getenv("AUTOBOT_PLANNING_MODEL", "dolphin-llama3:8b"),
                # Fallback models for when uncensored is not needed
                "orchestrator_fallback": os.getenv(
                    "AUTOBOT_ORCHESTRATOR_FALLBACK_MODEL", "llama3.2:3b"
                ),
                "chat_fallback": os.getenv(
                    "AUTOBOT_CHAT_FALLBACK_MODEL", "llama3.2:1b"
                ),
                "fallback": os.getenv("AUTOBOT_FALLBACK_MODEL", "dolphin-llama3:8b"),
            },
        )

        # Allow environment override for specific tasks
        env_key = f"AUTOBOT_MODEL_{task_type.upper()}"
        env_model = os.getenv(env_key)
        if env_model:
            logger.info(f"Using environment override for {task_type}: {env_model}")
            return env_model

        # Get from config with fallback
        config_key = f"backend.llm.task_models.{task_type}"
        configured_model = self.get_nested(config_key)
        if configured_model:
            return configured_model

        # Use agent-specific default or fall back to general default
        return agent_models.get(task_type, agent_models["default"])

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
            # Import here to avoid circular dependency
            from src.hardware_acceleration import get_hardware_acceleration_manager

            hw_manager = get_hardware_acceleration_manager()
            device_config = hw_manager.get_ollama_device_config(task_type)

            # Add configuration override support
            base_config = {
                "hardware_acceleration": {
                    "enabled": os.getenv(
                        "AUTOBOT_HARDWARE_ACCELERATION", "true"
                    ).lower()
                    == "true",
                    "priority_order": ["npu", "gpu", "cpu"],
                    "device_assignments": device_config,
                    "cpu_reserved_cores": int(
                        os.getenv("AUTOBOT_CPU_RESERVED_CORES", "2")
                    ),
                    "memory_optimization": os.getenv(
                        "AUTOBOT_MEMORY_OPTIMIZATION", "enabled"
                    )
                    == "enabled",
                }
            }

            # Allow per-task overrides
            task_override_key = f"AUTOBOT_DEVICE_{task_type.upper()}"
            if os.getenv(task_override_key):
                base_config["hardware_acceleration"]["device_assignments"][
                    "device_type"
                ] = os.getenv(task_override_key)

            return base_config

        except Exception as e:
            logger.warning(f"Failed to get hardware acceleration config: {e}")
            # Fallback to CPU-only configuration
            return {
                "hardware_acceleration": {
                    "enabled": False,
                    "device_type": "cpu",
                    "fallback_reason": str(e),
                }
            }

    def get_ollama_runtime_config(self, task_type: str = "default") -> Dict[str, Any]:
        """Get Ollama runtime configuration with hardware optimization.

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

        # Task-specific optimizations
        task_optimizations = {
            "chat": {
                "temperature": 0.8,
                "num_predict": 256,  # Shorter responses for chat
                "top_p": 0.9,
            },
            "system_commands": {
                "temperature": 0.3,  # More deterministic for commands
                "num_predict": 128,
                "top_p": 0.7,
            },
            "knowledge_retrieval": {
                "temperature": 0.4,  # Factual responses
                "num_predict": 200,
                "top_p": 0.8,
            },
            "rag": {
                "temperature": 0.6,  # Balanced for synthesis
                "num_predict": 512,
                "top_p": 0.85,
            },
            "research": {
                "temperature": 0.7,  # Creative for research
                "num_predict": 600,
                "top_p": 0.9,
            },
            "orchestrator": {
                "temperature": 0.5,  # Balanced for coordination
                "num_predict": 400,
                "top_p": 0.8,
            },
        }

        # Apply task-specific optimizations
        if task_type in task_optimizations:
            ollama_config.update(task_optimizations[task_type])

        # Environment variable overrides
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
                        ollama_config[config_key] = float(env_value)
                    elif config_key == "num_predict":
                        ollama_config[config_key] = int(env_value)
                except ValueError:
                    logger.warning(f"Invalid value for {env_var}: {env_value}")

        return ollama_config

    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration with fallback defaults"""
        redis_config = self.get_nested("memory.redis", {})

        defaults = {
            "enabled": os.getenv("AUTOBOT_REDIS_ENABLED", "true").lower() == "true",
            "host": os.getenv("AUTOBOT_REDIS_HOST", cfg.get_host('redis')),
            "port": int(os.getenv("AUTOBOT_REDIS_PORT", str(cfg.get_port('redis')))),
            "db": int(os.getenv("AUTOBOT_REDIS_DB", "1")),
            "channels": {
                "command_approval_request": "command_approval_request",
                "command_approval_response_prefix": "command_approval_",
                "worker_capabilities": "worker_capabilities",
            },
        }

        return self._deep_merge(defaults, redis_config)

    def get_backend_config(self) -> Dict[str, Any]:
        """Get backend configuration with fallback defaults"""
        backend_config = self.get("backend", {})

        defaults = {
            "server_host": os.getenv("AUTOBOT_BACKEND_HOST", "0.0.0.0"),
            "server_port": int(os.getenv("AUTOBOT_BACKEND_PORT", "8001")),
            "api_endpoint": os.getenv(
                "AUTOBOT_BACKEND_API_ENDPOINT",
                f"http://localhost:{os.getenv('AUTOBOT_BACKEND_PORT', '8001')}",
            ),
            "cors_origins": self._get_cors_origins(),
        }

        return self._deep_merge(defaults, backend_config)

    def _get_cors_origins(self):
        """Get CORS origins from environment or defaults"""
        cors_origins_env = os.getenv("AUTOBOT_CORS_ORIGINS")
        if cors_origins_env:
            return cors_origins_env.split(",")

        # Dynamic default CORS origins based on frontend configuration
        frontend_host = os.getenv("AUTOBOT_FRONTEND_HOST", "127.0.0.1")
        frontend_port = os.getenv("AUTOBOT_FRONTEND_PORT", "5173")

        return [
            f"http://{frontend_host}:{frontend_port}",
            f"http://localhost:{frontend_port}",
            f"http://127.0.0.1:{frontend_port}",
        ]

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
                            "YAML CONFIG SAVE: Removing legacy ollama_model field - now managed by backend.llm.local.providers.ollama.selected_model"
                        )
                        del backend["ollama_model"]
                    if "ollama_endpoint" in backend:
                        logger.info(
                            "YAML CONFIG SAVE: Removing legacy ollama_endpoint field - now managed by backend.llm.local.providers.ollama.endpoint"
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

    def get_ollama_url(self) -> str:
        """Get the Ollama service URL from configuration, with proper fallbacks"""
        # First check environment variable
        env_url = os.getenv("AUTOBOT_OLLAMA_URL")
        if env_url:
            return env_url

        # Then check configuration
        # Try the endpoint first
        endpoint = self.get_nested("backend.llm.local.providers.ollama.endpoint")
        if endpoint:
            return endpoint.replace("/api/generate", "")  # Get base URL

        # Then try host
        host = self.get_nested("backend.llm.local.providers.ollama.host")
        if host:
            return host

        # Finally fall back to configured host
        host = os.getenv("AUTOBOT_OLLAMA_HOST", "127.0.0.1")
        port = os.getenv("AUTOBOT_OLLAMA_PORT", "11434")
        return f"http://{host}:{port}"

    def get_redis_url(self) -> str:
        """Get the Redis service URL from configuration"""
        # First check environment variable
        env_url = os.getenv("AUTOBOT_REDIS_URL")
        if env_url:
            return env_url

        # Then check configuration
        redis_host = os.getenv('AUTOBOT_REDIS_HOST')
        redis_port = os.getenv('AUTOBOT_REDIS_PORT')
        if not redis_host or not redis_port:
            raise ValueError('Redis configuration missing: AUTOBOT_REDIS_HOST and AUTOBOT_REDIS_PORT environment variables must be set')

        host = self.get_nested("memory.redis.host", redis_host)
        port = self.get_nested("memory.redis.port", int(redis_port))

        return f"redis://{host}:{port}"


# Global configuration instance
config = ConfigManager()

# Alias for backward compatibility and consistent naming
global_config_manager = config


def log_service_configuration():
    """Log current service configuration for debugging"""
    logger = logging.getLogger(__name__)
    try:
        logger.info(f"OLLAMA_HOST_IP: {OLLAMA_HOST_IP}")
        logger.info(f"BACKEND_HOST_IP: {BACKEND_HOST_IP}")
        logger.info(f"REDIS_HOST_IP: {REDIS_HOST_IP}")
        logger.info(f"Service URLs loaded: {config._config.get('services', {}).keys() if hasattr(config, '_config') and config._config else 'None'}")
    except Exception as e:
        logger.warning(f"Error logging service configuration: {e}")


# Log service configuration on startup for debugging
try:
    log_service_configuration()
except Exception as e:
    logging.getLogger(__name__).warning(f"Could not log service configuration: {e}")

# NOTE: After config is loaded, update the legacy variables with proper values
# This ensures backward compatibility while using the configuration system
try:
    # Update OLLAMA_URL to use the configuration
    _ollama_url = config.get_ollama_url()
    if _ollama_url != OLLAMA_URL:
        OLLAMA_URL = _ollama_url
        logger.info(f"Updated OLLAMA_URL from config: {OLLAMA_URL}")
except Exception as e:
    logger.warning(f"Failed to update OLLAMA_URL from config: {e}")


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
