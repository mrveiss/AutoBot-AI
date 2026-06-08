# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
FastAPI Middleware Configuration

Configures all middleware for FastAPI application:
- CORS (Cross-Origin Resource Sharing)
- GZip compression
- Service authentication
"""

from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from autobot_shared.logging_manager import get_logger
from config.manager import get_config_manager
from constants.network_constants import (  # noqa: F401 - used in docstring example
    NetworkConstants,
)

logger = get_logger(__name__)


def configure_cors(app: FastAPI, allow_origins: List[str] | None = None):
    """
    Configure CORS middleware

    Args:
        app: FastAPI application instance
        allow_origins: List of allowed origins (default: load from config)

    Example:
        ```python
        configure_cors(app)
        configure_cors(app, allow_origins=[f"http://localhost:{NetworkConstants.FRONTEND_PORT}"])
        ```
    """
    # Generate from centralized configuration if not provided
    if allow_origins is None:
        config = get_config_manager()
        allow_origins = config.get_cors_origins()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger.info(f"✅ CORS middleware configured with {len(allow_origins)} allowed origins")


def configure_gzip(app: FastAPI, minimum_size: int = 1000):
    """
    Configure GZip compression middleware

    Args:
        app: FastAPI application instance
        minimum_size: Minimum response size to compress (default: 1000 bytes)

    Example:
        ```python
        configure_gzip(app)
        configure_gzip(app, minimum_size=500)
        ```
    """
    app.add_middleware(GZipMiddleware, minimum_size=minimum_size)
    logger.info("✅ GZip middleware configured (minimum size: %s bytes)", minimum_size)


def configure_service_auth(app: FastAPI):
    """
    Configure service authentication middleware

    Attempts to enable ENFORCEMENT MODE first, falls back to LOGGING MODE.
    If neither available, logs warning and continues without auth middleware.

    Args:
        app: FastAPI application instance

    Example:
        ```python
        configure_service_auth(app)
        ```
    """
    # Try ENFORCEMENT MODE
    try:
        from middleware.service_auth_enforcement import (
            enforce_service_auth,
            log_enforcement_status,
        )

        app.add_middleware(BaseHTTPMiddleware, dispatch=enforce_service_auth)
        log_enforcement_status()
        logger.info("✅ Service Authentication Middleware (ENFORCEMENT MODE) enabled")
        return

    except ImportError as e:
        logger.warning("⚠️ Service auth enforcement middleware not available: %s", e)

    # Fallback to LOGGING MODE
    try:
        from middleware.service_auth_logging import ServiceAuthLoggingMiddleware

        app.add_middleware(ServiceAuthLoggingMiddleware)
        logger.info("✅ Service Authentication Middleware (LOGGING MODE - fallback) enabled")
        return

    except ImportError as e2:
        logger.warning("⚠️ Service auth middleware not available: %s", e2)


def configure_audit(app: FastAPI):
    """Configure audit logging middleware.

    Registers AuditMiddleware which captures all authenticated API requests to
    security-sensitive endpoints (modifying methods + sensitive path prefixes).
    If the middleware module is unavailable, logs a warning and continues.

    Issue #3277: wires AuditMiddleware into the FastAPI application.

    Args:
        app: FastAPI application instance

    Example:
        ```python
        configure_audit(app)
        ```
    """
    try:
        from middleware.audit_middleware import AuditMiddleware

        app.add_middleware(AuditMiddleware)
        logger.info("Audit middleware enabled")
    except ImportError as e:
        logger.warning("Audit middleware not available: %s", e)


def configure_llm_awareness(app: FastAPI):
    """
    Configure LLM awareness middleware

    Injects system awareness context (phase, maturity, capabilities) into LLM
    prompts for /api/chat, /api/llm, /api/intelligent-agent, and /api/workflow
    endpoints. If the middleware module is unavailable, logs a warning and
    continues without it.

    Args:
        app: FastAPI application instance

    Example:
        ```python
        configure_llm_awareness(app)
        ```
    """
    try:
        from middleware.llm_awareness_middleware import LLMAwarenessMiddleware

        app.add_middleware(LLMAwarenessMiddleware)
        logger.info("LLM Awareness Middleware enabled")
    except ImportError as e:
        logger.warning("LLM awareness middleware not available: %s", e)


def configure_validation(app: FastAPI):
    """Configure centralised input validation middleware (Issue #3274).

    Registers ValidationMiddleware which:
    - Scans query parameters and JSON request bodies for SQL injection,
      command injection, and path-traversal patterns.
    - Rejects oversized bodies (> 1 MiB) with HTTP 413.
    - Returns ``{"error": ..., "details": ...}`` on any validation failure.

    Must be registered *before* service-auth and route handlers so that
    malicious payloads are rejected at the perimeter.

    Args:
        app: FastAPI application instance

    Example:
        ```python
        configure_validation(app)
        ```
    """
    try:
        from middleware.validation_middleware import ValidationMiddleware

        app.add_middleware(ValidationMiddleware)
        logger.info("Input validation middleware enabled")
    except ImportError as e:
        logger.warning("Input validation middleware not available: %s", e)


def configure_llc_agent_auth(app: FastAPI):
    """Configure LLC agent authentication middleware (GH#8218).

    Registers LLCAgentAuthMiddleware which validates bearer tokens for
    /api/llc/agent/* routes using SHA-256 DB lookup. All other routes are
    unaffected.

    Args:
        app: FastAPI application instance
    """
    try:
        from llc.middleware.agent_auth import LLCAgentAuthMiddleware

        app.add_middleware(LLCAgentAuthMiddleware)
        logger.info("LLC agent auth middleware enabled")
    except ImportError as e:
        logger.warning("LLC agent auth middleware not available: %s", e)


def configure_sunset_legacy_health(app: FastAPI):
    """Issue #6902: telegraph deprecation of legacy /api/<module>/health routes.

    Adds RFC 8594 ``Sunset`` and ``Deprecation`` response headers to every
    legacy module-local /health endpoint so external scrapers see the
    deprecation signal at runtime. The canonical aggregator at
    ``/api/system/health`` and its alias ``/api/health`` are exempted.

    Args:
        app: FastAPI application instance
    """
    try:
        from middleware.sunset_legacy_health import SunsetLegacyHealthMiddleware

        app.add_middleware(SunsetLegacyHealthMiddleware)
        logger.info("Sunset-legacy-health middleware enabled (#6902)")
    except ImportError as e:
        logger.warning("Sunset-legacy-health middleware not available: %s", e)


def configure_middleware(
    app: FastAPI,
    allow_origins: List[str] | None = None,
    gzip_minimum_size: int = 1000,
    enable_service_auth: bool = True,
    enable_llm_awareness: bool = True,
    enable_audit: bool = True,
    enable_validation: bool = True,
):
    """
    Configure all middleware for FastAPI application

    Args:
        app: FastAPI application instance
        allow_origins: List of allowed CORS origins (default: load from config)
        gzip_minimum_size: Minimum size for GZip compression (default: 1000 bytes)
        enable_service_auth: Enable service authentication middleware (default: True)
        enable_llm_awareness: Enable LLM awareness context injection (default: True)
        enable_audit: Enable audit logging middleware (default: True)
        enable_validation: Enable centralised input validation middleware (default: True)

    Example:
        ```python
        from initialization.middleware import configure_middleware

        app = FastAPI()
        configure_middleware(app)
        ```
    """
    logger.info("Configuring middleware...")

    # Configure CORS
    configure_cors(app, allow_origins)

    # Configure GZip compression
    configure_gzip(app, gzip_minimum_size)

    # Configure input validation (Issue #3274) — must be outermost non-CORS
    # middleware so injection patterns are rejected before any handler runs.
    if enable_validation:
        configure_validation(app)

    # Configure Service Authentication (optional)
    if enable_service_auth:
        configure_service_auth(app)

    # Configure Audit Logging (issue #3277) — must be after service auth so
    # user context (request.state.user) is already populated for audit entries.
    if enable_audit:
        configure_audit(app)

    # Configure LLC agent auth (GH#8218) — scoped to /api/llc/agent/* only.
    configure_llc_agent_auth(app)

    # Configure LLM Awareness context injection (optional)
    # Must be registered after service auth so awareness context is applied
    # only to authenticated requests that reach the route handlers.
    if enable_llm_awareness:
        configure_llm_awareness(app)

    # Issue #6902: Sunset/Deprecation headers on legacy /api/<module>/health
    # routes. Registered last so it runs first on the response path and any
    # earlier middleware can still inspect/modify the response body.
    configure_sunset_legacy_health(app)

    logger.info("All middleware configured successfully")


__all__ = [
    "configure_middleware",
    "configure_cors",
    "configure_gzip",
    "configure_service_auth",
    "configure_audit",
    "configure_llm_awareness",
    "configure_validation",
    "configure_llc_agent_auth",
]
