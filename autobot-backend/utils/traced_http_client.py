# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Traced HTTP Client for Cross-VM Communication (Issue #57)

Provides HTTP client utilities that automatically propagate OpenTelemetry
trace context across AutoBot's distributed VM infrastructure.

Wraps the shared ``HTTPClientManager`` singleton (aiohttp) rather than
creating an independent ``httpx.AsyncClient`` per call.  All connections
go through the managed pool, so tracing is layered on top without
bypassing connection limits or pool accounting.

Usage:
    from utils.traced_http_client import TracedHttpClient
    from constants.network_constants import ServiceURLs

    async with TracedHttpClient() as client:
        response = await client.post(
            f"{ServiceURLs.AI_STACK}/api/process",
            json={"data": "payload"}
        )
"""

from contextlib import asynccontextmanager

import aiohttp
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from autobot_shared.http_client import HTTPClientManager, get_http_client
from autobot_shared.logging_manager import get_logger
from constants.network_constants import NetworkConstants
from constants.threshold_constants import TimingConstants

logger = get_logger(__name__)


class TracedHttpClient:
    """
    HTTP client with automatic OpenTelemetry trace context propagation.

    Wraps the shared ``HTTPClientManager`` pool so that all cross-VM calls
    participate in connection pooling, dynamic pool sizing, and W3C trace
    context propagation already implemented in ``HTTPClientManager.request()``.

    The OTel span is opened around the ``HTTPClientManager.request()`` call so
    that timing captured in the span reflects the full round-trip including
    pool-wait time, matching the observable latency from the caller's
    perspective.

    Note: ``HTTPClientManager.request()`` already injects W3C ``traceparent``
    / ``tracestate`` headers via ``opentelemetry.propagate.inject``.  This
    class additionally wraps the call in a CLIENT span, giving callers a
    named span in their trace for each outbound HTTP call.
    """

    # AutoBot VM service mapping using NetworkConstants
    VM_SERVICES = {
        NetworkConstants.MAIN_MACHINE_IP: "autobot-backend",
        NetworkConstants.FRONTEND_VM_IP: "autobot-frontend",
        NetworkConstants.NPU_WORKER_VM_IP: "autobot-npu-worker",
        NetworkConstants.REDIS_VM_IP: "autobot-redis",
        NetworkConstants.AI_STACK_VM_IP: "autobot-ai-stack",
        NetworkConstants.BROWSER_VM_IP: "autobot-browser",
    }

    def __init__(
        self,
        timeout: float = TimingConstants.SHORT_TIMEOUT,
        follow_redirects: bool = True,
        http_client: HTTPClientManager | None = None,
    ):
        """
        Initialize traced HTTP client.

        Args:
            timeout: Per-request timeout in seconds.  Passed as an
                ``aiohttp.ClientTimeout(total=timeout)`` kwarg when callers
                do not supply their own ``timeout`` kwarg.
            follow_redirects: Unused — kept for API compatibility.
                ``HTTPClientManager`` uses the session's default redirect
                behaviour.  Pass ``allow_redirects=False`` in request kwargs
                to disable for a specific call.
            http_client: Optional ``HTTPClientManager`` instance to use.
                Defaults to the process-global singleton from
                ``get_http_client()``.  Inject an alternative only in tests.
        """
        self._timeout = timeout
        self._follow_redirects = follow_redirects
        self._http_client: HTTPClientManager = http_client or get_http_client()

    async def __aenter__(self) -> "TracedHttpClient":
        """Return self — pool lifecycle is managed by HTTPClientManager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """No-op — the shared pool is not closed per TracedHttpClient instance."""

    def _get_target_service(self, url: str) -> str:
        """
        Determine target service name from URL for span labelling.

        Args:
            url: Target URL.

        Returns:
            Human-readable service name or ``'unknown-service'``.
        """
        for ip, service in self.VM_SERVICES.items():
            if ip in url:
                return service
        return "unknown-service"

    def _record_response_attributes(self, span: trace.Span, response: aiohttp.ClientResponse) -> None:
        """
        Record HTTP response attributes on the current span.

        Only ``http.status_code`` is recorded here.  Response body length is
        intentionally omitted: reading ``response.content`` eagerly would break
        streaming responses and is not needed for distributed tracing.

        Args:
            span: Active OTel span.
            response: aiohttp response returned by HTTPClientManager.
        """
        if span.is_recording():
            span.set_attribute("http.status_code", response.status)

    def _record_exception_attributes(self, span: trace.Span, error: Exception) -> None:
        """
        Record exception details on the current span.

        Args:
            span: Active OTel span.
            error: Exception that caused the request to fail.
        """
        if span.is_recording():
            span.record_exception(error)
            span.set_attribute("error.type", type(error).__name__)

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """
        Execute a traced HTTP request via the shared ``HTTPClientManager``.

        Opens an OTel CLIENT span around the pooled ``request()`` call.
        ``HTTPClientManager.request()`` handles W3C trace context injection
        into outgoing headers, so no duplicate inject is performed here.

        Args:
            method: HTTP method in upper-case (``'GET'``, ``'POST'``, …).
            url: Target URL.
            **kwargs: Additional keyword arguments forwarded verbatim to
                ``HTTPClientManager.request()``.  If ``timeout`` is not
                provided, ``aiohttp.ClientTimeout(total=self._timeout)`` is
                inserted automatically.

        Returns:
            ``aiohttp.ClientResponse`` from the shared pool.  The caller is
            responsible for consuming/closing the response (use as async
            context manager or call ``response.release()``).
        """
        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=self._timeout)

        tracer = trace.get_tracer(__name__)
        target_service = self._get_target_service(url)

        with tracer.start_as_current_span(
            f"HTTP {method} {target_service}",
            kind=SpanKind.CLIENT,
            attributes={
                "http.method": method,
                "http.url": url,
                "peer.service": target_service,
            },
        ) as span:
            try:
                response = await self._http_client.request(method, url, **kwargs)
                self._record_response_attributes(span, response)
                return response
            except Exception as e:
                self._record_exception_attributes(span, e)
                raise

    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Execute a traced GET request."""
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Execute a traced POST request."""
        return await self._request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Execute a traced PUT request."""
        return await self._request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Execute a traced PATCH request."""
        return await self._request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Execute a traced DELETE request."""
        return await self._request("DELETE", url, **kwargs)


@asynccontextmanager
async def traced_http_client(
    timeout: float = TimingConstants.SHORT_TIMEOUT,
    follow_redirects: bool = True,
):
    """
    Convenience async context manager for traced HTTP client.

    Usage:
        from constants.network_constants import ServiceURLs

        async with traced_http_client() as client:
            response = await client.get(f"{ServiceURLs.AI_STACK}/api/status")

    Args:
        timeout: Per-request timeout in seconds.
        follow_redirects: Kept for API compatibility (see ``TracedHttpClient``).

    Yields:
        ``TracedHttpClient`` instance backed by the shared pool.
    """
    client = TracedHttpClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
    )
    async with client as c:
        yield c


# Convenience functions for single-call usage
async def traced_get(url: str, **kwargs) -> aiohttp.ClientResponse:
    """Execute a single traced GET request."""
    async with traced_http_client() as client:
        return await client.get(url, **kwargs)


async def traced_post(url: str, **kwargs) -> aiohttp.ClientResponse:
    """Execute a single traced POST request."""
    async with traced_http_client() as client:
        return await client.post(url, **kwargs)


async def traced_put(url: str, **kwargs) -> aiohttp.ClientResponse:
    """Execute a single traced PUT request."""
    async with traced_http_client() as client:
        return await client.put(url, **kwargs)


async def traced_delete(url: str, **kwargs) -> aiohttp.ClientResponse:
    """Execute a single traced DELETE request."""
    async with traced_http_client() as client:
        return await client.delete(url, **kwargs)
