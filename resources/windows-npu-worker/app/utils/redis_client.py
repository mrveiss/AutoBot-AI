# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Standalone Redis Client for Windows NPU Worker
===============================================

This module provides Redis client initialization with connection pooling,
retry logic, and health monitoring for the Windows NPU worker.

STANDALONE DESIGN: This is a self-contained utility for the Windows NPU worker
deployment. It does NOT import from src.utils and has its own implementation.

Issue #725: Added mTLS support for secure Redis connections.

USAGE PATTERN:
==============
from utils.redis_client import get_redis_client

# Get async Redis client with connection pooling
redis_client = await get_redis_client(config)

FEATURES:
=========
✅ Connection pooling (uses max_connections from config)
✅ Automatic retry logic (uses retry_on_timeout from config)
✅ Timeout handling (uses socket_timeout, socket_connect_timeout from config)
✅ Health monitoring with ping checks
✅ Password authentication support
✅ Database selection from config
✅ TCP keepalive configuration
✅ Graceful degradation (returns None on failure, allows optional Redis)
✅ TLS/mTLS support (Issue #725)

CONFIG PARAMETERS (from npu_worker.yaml):
=========================================
redis:
  host: "172.16.168.23"
  port: 6379
  password: null
  db: 0
  max_connections: 20
  socket_timeout: 5
  socket_connect_timeout: 2
  retry_on_timeout: true
  tls_enabled: false
  tls_port: 6380
  tls_ca_cert: null
  tls_cert_file: null
  tls_key_file: null
"""

import asyncio
import logging
import ssl
from typing import Optional

import redis.asyncio as async_redis
from redis.asyncio.connection import ConnectionPool, SSLConnection
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

logger = logging.getLogger(__name__)


class RedisConnectionManager:
    """
    Manages Redis connection pool for Windows NPU worker

    Provides connection pooling, retry logic, and health monitoring
    following the same patterns as the main AutoBot codebase.
    """

    def __init__(self, config: dict):
        """
        Initialize Redis connection manager

        Args:
            config: Configuration dictionary from npu_worker.yaml
        """
        self.config = config
        self.redis_config = config.get('redis', {})
        self._connection_pool = None
        self._client = None

    async def get_client(self) -> Optional[async_redis.Redis]:
        """
        Get Redis client with connection pooling

        Returns:
            Redis client instance or None if connection fails
        """
        if self._client is not None:
            return self._client

        try:
            # Create connection pool if not exists
            if self._connection_pool is None:
                self._connection_pool = self._create_connection_pool()

            # Create Redis client with connection pool
            self._client = async_redis.Redis(connection_pool=self._connection_pool)

            # Test connection
            await self._client.ping()
            logger.info("Redis connection established successfully")

            return self._client

        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            logger.info("NPU worker will operate without Redis (standalone mode)")
            return None

    def _create_connection_pool(self) -> ConnectionPool:
        """
        Create Redis connection pool with all config parameters

        Issue #725: Added TLS/mTLS support for secure connections.

        Returns:
            ConnectionPool instance
        """
        # Extract configuration values
        host = self.redis_config.get('host', 'localhost')
        password = self.redis_config.get('password')
        db = self.redis_config.get('db', 0)
        max_connections = self.redis_config.get('max_connections', 20)
        socket_timeout = self.redis_config.get('socket_timeout', 5)
        socket_connect_timeout = self.redis_config.get('socket_connect_timeout', 2)
        retry_on_timeout = self.redis_config.get('retry_on_timeout', True)

        # Issue #725: TLS configuration
        tls_enabled = self.redis_config.get('tls_enabled', False)
        port = self.redis_config.get('tls_port', 6380) if tls_enabled else self.redis_config.get('port', 6379)

        # Configure retry logic
        retry = Retry(
            ExponentialBackoff(base=0.05, cap=1.0),
            retries=3
        ) if retry_on_timeout else None

        # Base connection pool parameters
        pool_kwargs = {
            "host": host,
            "port": port,
            "password": password,
            "db": db,
            "max_connections": max_connections,
            "socket_timeout": socket_timeout,
            "socket_connect_timeout": socket_connect_timeout,
            "socket_keepalive": True,
            "socket_keepalive_options": {},
            "decode_responses": True,
            "retry": retry,
            "retry_on_timeout": retry_on_timeout,
            "health_check_interval": 30,
        }

        # Issue #725: Add TLS/SSL configuration if enabled
        if tls_enabled:
            tls_ca_cert = self.redis_config.get('tls_ca_cert')
            tls_cert_file = self.redis_config.get('tls_cert_file')
            tls_key_file = self.redis_config.get('tls_key_file')

            # Create SSL context for mTLS
            ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            if tls_ca_cert:
                ssl_context.load_verify_locations(tls_ca_cert)
            if tls_cert_file and tls_key_file:
                ssl_context.load_cert_chain(tls_cert_file, tls_key_file)

            pool_kwargs["connection_class"] = SSLConnection
            pool_kwargs["ssl"] = ssl_context

            logger.info(
                f"Redis TLS connection pool created: "
                f"host={host}, port={port}, db={db}, "
                f"max_connections={max_connections}, "
                f"socket_timeout={socket_timeout}s, TLS=enabled"
            )
        else:
            logger.info(
                f"Redis connection pool created: "
                f"host={host}, port={port}, db={db}, "
                f"max_connections={max_connections}, "
                f"socket_timeout={socket_timeout}s"
            )

        # Create connection pool
        pool = ConnectionPool(**pool_kwargs)

        return pool

    async def health_check(self) -> bool:
        """
        Check Redis connection health

        Returns:
            True if Redis is healthy, False otherwise
        """
        if self._client is None:
            return False

        try:
            await self._client.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            return False

    async def close(self):
        """Close Redis connection and cleanup resources"""
        if self._client is not None:
            try:
                await self._client.aclose()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._client = None
                self._connection_pool = None


# Global connection manager instance with thread-safe initialization (Issue #662)
_connection_manager: Optional[RedisConnectionManager] = None
_connection_manager_lock = asyncio.Lock()


async def get_redis_client(config: dict) -> Optional[async_redis.Redis]:
    """
    Get Redis client with connection pooling (canonical pattern, thread-safe)

    This is the ONLY approved method for getting a Redis client in the
    Windows NPU worker. Direct redis.Redis() instantiation is FORBIDDEN.

    Args:
        config: Configuration dictionary from npu_worker.yaml

    Returns:
        Redis client instance or None if Redis is unavailable

    Example:
        # In npu_worker.py
        redis_client = await get_redis_client(config)
        if redis_client:
            await redis_client.set("key", "value")
    """
    global _connection_manager

    # Create connection manager on first call (thread-safe)
    if _connection_manager is None:
        async with _connection_manager_lock:
            # Double-check after acquiring lock
            if _connection_manager is None:
                _connection_manager = RedisConnectionManager(config)

    # Get client from manager
    return await _connection_manager.get_client()


async def close_redis_client():
    """Close Redis client and cleanup resources"""
    global _connection_manager

    async with _connection_manager_lock:
        if _connection_manager is not None:
            await _connection_manager.close()
            _connection_manager = None
