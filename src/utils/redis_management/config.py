# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Configuration Module

Contains configuration classes for Redis connection management:
- RedisConfig: Database configuration dataclass
- RedisConfigLoader: Multi-source configuration loader
- PoolConfig: Connection pool configuration

Extracted from redis_client.py as part of Issue #381 refactoring.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import yaml

from src.constants.network_constants import NetworkConstants
from src.constants.threshold_constants import RetryConfig

logger = logging.getLogger(__name__)


@dataclass
class RedisConfig:
    """
    Redis database configuration.

    Holds all configuration options for a Redis database connection,
    including network settings, pooling options, and retry configuration.
    """

    name: str
    db: int
    host: str = NetworkConstants.REDIS_VM_IP
    port: int = NetworkConstants.REDIS_PORT
    password: Optional[str] = None
    decode_responses: bool = True
    max_connections: int = 100
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    socket_keepalive: bool = True
    socket_keepalive_options: Optional[Dict[int, int]] = None
    health_check_interval: int = 30
    retry_on_timeout: bool = True
    max_retries: int = RetryConfig.DEFAULT_RETRIES
    description: str = ""

    def __post_init__(self):
        """Auto-load password from environment if not provided."""
        if self.password is None:
            # Try REDIS_PASSWORD first, then AUTOBOT_REDIS_PASSWORD
            self.password = os.getenv("REDIS_PASSWORD") or os.getenv(
                "AUTOBOT_REDIS_PASSWORD"
            )


class RedisConfigLoader:
    """
    Load Redis configurations from multiple sources.

    Supports loading from:
    - YAML configuration files
    - Service registry
    - Centralized timeout configuration
    """

    @staticmethod
    def load_from_yaml(yaml_path: str = None) -> Dict[str, RedisConfig]:
        """
        Load configurations from YAML file.

        Priority paths (container-aware):
        1. Provided yaml_path
        2. /app/config/redis-databases.yaml (container)
        3. ./config/redis-databases.yaml (host relative)
        4. /home/kali/Desktop/AutoBot/config/redis-databases.yaml (host absolute)

        Args:
            yaml_path: Optional explicit path to YAML config file

        Returns:
            Dict mapping database names to RedisConfig objects
        """
        if yaml_path is None:
            # Auto-detect container vs host environment
            possible_paths = [
                "/app/config/redis-databases.yaml",  # Container
                "./config/redis-databases.yaml",  # Host relative
                "/home/kali/Desktop/AutoBot/config/redis-databases.yaml",  # Host absolute
            ]

            for path in possible_paths:
                if os.path.exists(path):
                    yaml_path = path
                    break

        if not yaml_path or not os.path.exists(yaml_path):
            logger.debug("No YAML configuration file found, using defaults")
            return {}

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            configs = {}
            databases = config_data.get(
                "redis_databases", config_data.get("databases", {})
            )

            for db_name, db_config in databases.items():
                configs[db_name] = RedisConfig(
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
                    max_retries=db_config.get("max_retries", RetryConfig.DEFAULT_RETRIES),
                    description=db_config.get("description", ""),
                )

            logger.info(
                f"Loaded {len(configs)} database configurations from {yaml_path}"
            )
            return configs

        except Exception as e:
            logger.error(f"Error loading YAML config from {yaml_path}: {e}")
            return {}

    @staticmethod
    def load_from_service_registry() -> Dict[str, RedisConfig]:
        """
        Load configurations from service registry.

        Returns:
            Dict mapping database names to RedisConfig objects
        """
        try:
            from src.utils.service_registry import get_service_registry

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
                        password=(
                            redis_config.password
                            if hasattr(redis_config, "password")
                            else None
                        ),
                    )
                }
        except (ImportError, Exception) as e:
            logger.debug(f"Could not load from service registry: {e}")

        return {}

    @staticmethod
    def load_timeout_config() -> Dict[str, Any]:
        """
        Load centralized timeout configuration.

        Returns:
            Dict with timeout and retry configuration
        """
        try:
            from src.config.timeout_config import get_redis_timeout_config

            return get_redis_timeout_config()
        except (ImportError, AttributeError):
            # Fallback to default configuration
            return {
                "socket_timeout": 5.0,
                "socket_connect_timeout": 5.0,
                "retry_on_timeout": True,
                "max_retries": RetryConfig.DEFAULT_RETRIES,
            }


@dataclass
class PoolConfig:
    """
    Redis connection pool configuration.

    Controls connection pool behavior including sizing,
    timeouts, retry logic, and circuit breaker settings.
    """

    max_connections: int = 100  # Increased from 20 for concurrent operations
    min_connections: int = 2
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    max_retries: int = RetryConfig.DEFAULT_RETRIES
    backoff_factor: float = RetryConfig.BACKOFF_BASE
    health_check_interval: float = 30.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60  # seconds
