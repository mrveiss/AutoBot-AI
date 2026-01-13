# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Connection Pool Manager - HTTP/2 connection pooling for cloud API providers.

Reduces connection overhead for cloud APIs by maintaining persistent
connections with HTTP/2 multiplexing support.

Issue #717: Efficient Inference Design implementation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """Configuration for connection pool."""

    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 5.0  # seconds
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    write_timeout: float = 30.0
    pool_timeout: float = 30.0
    http2: bool = True
    retries: int = 0  # httpx handles retries internally


@dataclass
class PoolMetrics:
    """Metrics for connection pool performance."""

    requests_sent: int = 0
    requests_failed: int = 0
    connection_reuses: int = 0
    avg_response_time_ms: float = 0.0
    active_connections: int = 0
    pool_created_at: float = field(default_factory=time.time)


class ConnectionPoolManager:
    """
    Manage HTTP connection pools for cloud LLM providers.

    Provides shared connection pools with HTTP/2 multiplexing to reduce
    latency for cloud API calls. Each provider gets its own pool to
    optimize connection reuse.

    Typical usage:
        pool_mgr = ConnectionPoolManager()
        client = await pool_mgr.get_client("openai", base_url="https://api.openai.com")
        response = await client.post("/v1/chat/completions", json=payload)
    """

    def __init__(self, default_config: PoolConfig = None):
        """
        Initialize connection pool manager.

        Args:
            default_config: Default pool configuration for all providers
        """
        if not HTTPX_AVAILABLE:
            logger.warning("httpx not available, connection pooling disabled")

        self.default_config = default_config or PoolConfig()
        self._clients: Dict[str, "httpx.AsyncClient"] = {}
        self._configs: Dict[str, PoolConfig] = {}
        self._metrics: Dict[str, PoolMetrics] = {}
        self._lock = asyncio.Lock()

        logger.info(
            "ConnectionPoolManager initialized: max_conn=%d, http2=%s",
            self.default_config.max_connections,
            self.default_config.http2,
        )

    async def get_client(
        self,
        provider_name: str,
        base_url: str,
        headers: Dict[str, str] = None,
        config: PoolConfig = None,
    ) -> Optional["httpx.AsyncClient"]:
        """
        Get or create an HTTP client for a provider.

        Args:
            provider_name: Unique identifier for the provider
            base_url: Base URL for API calls
            headers: Default headers to include in all requests
            config: Pool configuration (uses default if None)

        Returns:
            httpx.AsyncClient instance or None if httpx unavailable
        """
        if not HTTPX_AVAILABLE:
            return None

        async with self._lock:
            if provider_name not in self._clients:
                self._clients[provider_name] = await self._create_client(
                    provider_name, base_url, headers, config
                )
                self._metrics[provider_name] = PoolMetrics()

            return self._clients[provider_name]

    async def _create_client(
        self,
        provider_name: str,
        base_url: str,
        headers: Dict[str, str] = None,
        config: PoolConfig = None,
    ) -> "httpx.AsyncClient":
        """Create a new HTTP client with connection pooling."""
        cfg = config or self.default_config
        self._configs[provider_name] = cfg

        limits = httpx.Limits(
            max_connections=cfg.max_connections,
            max_keepalive_connections=cfg.max_keepalive_connections,
            keepalive_expiry=cfg.keepalive_expiry,
        )

        timeout = httpx.Timeout(
            connect=cfg.connect_timeout,
            read=cfg.read_timeout,
            write=cfg.write_timeout,
            pool=cfg.pool_timeout,
        )

        client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers or {},
            limits=limits,
            timeout=timeout,
            http2=cfg.http2,
        )

        logger.info(
            "Created connection pool for %s: base_url=%s, http2=%s",
            provider_name,
            base_url,
            cfg.http2,
        )

        return client

    async def request(
        self,
        provider_name: str,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Optional["httpx.Response"]:
        """
        Make an HTTP request using the provider's connection pool.

        Args:
            provider_name: Provider identifier
            method: HTTP method (GET, POST, etc.)
            url: Request URL (relative to base_url)
            **kwargs: Additional arguments for httpx request

        Returns:
            httpx.Response or None if client not available
        """
        client = self._clients.get(provider_name)
        if not client:
            logger.error("No client for provider: %s", provider_name)
            return None

        start_time = time.time()
        metrics = self._metrics.get(provider_name, PoolMetrics())

        try:
            response = await client.request(method, url, **kwargs)
            metrics.requests_sent += 1

            # Update response time (rolling average)
            response_time_ms = (time.time() - start_time) * 1000
            metrics.avg_response_time_ms = (
                metrics.avg_response_time_ms * (metrics.requests_sent - 1)
                + response_time_ms
            ) / metrics.requests_sent

            return response

        except Exception as e:
            metrics.requests_failed += 1
            logger.error("Request to %s failed: %s", provider_name, e)
            raise

    def get_metrics(self, provider_name: str = None) -> Dict[str, Any]:
        """
        Get connection pool metrics.

        Args:
            provider_name: Specific provider or None for all

        Returns:
            Dict of metrics
        """
        if provider_name:
            metrics = self._metrics.get(provider_name)
            if metrics:
                return {
                    "provider": provider_name,
                    "requests_sent": metrics.requests_sent,
                    "requests_failed": metrics.requests_failed,
                    "avg_response_time_ms": round(metrics.avg_response_time_ms, 2),
                    "uptime_seconds": time.time() - metrics.pool_created_at,
                }
            return {}

        # Return all providers
        return {
            name: self.get_metrics(name) for name in self._metrics.keys()
        }

    async def close_client(self, provider_name: str) -> None:
        """Close a specific provider's connection pool."""
        async with self._lock:
            if provider_name in self._clients:
                await self._clients[provider_name].aclose()
                del self._clients[provider_name]
                logger.info("Closed connection pool for %s", provider_name)

    async def close_all(self) -> None:
        """Close all connection pools."""
        async with self._lock:
            for name, client in self._clients.items():
                try:
                    await client.aclose()
                    logger.debug("Closed connection pool for %s", name)
                except Exception as e:
                    logger.warning("Error closing pool for %s: %s", name, e)

            self._clients.clear()
            logger.info("All connection pools closed")


# Global connection pool manager (lazy initialization)
_pool_manager: ConnectionPoolManager = None
_pool_lock = asyncio.Lock()


async def get_connection_pool_manager(
    config: PoolConfig = None,
) -> ConnectionPoolManager:
    """
    Get or create the global connection pool manager.

    Args:
        config: Optional configuration (only used on first call)

    Returns:
        ConnectionPoolManager singleton instance
    """
    global _pool_manager
    if _pool_manager is None:
        async with _pool_lock:
            if _pool_manager is None:
                _pool_manager = ConnectionPoolManager(config)
    return _pool_manager


__all__ = [
    "ConnectionPoolManager",
    "PoolConfig",
    "PoolMetrics",
    "get_connection_pool_manager",
]
