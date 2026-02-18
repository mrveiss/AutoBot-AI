# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics Middleware for AutoBot
Automatically tracks API calls for pattern analysis and performance monitoring
"""

import asyncio
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class AnalyticsMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically track API calls for analytics"""

    def __init__(self, app, analytics_controller=None):
        """Initialize analytics middleware with optional analytics controller."""
        super().__init__(app)
        self.analytics_controller = analytics_controller
        self.tracked_paths = {"/api/", "/docs", "/redoc"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track API calls and response times"""
        start_time = time.time()
        endpoint = str(request.url.path)
        method = request.method

        # Only track relevant endpoints
        should_track = any(endpoint.startswith(path) for path in self.tracked_paths)

        if not should_track:
            return await call_next(request)

        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # Track errors
            status_code = 500
            logger.error("Error processing %s %s: %s", method, endpoint, e)
            raise

        # Calculate response time
        response_time = time.time() - start_time

        # Track analytics asynchronously (don't block response)
        if self.analytics_controller and hasattr(
            self.analytics_controller, "track_api_call"
        ):
            asyncio.create_task(
                self._track_call_async(endpoint, response_time, status_code, method)
            )

        # Add analytics headers to response
        response.headers["X-Response-Time"] = f"{response_time:.3f}s"
        response.headers["X-Tracked-Analytics"] = "true"

        return response

    async def _track_call_async(
        self, endpoint: str, response_time: float, status_code: int, method: str
    ):
        """Track API call asynchronously"""
        try:
            full_endpoint = f"{method} {endpoint}"
            await self.analytics_controller.track_api_call(
                full_endpoint, response_time, status_code
            )
        except Exception as e:
            # Don't let analytics tracking errors affect the main request
            logger.debug("Analytics tracking failed for %s: %s", endpoint, e)


def create_analytics_middleware(analytics_controller=None):
    """Factory function to create analytics middleware with injected controller."""

    def middleware_factory(app):
        """Create analytics middleware instance for the given app."""
        return AnalyticsMiddleware(app, analytics_controller)

    return middleware_factory
