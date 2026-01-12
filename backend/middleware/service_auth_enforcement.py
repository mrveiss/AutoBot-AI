# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Authentication Enforcement Middleware
Enforces service-to-service authentication on internal endpoints
Week 3 Phase 2: Comprehensive endpoint categorization and selective enforcement
"""

import os
from typing import List

import structlog
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from backend.security.service_auth import validate_service_auth

logger = structlog.get_logger()

# ============================================================================
# ENDPOINT CATEGORIZATION
# ============================================================================

# Endpoints that DO NOT require service authentication (frontend-accessible)
EXEMPT_PATHS: List[str] = [
    # Health and version endpoints
    "/health",  # Health check (no /api prefix)
    "/api/health",  # API health check
    "/api/version",  # Version information
    # User-facing chat and conversation endpoints
    "/api/chat",
    "/api/chats",
    "/api/conversations",
    "/api/conversation_files",
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
    # WebSocket connections
    "/ws",
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
    "/api/orchestration",
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
            logger.debug(
                "Path exempt from service auth", path=path, exempt_pattern=exempt
            )
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
            logger.debug(
                "Path requires service auth", path=path, service_pattern=service_path
            )
            return True
    return False


# ============================================================================
# ENFORCEMENT MIDDLEWARE
# ============================================================================


async def _handle_auth_success(
    request: Request, service_info: dict, path: str
) -> None:
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


async def enforce_service_auth(request: Request, call_next):
    """
    Enforce service authentication on required endpoints.

    Issue #665: Refactored to use extracted helper methods.

    Args:
        request: FastAPI request object
        call_next: Next middleware in chain

    Returns:
        Response from downstream middleware/endpoint
    """
    path = request.url.path

    # Check if path is exempt (frontend-accessible)
    if is_path_exempt(path):
        logger.debug("Request allowed - exempt path", path=path, method=request.method)
        return await call_next(request)

    # Check if path requires service authentication
    if requires_service_auth(path):
        logger.info(
            "Enforcing service authentication", path=path, method=request.method
        )

        try:
            service_info = await validate_service_auth(request)
            await _handle_auth_success(request, service_info, path)

        except HTTPException as e:
            return _handle_auth_failure(e, path, request.method)

        except Exception as e:
            logger.error(
                "Service authentication error",
                path=path,
                method=request.method,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise HTTPException(
                status_code=500, detail=f"Authentication system error: {str(e)}"
            )

    # Path doesn't require service auth - allow through
    logger.debug("Request allowed - no auth required", path=path, method=request.method)
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
    mode = os.getenv("SERVICE_AUTH_ENFORCEMENT_MODE", "false").lower()
    return mode == "true"


def log_enforcement_status():
    """Log the current enforcement status at startup."""
    if get_enforcement_mode():
        logger.info(
            "✅ Service Authentication ENFORCEMENT MODE enabled",
            exempt_paths_count=len(EXEMPT_PATHS),
            service_only_paths_count=len(SERVICE_ONLY_PATHS),
        )
        logger.info("Frontend-accessible paths (first 10)", paths=EXEMPT_PATHS[:10])
        logger.info("Service-only paths", paths=SERVICE_ONLY_PATHS)
    else:
        logger.info("ℹ️  Service Authentication in LOGGING MODE (enforcement disabled)")


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
        "exempt_paths": EXEMPT_PATHS,
        "service_only_paths": SERVICE_ONLY_PATHS,
        "total_exempt": len(EXEMPT_PATHS),
        "total_service_only": len(SERVICE_ONLY_PATHS),
    }
