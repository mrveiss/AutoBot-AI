# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Immediate Connection Test - No Timeouts
Replaces timeout-based Redis connection with immediate success/failure patterns
"""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, Tuple

import redis

from autobot_shared.redis_client import get_redis_client
from backend.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class RedisConnectionState:
    """Track Redis connection state without timeouts"""

    def __init__(self):
        """Initialize Redis connection state with default disconnected status."""
        self.is_connected = False
        self.client: Optional[redis.Redis] = None
        self.last_error: Optional[str] = None
        self.connection_params: Dict[str, Any] = {}

    def mark_connected(self, client: redis.Redis, params: Dict[str, Any]):
        """Mark as successfully connected"""
        self.is_connected = True
        self.client = client
        self.connection_params = params
        self.last_error = None

    def mark_disconnected(self, error: str):
        """Mark as disconnected with error"""
        self.is_connected = False
        self.client = None
        self.last_error = error


def _create_redis_client_for_test(host: str, port: int, db: int) -> redis.Redis:
    """
    Create Redis client configured for immediate connection testing.

    Uses no timeouts for instant success/failure detection.

    Args:
        host: Redis host address.
        port: Redis port number.
        db: Database number.

    Returns:
        Configured Redis client instance.

    Issue #620.
    """
    return redis.Redis(
        host=host,
        port=port,
        db=db,
        decode_responses=True,
        socket_keepalive=True,
        socket_keepalive_options={},
        retry_on_timeout=False,
        health_check_interval=0,
        socket_connect_timeout=None,
        socket_timeout=None,
    )


async def _test_redis_ping(client: redis.Redis) -> bool:
    """
    Execute immediate PING test against Redis client.

    Uses thread pool to prevent blocking the event loop.

    Args:
        client: Redis client to test.

    Returns:
        True if PING succeeds, False otherwise.

    Issue #620.
    """
    return await asyncio.to_thread(client.ping)


async def _cleanup_redis_client(client: Optional[redis.Redis]) -> None:
    """
    Cleanup Redis client connection safely.

    Args:
        client: Redis client to close, or None.

    Issue #620.
    """
    if client:
        try:
            await asyncio.to_thread(client.close)
        except Exception:  # nosec B110 - cleanup errors are non-critical
            pass


@asynccontextmanager
async def immediate_redis_test(host: str, port: int, db: int = 0):
    """
    Test Redis connection immediately - no timeout waits.
    Either succeeds instantly or fails instantly.

    NOTE: This function uses direct redis.Redis() instantiation intentionally
    for testing connectivity to arbitrary Redis endpoints. This is a diagnostic
    tool, NOT for production client creation. For production clients, use
    get_redis_client() from autobot_shared.redis_client.

    The direct instantiation here bypasses the canonical pattern specifically
    to test raw Redis connectivity without circuit breakers or pooling overhead.
    """
    connection_state = RedisConnectionState()

    try:
        client = _create_redis_client_for_test(host, port, db)
        ping_result = await _test_redis_ping(client)

        if ping_result:
            logger.info("Redis immediate connection SUCCESS: %s:%s", host, port)
            connection_state.mark_connected(
                client, {"host": host, "port": port, "db": db}
            )
            yield connection_state
        else:
            raise redis.ConnectionError("PING returned False")

    except Exception as e:
        error_msg = f"Redis immediate connection FAILED: {host}:{port} - {str(e)}"
        logger.warning("%s", error_msg)
        connection_state.mark_disconnected(error_msg)
        yield connection_state
    finally:
        await _cleanup_redis_client(connection_state.client)


async def create_redis_with_fallback(
    primary_config: Dict[str, Any], fallback_configs: Optional[list] = None
) -> Tuple[Optional[redis.Redis], str]:
    """
    Create Redis connection with immediate fallback testing.
    No timeouts - tries each config immediately.

    Returns:
        Tuple of (client, status_message)
    """

    # Try primary configuration first
    async with immediate_redis_test(
        primary_config["host"], primary_config["port"], primary_config.get("db", 0)
    ) as state:
        if state.is_connected:
            # Success! Return the working client
            return (
                state.client,
                f"Connected to {primary_config['host']}:{primary_config['port']}",
            )

    # Primary failed, try fallbacks if provided
    if fallback_configs:
        for i, config in enumerate(fallback_configs):
            logger.info(
                f"Trying fallback Redis config {i+1}: {config['host']}:{config['port']}"
            )

            async with immediate_redis_test(
                config["host"], config["port"], config.get("db", 0)
            ) as state:
                if state.is_connected:
                    return (
                        state.client,
                        f"Connected via fallback to {config['host']}:{config['port']}",
                    )

    # All connections failed
    return None, "All Redis connections failed immediately"


class RedisCircuitBreaker:
    """
    Circuit breaker pattern for Redis - no timeouts, just immediate state tracking (thread-safe)
    """

    def __init__(self, failure_threshold: int = 3):
        """Initialize circuit breaker with failure threshold and state tracking."""
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.is_circuit_open = False
        self.last_success_time = None
        self.last_failure_time = None
        self._lock = threading.Lock()  # Lock for thread-safe state access

    def record_success(self):
        """Record successful operation (thread-safe)"""
        with self._lock:
            self.failure_count = 0
            self.is_circuit_open = False
            try:
                self.last_success_time = asyncio.get_event_loop().time()
            except RuntimeError:
                # No event loop running, use 0
                self.last_success_time = 0

    def record_failure(self):
        """Record failed operation (thread-safe)"""
        with self._lock:
            self.failure_count += 1
            try:
                self.last_failure_time = asyncio.get_event_loop().time()
            except RuntimeError:
                # No event loop running, use 0
                self.last_failure_time = 0

            if self.failure_count >= self.failure_threshold:
                self.is_circuit_open = True
                failure_count = self.failure_count
            else:
                failure_count = None

        # Log outside lock to avoid holding lock during I/O
        if failure_count is not None:
            logger.warning(
                f"🚫 Redis circuit breaker OPENED after {failure_count} failures"
            )

    def should_attempt_connection(self) -> bool:
        """Check if we should attempt connection (no timeout logic, thread-safe)"""
        with self._lock:
            return not self.is_circuit_open

    async def attempt_redis_operation(self, client: redis.Redis, operation_name: str):
        """Attempt Redis operation with circuit breaker"""
        if not self.should_attempt_connection():
            raise redis.ConnectionError(f"Circuit breaker open for {operation_name}")

        try:
            # Execute operation immediately
            result = await asyncio.to_thread(client.ping)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


# Global circuit breaker instance
redis_circuit_breaker = RedisCircuitBreaker()


async def get_redis_with_immediate_test(
    config: Dict[str, Any],
) -> Tuple[Optional[redis.Redis], str]:
    """
    Get Redis client using immediate testing pattern.
    No arbitrary timeouts - either works immediately or fails immediately.
    """

    # Define fallback configurations
    # Redis runs on VM3, use direct connection
    fallback_configs = [
        {
            "host": NetworkConstants.REDIS_VM_IP,
            "port": NetworkConstants.REDIS_PORT,
            "db": config.get("db", 0),
        },
    ]

    return await create_redis_with_fallback(config, fallback_configs)


async def test_redis_connection_immediate(
    database: str = "main",
) -> Optional[redis.Redis]:
    """
    Test Redis connection immediately and return canonical client if successful.
    Used by backend startup to quickly test Redis availability.

    USES CANONICAL get_redis_client() PATTERN:
    - Circuit breaker protection
    - Health monitoring
    - Connection pooling
    - Centralized configuration

    Args:
        database: Named database ("main", "knowledge", "prompts", etc.)

    Returns:
        Redis client from canonical pattern if connection successful, None if failed
    """
    try:
        # Get canonical client (uses centralized configuration)
        client = get_redis_client(async_client=False, database=database)

        if client is None:
            logger.warning(
                f"⚠️ Redis canonical client unavailable for database: {database}"
            )
            return None

        # Verify connectivity with immediate ping test
        async with immediate_redis_test(
            NetworkConstants.REDIS_VM_IP,
            NetworkConstants.REDIS_PORT,
            0,  # Database number handled by canonical client
        ) as state:
            if state.is_connected:
                logger.info(
                    f"✅ Redis connection test successful for database: {database}"
                )
                # Return the canonical client (not the test client)
                return client
            else:
                logger.warning(
                    f"⚠️ Redis connection test failed for database: {database}"
                )
                return None
    except Exception as e:
        logger.error(f"❌ Redis connection test error for database {database}: {str(e)}")
        return None
