"""
Configuration Helper Module
Provides easy access to all configuration values from the unified config.
NO HARDCODED VALUES ALLOWED - Everything comes from configuration.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigHelper:
    """
    Helper class to access configuration values easily.
    Usage:
        from src.config_helper import cfg

        # Access values using dot notation
        backend_host = cfg.get('infrastructure.hosts.backend')
        redis_port = cfg.get('infrastructure.ports.redis')
        timeout = cfg.get('timeouts.llm.default')

        # Access hardcoded values with environment overrides
        log_path = cfg.get_hardcoded_value('file_paths', 'logs')
        api_url = cfg.get_hardcoded_value('urls', 'api_base')
    """

    def __init__(self):
        self._config = {}
        self._environment_configs = {}  # Cache for environment configurations
        self._load_complete_config()

    def _load_complete_config(self):
        """Load the complete configuration file"""
        config_path = Path(__file__).parent.parent / "config" / "complete.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Complete configuration not found: {config_path}")

        try:
            with open(config_path, "r") as f:
                self._config = yaml.safe_load(f)
            logger.info("Complete configuration loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load complete configuration: {e}")
            raise

    def get(self, path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.

        Args:
            path: Dot-separated path to config value (e.g., 'infrastructure.hosts.backend')
            default: Default value if path not found

        Returns:
            Configuration value or default
        """
        keys = path.split(".")
        value = self._config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        # Apply environment variable substitution if string contains ${...}
        if isinstance(value, str) and "${" in value:
            value = self._substitute_variables(value)

        return value

    def _substitute_variables(self, value: str) -> str:
        """Substitute ${path} references with actual values"""
        import re

        from src.constants import NetworkConstants, ServiceURLs

        def replace_var(match):
            var_path = match.group(1)
            replacement = self.get(var_path)
            return str(replacement) if replacement is not None else match.group(0)

        # Replace ${path.to.value} patterns
        pattern = r"\$\{([^}]+)\}"
        return re.sub(pattern, replace_var, value)

    def get_hardcoded_value(self, category: str, key: str, env: str = None) -> str:
        """
        Get hardcoded value with environment-specific overrides.

        This method centralizes access to previously hardcoded values like file paths and URLs,
        allowing them to be overridden based on the deployment environment.

        Args:
            category: Value category ('file_paths', 'urls', 'database_connections', etc.)
            key: Specific value key within the category
            env: Environment name (defaults to auto-detection)

        Returns:
            Configuration value with environment overrides applied

        Examples:
            log_dir = cfg.get_hardcoded_value('file_paths', 'logs')
            api_url = cfg.get_hardcoded_value('urls', 'api_base')
        """
        try:
            current_env = env or self._detect_environment()
            env_config = self._load_environment_config(current_env)

            # Try environment-specific override first
            override_path = f"hardcoded_overrides.{category}.{key}"
            override_value = self._get_nested_value(env_config, override_path)

            if override_value is not None:
                logger.debug(
                    f"Using environment override for {category}.{key}: {override_value}"
                )
                return str(override_value)

            # Fall back to base configuration
            base_path = f"{category}.{key}"
            base_value = self.get(base_path)

            if base_value is not None:
                logger.debug(f"Using base config for {category}.{key}: {base_value}")
                return str(base_value)

            # Final fallback based on category defaults
            default_value = self._get_category_default(category, key)
            logger.warning(
                f"No configuration found for {category}.{key}, using default: {default_value}"
            )
            return default_value

        except Exception as e:
            logger.error(f"Error retrieving hardcoded value {category}.{key}: {e}")
            # Return a safe default to prevent application failure
            return self._get_category_default(category, key)

    def _load_environment_config(self, env: str) -> Dict[str, Any]:
        """
        Load environment-specific configuration with caching.

        Args:
            env: Environment name (development, staging, production)

        Returns:
            Environment configuration dictionary
        """
        # Return cached config if available
        if env in self._environment_configs:
            return self._environment_configs[env]

        env_file = (
            Path(__file__).parent.parent / "config" / "environments" / f"{env}.yaml"
        )

        try:
            if env_file.exists():
                with open(env_file, "r") as f:
                    env_config = yaml.safe_load(f) or {}
                logger.info(f"Loaded environment configuration for {env}")
            else:
                logger.info(
                    f"No environment config found for {env}, using base configuration"
                )
                env_config = {}

            # Cache the configuration
            self._environment_configs[env] = env_config
            return env_config

        except Exception as e:
            logger.error(f"Failed to load environment config for {env}: {e}")
            self._environment_configs[env] = {}
            return {}

    def _detect_environment(self) -> str:
        """
        Detect the current deployment environment.

        Returns:
            Environment name (development, staging, production)
        """
        # Check environment variable first
        env = os.getenv("AUTOBOT_ENVIRONMENT")
        if env:
            return env.lower()

        # Check for common environment indicators
        if os.getenv("NODE_ENV") == "production":
            return "production"
        elif os.getenv("NODE_ENV") == "staging":
            return "staging"
        elif os.getenv("DOCKER_CONTAINER"):
            return "production"

        # Default to development
        return "development"

    def _get_nested_value(self, config: Dict[str, Any], path: str) -> Any:
        """
        Get nested value from configuration using dot notation.

        Args:
            config: Configuration dictionary
            path: Dot-separated path to value

        Returns:
            Value if found, None otherwise
        """
        keys = path.split(".")
        value = config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None

        return value

    def _get_category_default(self, category: str, key: str) -> str:
        """
        Get safe default value for a category/key combination.

        Args:
            category: Value category
            key: Value key

        Returns:
            Safe default value
        """
        defaults = {
            "file_paths": {
                "logs": "logs",
                "data": "data",
                "temp": "temp",
                "cache": "cache",
                "config": "config",
                "backup": "backup",
            },
            "urls": {
                "api_base": ServiceURLs.BACKEND_LOCAL,
                "frontend_base": ServiceURLs.FRONTEND_LOCAL,
                "redis_url": "redis://localhost:6379",
                "ollama_url": ServiceURLs.OLLAMA_LOCAL,
            },
            "database_connections": {
                "redis_host": "localhost",
                "redis_port": str(NetworkConstants.REDIS_PORT),
            },
        }

        category_defaults = defaults.get(category, {})
        return category_defaults.get(key, f"{category}_{key}_default")

    def get_environment_info(self) -> Dict[str, Any]:
        """
        Get information about the current environment configuration.

        Returns:
            Dictionary with environment details
        """
        current_env = self._detect_environment()
        env_config = self._load_environment_config(current_env)

        return {
            "current_environment": current_env,
            "config_file_exists": len(env_config) > 0,
            "available_overrides": list(env_config.keys()) if env_config else [],
            "environment_variable": os.getenv("AUTOBOT_ENVIRONMENT"),
            "node_env": os.getenv("NODE_ENV"),
            "docker_container": bool(os.getenv("DOCKER_CONTAINER")),
        }

    def get_service_url(self, service: str, endpoint: str = None) -> str:
        """
        Get service URL with optional endpoint.

        Args:
            service: Service name (e.g., 'backend', 'frontend', 'redis')
            endpoint: Optional endpoint path

        Returns:
            Complete service URL
        """
        base_url = self.get(f"services.{service}.base_url")
        if not base_url:
            base_url = self.get(f"services.{service}.url")

        if endpoint:
            return f"{base_url}{endpoint}"
        return base_url

    def get_redis_config(self) -> Dict[str, Any]:
        """Get complete Redis configuration"""
        return {
            "host": self.get("redis.host"),
            "port": self.get("redis.port"),
            "password": self.get("redis.password"),
            "db": self.get("redis.databases.main", 0),
            **self.get("redis.connection", {}),
        }

    def get_timeout(self, category: str, type: str = "default") -> float:
        """
        Get timeout value for specific category and type.

        Args:
            category: Timeout category (e.g., 'llm', 'http', 'agent')
            type: Timeout type (e.g., 'default', 'quick', 'long')

        Returns:
            Timeout value in seconds
        """
        return self.get(f"timeouts.{category}.{type}", 60)

    def get_path(self, category: str, name: str = None) -> str:
        """
        Get file or directory path.

        Args:
            category: Path category (e.g., 'logs', 'data', 'config')
            name: Specific path name

        Returns:
            File or directory path
        """
        if name:
            return self.get(f"paths.{category}.{name}")
        return self.get(f"paths.{category}.directory")

    def get_limit(self, category: str, name: str) -> Any:
        """
        Get system limit value.

        Args:
            category: Limit category (e.g., 'redis', 'api', 'process')
            name: Limit name

        Returns:
            Limit value
        """
        return self.get(f"limits.{category}.{name}")

    def is_feature_enabled(self, feature: str) -> bool:
        """
        Check if a feature flag is enabled.

        Args:
            feature: Feature name

        Returns:
            True if feature is enabled
        """
        return self.get(f"features.{feature}", False)

    def get_retry_config(self, service: str = None) -> Dict[str, Any]:
        """
        Get retry configuration for a service.

        Args:
            service: Optional service name for specific retry config

        Returns:
            Retry configuration dictionary
        """
        if service:
            service_retry = self.get(f"retry.{service}", {})
            if service_retry:
                return service_retry

        return {
            "attempts": self.get("retry.default_attempts", 3),
            "delay": self.get("retry.default_delay", 1),
            "max_attempts": self.get("retry.max_attempts", 5),
            "exponential_backoff": self.get("retry.exponential_backoff", True),
            "backoff_factor": self.get("retry.backoff_factor", 2),
            "max_delay": self.get("retry.max_delay", 60),
        }

    def get_host(self, service: str) -> str:
        """Get host IP for a service"""
        return self.get(f"infrastructure.hosts.{service}", "127.0.0.1")

    def get_port(self, service: str) -> int:
        """Get port for a service"""
        return self.get(f"infrastructure.ports.{service}", 8000)

    def reload(self):
        """Reload configuration from file"""
        self._environment_configs.clear()  # Clear environment config cache
        self._load_complete_config()


