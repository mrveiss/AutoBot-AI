# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Authentication Logging Middleware for AutoBot
Day 2 Deployment: Logs authentication attempts WITHOUT blocking requests

DEPLOYMENT STRATEGY: Use this middleware file for initial rollout to observe
authentication patterns without impacting service availability.
"""

import structlog
from backend.security.service_auth import validate_service_auth
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()


class ServiceAuthLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs service authentication attempts without enforcing authentication.

    Purpose:
    - Day 2 deployment to observe authentication patterns
    - Identify which services are calling which endpoints
    - Detect missing or invalid authentication headers
    - Build baseline for authentication metrics

    Behavior:
    - ALWAYS allows requests to proceed (no blocking)
    - Logs successful authentication
    - Logs authentication failures with details
    - Does NOT raise exceptions or return error responses
    """

    def _is_exempt_path(self, request: Request) -> bool:
        """Helper for dispatch. Ref: #1088.

        Return True if the request path matches a service-auth exemption.
        """
        skip_paths = [
            "/health",  # Health check (no prefix)
            "/api/health",  # General health check
            "/api/version",  # Version info
            "/docs",  # API documentation
            "/openapi.json",  # OpenAPI spec
            "/api/system/health",  # System health (frontend)
            "/api/monitoring/services/health",  # Service monitoring (frontend)
            "/api/settings",  # User settings (browser auth - with and without trailing slash)
            "/api/frontend-config",  # Frontend configuration
            "/api/chats",  # Chat list and operations (browser auth)
            "/api/chat/",  # Chat session operations (browser auth)
            "/api/terminal/",  # Terminal operations (browser auth)
            "/api/cache/",  # Cache statistics and management
            "/api/npu/",  # NPU worker management and status
        ]
        return any(request.url.path.startswith(path) for path in skip_paths)

    async def _log_auth_result(self, request: Request) -> None:
        """Helper for dispatch. Ref: #1088.

        Attempt service auth validation and log the outcome without raising.
        """
        try:
            service_info = await validate_service_auth(request)
            logger.info(
                "✅ Service auth valid (logging mode)",
                service_id=service_info["service_id"],
                method=request.method,
                path=request.url.path,
                timestamp=service_info["timestamp"],
                mode="logging_only",
            )
        except Exception as e:
            # Log authentication failure but DO NOT block request
            logger.warning(
                "⚠️  Service auth failed (logging only - request allowed)",
                error=str(e),
                method=request.method,
                path=request.url.path,
                headers={
                    "X-Service-ID": request.headers.get("X-Service-ID", "missing"),
                    "X-Service-Signature": (
                        request.headers.get("X-Service-Signature", "missing")[:20]
                        if request.headers.get("X-Service-Signature")
                        else "missing"
                    ),
                    "X-Service-Timestamp": request.headers.get(
                        "X-Service-Timestamp", "missing"
                    ),
                },
                mode="logging_only",
            )

    async def dispatch(self, request: Request, call_next):
        """
        Process request with authentication logging only.

        Args:
            request: FastAPI request object
            call_next: Next middleware in chain

        Returns:
            Response from next middleware (ALWAYS proceeds)
        """
        # Skip authentication for health check, documentation, and frontend endpoints
        # Service auth is for service-to-service calls only, not browser-to-backend
        if self._is_exempt_path(request):
            logger.debug(
                f"Skipping auth check for {request.url.path} (matched exemption)"
            )
            return await call_next(request)

        await self._log_auth_result(request)

        # ALWAYS proceed with request (logging mode)
        return await call_next(request)
