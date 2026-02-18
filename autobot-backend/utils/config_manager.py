"""
Centralized Configuration Manager for AutoBot
Standardizes configuration access across all components
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

# Import SSOT for Ollama defaults
try:
    from autobot_shared.ssot_config import get_config as get_ssot_config

    _SSOT_AVAILABLE = True
except ImportError:
    _SSOT_AVAILABLE = False


def _get_ollama_base_url() -> str:
    """Get Ollama base URL from SSOT config. Issue #694."""
    if _SSOT_AVAILABLE:
        try:
            return get_ssot_config().ollama_url
        except Exception:
            pass  # nosec B110 - intentional fallback to env vars
    # Fallback to environment variable, then default
    return os.getenv("AUTOBOT_OLLAMA_ENDPOINT", "http://127.0.0.1:11434")


logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Centralized configuration manager that standardizes config access
    """

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "config/config.yaml"
        self._config_cache = {}
        self._load_config()

    def _load_config(self):
        """Load configuration from YAML file with fallback defaults"""
        # Always start with defaults
        self._config_cache = self._get_default_config()

        try:
            config_path = Path(self.config_file)

            if config_path.exists():
                with open(config_path, "r") as f:
                    file_config = yaml.safe_load(f) or {}
                # Merge file config with defaults
                self._merge_configs(self._config_cache, file_config)
                logger.info(f"Configuration loaded from {config_path}")
            else:
                logger.info(
                    f"Configuration file not found: {config_path}. " "Using defaults."
                )

        except Exception as e:
            logger.error(f"Failed to load configuration file: {e}. " "Using defaults.")

    def _merge_configs(
        self, base_config: Dict[str, Any], override_config: Dict[str, Any]
    ):
        """Recursively merge override config into base config"""
        for key, value in override_config.items():
            if (
                key in base_config
                and isinstance(base_config[key], dict)
                and isinstance(value, dict)
            ):
                self._merge_configs(base_config[key], value)
            else:
                base_config[key] = value

    def _get_llm_defaults(self) -> Dict[str, Any]:
        """
        Get default LLM configuration values.

        Returns LLM provider settings for orchestrator and task processing.
        Issue #620.
        """
        return {
            "orchestrator_llm": "ollama",
            "task_llm": "ollama",
            "ollama": {
                "model": "llama3.2",
                "base_url": _get_ollama_base_url(),
                "timeout": 30,
                "port": 11434,
            },
            "openai": {"api_key": ""},
        }

    def _get_infrastructure_defaults(self) -> Dict[str, Any]:
        """
        Get default infrastructure configuration values.

        Returns deployment, data storage, and Redis connection settings.
        Issue #620.
        """
        return {
            "deployment": {"mode": "local", "host": "localhost", "port": 8001},
            "data": {
                "reliability_stats_file": "data/reliability_stats.json",
                "long_term_db_path": "data/agent_memory.db",
                "chat_history_file": "data/chat_history.json",
                "chats_directory": "data/chats",
            },
            "redis": {"host": "localhost", "port": 6379, "db": 0, "password": None},
        }

    def _get_multimodal_defaults(self) -> Dict[str, Any]:
        """
        Get default multimodal AI configuration values.

        Returns vision, voice, and context processing settings.
        Issue #620.
        """
        return {
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
        }

    def _get_hardware_defaults(self) -> Dict[str, Any]:
        """
        Get default hardware acceleration configuration values.

        Returns NPU, GPU, and CPU acceleration settings.
        Issue #620.
        """
        return {
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
        }

    def _get_system_defaults(self) -> Dict[str, Any]:
        """
        Get default system and network configuration values.

        Returns system environment, network, memory, and task transport settings.
        Issue #620.
        """
        return {
            "system": {
                "environment": {"DISPLAY": ":0", "USER": "unknown", "SHELL": "unknown"},
                "desktop_streaming": {
                    "default_resolution": "1024x768",
                    "default_depth": 24,
                    "max_sessions": 10,
                },
            },
            "network": {"share": {"username": None, "password": None}},
            "memory": {
                "redis": {
                    "enabled": True,
                    "host": "localhost",
                    "port": 6379,
                    "db": 0,
                    "password": None,
                }
            },
            "task_transport": {
                "type": "redis",
                "redis": {"host": "localhost", "port": 6379, "password": None, "db": 0},
            },
        }

    def _get_security_logging_defaults(self) -> Dict[str, Any]:
        """
        Get default security and logging configuration values.

        Returns sandboxing, command filtering, and log rotation settings.
        Issue #620.
        """
        return {
            "security": {
                "enable_sandboxing": True,
                "allowed_commands": [],
                "blocked_commands": ["rm -rf", "format", "delete"],
                "secrets_key": None,
                "audit_log_file": "data/audit.log",
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "file_handlers": {
                    "backend": "logs/autobot_backend.log",
                    "frontend": "logs/frontend.log",
                    "llm": "logs/llm_usage.log",
                    "debug": "logs/debug.log",
                    "audit": "logs/audit.log",
                },
                "rotation": {"max_bytes": 10485760, "backup_count": 5},  # 10MB
            },
        }

    def _get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration values.

        Assembles complete default configuration from categorized helper methods.
        Issue #620.
        """
        config = {"llm": self._get_llm_defaults()}

        # Add infrastructure defaults
        config.update(self._get_infrastructure_defaults())

        # Add multimodal defaults
        config["multimodal"] = self._get_multimodal_defaults()

        # Add hardware defaults
        config.update(self._get_hardware_defaults())

        # Add system defaults
        config.update(self._get_system_defaults())

        # Add security and logging defaults
        config.update(self._get_security_logging_defaults())

        return config

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-separated key path

        Args:
            key: Dot-separated key path (e.g., 'llm.ollama.model')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        try:
            value = self._config_cache
            for part in key.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return self._get_env_var(key, default)

            # If config value is empty string or None, try environment fallback
            if value in ("", None):
                env_value = self._get_env_var(key, None)
                if env_value is not None:
                    return env_value

            return value if value is not None else default
        except Exception:
            return self._get_env_var(key, default)

    def _get_env_var(self, key: str, default: Any = None) -> Any:
        """
        Get value from environment variable as fallback

        Args:
            key: Configuration key (converted to env var format)
            default: Default value

        Returns:
            Environment variable value or default
        """
        # Convert dot notation to env var format
        env_key = key.upper().replace(".", "_")

        # Try common AutoBot prefixes
        for prefix in ["AUTOBOT_", "AB_", ""]:
            full_key = f"{prefix}{env_key}"
            if full_key in os.environ:
                value = os.environ[full_key]
                # Try to parse common types
                return self._parse_env_value(value)

        return default

    def _parse_env_value(self, value: str) -> Union[str, int, float, bool, list]:
        """Parse environment variable value to appropriate type"""
        if value.lower() in ("true", "false"):
            return value.lower() == "true"

        if value.isdigit():
            return int(value)

        try:
            return float(value)
        except ValueError:
            pass

        # Check for comma-separated lists
        if "," in value:
            return [item.strip() for item in value.split(",")]

        return value

    def set(self, key: str, value: Any):
        """
        Set configuration value by dot-separated key path

        Args:
            key: Dot-separated key path
            value: Value to set
        """
        keys = key.split(".")
        config = self._config_cache

        # Navigate to parent
        for part in keys[:-1]:
            if part not in config:
                config[part] = {}
            config = config[part]

        # Set value
        config[keys[-1]] = value

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get entire configuration section

        Args:
            section: Section name (e.g., 'llm', 'multimodal')

        Returns:
            Configuration section dictionary
        """
        return self.get(section, {})

    def reload(self):
        """Reload configuration from file"""
        self._load_config()

    def save(self, file_path: Optional[str] = None):
        """
        Save current configuration to file

        Args:
            file_path: Optional path to save to (defaults to current file)
        """
        save_path = Path(file_path or self.config_file)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(save_path, "w") as f:
                yaml.dump(self._config_cache, f, default_flow_style=False, indent=2)
            logger.info(f"Configuration saved to {save_path}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")

    def validate_config(self) -> List[str]:
        """
        Validate configuration and return list of issues

        Returns:
            List of validation issues (empty if valid)
        """
        issues = []

        # Check required sections
        required_sections = ["llm", "deployment", "redis"]
        for section in required_sections:
            if section not in self._config_cache:
                issues.append(f"Missing required section: {section}")

        # Validate LLM configuration
        llm_config = self.get_section("llm")
        if llm_config:
            if "orchestrator_llm" not in llm_config:
                issues.append("Missing llm.orchestrator_llm")
            if "task_llm" not in llm_config:
                issues.append("Missing llm.task_llm")

        # Validate deployment configuration
        deploy_config = self.get_section("deployment")
        if deploy_config:
            if "mode" not in deploy_config:
                issues.append("Missing deployment.mode")
            if "port" not in deploy_config:
                issues.append("Missing deployment.port")

        # Validate Redis configuration
        redis_config = self.get_section("redis")
        if redis_config:
            if "host" not in redis_config:
                issues.append("Missing redis.host")
            if "port" not in redis_config:
                issues.append("Missing redis.port")

        return issues

    def get_multimodal_config(self) -> Dict[str, Any]:
        """Get multi-modal AI configuration"""
        return self.get_section("multimodal")

    def get_npu_config(self) -> Dict[str, Any]:
        """Get NPU configuration"""
        return self.get_section("npu")

    def is_feature_enabled(self, feature: str) -> bool:
        """
        Check if a feature is enabled

        Args:
            feature: Feature name (e.g., 'multimodal.vision', 'npu.enabled')

        Returns:
            True if feature is enabled
        """
        return bool(self.get(f"{feature}.enabled", False))

    def get_all_config(self) -> Dict[str, Any]:
        """Get complete configuration dictionary"""
        return self._config_cache.copy()


# Singleton instance for global access
config_manager = ConfigManager()


# Convenience functions for common operations
def get_config(key: str, default: Any = None) -> Any:
    """Get configuration value"""
    return config_manager.get(key, default)


def get_config_section(section: str) -> Dict[str, Any]:
    """Get configuration section"""
    return config_manager.get_section(section)


def is_feature_enabled(feature: str) -> bool:
    """Check if feature is enabled"""
    return config_manager.is_feature_enabled(feature)


def reload_config():
    """Reload configuration from file"""
    config_manager.reload()


def validate_config() -> List[str]:
    """Validate configuration and return issues"""
    return config_manager.validate_config()


# Backward compatibility - create instance that mimics src.config
class Config:
    """Backward compatibility wrapper for existing config usage"""

    def __init__(self):
        self._manager = config_manager

    @property
    def config(self) -> Dict[str, Any]:
        """Get complete configuration"""
        return self._manager.get_all_config()

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._manager.get(key, default)


# Global config instance for backward compatibility
config = Config()
