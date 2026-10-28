# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Redis Configuration Module (#2313).

Contains configuration classes for Redis connection management:
- RedisDbConfig: Database configuration dataclass
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
from autobot_shared.redis_management.database_names import database_number
from autobot_shared.redis_management.endpoint import redis_tls_port, resolve_redis_endpoint
from autobot_shared.redis_management.types import resolve_databases_yaml

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
class RedisDbConfig:
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
    # #16626: ACL username sent with the password as `AUTH <username> <password>`.
    # None keeps today's password-only AUTH.
    username: str | None = None
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
        """Auto-load password, username and TLS settings from environment if not provided."""
        if self.password is None:
            # Try REDIS_PASSWORD first, then AUTOBOT_REDIS_PASSWORD
            self.password = os.getenv("REDIS_PASSWORD") or os.getenv("AUTOBOT_REDIS_PASSWORD")
        if self.username is None:
            # Same precedence as the password (#16626)
            self.username = os.getenv("REDIS_USERNAME") or os.getenv("AUTOBOT_REDIS_USERNAME")
        # Auto-load TLS settings - Issue #164. The on/off rule and the port are the
        # endpoint resolver's, so a client and a URL agree on TLS too (#19232).
        tls_port = redis_tls_port()
        if tls_port is not None:
            self.ssl = True
            self.port = tls_port

            # Check for explicit cert paths first (set by SLM enable-tls playbook)
            self.ssl_ca_certs = os.getenv("AUTOBOT_TLS_CA_PATH")
            self.ssl_certfile = os.getenv("AUTOBOT_TLS_CERT_PATH")
            self.ssl_keyfile = os.getenv("AUTOBOT_TLS_KEY_PATH")

            # Fallback to legacy cert_dir pattern for backwards compatibility
            if not self.ssl_ca_certs or not self.ssl_certfile or not self.ssl_keyfile:
                from pathlib import Path

                from autobot_shared.env_registry_tls import DEFAULT_TLS_CERT_DIR

                cert_dir = os.getenv("AUTOBOT_TLS_CERT_DIR", DEFAULT_TLS_CERT_DIR)  # the one default (#19317)
                project_root = Path(__file__).parent.parent.parent
                self.ssl_ca_certs = str(project_root / cert_dir / "ca" / "ca-cert.pem")
                self.ssl_certfile = str(project_root / cert_dir / "main-host" / "server-cert.pem")
                self.ssl_keyfile = str(project_root / cert_dir / "main-host" / "server-key.pem")


#: Keys a YAML database entry may not set: the endpoint has one resolution path (#19232).
_ENDPOINT_KEYS = frozenset({"host", "port", "password", "username"})


def _resolved_endpoint() -> Dict[str, Any]:
    """The shared endpoint as the loader's plain dict."""
    resolved = resolve_redis_endpoint()
    return {"host": resolved.host, "port": resolved.port, "password": resolved.password, "username": resolved.username}


class RedisConfigLoader:
    """
    Load Redis configurations from multiple sources.

    Supports loading from:
    - YAML configuration files (per-database tuning)
    - Centralized timeout configuration
    """

    @staticmethod
    def _resolve_yaml_path(yaml_path: str | None) -> str | None:
        """
        Resolve the YAML configuration file path.

        An explicit path, else ``types.resolve_databases_yaml`` -- the one candidate
        list the number table also reads (#19232). Issue #620.
        """
        if yaml_path is not None:
            return yaml_path if os.path.exists(yaml_path) else None
        return resolve_databases_yaml()

    @staticmethod
    def _parse_database_config(db_name: str, db_config: Dict[str, Any], endpoint: Dict[str, Any]) -> RedisDbConfig:
        """
        One YAML entry's pool and timeout tuning, on the shared number and endpoint.

        The database number comes from ``database_number`` (the YAML plus any
        ``AUTOBOT_REDIS_DB_*`` override) and host/port/credentials from *endpoint*,
        the connection manager's one resolution (#19232). A per-entry
        host/port/password/username would be a second path to a different server.
        Issue #620.
        """
        ignored = sorted(_ENDPOINT_KEYS & db_config.keys())
        if ignored:
            logger.warning("redis-databases.yaml %r: ignoring %s (#19232: one endpoint)", db_name, ignored)
        return RedisDbConfig(
            name=db_name,
            db=database_number(db_name),
            host=endpoint["host"],
            port=endpoint["port"],
            password=endpoint.get("password"),
            username=endpoint.get("username"),
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
    def load_from_yaml(
        yaml_path: str | None = None, endpoint: Dict[str, Any] | None = None
    ) -> Dict[str, RedisDbConfig]:
        """
        Load configurations from YAML file.

        Path: the provided yaml_path, else ``types.resolve_databases_yaml()``.

        Args:
            yaml_path: Optional explicit path to YAML config file
            endpoint: host/port/password/username every entry connects with;
                default: ``endpoint.resolve_redis_endpoint()`` (#19232)

        Returns:
            Dict mapping database names to RedisDbConfig objects
        """
        resolved_path = RedisConfigLoader._resolve_yaml_path(yaml_path)

        if not resolved_path:
            logger.debug("No YAML configuration file found, using defaults")
            return {}

        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            databases = config_data.get("redis_databases", config_data.get("databases", {}))

            shared = endpoint if endpoint is not None else _resolved_endpoint()
            configs = {
                db_name: RedisConfigLoader._parse_database_config(db_name, db_config, shared)
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


# Documented per-field defaults for PoolConfig — the fallback used by
# __post_init__ when a caller passes a non-numeric value (#11830).
_POOL_CONFIG_FIELD_DEFAULTS: Dict[str, Any] = {
    "max_connections": _MAX_CONNECTIONS_POOL,
    "min_connections": _MIN_CONNECTIONS_POOL,
    "socket_timeout": float(_SOCKET_TIMEOUT),
    "socket_connect_timeout": float(_SOCKET_TIMEOUT),
    "retry_on_timeout": _RETRY_ON_TIMEOUT,
    "max_retries": _DEFAULT_RETRIES,
    "backoff_factor": _BACKOFF_BASE,
    "health_check_interval": float(_HEALTH_CHECK_INTERVAL),
    "circuit_breaker_threshold": _CIRCUIT_BREAKER_THRESHOLD,
    "circuit_breaker_timeout": _CIRCUIT_BREAKER_TIMEOUT,
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

    def __post_init__(self) -> None:
        """Coerce every field to a real value of its documented type (#11830).

        This is shared startup-path code (must-not-crash): a value sourced from
        a test-stubbed config module (MagicMock/None/str) falls back to the
        documented default with a single WARNING instead of raising — a
        MagicMock ``circuit_breaker_threshold`` otherwise survives until
        ``RedisConnectionManager._record_failure`` and TypeErrors there.
        """
        invalid: list[str] = []
        for field_name, default in _POOL_CONFIG_FIELD_DEFAULTS.items():
            value = getattr(self, field_name)
            if isinstance(default, bool):
                valid = isinstance(value, bool)
            else:
                valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            if valid:
                if not isinstance(default, bool):
                    # Normalize to the field's documented type (int fields must
                    # stay int — redis-py rejects float max_connections).
                    setattr(self, field_name, type(default)(value))
                continue
            invalid.append(f"{field_name}={value!r}")
            setattr(self, field_name, default)
        if invalid:
            logger.warning(
                "PoolConfig received non-numeric value(s) — falling back to defaults: %s",
                ", ".join(invalid),
            )
