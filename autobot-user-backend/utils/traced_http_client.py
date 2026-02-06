# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Traced HTTP Client for Cross-VM Communication (Issue #57)

Provides HTTP client utilities that automatically propagate OpenTelemetry
trace context across AutoBot's distributed VM infrastructure.

Usage:
    from src.utils.traced_http_client import TracedHttpClient
    from src.constants.network_constants import ServiceURLs

    async with TracedHttpClient() as client:
        response = await client.post(
            f"{ServiceURLs.AI_STACK}/api/process",
            json={"data": "payload"}
        )
"""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Optional

import httpx
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from src.constants.network_constants import NetworkConstants
from src.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


class TracedHttpClient:
    """
    HTTP client with automatic OpenTelemetry trace context propagation.

    Ensures distributed traces are connected across AutoBot's 5-VM infrastructure.
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
    ):
        """
        Initialize traced HTTP client.

        Args:
            timeout: Request timeout in seconds
            follow_redirects: Whether to follow HTTP redirects
        """
        self._timeout = timeout
        self._follow_redirects = follow_redirects
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "TracedHttpClient":
        """Create async context manager."""
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=self._follow_redirects,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up async context manager."""
        if self._client:
            await self._client.aclose()

    def _get_trace_headers(self) -> Dict[str, str]:
        """
        Get current trace context as HTTP headers.

        Returns:
            Dictionary of trace context headers (traceparent, tracestate, b3, etc.)
        """
        try:
            from opentelemetry.propagate import inject

            headers: Dict[str, str] = {}
            inject(headers)
            return headers
        except Exception as e:
            logger.debug("Could not extract trace context: %s", e)
            return {}

    def _get_target_service(self, url: str) -> str:
        """
        Determine target service name from URL.

        Args:
            url: Target URL

        Returns:
            Service name for span attributes
        """
        for ip, service in self.VM_SERVICES.items():
            if ip in url:
                return service
        return "unknown-service"

    def _prepare_request_headers(self, kwargs: dict) -> dict:
        """
        Prepare request headers by merging trace headers with existing headers.

        Issue #620.

        Args:
            kwargs: Original request kwargs

        Returns:
            Updated kwargs with merged headers
        """
        trace_headers = self._get_trace_headers()
        existing_headers = kwargs.get("headers", {}) or {}
        kwargs["headers"] = {**existing_headers, **trace_headers}
        return kwargs

    def _record_response_attributes(self, span, response: httpx.Response) -> None:
        """
        Record response attributes on the span.

        Issue #620.

        Args:
            span: The current trace span
            response: HTTP response object
        """
        if span.is_recording():
            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute(
                "http.response_content_length",
                len(response.content) if response.content else 0,
            )

    def _record_exception_attributes(self, span, error: Exception) -> None:
        """
        Record exception attributes on the span.

        Issue #620.

        Args:
            span: The current trace span
            error: The exception that occurred
        """
        if span.is_recording():
            span.record_exception(error)
            span.set_attribute("error.type", type(error).__name__)

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """
        Execute traced HTTP request.

        Issue #620: Refactored to use extracted helper methods.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            **kwargs: Additional httpx request arguments

        Returns:
            HTTP response
        """
        if not self._client:
            raise RuntimeError("TracedHttpClient must be used as async context manager")

        kwargs = self._prepare_request_headers(kwargs)
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
                response = await self._client.request(method, url, **kwargs)
                self._record_response_attributes(span, response)
                return response
            except Exception as e:
                self._record_exception_attributes(span, e)
                raise

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Execute traced GET request."""
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Execute traced POST request."""
        return await self._request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        """Execute traced PUT request."""
        return await self._request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> httpx.Response:
        """Execute traced PATCH request."""
        return await self._request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """Execute traced DELETE request."""
        return await self._request("DELETE", url, **kwargs)


@asynccontextmanager
async def traced_http_client(
    timeout: float = TimingConstants.SHORT_TIMEOUT,
    follow_redirects: bool = True,
):
    """
    Convenience async context manager for traced HTTP client.

    Usage:
        from src.constants.network_constants import ServiceURLs

        async with traced_http_client() as client:
            response = await client.get(f"{ServiceURLs.AI_STACK}/api/status")

    Args:
        timeout: Request timeout in seconds
        follow_redirects: Whether to follow HTTP redirects

    Yields:
        TracedHttpClient instance
    """
    client = TracedHttpClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
    )
    async with client as c:
        yield c


# Convenience functions for simple requests
async def traced_get(url: str, **kwargs) -> httpx.Response:
    """Execute a single traced GET request."""
    async with traced_http_client() as client:
        return await client.get(url, **kwargs)


async def traced_post(url: str, **kwargs) -> httpx.Response:
    """Execute a single traced POST request."""
    async with traced_http_client() as client:
        return await client.post(url, **kwargs)


async def traced_put(url: str, **kwargs) -> httpx.Response:
    """Execute a single traced PUT request."""
    async with traced_http_client() as client:
        return await client.put(url, **kwargs)


async def traced_delete(url: str, **kwargs) -> httpx.Response:
    """Execute a single traced DELETE request."""
    async with traced_http_client() as client:
        return await client.delete(url, **kwargs)
