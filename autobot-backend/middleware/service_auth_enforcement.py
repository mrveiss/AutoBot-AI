# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Service Authentication Enforcement Middleware
Enforces service-to-service authentication on internal endpoints
Week 3 Phase 2: Comprehensive endpoint categorization and selective enforcement
"""

import random
import secrets
import time
from collections import defaultdict
from typing import Dict, List

import structlog
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from autobot_shared.ssot_config import config
from constants.api_constants import PATH_API_HEALTH, PATH_HEALTH
from security.service_auth import validate_service_auth

logger = structlog.get_logger()

# Rate limiting tracker for failed auth attempts per IP
_failed_auth_tracker: Dict[str, List[float]] = defaultdict(list)

# ============================================================================
# ENDPOINT CATEGORIZATION
# ============================================================================

# Endpoints that DO NOT require service authentication (frontend-accessible)
EXEMPT_PATHS: List[str] = [
    # Health and version endpoints
    PATH_HEALTH,  # Health check (no /api prefix)
    PATH_API_HEALTH,  # API health check
    "/api/version",  # Version information
    # User-facing chat and conversation endpoints
    "/api/chat",
    "/api/chats",
    "/api/conversations",
    "/api/conversation_files",
    # Live Canvas — JWT-auth endpoints (MVA-359)
    "/api/canvas",
    # Knowledge base user operations
    "/api/knowledge",
    "/api/knowledge_base",
    # Terminal access for users
    "/api/terminal",
    "/api/agent_terminal",
    # User settings and configuration
    "/api/settings",
    "/api/frontend_config",
    # System health and monitoring (public endpoints)
    "/api/system/health",
    "/api/monitoring/services/health",
    "/api/services/status",
    # Cache management (frontend-accessible)
    "/api/cache/",
    # NPU worker management (frontend-accessible via Settings panel)
    "/api/npu/workers",  # NPU worker CRUD operations
    "/api/npu/load-balancing",  # Load balancing configuration
    # User-facing file operations
    "/api/files",
    # LLM configuration and models
    "/api/llm",
    # Prompts management
    "/api/prompts",
    # Memory operations
    "/api/memory",
    # Monitoring dashboards
    "/api/monitoring",
    "/api/metrics",
    "/api/analytics",
    # WebSocket connections (api.websockets router mounted at /api prefix)
    "/api/ws",
    # API documentation
    "/docs",
    "/openapi.json",
    "/redoc",
    # Development endpoints
    "/api/developer",
    "/api/validation_dashboard",
    # Real User Monitoring
    "/api/rum",
    # Infrastructure monitoring (visible to users)
    "/api/infrastructure",
    # Additional user-facing endpoints
    "/api/orchestrator",
    "/api/workflow",
    "/api/embeddings",
    "/api/voice",
    "/api/multimodal",
]

# Endpoints that REQUIRE service authentication (service-to-service only)
SERVICE_ONLY_PATHS: List[str] = [
    # NPU Worker internal endpoints
    "/api/npu/results",
    "/api/npu/heartbeat",
    "/api/npu/status",
    "/api/npu/internal",
    # AI Stack internal endpoints
    "/api/ai-stack/results",
    "/api/ai-stack/heartbeat",
    "/api/ai-stack/models",
    "/api/ai-stack/internal",
    # Browser Service internal endpoints
    "/api/browser/results",
    "/api/browser/screenshots",
    "/api/browser/logs",
    "/api/browser/heartbeat",
    "/api/browser/internal",
    # Internal service communication
    "/api/internal",
    # Service registry (internal only)
    "/api/registry/internal",
    # Audit logging (internal only)
    "/api/audit/internal",
]

# ============================================================================
# PATH MATCHING FUNCTIONS
# ============================================================================


def is_path_exempt(path: str) -> bool:
    """
    Check if path is exempt from service authentication.

    Frontend-accessible endpoints that don't require service auth.

    Args:
        path: Request path

    Returns:
        True if path is exempt from service authentication
    """
    for exempt in EXEMPT_PATHS:
        if path.startswith(exempt):
            logger.debug("Path exempt from service auth", path=path, exempt_pattern=exempt)
            return True
    return False


def requires_service_auth(path: str) -> bool:
    """
    Check if path requires service authentication.

    Internal service-to-service endpoints that must have auth.

    Args:
        path: Request path

    Returns:
        True if path requires service authentication
    """
    for service_path in SERVICE_ONLY_PATHS:
        if path.startswith(service_path):
            logger.debug("Path requires service auth", path=path, service_pattern=service_path)
            return True
    return False


# ============================================================================
# ENFORCEMENT MIDDLEWARE
# ============================================================================


async def _handle_auth_success(request: Request, service_info: dict, path: str) -> None:
    """
    Handle successful service authentication.

    Issue #665: Extracted from enforce_service_auth to reduce function length.

    Args:
        request: FastAPI request object
        service_info: Validated service information
        path: Request path
    """
    request.state.service_id = service_info["service_id"]
    request.state.authenticated = True

    logger.info(
        "Service authenticated successfully",
        service_id=service_info["service_id"],
        path=path,
        method=request.method,
    )


def _handle_auth_failure(e: HTTPException, path: str, method: str) -> JSONResponse:
    """
    Handle service authentication failure.

    Issue #665: Extracted from enforce_service_auth to reduce function length.

    Args:
        e: HTTPException from authentication
        path: Request path
        method: HTTP method

    Returns:
        JSONResponse with error details
    """
    logger.error(
        "Service authentication FAILED - request BLOCKED",
        path=path,
        method=method,
        error=str(e.detail),
        status_code=e.status_code,
    )
    return JSONResponse(
        status_code=e.status_code,
        content={"detail": e.detail, "authenticated": False},
    )


def _has_override_token(request: Request) -> bool:
    """Check for emergency override token to bypass service auth.

    Helper for enforce_service_auth (Issue #255).
    """
    override_token = request.headers.get("X-Override-Token")
    expected = config.service_auth_override_token
    if not override_token or not expected:
        return False
    return secrets.compare_digest(override_token, expected)


def _get_enforcement_percentage() -> int:
    """Get circuit breaker enforcement percentage (0-100).

    Helper for enforce_service_auth (Issue #255).
    """
    return int(config.service_auth_circuit_breaker_percentage)


def _should_enforce_by_circuit_breaker() -> bool:
    """Determine if request should be enforced based on circuit breaker.

    Helper for enforce_service_auth (Issue #255).
    """
    pct = _get_enforcement_percentage()
    if pct >= 100:
        return True
    if pct <= 0:
        return False
    return random.randint(1, 100) <= pct  # nosec B311 - percentage-based sampling gate, not cryptographic


def _is_rate_limited(ip: str) -> bool:
    """Check if IP is rate-limited due to excessive auth failures.

    Helper for enforce_service_auth (Issue #255).
    """
    window = int(config.service_auth_rate_limit_window)
    max_failures = int(config.service_auth_rate_limit_max_failures)
    now = time.time()
    cutoff = now - window
    _failed_auth_tracker[ip] = [t for t in _failed_auth_tracker[ip] if t > cutoff]
    return len(_failed_auth_tracker[ip]) >= max_failures


def _record_failed_auth(ip: str) -> None:
    """Record a failed authentication attempt for rate limiting.

    Helper for enforce_service_auth (Issue #255).
    """
    _failed_auth_tracker[ip].append(time.time())


async def _handle_override_bypass(request: Request, path: str):
    """Log and allow override token bypass.

    Helper for enforce_service_auth (Issue #255).
    """
    logger.warning(
        "Override token used - bypassing service auth",
        path=path,
        method=request.method,
        ip=request.client.host if request.client else "unknown",
    )


async def _enforce_auth_on_path(request: Request, path: str):
    """Enforce authentication on a service-only path.

    Helper for enforce_service_auth (Issue #255).
    """
    client_ip = request.client.host if request.client else "unknown"

    if _is_rate_limited(client_ip):
        logger.warning("Rate limit exceeded", ip=client_ip, path=path)
        raise HTTPException(status_code=429, detail="Too many auth failures")

    try:
        service_info = await validate_service_auth(request)
        await _handle_auth_success(request, service_info, path)
    except HTTPException:
        _record_failed_auth(client_ip)
        raise


async def _log_only_auth_on_path(request: Request, path: str) -> None:
    """Validate service auth and log the result without blocking the request.

    Used when SERVICE_AUTH_ENFORCEMENT_MODE is disabled (logging mode).
    Mirrors ServiceAuthLoggingMiddleware behavior so the transition from
    logging to enforcement mode is a single env-var flip.

    Args:
        request: FastAPI request object
        path: Request path (used for structured logging)
    """
    try:
        service_info = await validate_service_auth(request)
        request.state.service_id = service_info["service_id"]
        request.state.authenticated = True
        logger.info(
            "Service auth valid (logging mode - not enforced)",
            service_id=service_info["service_id"],
            path=path,
            method=request.method,
        )
    except HTTPException as e:
        logger.warning(
            "Service auth failed (logging mode - request allowed)",
            path=path,
            method=request.method,
            error=str(e.detail),
            headers={
                "X-Service-ID": request.headers.get("X-Service-ID", "missing"),
                "X-Service-Signature": (
                    request.headers.get("X-Service-Signature", "missing")[:20]
                    if request.headers.get("X-Service-Signature")
                    else "missing"
                ),
                "X-Service-Timestamp": request.headers.get("X-Service-Timestamp", "missing"),
            },
        )


async def enforce_service_auth(request: Request, call_next):
    """
    Enforce service authentication on required endpoints.

    When SERVICE_AUTH_ENFORCEMENT_MODE=true (default): blocks unauthenticated
    requests to service-only paths with 401/429 responses.

    When SERVICE_AUTH_ENFORCEMENT_MODE=false: logs auth results without
    blocking (logging mode) — use during initial rollout to validate services
    before activating enforcement.

    Supports override token, circuit breaker, and rate limiting (Issue #255).

    Args:
        request: FastAPI request object
        call_next: Next middleware in chain

    Returns:
        Response from downstream middleware/endpoint
    """
    path = request.url.path

    if is_path_exempt(path):
        return await call_next(request)

    if requires_service_auth(path):
        if not get_enforcement_mode():
            await _log_only_auth_on_path(request, path)
            return await call_next(request)

        if _has_override_token(request):
            await _handle_override_bypass(request, path)
            return await call_next(request)

        if not _should_enforce_by_circuit_breaker():
            logger.debug("Circuit breaker: request allowed", path=path)
            return await call_next(request)

        try:
            await _enforce_auth_on_path(request, path)
        except HTTPException as e:
            return _handle_auth_failure(e, path, request.method)

    return await call_next(request)


# ============================================================================
# CONFIGURATION HELPERS
# ============================================================================


def get_enforcement_mode() -> bool:
    """
    Check if service authentication enforcement mode is enabled.

    Returns:
        True if enforcement mode is active
    """
    mode = config.service_auth_enforcement_mode.lower()
    return mode == "true"


def log_enforcement_status():
    """Log the current enforcement status at startup."""
    if get_enforcement_mode():
        logger.info(
            "Service Authentication ENFORCEMENT MODE enabled",
            exempt_paths_count=len(EXEMPT_PATHS),
            service_only_paths_count=len(SERVICE_ONLY_PATHS),
            circuit_breaker_pct=_get_enforcement_percentage(),
            override_token_set=bool(config.service_auth_override_token),
        )
        logger.info("Service-only paths", paths=SERVICE_ONLY_PATHS)
    else:
        logger.info("Service Authentication in LOGGING MODE (enforcement disabled)")


# ============================================================================
# ENDPOINT INFORMATION ENDPOINT
# ============================================================================


def get_endpoint_categories() -> dict:
    """
    Get endpoint categorization information.

    Useful for documentation and debugging.

    Returns:
        Dict with endpoint categories and enforcement status
    """
    return {
        "enforcement_mode": get_enforcement_mode(),
        "circuit_breaker_percentage": _get_enforcement_percentage(),
        "override_token_configured": bool(config.service_auth_override_token),
        "rate_limit_max_failures": int(config.service_auth_rate_limit_max_failures),
        "exempt_paths": EXEMPT_PATHS,
        "service_only_paths": SERVICE_ONLY_PATHS,
        "total_exempt": len(EXEMPT_PATHS),
        "total_service_only": len(SERVICE_ONLY_PATHS),
    }
