# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Singleton HTTP Client Manager
Provides efficient aiohttp client session management to prevent resource exhaustion

#15641 split this module in three. The session manager itself is
:mod:`autobot_shared.http_client_manager` and the outbound-address policy is
:mod:`autobot_shared.http_egress_guard`; what remains here is the layer the
~115 call sites actually import — the process-wide singleton, its shutdown and
loop-reset hooks, the caller-side signing helper, and the usage examples.

``HTTPClientManager`` is bound in this namespace by the import the singleton
needs, so ``from autobot_shared.http_client import HTTPClientManager`` keeps
resolving exactly as before.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Dict

import aiohttp

from autobot_shared.http_client_manager import HTTPClientManager

# Re-exported, not defined here: the signature formula lives in a stdlib-only module
# so callers that only verify signatures do not inherit this module's aiohttp
# dependency (#12814). Kept importable from here for existing call sites.
from autobot_shared.service_signing import _service_signature

logger = logging.getLogger(__name__)


# Global singleton instance (thread-safe)

_http_client: HTTPClientManager | None = None
_http_client_lock = threading.Lock()


def get_http_client() -> HTTPClientManager:
    """
    Get the global HTTP client manager instance (thread-safe).

    Returns:
        HTTPClientManager: The singleton HTTP client
    """
    global _http_client
    if _http_client is None:
        with _http_client_lock:
            # Double-check after acquiring lock
            if _http_client is None:
                _http_client = HTTPClientManager()
    return _http_client


async def close_http_client() -> None:
    """Close the global HTTP client and cleanup resources."""
    global _http_client
    if _http_client:
        await _http_client.close()
        _http_client = None


def reset_http_client_for_new_loop() -> None:
    """Discard the loop-bound session/manager so the next call recreates them.

    Mirror of ``autobot_shared.redis_client.reset_async_redis_pools`` (#10936):
    call from synchronous code immediately before entering a NEW event loop
    (e.g. a Celery ``worker_process_init`` handler) so the aiohttp
    ``ClientSession`` — which is bound to the loop that created it — is never
    reused across loop boundaries. The old session is discarded, not closed;
    its connections are reclaimed by GC exactly as discarded Redis pools are.

    Limitation (same as ``reset_async_redis_pools``): objects that cached the
    manager instance at construction keep the old, loop-bound one — the reset
    only affects future ``get_http_client()`` / ``HTTPClientManager()`` calls.

    Issue #11637.
    """
    global _http_client
    with _http_client_lock:
        _http_client = None
        with HTTPClientManager._instance_lock:
            HTTPClientManager._instance = None
            # A contended asyncio.Lock binds permanently to the loop that
            # contended it — rebind so the new loop gets a fresh lock.
            HTTPClientManager._lock = asyncio.Lock()


def sign_request(
    service_id: str,
    service_key: str,
    method: str,
    path: str,
    timestamp: int,
) -> Dict[str, str]:
    """
    Generate HMAC-SHA256 authentication headers for service-to-service requests.

    Produces the three headers that ``ServiceAuthManager.validate_signature``
    expects on the receiving end:

    * ``X-Service-ID``        — caller's service identifier
    * ``X-Service-Signature`` — HMAC-SHA256 over ``service_id:method:path:timestamp``
    * ``X-Service-Timestamp`` — Unix epoch seconds as a decimal string

    This is a pure, synchronous function with no I/O — safe to call from any
    async or sync context.

    Args:
        service_id: This service's identifier (e.g. ``'main-backend'``).
        service_key: 256-bit hex-encoded secret shared with the destination.
        method: HTTP method in upper-case (e.g. ``'GET'``, ``'POST'``).
        path: URL path component only (e.g. ``'/api/inference'``).
        timestamp: Unix timestamp (seconds).  Must be within the receiver's
            replay-attack window (default ±300 s).

    Returns:
        Dict mapping header name → value, ready to merge into request headers.
    """
    signature = _service_signature(service_id, method, path, timestamp, service_key)
    return {
        "X-Service-ID": service_id,
        "X-Service-Signature": signature,
        "X-Service-Timestamp": str(timestamp),
    }


# Example usage patterns for migration
async def example_usage() -> None:
    """Example of how to use the HTTP client manager."""

    # Get the singleton client
    http_client = get_http_client()

    # Simple GET request
    try:
        data = await http_client.get_json("https://api.example.com/data")
        logger.info("Received data: %s", data)
    except aiohttp.ClientError as e:
        logger.error("Request failed: %s", e)

    # POST request with JSON
    try:
        response_data = await http_client.post_json("https://api.example.com/submit", json_data={"key": "value"})
        logger.info("Response: %s", response_data)
    except aiohttp.ClientError as e:
        logger.error("Request failed: %s", e)

    # Manual request with custom options. The raw-response path is
    # caller-owned: balance the active-request counter in a finally (#12981),
    # or use tracked_request() when the response fits in a single block.
    try:
        response = await http_client.get("https://api.example.com/stream", timeout=aiohttp.ClientTimeout(total=60))
        try:
            async with response:
                async for chunk in response.content.iter_chunked(1024):
                    # Process streaming data
                    pass
        finally:
            await http_client.decrement_active()
    except Exception as e:
        logger.error("Streaming failed: %s", e)

    # Get statistics
    stats = http_client.get_stats()
    logger.info("HTTP client stats: %s", stats)


# Decorator for automatic session management
def with_http_client(func):
    """Decorator to inject HTTP client into async functions."""

    async def wrapper(*args, **kwargs):
        """Async wrapper that injects HTTP client into decorated function."""
        http_client = get_http_client()
        return await func(*args, http_client=http_client, **kwargs)

    return wrapper
