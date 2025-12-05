# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Distributed Tracing Middleware for FastAPI (Issue #57)

ASGI middleware that adds OpenTelemetry distributed tracing to all requests.
Provides:
- Automatic span creation for each request
- Request/response attribute capture
- Error tracking and exception recording
- Trace context propagation headers
- Performance timing metrics

This middleware complements the FastAPIInstrumentor by adding
AutoBot-specific attributes and custom trace handling.
"""

import logging
import time
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from opentelemetry.trace import SpanKind, Status, StatusCode

from backend.services.tracing_service import get_tracing_service

logger = logging.getLogger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for distributed tracing with OpenTelemetry.

    Adds AutoBot-specific tracing attributes to each request span,
    including timing, user context, and service identification.
    """

    # Paths to exclude from detailed tracing (health checks, metrics, etc.)
    EXCLUDED_PATHS = {
        "/health",
        "/api/health",
        "/metrics",
        "/api/metrics",
        "/favicon.ico",
        "/static",
    }

    def __init__(self, app, service_name: str = "autobot-backend"):
        """
        Initialize tracing middleware.

        Args:
            app: ASGI application
            service_name: Name of this service for trace attribution
        """
        super().__init__(app)
        self.service_name = service_name
        self.tracing = get_tracing_service()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """
        Process request with distributed tracing.

        Args:
            request: The incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response from the handler
        """
        # Skip tracing for excluded paths
        path = request.url.path
        if self._should_skip_tracing(path):
            return await call_next(request)

        # Check if tracing is enabled
        if not self.tracing.enabled:
            return await call_next(request)

        # Start timing
        start_time = time.perf_counter()

        # Build span name from method and path
        span_name = f"{request.method} {self._get_route_pattern(request)}"

        # Extract trace context from incoming headers
        # This is handled automatically by the propagator set in tracing_service

        # Create custom attributes for AutoBot
        attributes = {
            "http.method": request.method,
            "http.url": str(request.url),
            "http.host": request.url.hostname or "unknown",
            "http.path": path,
            "http.scheme": request.url.scheme,
            "autobot.service": self.service_name,
            "autobot.request_id": request.headers.get("x-request-id", ""),
        }

        # Add query parameters if present
        if request.url.query:
            attributes["http.query"] = request.url.query

        # Add client IP
        client_ip = self._get_client_ip(request)
        if client_ip:
            attributes["http.client_ip"] = client_ip

        # Add user agent
        user_agent = request.headers.get("user-agent")
        if user_agent:
            attributes["http.user_agent"] = user_agent[:200]  # Truncate long UAs

        response: Optional[Response] = None

        # Use the tracing service's span context manager
        with self.tracing.span(
            span_name,
            kind=SpanKind.SERVER,
            attributes=attributes,
        ) as span:
            try:
                # Call the next handler
                response = await call_next(request)

                # Add response attributes
                if span and span.is_recording():
                    span.set_attribute("http.status_code", response.status_code)

                    # Set span status based on HTTP status
                    if response.status_code >= 500:
                        span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                    elif response.status_code >= 400:
                        span.set_status(Status(StatusCode.ERROR, f"Client error {response.status_code}"))
                    else:
                        span.set_status(Status(StatusCode.OK))

                    # Add content type
                    content_type = response.headers.get("content-type")
                    if content_type:
                        span.set_attribute("http.response_content_type", content_type)

                return response

            except Exception as e:
                # Record the exception in the span
                if span and span.is_recording():
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e)[:500])
                raise

            finally:
                # Record timing
                duration_ms = (time.perf_counter() - start_time) * 1000
                if span and span.is_recording():
                    span.set_attribute("http.duration_ms", duration_ms)

                # Log for debugging if trace is slow
                if duration_ms > 5000:  # 5 second threshold
                    logger.warning(
                        f"Slow request traced: {span_name} took {duration_ms:.2f}ms"
                    )

    def _should_skip_tracing(self, path: str) -> bool:
        """
        Check if the path should skip detailed tracing.

        Args:
            path: Request path

        Returns:
            True if tracing should be skipped
        """
        # Check exact matches
        if path in self.EXCLUDED_PATHS:
            return True

        # Check prefix matches
        for excluded in self.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return True

        return False

    def _get_route_pattern(self, request: Request) -> str:
        """
        Get the route pattern (with path parameters) for span naming.

        Args:
            request: The request object

        Returns:
            Route pattern string (e.g., /api/users/{user_id})
        """
        # Try to get the route from FastAPI's path matching
        if hasattr(request, "scope") and "route" in request.scope:
            route = request.scope.get("route")
            if route and hasattr(route, "path"):
                return route.path

        # Fall back to the actual path (with numeric IDs replaced)
        path = request.url.path

        # Replace numeric path segments with {id} for better aggregation
        import re
        pattern = re.sub(r"/\d+", "/{id}", path)
        return pattern

    def _get_client_ip(self, request: Request) -> Optional[str]:
        """
        Extract client IP from request headers.

        Args:
            request: The request object

        Returns:
            Client IP address or None
        """
        # Check forwarded headers first (for proxy scenarios)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Take the first IP in the chain
            return forwarded.split(",")[0].strip()

        # Check real IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to direct client connection
        if request.client:
            return request.client.host

        return None


def create_tracing_middleware(
    service_name: str = "autobot-backend",
) -> type:
    """
    Factory function to create configured tracing middleware.

    Args:
        service_name: Name of the service

    Returns:
        Configured middleware class
    """
    class ConfiguredTracingMiddleware(TracingMiddleware):
        def __init__(self, app):
            super().__init__(app, service_name=service_name)

    return ConfiguredTracingMiddleware
