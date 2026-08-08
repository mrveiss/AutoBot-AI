# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Singleton HTTP Client Manager
Provides efficient aiohttp client session management to prevent resource exhaustion
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import aiohttp
from aiohttp import ClientSession, ClientTimeout, TCPConnector

# Re-exported, not defined here: the signature formula lives in a stdlib-only module
# so callers that only verify signatures do not inherit this module's aiohttp
# dependency (#12814). Kept importable from here for existing call sites.
from autobot_shared.service_signing import _service_signature

# #12656: import from the canonical source directly. This previously went via
# `constants.threshold_constants`, an autobot-backend module that is itself a
# pure re-export of ssot_constants — so autobot_shared depended on the backend
# to reach its own constants, and could not be imported standalone.
from autobot_shared.ssot_constants import TimingConstants

logger = logging.getLogger(__name__)


class EgressBlockedError(ValueError):
    """Raised when a guarded request targets an address egress policy forbids."""


async def _assert_egress_allowed(url: str, *, allow_private: bool) -> None:
    """Refuse a URL that outbound connector traffic must not reach (#13625).

    Imported lazily so ``http_client`` keeps its stdlib+aiohttp dependency
    surface for callers that never opt in.
    """
    from autobot_shared.url_safety import is_public_url_async

    if not await is_public_url_async(url, allow_private=allow_private):
        raise EgressBlockedError(f"Refusing outbound request to a disallowed address: {url!r}")


