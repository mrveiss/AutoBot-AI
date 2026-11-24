# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Analytics Middleware for AutoBot
Automatically tracks API calls for pattern analysis and performance monitoring

Issue #9035: Respects telemetry opt-out configuration
"""

import asyncio
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from autobot_shared.logging_manager import get_logger
from services.telemetry_settings import get_telemetry_settings

logger = get_logger(__name__)


class AnalyticsMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically track API calls for analytics"""

    def __init__(self, app, analytics_controller=None):
        """Initialize analytics middleware with optional analytics controller."""
        super().__init__(app)
        self.analytics_controller = analytics_controller
        self.tracked_paths = {"/api/", "/docs", "/redoc"}
        self._background_tasks: set = set()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track API calls and response times (Issue #9035: respects the telemetry opt-out)."""
        # The persisted opt-out, read per request so an admin's choice applies at once (#9035, #21684)
        if not get_telemetry_settings()["enabled"]:
            return await call_next(request)

        endpoint = str(request.url.path)
        if not any(endpoint.startswith(path) for path in self.tracked_paths):
            return await call_next(request)

        start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error("Error processing %s %s: %s", request.method, endpoint, e)
            self._track(request, endpoint, time.time() - start_time, 500)
            raise

        response_time = time.time() - start_time
        self._track(request, endpoint, response_time, response.status_code)
        response.headers["X-Response-Time"] = f"{response_time:.3f}s"
        response.headers["X-Tracked-Analytics"] = "true"
        return response

    def _track(self, request: Request, endpoint: str, response_time: float, status_code: int) -> None:
        """Record one call in the background, keyed by the route template when routing resolved one."""
        if not (self.analytics_controller and hasattr(self.analytics_controller, "track_api_call")):
            return
        route = request.scope.get("route")
        template = getattr(route, "path", None) or endpoint
        task = asyncio.create_task(self._track_call_async(template, response_time, status_code, request.method))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _track_call_async(self, endpoint: str, response_time: float, status_code: int, method: str):
        """Track API call asynchronously"""
        try:
            full_endpoint = f"{method} {endpoint}"
            await self.analytics_controller.track_api_call(full_endpoint, response_time, status_code)
        except Exception as e:
            # Don't let analytics tracking errors affect the main request
            logger.debug("Analytics tracking failed for %s: %s", endpoint, e)


def create_analytics_middleware(analytics_controller=None):
    """Factory function to create analytics middleware with injected controller."""

    def middleware_factory(app):
        """Create analytics middleware instance for the given app."""
        return AnalyticsMiddleware(app, analytics_controller)

    return middleware_factory
