# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Configuration Module (#2313).

Contains configuration classes for Redis connection management:
- RedisConfig: Database configuration dataclass
- RedisConfigLoader: Multi-source configuration loader
- PoolConfig: Connection pool configuration

Extracted from redis_client.py (Issue #381).
Moved from autobot-backend/utils/ to autobot_shared/ (Issue #2313).

Backend-specific constant imports (REDIS_CONFIG, RetryConfig) have been replaced
with their literal values so this module has no backend dependencies.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict

import yaml

from autobot_shared.network_constants import NetworkConstants

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis connection defaults (previously from constants.redis_constants.REDIS_CONFIG)
# ---------------------------------------------------------------------------
_SOCKET_TIMEOUT = 5
_MAX_CONNECTIONS_POOL = 20
_MIN_CONNECTIONS_POOL = 2
_HEALTH_CHECK_INTERVAL = 30
_RETRY_ON_TIMEOUT = True
_CIRCUIT_BREAKER_THRESHOLD = 5
_CIRCUIT_BREAKER_TIMEOUT = 60

# Retry defaults (previously from constants.threshold_constants.RetryConfig)
_DEFAULT_RETRIES = 3
_BACKOFF_BASE = 2.0


@dataclass
class RedisConfig:
    """
    Redis database configuration.

    Holds all configuration options for a Redis database connection,
    including network settings, pooling options, retry configuration, and TLS.
    """

    name: str
    db: int
    host: str = NetworkConstants.REDIS_VM_IP
    port: int = NetworkConstants.REDIS_PORT
    password: str | None = None
    decode_responses: bool = True
    max_connections: int = _MAX_CONNECTIONS_POOL
    socket_timeout: float = float(_SOCKET_TIMEOUT)
    socket_connect_timeout: float = float(_SOCKET_TIMEOUT)
    socket_keepalive: bool = True
    socket_keepalive_options: Dict[int, int] | None = None
    health_check_interval: int = _HEALTH_CHECK_INTERVAL
    retry_on_timeout: bool = _RETRY_ON_TIMEOUT
    max_retries: int = _DEFAULT_RETRIES
    description: str = ""
    # TLS configuration
    ssl: bool = False
    ssl_ca_certs: str | None = None
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    ssl_cert_reqs: str = "required"

    def __post_init__(self) -> None:
        """Auto-load password and TLS settings from environment if not provided."""
        if self.password is None:
            # Try REDIS_PASSWORD first, then AUTOBOT_REDIS_PASSWORD
            self.password = os.getenv("REDIS_PASSWORD") or os.getenv("AUTOBOT_REDIS_PASSWORD")
        # Auto-load TLS settings from SSOT config - Issue #164
        if os.getenv("AUTOBOT_REDIS_TLS_ENABLED", "").lower() == "true":
            self.ssl = True
            self.port = int(os.getenv("AUTOBOT_REDIS_TLS_PORT", "6380"))

            # Check for explicit cert paths first (set by SLM enable-tls playbook)
            self.ssl_ca_certs = os.getenv("AUTOBOT_TLS_CA_PATH")
            self.ssl_certfile = os.getenv("AUTOBOT_TLS_CERT_PATH")
            self.ssl_keyfile = os.getenv("AUTOBOT_TLS_KEY_PATH")

            # Fallback to legacy cert_dir pattern for backwards compatibility
            if not self.ssl_ca_certs or not self.ssl_certfile or not self.ssl_keyfile:
                from pathlib import Path

                cert_dir = os.getenv("AUTOBOT_TLS_CERT_DIR", "certs")  # ssot-config-exempt: TLS cert dir
                project_root = Path(__file__).parent.parent.parent
                self.ssl_ca_certs = str(project_root / cert_dir / "ca" / "ca-cert.pem")
                self.ssl_certfile = str(project_root / cert_dir / "main-host" / "server-cert.pem")
                self.ssl_keyfile = str(project_root / cert_dir / "main-host" / "server-key.pem")


class RedisConfigLoader:
    """
    Load Redis configurations from multiple sources.

    Supports loading from:
    - YAML configuration files
    - Service registry
    - Centralized timeout configuration
    """

    @staticmethod
    def _resolve_yaml_path(yaml_path: str | None) -> str | None:
        """
        Resolve the YAML configuration file path.

        Checks container and host paths if no explicit path provided.
        Issue #620.
        """
        if yaml_path is not None:
            return yaml_path if os.path.exists(yaml_path) else None

        possible_paths = [
            "/app/config/redis-databases.yaml",  # Container
            "./config/redis-databases.yaml",  # Host relative
            os.path.join(
                os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot"),
                "config/redis-databases.yaml",
            ),  # Host absolute
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        return None

    @staticmethod
    def _parse_database_config(db_name: str, db_config: Dict[str, Any]) -> RedisConfig:
        """
        Parse a single database configuration from YAML data.

        Issue #620.
        """
        return RedisConfig(
            name=db_name,
            db=db_config.get("db", 0),
            host=db_config.get("host", NetworkConstants.REDIS_VM_IP),
            port=db_config.get("port", NetworkConstants.REDIS_PORT),
            password=db_config.get("password"),
            decode_responses=db_config.get("decode_responses", True),
            max_connections=db_config.get("max_connections", 100),
            socket_timeout=db_config.get("socket_timeout", 5.0),
            socket_connect_timeout=db_config.get("socket_connect_timeout", 5.0),
            socket_keepalive=db_config.get("socket_keepalive", True),
            health_check_interval=db_config.get("health_check_interval", 30),
            retry_on_timeout=db_config.get("retry_on_timeout", True),
            max_retries=db_config.get("max_retries", _DEFAULT_RETRIES),
            description=db_config.get("description", ""),
        )

    @staticmethod
    def load_from_yaml(yaml_path: str | None = None) -> Dict[str, RedisConfig]:
        """
        Load configurations from YAML file.

        Priority paths (container-aware):
        1. Provided yaml_path
        2. /app/config/redis-databases.yaml (container)
        3. ./config/redis-databases.yaml (host relative)
        4. $AUTOBOT_BASE_DIR/config/redis-databases.yaml (host absolute)

        Args:
            yaml_path: Optional explicit path to YAML config file

        Returns:
            Dict mapping database names to RedisConfig objects
        """
        resolved_path = RedisConfigLoader._resolve_yaml_path(yaml_path)

        if not resolved_path:
            logger.debug("No YAML configuration file found, using defaults")
            return {}

        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            databases = config_data.get("redis_databases", config_data.get("databases", {}))

            configs = {
                db_name: RedisConfigLoader._parse_database_config(db_name, db_config)
                for db_name, db_config in databases.items()
            }

            logger.info(
                "Loaded %d database configurations from %s",
                len(configs),
                resolved_path,
            )
            return configs

        except Exception as e:
            logger.error("Error loading YAML config from %s: %s", resolved_path, e)
            return {}

    @staticmethod
    def load_from_service_registry() -> Dict[str, RedisConfig]:
        """
        Load configurations from service registry.

        Returns:
            Dict mapping database names to RedisConfig objects
        """
        try:
            from utils.service_registry import get_service_registry

            registry = get_service_registry()
            redis_config = registry.get_service_config("redis")

            if redis_config:
                # Convert service registry format to RedisConfig
                return {
                    "main": RedisConfig(
                        name="main",
                        db=0,
                        host=redis_config.host,
                        port=redis_config.port,
                        password=(redis_config.password if hasattr(redis_config, "password") else None),
                    )
                }
        except (ImportError, Exception) as e:
            logger.debug("Could not load from service registry: %s", e)

        return {}

    @staticmethod
    def load_timeout_config() -> Dict[str, Any]:
        """
        Load centralized timeout configuration.

        Returns:
            Dict with timeout and retry configuration
        """
        try:
            from config.timeout_config import get_redis_timeout_config

            return get_redis_timeout_config()
        except (ImportError, AttributeError):
            # Fallback to default configuration
            return {
                "socket_timeout": 5.0,
                "socket_connect_timeout": 5.0,
                "retry_on_timeout": True,
                "max_retries": _DEFAULT_RETRIES,
            }


@dataclass
class PoolConfig:
    """
    Redis connection pool configuration.

    Controls connection pool behavior including sizing,
    timeouts, retry logic, and circuit breaker settings.

    Issue #611: Values previously referenced REDIS_CONFIG constants,
    now inlined after move to autobot_shared (#2313).
    """

    max_connections: int = _MAX_CONNECTIONS_POOL
    min_connections: int = _MIN_CONNECTIONS_POOL
    socket_timeout: float = float(_SOCKET_TIMEOUT)
    socket_connect_timeout: float = float(_SOCKET_TIMEOUT)
    retry_on_timeout: bool = _RETRY_ON_TIMEOUT
    max_retries: int = _DEFAULT_RETRIES
    backoff_factor: float = _BACKOFF_BASE
    health_check_interval: float = float(_HEALTH_CHECK_INTERVAL)
    circuit_breaker_threshold: int = _CIRCUIT_BREAKER_THRESHOLD
    circuit_breaker_timeout: int = _CIRCUIT_BREAKER_TIMEOUT