class HTTPClientManager:
    """
    Singleton aiohttp ClientSession manager for efficient HTTP requests.
    Prevents creating new ClientSession for each request which causes resource exhaustion.
    """

    _instance: "HTTPClientManager" | None = None
    _instance_lock = threading.Lock()
    _session: ClientSession | None = None
    _lock = asyncio.Lock()

    def __new__(cls):
        """Create or return singleton HTTPClientManager instance (double-checked, #11637)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super(HTTPClientManager, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the HTTP client manager."""
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._session = None
            self._connector: TCPConnector | None = None
            self._closed = False
            self._request_count = 0
            self._error_count = 0
            self._counter_lock = asyncio.Lock()  # Lock for thread-safe counter access

            # Dynamic pool sizing configuration
            self._pool_min = 20  # Minimum pool size
            self._pool_max = 200  # Maximum pool size
            self._current_pool_size = 100  # Start at default
            self._pool_adjustment_interval = TimingConstants.STANDARD_TIMEOUT  # Adjust every 60s
            self._last_adjustment_time: float = 0.0
            self._active_requests = 0  # Track concurrent requests
            self._pending_pool_recreation = False  # Issue #352: Track deferred recreation

    async def get_session(self) -> ClientSession:
        """
        Get or create the singleton aiohttp ClientSession.

        Returns:
            ClientSession: The shared aiohttp session
        """
        if self._closed:
            raise RuntimeError("HTTPClientManager has been closed")

        if self._session is None or self._session.closed:
            async with self._lock:
                # Double-check after acquiring lock
                if self._session is None or self._session.closed:
                    await self._create_session()

        assert self._session is not None  # _create_session() always sets it
        return self._session

    async def _create_session(self) -> None:
        """Create a new aiohttp ClientSession with optimized settings."""
        # Close existing session if any
        if self._session and not self._session.closed:
            await self._session.close()

        # Create connector with dynamic connection pooling
        self._connector = TCPConnector(
            limit=self._current_pool_size,  # Dynamic pool size
            limit_per_host=min(30, self._current_pool_size // 3),  # 1/3 of total pool
            ttl_dns_cache=300,  # DNS cache timeout
            enable_cleanup_closed=True,
        )

        # Create session with timeout and connector
        timeout = ClientTimeout(
            total=30,  # Total timeout
            connect=5,  # Connection timeout
            sock_read=10,  # Socket read timeout
        )

        self._session = ClientSession(
            connector=self._connector,
            timeout=timeout,
            headers={"User-Agent": "AutoBot/1.0"},
        )

        logger.info(f"Created new aiohttp ClientSession with pool size: {self._current_pool_size}")

    def _calculate_new_pool_size(self, utilization: float, error_rate: float) -> tuple[int, bool]:
        """
        Calculate new pool size based on utilization and error metrics.

        Args:
            utilization: Current pool utilization ratio
            error_rate: Current error rate ratio

        Returns:
            Tuple of (new_pool_size, was_adjusted). Issue #620.
        """
        old_size = self._current_pool_size
        new_size = old_size
        adjusted = False

        # Increase pool if under pressure
        if (utilization > 0.7 or error_rate > 0.05) and old_size < self._pool_max:
            new_size = min(int(old_size * 1.25), self._pool_max)
            adjusted = True
            logger.info(
                f"Increased connection pool: {old_size} → {new_size} "
                f"(utilization: {utilization:.1%}, error_rate: {error_rate:.1%})"
            )

        # Decrease pool if over-provisioned
        elif utilization < 0.2 and error_rate < 0.01 and old_size > self._pool_min:
            new_size = max(int(old_size * 0.85), self._pool_min)
            adjusted = True
            logger.info(f"Decreased connection pool: {old_size} → {new_size} " f"(utilization: {utilization:.1%})")

        return new_size, adjusted

    async def _handle_pool_recreation(self) -> None:
        """
        Handle session recreation after pool size change.

        Issue #352: Fixed race condition - don't recreate while requests in flight.
        Issue #620.
        """
        if self._active_requests > 0:
            self._pending_pool_recreation = True
            logger.info(
                f"Pool size changed to {self._current_pool_size} but "
                f"deferring session recreation ({self._active_requests} active requests)"
            )
        else:
            self._pending_pool_recreation = False
            logger.info("Recreating session with new pool size")
            await self._create_session()

    async def _adjust_pool_size(self) -> None:
        """
        Dynamically adjust connection pool size based on usage patterns.

        Increases pool size if utilization > 70% or error rate > 5%.
        Decreases pool size if utilization < 20% and error rate < 1%.
        """
        current_time = time.time()

        # Only adjust at specified intervals
        if current_time - self._last_adjustment_time < self._pool_adjustment_interval:
            return

        async with self._counter_lock:
            # Calculate utilization metrics
            utilization = self._active_requests / self._current_pool_size if self._current_pool_size > 0 else 0
            error_rate = self._error_count / self._request_count if self._request_count > 0 else 0

            # Issue #620: Use helper for pool size calculation
            new_size, adjusted = self._calculate_new_pool_size(utilization, error_rate)
            self._current_pool_size = new_size
            self._last_adjustment_time = current_time

            # Issue #620: Use helper for session recreation
            if adjusted and self._session and not self._session.closed:
                await self._handle_pool_recreation()

    async def request(
        self,
        method: str,
        url: str,
        *,
        suppress_error_log: bool = False,
        guard_egress: bool | None = None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """
        Make an HTTP request using the shared session.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            suppress_error_log: When True, log request failures at DEBUG instead
                of ERROR. Pass this only from call sites where failure is
                expected and noisy (e.g. health probes to optional services like
                Ollama / NPU worker). Default False so genuine outbound-call
                failures are still surfaced at ERROR everywhere else (#9767).
            guard_egress: Opt in to SSRF validation of *url* (#13625, Rule 8).
                ``None`` (default) means **no guarding**, which is the behaviour
                every existing caller has today. Pass ``False`` to permit only
                public addresses, or ``True`` to additionally permit RFC-1918/ULA
                when the deployment has enabled it — loopback, link-local
                (incl. cloud metadata), multicast, reserved and unspecified are
                refused in both cases.

                Deliberately opt-in rather than default-on: this client is shared
                by ~103 call sites, most of them internal service-to-service
                traffic (NPU workers, SLM nodes) that legitimately targets private
                addresses. Guarding everything here would either break that
                traffic or silently widen egress policy for all of it. Connectors
                and integrations pass this explicitly, so "this request is
                guarded" is visible at the call site.
            **kwargs: Additional arguments for aiohttp request

        Returns:
            ClientResponse: The response object. The active-request slot taken
                by this call is **caller-owned** on the success path — the
                caller MUST call ``decrement_active()`` once the response is
                fully consumed. Failures decrement here, before raising.

        Note: For streaming responses, caller should use increment_active()/decrement_active()
        to prevent pool recreation during streaming.

        Issue #12981: prefer ``tracked_request()`` (or the ``*_json()`` helpers
        built on it) unless you genuinely need to hold a raw response open
        beyond a single block — it balances the counter for you and therefore
        cannot be forgotten.
        """
        if guard_egress is not None:
            # A guard on the initial URL alone is worthless: aiohttp follows
            # redirects by default, so one 302 reaches anything the guard just
            # refused — including cloud metadata (#13625). Refuse redirects on
            # guarded requests instead of validating a URL we then abandon.
            if kwargs.get("allow_redirects"):
                raise ValueError(
                    "guard_egress cannot be combined with allow_redirects=True — a redirect escapes the check. "
                    "Use autobot_shared.security.ssrf_guard.pinned_request_with_redirects, which re-validates "
                    "and re-pins every hop."
                )
            kwargs["allow_redirects"] = False
            await _assert_egress_allowed(url, allow_private=guard_egress)

        # Check if pool adjustment needed (non-blocking)
        asyncio.create_task(self._adjust_pool_size())

        session = await self.get_session()

        # Track active requests for utilization calculation
        await self.increment_active()

        # Issue #697: Inject W3C trace context into outgoing headers
        try:
            from opentelemetry.propagate import inject

            headers = kwargs.pop("headers", {}) or {}
            inject(headers)
            kwargs["headers"] = headers
        except ImportError:
            pass  # OTel not installed, skip propagation

        try:
            response = await session.request(method, url, **kwargs)
            return response
        except Exception as e:
            async with self._counter_lock:
                self._error_count += 1
                # Also decrement active on error since we're not returning response
                self._active_requests = max(0, self._active_requests - 1)
            # Default to ERROR so genuine outbound-call failures are visible.
            # Health-probe call sites opt out via suppress_error_log=True to avoid
            # spamming for expected failures against optional services (#9767).
            if suppress_error_log:
                logger.debug("HTTP request failed: %s", e)
            else:
                logger.error("HTTP request failed: %s", e)
            raise

    async def increment_active(self) -> None:
        """
        Increment the active-request counter (thread-safe).

        Issue #11656: extracted from ``request()`` so both ``request()`` and
        ``tracked_session()`` share the SAME counter-increment mechanism
        instead of duplicating the lock/increment logic.
        """
        async with self._counter_lock:
            self._request_count += 1
            self._active_requests += 1

    @asynccontextmanager
    async def tracked_session(self) -> AsyncIterator[ClientSession]:
        """
        Async context manager for raw-session access that participates in
        active-request tracking.

        Issue #11656: callers using the raw ``get_session()`` (e.g. the Jina
        fetch in ``media/link/pipeline.py``) were invisible to the
        pool-recreation guard in ``_handle_pool_recreation()`` — a resize
        driven by concurrent ``request()`` traffic could close the shared
        session mid-flight. This helper increments/decrements the SAME
        ``_active_requests`` counter that ``request()`` uses (via
        ``increment_active()``/``decrement_active()``), so deferred pool
        recreation now also accounts for in-flight raw-session users.

        Usage:
            async with http_client.tracked_session() as session:
                async with session.get(url) as response:
                    ...

        Exception-safe: the counter is always decremented, even if the
        caller raises.
        """
        await self.increment_active()
        try:
            session = await self.get_session()
            yield session
        finally:
            await self.decrement_active()

    async def decrement_active(self) -> None:
        """
        Decrement active request counter and potentially trigger deferred pool recreation.

        Issue #680: Call this when a streaming response is fully consumed, not when the
        initial request completes. This prevents pool recreation from closing streaming
        connections mid-stream.

        Usage:
            response = await http_client.post(url, ...)
            try:
                async with response:
                    # stream the response
            finally:
                await http_client.decrement_active()
        """
        should_recreate = False
        async with self._counter_lock:
            self._active_requests = max(0, self._active_requests - 1)
            # Issue #352: Check if we should apply deferred pool recreation
            if (
                self._active_requests == 0
                and self._pending_pool_recreation
                and self._session
                and not self._session.closed
            ):
                self._pending_pool_recreation = False
                should_recreate = True

        # Issue #352: Apply deferred recreation outside of lock to avoid deadlock
        if should_recreate:
            logger.info("Applying deferred session recreation " f"(new pool size: {self._current_pool_size})")
            await self._create_session()

    @asynccontextmanager
    async def tracked_request(self, method: str, url: str, **kwargs) -> AsyncIterator[aiohttp.ClientResponse]:
        """
        Issue a request and yield a response whose active-request slot is
        released automatically when the block exits.

        Issue #12981: ``request()`` increments ``_active_requests`` on every
        call but only decrements it on the failure path, delegating the
        success-path decrement to the caller. Repo-wide, essentially no caller
        honoured that contract, so the counter only ever grew — permanently
        skewing ``_adjust_pool_size()`` utilisation and making the
        ``_active_requests == 0`` gate in ``decrement_active()`` (deferred pool
        recreation) unreachable.

        This helper owns the FULL lifecycle — request, response body, and the
        counter — so the decrement cannot be forgotten. Use it for any request
        whose response is consumed within a single block; use ``request()``
        plus an explicit ``decrement_active()`` only when the response must
        outlive the block (streaming, #680).

        Usage:
            async with http_client.tracked_request("GET", url) as response:
                response.raise_for_status()
                data = await response.json()

        Exception-safe: the counter is always decremented, even if the caller
        raises. A failure inside ``request()`` itself decrements there, so the
        slot is never released twice.
        """
        # ``guard_egress`` (#13625) passes straight through to ``request``.
        response = await self.request(method, url, **kwargs)
        try:
            async with response:
                yield response
        finally:
            await self.decrement_active()

    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """
        Convenience method for GET requests.

        Returns a raw caller-owned response: call ``decrement_active()`` when
        it is fully consumed, or prefer ``tracked_request("GET", ...)`` which
        balances the counter for you (#12981).
        """
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """
        Convenience method for POST requests.

        Returns a raw caller-owned response: call ``decrement_active()`` when
        it is fully consumed, or prefer ``tracked_request("POST", ...)`` which
        balances the counter for you (#12981).
        """
        return await self.request("POST", url, **kwargs)

    async def get_json(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Make a GET request and return JSON response.

        Owns the full request lifecycle, so the active-request counter is
        balanced automatically (#12981).

        Args:
            url: Target URL
            **kwargs: Additional arguments for request

        Returns:
            Dict containing the JSON response
        """
        async with self.tracked_request("GET", url, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    async def post_json(self, url: str, json_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Make a POST request with JSON data and return JSON response.

        Owns the full request lifecycle, so the active-request counter is
        balanced automatically (#12981).

        Args:
            url: Target URL
            json_data: Data to send as JSON
            **kwargs: Additional arguments for request

        Returns:
            Dict containing the JSON response
        """
        async with self.tracked_request("POST", url, json=json_data, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    async def close(self) -> None:
        """Close the HTTP client session and cleanup resources."""
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
                logger.info(
                    f"Closed HTTP client session. "
                    f"Total requests: {self._request_count}, "
                    f"Errors: {self._error_count}"
                )

            self._session = None
            self._connector = None
            self._closed = True

    def get_stats(self) -> Dict[str, Any]:
        """Get client usage statistics."""
        utilization = self._active_requests / self._current_pool_size if self._current_pool_size > 0 else 0

        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "active_requests": self._active_requests,
            "error_rate": (self._error_count / self._request_count if self._request_count > 0 else 0),
            "session_active": bool(self._session and not self._session.closed),
            "pool_size": {
                "current": self._current_pool_size,
                "min": self._pool_min,
                "max": self._pool_max,
                "utilization": utilization,
            },
        }

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


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
