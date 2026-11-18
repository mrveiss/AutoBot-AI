# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Connection-pool parameter builders for ``RedisConnectionManager`` (#18553).

Split out of ``connection_manager.py`` (a grandfathered file that may not grow) when the per-call
``decode_responses`` override was added: this is where a pool's constructor arguments, including the
effective decode mode, are assembled. The builders are pure functions of a ``RedisDbConfig``; the only
manager state they read is ``_tcp_keepalive_options``.

``resolve_db_config`` (the ONE place a database name becomes its ``RedisDbConfig``) and
``build_sync_pool`` are public: the keyspace survey (``keyspace_survey``) builds its clients through
them, so a survey connects with exactly the host, port, auth and TLS a named client gets (#18553).
"""

import logging
from typing import Any, Callable, Dict

import redis
from redis.asyncio.connection import SSLConnection as AsyncSSLConnection
from redis.backoff import ExponentialBackoff
from redis.connection import SSLConnection
from redis.retry import Retry

from autobot_shared.redis_management.config import PoolConfig, RedisDbConfig

logger = logging.getLogger(__name__)


class PoolParamsMixin:
    """Builds sync and async pool arguments from a ``RedisDbConfig``."""

    _tcp_keepalive_options: Dict[int, int]
    _configs: Dict[str, RedisDbConfig]
    _config: Dict[str, Any]
    _pool_config: PoolConfig
    _get_database_number: Callable[[str], int]
    _validate_config_host: Callable[[str, RedisDbConfig], None]

    def resolve_db_config(self, database_name: str) -> RedisDbConfig:
        """The ``RedisDbConfig`` for *database_name*: its YAML/registry entry, else one from SSOT config.

        Refuses an undeclared name (``KeyError``) and a blank host (``RedisConfigurationError``).
        """
        config = self._configs.get(database_name)
        if config is None:
            pool = self._pool_config
            config = RedisDbConfig(
                name=database_name,
                db=self._get_database_number(database_name),
                host=self._config["host"],
                port=self._config["port"],
                password=self._config.get("password"),
                username=self._config.get("username"),
                max_connections=pool.max_connections,
                socket_timeout=pool.socket_timeout,
                socket_connect_timeout=pool.socket_connect_timeout,
                retry_on_timeout=pool.retry_on_timeout,
                max_retries=pool.max_retries,
                health_check_interval=int(pool.health_check_interval),
            )
        self._validate_config_host(database_name, config)
        return config

    @staticmethod
    def _effective_decode(config: RedisDbConfig, override: bool | None) -> bool:
        """The decode mode a pool is built with: the caller's override, else the YAML value."""
        return config.decode_responses if override is None else override

    def _build_async_pool_params(
        self, config: RedisDbConfig, database_name: str, decode_responses: bool | None = None
    ) -> dict:
        """
        Build connection pool parameters for async Redis.

        Issue #665: Extracted from _create_async_pool_with_retry to reduce function length.

        Args:
            config: Redis configuration
            database_name: Name of database for logging
            decode_responses: Per-pool override (#18553); None keeps the YAML value

        Returns:
            Dictionary of pool parameters
        """
        pool_params = {
            "host": config.host,
            "port": config.port,
            "db": config.db,
            "password": config.password,
            "username": config.username,
            "decode_responses": self._effective_decode(config, decode_responses),
            "max_connections": config.max_connections,
            "socket_timeout": config.socket_timeout,
            "socket_connect_timeout": config.socket_connect_timeout,
            "socket_keepalive": config.socket_keepalive,
            "socket_keepalive_options": config.socket_keepalive_options or self._tcp_keepalive_options,
            "retry_on_timeout": config.retry_on_timeout,
            "health_check_interval": 0,
        }

        # Add TLS parameters if enabled
        # Use connection_class=AsyncSSLConnection for proper TLS handling
        if config.ssl:
            pool_params["connection_class"] = AsyncSSLConnection
            if config.ssl_ca_certs:
                pool_params["ssl_ca_certs"] = config.ssl_ca_certs
            if config.ssl_certfile:
                pool_params["ssl_certfile"] = config.ssl_certfile
            if config.ssl_keyfile:
                pool_params["ssl_keyfile"] = config.ssl_keyfile
            pool_params["ssl_cert_reqs"] = config.ssl_cert_reqs or "required"
            logger.info(f"TLS enabled for async Redis connection '{database_name}'")

        return pool_params

    def _apply_tls_params(self, pool_params: Dict[str, Any], config: RedisDbConfig, database_name: str) -> None:
        """Apply TLS parameters to pool configuration if TLS is enabled.

        Args:
            pool_params: Pool parameters dictionary to modify in-place
            config: Redis configuration with TLS settings
            database_name: Name of database for logging. Issue #620.
        """
        if not config.ssl:
            return

        pool_params["connection_class"] = SSLConnection
        if config.ssl_ca_certs:
            pool_params["ssl_ca_certs"] = config.ssl_ca_certs
        if config.ssl_certfile:
            pool_params["ssl_certfile"] = config.ssl_certfile
        if config.ssl_keyfile:
            pool_params["ssl_keyfile"] = config.ssl_keyfile
        pool_params["ssl_cert_reqs"] = config.ssl_cert_reqs or "required"
        logger.info(f"TLS enabled for sync Redis connection '{database_name}'")

    def build_sync_pool(
        self, database_name: str, config: RedisDbConfig, decode_responses: bool | None = None
    ) -> redis.ConnectionPool:
        """
        Create a sync pool for *config* with TCP keepalive tuning (the one sync pool builder).

        Features:
        - TCP keepalive configuration (prevents connection drops)
        - Exponential backoff retry
        - Parameter filtering
        """
        retry_policy = Retry(
            backoff=ExponentialBackoff(base=0.008, cap=10.0),
            retries=config.max_retries,
        )

        pool_params = {
            "host": config.host,
            "port": config.port,
            "db": config.db,
            "password": config.password,
            "username": config.username,
            "decode_responses": self._effective_decode(config, decode_responses),
            "max_connections": config.max_connections,
            "socket_timeout": config.socket_timeout,
            "socket_connect_timeout": config.socket_connect_timeout,
            "socket_keepalive": True,
            "socket_keepalive_options": (config.socket_keepalive_options or self._tcp_keepalive_options),
            "retry_on_timeout": config.retry_on_timeout,
            "retry": retry_policy,
        }

        self._apply_tls_params(pool_params, config, database_name)
        pool_params = {k: v for k, v in pool_params.items() if v is not None}

        logger.info(f"Created sync pool for '{database_name}' with TCP keepalive tuning")
        return redis.ConnectionPool(**pool_params)  # type: ignore[arg-type]  # GH#7105: valid kwargs; stubs lack **kwargs model  # noqa: E501
