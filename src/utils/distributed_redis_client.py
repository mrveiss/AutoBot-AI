# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Distributed Redis Client for AutoBot 6-VM Architecture
Handles connection to remote Redis VM

DEPRECATION NOTICE: This module is deprecated. Use get_redis_client() from
src.utils.redis_client instead, which provides the same functionality with
better connection pooling, health checks, and retry logic.
"""

import asyncio
import logging
import time
from typing import Optional

import redis

from src.constants.network_constants import NetworkConstants
from src.constants.threshold_constants import RetryConfig
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class DistributedRedisClient:
    """Redis client optimized for distributed AutoBot architecture"""

    def __init__(self):
        """Initialize distributed Redis client for AutoBot architecture."""
        self.redis_host = NetworkConstants.REDIS_VM_IP
        self.redis_port = NetworkConstants.REDIS_PORT
        self.redis_password = None  # Will be loaded from environment
        self._client = None
        self._connection_attempts = 0
        self._last_connection_time = 0
        self._max_retries = RetryConfig.DEFAULT_RETRIES
        self._retry_delay = 2

        # Lock for thread-safe state access
        import threading

        self._lock = threading.Lock()

    def _get_redis_password(self) -> Optional[str]:
        """Get Redis password from environment"""
        import os

        return os.getenv("REDIS_PASSWORD") or os.getenv("AUTOBOT_REDIS_PASSWORD")

    def get_client(self) -> Optional[redis.Redis]:
        """
        Get Redis client with proper error handling for distributed setup (thread-safe).
        Returns None if connection fails (non-blocking)
        """
        current_time = time.time()

        with self._lock:
            # Rate limit connection attempts (max 1 per 5 seconds)
            if current_time - self._last_connection_time < 5:
                return self._client

            self._last_connection_time = current_time
            client = self._client

        if client is None or not self._test_connection():
            new_client = self._create_connection()
            with self._lock:
                self._client = new_client
            return new_client

        return client

    def _create_connection(self) -> Optional[redis.Redis]:
        """Create Redis connection using canonical get_redis_client() (thread-safe)

        Uses the canonical get_redis_client() pattern which provides:
        - Connection pooling
        - Health monitoring
        - Retry logic
        - Centralized configuration
        """
        try:
            with self._lock:
                self._connection_attempts += 1
                attempts = self._connection_attempts

            # Use canonical Redis client (already configured for distributed setup)
            client = get_redis_client(async_client=False, database="main")

            if client is None:
                logger.warning("⚠️ Redis canonical client unavailable")
                return None

            # Test connection
            client.ping()

            logger.info(
                f"✅ Connected to Redis VM at {self.redis_host}:{self.redis_port}"
            )
            with self._lock:
                self._connection_attempts = 0
            return client

        except redis.ConnectionError as e:
            with self._lock:
                attempts = self._connection_attempts
            if attempts <= self._max_retries:
                logger.warning(
                    f"Redis VM connection attempt {attempts}/{self._max_retries} failed: {e}"
                )
            else:
                logger.error(
                    f"❌ Failed to connect to Redis VM after {self._max_retries} attempts"
                )
            return None

        except Exception as e:
            logger.error("❌ Unexpected Redis connection error: %s", e)
            return None

    def _test_connection(self) -> bool:
        """Test if current connection is working (thread-safe)"""
        with self._lock:
            client = self._client

        if client is None:
            return False

        try:
            client.ping()
            return True
        except Exception:
            return False

    async def get_client_async(self) -> Optional[redis.Redis]:
        """Async wrapper for getting Redis client"""
        return await asyncio.to_thread(self.get_client)

    def is_connected(self) -> bool:
        """Check if Redis client is connected to remote VM (thread-safe)"""
        with self._lock:
            has_client = self._client is not None
        return has_client and self._test_connection()

    def get_connection_info(self) -> dict:
        """Get connection status and info (thread-safe)"""
        with self._lock:
            connection_attempts = self._connection_attempts
            last_connection_time = self._last_connection_time
            client_exists = self._client is not None

        return {
            "host": self.redis_host,
            "port": self.redis_port,
            "connected": self.is_connected(),
            "connection_attempts": connection_attempts,
            "last_connection_time": last_connection_time,
            "client_exists": client_exists,
        }


# Global instance for distributed Redis access
distributed_redis_client = DistributedRedisClient()


def get_distributed_redis() -> Optional[redis.Redis]:
    """Get distributed Redis client - safe for use across the application"""
    return distributed_redis_client.get_client()


async def get_distributed_redis_async() -> Optional[redis.Redis]:
    """Get distributed Redis client asynchronously"""
    return await distributed_redis_client.get_client_async()


def test_distributed_redis_connection() -> bool:
    """Test connection to distributed Redis VM"""
    client = get_distributed_redis()
    if client:
        try:
            response = client.ping()
            logger.info("✅ Redis VM connection test successful: %s", response)
            return True
        except Exception as e:
            logger.error("❌ Redis VM connection test failed: %s", e)
            return False
    else:
        logger.warning("⚠️  No Redis client available for testing")
        return False


if __name__ == "__main__":
    # Test script for distributed Redis connection
    logger.info("🧪 Testing Distributed Redis Connection...")

    # Test synchronous connection
    success = test_distributed_redis_connection()

    # Get connection info
    info = distributed_redis_client.get_connection_info()
    logger.info("📊 Connection Info: {info}")

    if success:
        logger.info("✅ Distributed Redis connection working correctly!")
    else:
        logger.info("❌ Distributed Redis connection failed!")
        print(
            f"Check that Redis VM ({NetworkConstants.REDIS_VM_IP}:{NetworkConstants.REDIS_PORT}) is accessible"
        )