# Create singleton instance
cfg = ConfigHelper()


# Convenience functions for common access patterns
def get_backend_url(endpoint: str = None) -> str:
    """Get backend service URL with optional endpoint"""
    return cfg.get_service_url("backend", endpoint)


def get_frontend_url(endpoint: str = None) -> str:
    """Get frontend service URL with optional endpoint"""
    return cfg.get_service_url("frontend", endpoint)


def get_redis_url() -> str:
    """Get Redis connection URL"""
    return cfg.get_service_url("redis")


def get_ollama_url(endpoint: str = None) -> str:
    """Get Ollama service URL with optional endpoint"""
    return cfg.get_service_url("ollama", endpoint)


def get_timeout(category: str = "http", type: str = "standard") -> float:
    """Get timeout value"""
    return cfg.get_timeout(category, type)


def get_log_path(name: str = "system") -> str:
    """Get log file path"""
    return cfg.get_path("logs", name)


def get_data_path(name: str = None) -> str:
    """Get data directory or file path"""
    return cfg.get_path("data", name)


# New convenience functions for hardcoded values
def get_hardcoded_file_path(key: str, env: str = None) -> str:
    """Get hardcoded file path with environment overrides"""
    return cfg.get_hardcoded_value("file_paths", key, env)


def get_hardcoded_url(key: str, env: str = None) -> str:
    """Get hardcoded URL with environment overrides"""
    return cfg.get_hardcoded_value("urls", key, env)


# Export commonly used values as constants (computed at import time)
# These are provided for convenience but cfg.get() should be preferred

# Infrastructure
BACKEND_HOST = cfg.get_host("backend")
BACKEND_PORT = cfg.get_port("backend")
FRONTEND_HOST = cfg.get_host("frontend")
FRONTEND_PORT = cfg.get_port("frontend")
REDIS_HOST = cfg.get_host("redis")
REDIS_PORT = cfg.get_port("redis")
OLLAMA_HOST = cfg.get_host("ollama")
OLLAMA_PORT = cfg.get_port("ollama")

# URLs
BACKEND_URL = get_backend_url()
FRONTEND_URL = get_frontend_url()
REDIS_URL = get_redis_url()
OLLAMA_URL = get_ollama_url()

# Timeouts
DEFAULT_TIMEOUT = get_timeout("http", "standard")
LLM_TIMEOUT = get_timeout("llm", "default")
COMMAND_TIMEOUT = get_timeout("commands", "standard")

# Paths
LOG_DIR = cfg.get_path("logs")
DATA_DIR = cfg.get_path("data")
CONFIG_DIR = cfg.get_path("config")
