# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ollama Connection Pool Manager

Manages connection pooling for Ollama API calls to prevent resource contention
and improve performance across multiple concurrent requests.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)


@dataclass
class ConnectionPoolConfig:
    """Configuration for Ollama connection pool"""

    max_connections: int = 3  # Maximum concurrent connections to Ollama
    max_queue_size: int = 50  # Maximum queued requests
    connection_timeout: float = 30.0  # Timeout for individual connections
    queue_timeout: float = 60.0  # Timeout for waiting in queue
    health_check_interval: float = 300.0  # Health check every 5 minutes


class OllamaConnectionPool:
    """
    Connection pool manager for Ollama API calls.

    Prevents resource contention by limiting concurrent connections and
    queuing requests when the pool is at capacity.
    """

    def __init__(self, config: ConnectionPoolConfig = None):
        """Initialize the connection pool"""
        self.config = config or ConnectionPoolConfig()
        self.semaphore = asyncio.Semaphore(self.config.max_connections)
        self.request_queue = asyncio.Queue(maxsize=self.config.max_queue_size)
        self._stats_lock = asyncio.Lock()
        self.active_connections = 0
        self.total_requests = 0
        self.failed_requests = 0
        self.last_health_check = 0.0
        self.pool_healthy = True

        # Connection statistics
        self.connection_stats = {
            "active": 0,
            "queued": 0,
            "completed": 0,
            "failed": 0,
            "avg_wait_time": 0.0,
            "avg_execution_time": 0.0,
        }

        logger.info(
            f"Ollama connection pool initialized: max_connections={self.config.max_connections}"
        )

    @asynccontextmanager
    async def acquire_connection(self):
        """
        Context manager for acquiring a connection from the pool (thread-safe).

        Usage:
            async with pool.acquire_connection() as session:
                # Use session for HTTP requests
                pass
        """
        start_time = time.time()

        # Get request ID under lock
        async with self._stats_lock:
            request_id = f"req_{self.total_requests + 1}"

        semaphore_acquired = False

        try:
            # Wait for available connection slot
            logger.debug(f"[{request_id}] Waiting for connection slot")
            async with self._stats_lock:
                self.connection_stats["queued"] += 1

            # Use timeout to prevent infinite waiting
            await asyncio.wait_for(
                self.semaphore.acquire(), timeout=self.config.queue_timeout
            )
            semaphore_acquired = True

            wait_time = time.time() - start_time

            # Update stats under lock
            async with self._stats_lock:
                self.connection_stats["queued"] -= 1
                self.active_connections += 1
                self.total_requests += 1
                self.connection_stats["active"] += 1

                # Update average wait time
                if self.total_requests > 1:
                    self.connection_stats["avg_wait_time"] = (
                        self.connection_stats["avg_wait_time"] * (self.total_requests - 1)
                        + wait_time
                    ) / self.total_requests
                else:
                    self.connection_stats["avg_wait_time"] = wait_time

            logger.debug(
                f"[{request_id}] Acquired connection (waited {wait_time:.2f}s)"
            )

            # Use singleton HTTP client for efficient connection pooling
            http_client = get_http_client()
            session = await http_client.get_session()

            execution_start = time.time()

            try:
                yield session

                # Record successful execution under lock
                execution_time = time.time() - execution_start
                async with self._stats_lock:
                    self.connection_stats["completed"] += 1

                    # Update average execution time
                    if self.connection_stats["completed"] > 1:
                        self.connection_stats["avg_execution_time"] = (
                            self.connection_stats["avg_execution_time"]
                            * (self.connection_stats["completed"] - 1)
                            + execution_time
                        ) / self.connection_stats["completed"]
                    else:
                        self.connection_stats["avg_execution_time"] = execution_time

                logger.debug(
                    f"[{request_id}] Connection completed successfully ({execution_time:.2f}s)"
                )

            except Exception as e:
                # Record failed execution under lock
                async with self._stats_lock:
                    self.failed_requests += 1
                    self.connection_stats["failed"] += 1
                logger.error(f"[{request_id}] Connection failed: {e}")
                raise

            # Session cleanup is handled by singleton HTTPClientManager

        except asyncio.TimeoutError:
            async with self._stats_lock:
                self.connection_stats["queued"] -= 1
                self.failed_requests += 1
                self.connection_stats["failed"] += 1
            logger.error(
                f"[{request_id}] Timeout waiting for connection slot ({self.config.queue_timeout}s)"
            )
            raise asyncio.TimeoutError(
                f"Timeout waiting for Ollama connection slot after {self.config.queue_timeout}s"
            )

        finally:
            if semaphore_acquired:
                async with self._stats_lock:
                    if self.active_connections > 0:
                        self.active_connections -= 1
                        self.connection_stats["active"] -= 1
                self.semaphore.release()
                logger.debug(f"[{request_id}] Released connection")

    async def health_check(self, ollama_url: str) -> bool:
        """
        Perform health check on Ollama service (thread-safe).

        Args:
            ollama_url: Base URL for Ollama service

        Returns:
            bool: True if healthy, False otherwise
        """
        current_time = time.time()

        # Check if recently performed (read under lock)
        async with self._stats_lock:
            if current_time - self.last_health_check < self.config.health_check_interval:
                return self.pool_healthy

        try:
            async with self.acquire_connection() as session:
                health_url = f"{ollama_url}/api/tags"
                async with session.get(health_url) as response:
                    async with self._stats_lock:
                        if response.status == 200:
                            self.pool_healthy = True
                            logger.info("Ollama connection pool health check: HEALTHY")
                        else:
                            self.pool_healthy = False
                            logger.warning(
                                f"Ollama health check failed: HTTP {response.status}"
                            )

        except Exception as e:
            async with self._stats_lock:
                self.pool_healthy = False
            logger.error(f"Ollama health check failed: {e}")

        finally:
            async with self._stats_lock:
                self.last_health_check = current_time
                healthy = self.pool_healthy

        return healthy

    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get current pool statistics (thread-safe)"""
        async with self._stats_lock:
            total = self.total_requests
            failed = self.failed_requests
            active = self.active_connections
            queued = self.connection_stats["queued"]
            healthy = self.pool_healthy
            last_check = self.last_health_check
            completed = self.connection_stats["completed"]
            avg_wait = self.connection_stats["avg_wait_time"]
            avg_exec = self.connection_stats["avg_execution_time"]

        success_rate = 0.0
        if total > 0:
            success_rate = (total - failed) / total

        return {
            "pool_config": {
                "max_connections": self.config.max_connections,
                "max_queue_size": self.config.max_queue_size,
                "connection_timeout": self.config.connection_timeout,
                "queue_timeout": self.config.queue_timeout,
            },
            "current_state": {
                "active_connections": active,
                "queued_requests": queued,
                "pool_healthy": healthy,
                "last_health_check": last_check,
            },
            "statistics": {
                "total_requests": total,
                "completed_requests": completed,
                "failed_requests": failed,
                "success_rate": success_rate,
                "avg_wait_time": avg_wait,
                "avg_execution_time": avg_exec,
            },
        }

    async def execute_with_pool(self, request_func: Callable, *args, **kwargs) -> Any:
        """
        Execute a request function using the connection pool.

        Args:
            request_func: Async function that takes session as first parameter
            *args: Additional arguments for request_func
            **kwargs: Additional keyword arguments for request_func

        Returns:
            Result from request_func
        """
        async with self.acquire_connection() as session:
            return await request_func(session, *args, **kwargs)


# Global connection pool instance (thread-safe)
import threading

_ollama_pool: Optional[OllamaConnectionPool] = None
_ollama_pool_lock = threading.Lock()


def get_ollama_pool() -> OllamaConnectionPool:
    """Get the global Ollama connection pool instance (thread-safe)"""
    global _ollama_pool
    if _ollama_pool is None:
        with _ollama_pool_lock:
            # Double-check after acquiring lock
            if _ollama_pool is None:
                _ollama_pool = OllamaConnectionPool()
    return _ollama_pool


def configure_ollama_pool(config: ConnectionPoolConfig):
    """Configure the global Ollama connection pool (thread-safe)"""
    global _ollama_pool
    with _ollama_pool_lock:
        _ollama_pool = OllamaConnectionPool(config)
        logger.info("Ollama connection pool reconfigured")


async def cleanup_ollama_pool():
    """Cleanup the global Ollama connection pool (thread-safe)"""
    global _ollama_pool
    with _ollama_pool_lock:
        pool = _ollama_pool
        if pool is None:
            return

    # Wait for active connections to complete (check without holding lock)
    while True:
        async with pool._stats_lock:
            active = pool.active_connections
        if active == 0:
            break
        logger.info(f"Waiting for {active} active connections to complete")
        await asyncio.sleep(0.1)

    with _ollama_pool_lock:
        logger.info("Ollama connection pool cleaned up")
        _ollama_pool = None


# Convenience function for one-off requests
async def execute_ollama_request(
    request_func: Callable, ollama_url: str, *args, **kwargs
) -> Any:
    """
    Execute a single Ollama request using the connection pool.

    Args:
        request_func: Async function that takes (session, url, *args, **kwargs)
        ollama_url: Base URL for Ollama service
        *args: Additional arguments for request_func
        **kwargs: Additional keyword arguments for request_func

    Returns:
        Result from request_func
    """
    pool = get_ollama_pool()

    # Perform health check if needed
    if not await pool.health_check(ollama_url):
        logger.warning(
            "Ollama service may be unhealthy, proceeding with request anyway"
        )

    return await pool.execute_with_pool(request_func, ollama_url, *args, **kwargs)
