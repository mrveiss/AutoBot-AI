# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Audit Logging Middleware and Decorators for AutoBot

Provides easy-to-use decorators and FastAPI middleware for automatic
audit logging of security-sensitive operations.

Usage Examples:

    # Decorator for endpoint functions
    @audit_operation("auth.login")
    async def login(request: Request, ...):
        ...

    # Decorator with custom result handling
    @audit_operation("file.delete", result_handler=lambda r: "success" if r else "failed")
    async def delete_file(...):
        ...

    # Manual logging in endpoint
    async def my_endpoint(request: Request):
        await audit_log_from_request(
            request,
            operation="custom.operation",
            result="success",
            resource="/api/custom"
        )
"""

import asyncio
import functools
import time
from typing import Any, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from autobot_shared.logging_manager import get_logger
from constants.api_constants import PATH_API_HEALTH
from middleware.proxy_utils import get_client_ip
from services.audit_logger import AuditResult, get_audit_logger

logger = get_logger(__name__)

# Module-level set to hold references to fire-and-forget background tasks (#1556)
_audit_background_tasks: set = set()

# Reference to the main event loop, set at startup via set_main_event_loop().
# Required so _schedule_audit_log() can submit work from thread-pool contexts
# (sync FastAPI endpoints) where asyncio.get_running_loop() raises RuntimeError.
# See: issue #1568.  The broader asyncio.get_event_loop() deprecation is
# tracked in issue #1752 — this reference avoids calling that deprecated API
# at runtime and instead relies on an explicitly stored loop.
_main_event_loop: asyncio.AbstractEventLoop | None = None


def set_main_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store the main event loop for use in thread-pool audit scheduling.

    Must be called once during application startup (inside the async lifespan
    context), before the app begins serving requests.  Issue #1568.

    Args:
        loop: The running event loop returned by asyncio.get_running_loop().
    """
    global _main_event_loop
    _main_event_loop = loop
    logger.debug("Audit middleware: main event loop registered")


# Issue #380: Module-level frozensets for audit checks
_MODIFYING_HTTP_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})
# Issue #3334: /api/config/ replaced by /api/settings/ — updated sensitive prefix list
_SENSITIVE_PATH_PREFIXES = (
    "/api/auth/",
    "/api/security/",
    "/api/elevation/",
    "/api/files/",
    "/api/settings/",
)


# Operations that should be automatically audited
AUTO_AUDIT_OPERATIONS = {
    # Authentication endpoints
    "/api/auth/login": "auth.login",
    "/api/auth/logout": "auth.logout",
    "/api/auth/check": "auth.permission_check",
    # File operations
    "/api/files/upload": "file.upload",
    "/api/files/download": "file.download",
    "/api/files/delete": "file.delete",
    # Elevation
    "/api/elevation/request": "elevation.request",
    "/api/elevation/authorize": "elevation.authorize",
    "/api/elevation/execute": "elevation.execute",
    # Session management
    "/api/chat/sessions": "session.create",
    "/api/agent-terminal/sessions": "session.create",
    "/api/terminal/sessions": "session.create",
    # Configuration — Issue #3334: consolidated under /api/settings/
    "/api/settings/": "config.update",
    "/api/settings/config": "config.update",
    "/api/settings/backend": "config.update",
}


class AuditMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic audit logging of HTTP requests

    Logs all requests to security-sensitive endpoints automatically.
    Can be configured to log all requests or only specific patterns.
    """

    def __init__(
        self,
        app: ASGIApp,
        audit_all: bool = False,
        exclude_paths: list | None = None,
    ):
        """
        Initialize audit middleware

        Args:
            app: FastAPI application
            audit_all: Log all requests (not just security-sensitive)
            exclude_paths: List of path patterns to exclude from audit
        """
        super().__init__(app)
        self.audit_all = audit_all
        self._background_tasks: set = set()
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/openapi.json",
            PATH_API_HEALTH,
            "/api/metrics",
            "/static",
        ]

    def should_audit(self, path: str, method: str) -> bool:
        """Determine if request should be audited"""
        # Check exclusions
        for excluded in self.exclude_paths:
            if path.startswith(excluded):
                return False

        # Audit all if configured
        if self.audit_all:
            return True

        # Check if path is in auto-audit list
        return path in AUTO_AUDIT_OPERATIONS or self._is_sensitive_operation(path, method)

    def _is_sensitive_operation(self, path: str, method: str) -> bool:
        """Check if operation is security-sensitive"""
        # Methods that modify data (Issue #380: use module-level frozenset)
        if method in _MODIFYING_HTTP_METHODS:
            return True

        # Specific sensitive read operations (Issue #380: use module-level tuple)
        return any(path.startswith(pattern) for pattern in _SENSITIVE_PATH_PREFIXES)

    def _determine_audit_result(self, response) -> AuditResult:
        """Helper for dispatch. Ref: #1088.

        Map HTTP response status code to an AuditResult literal.
        """
        if response.status_code < 300:
            return "success"
        if response.status_code in (401, 403):
            return "denied"
        return "failed"

    def _build_audit_details(self, method: str, response, error_details, request: Request) -> dict:
        """Helper for dispatch. Ref: #1088.

        Build the details dict passed to _log_audit.
        """
        return {
            "method": method,
            "status_code": response.status_code if response else None,
            "error": error_details,
            "user_agent": request.headers.get("user-agent"),
        }

    async def dispatch(self, request: Request, call_next):
        """Process request with audit logging"""
        start_time = time.time()

        # Extract request context
        path = request.url.path
        method = request.method

        # Check if should audit
        if not self.should_audit(path, method):
            return await call_next(request)

        # Get user context from request
        user_id = self._get_user_from_request(request)
        session_id = self._get_session_from_request(request)
        ip_address = self._get_client_ip(request)

        # Determine operation type
        operation = AUTO_AUDIT_OPERATIONS.get(path, f"{method.lower()}.{path.replace('/', '.')}")

        # Process request
        response = None
        result: AuditResult = "success"
        error_details = None

        try:
            response = await call_next(request)
            result = self._determine_audit_result(response)
            return response

        except Exception as e:
            result = "error"
            error_details = str(e)
            raise

        finally:
            performance_ms = (time.time() - start_time) * 1000
            task = asyncio.create_task(
                self._log_audit(
                    operation=operation,
                    result=result,
                    user_id=user_id,
                    session_id=session_id,
                    ip_address=ip_address,
                    resource=path,
                    performance_ms=performance_ms,
                    details=self._build_audit_details(method, response, error_details, request),
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    def _get_user_from_request(self, request: Request) -> str | None:
        """Extract user ID from request"""
        # Try to get user from state (set by auth middleware)
        if hasattr(request.state, "user"):
            user = request.state.user
            if isinstance(user, dict):
                return user.get("username")
            return str(user)

        # Try to get from headers
        return request.headers.get("X-User-ID") or request.headers.get("X-Username")

    def _get_session_from_request(self, request: Request) -> str | None:
        """Extract session ID from request"""
        # Try to get from state
        if hasattr(request.state, "session_id"):
            return request.state.session_id

        # Try to get from headers
        return request.headers.get("X-Session-ID") or request.headers.get("X-Session")

    def _get_client_ip(self, request: Request) -> str | None:
        """Extract client IP from request.

        Delegates to get_client_ip() which only trusts X-Forwarded-For
        when the direct TCP peer is a known reverse proxy (Issue #2252).
        """
        return get_client_ip(request)

    async def _log_audit(
        self,
        operation: str,
        result: AuditResult,
        user_id: str | None,
        session_id: str | None,
        ip_address: str | None,
        resource: str | None,
        performance_ms: float,
        details: dict,
    ):
        """Log audit entry asynchronously"""
        try:
            audit_logger = await get_audit_logger()
            await audit_logger.log(
                operation=operation,
                result=result,
                user_id=user_id,
                session_id=session_id,
                ip_address=ip_address,
                resource=resource,
                performance_ms=performance_ms,
                details=details,
            )
        except Exception as e:
            logger.error("Failed to log audit entry: %s", e)


def _extract_request_context(args: tuple) -> tuple:
    """
    Extract request and user context from function arguments.

    Issue #281: Extracted helper for request context extraction.

    Args:
        args: Function arguments tuple

    Returns:
        Tuple of (request, user_id, session_id, ip_address)
    """
    request = None
    for arg in args:
        if isinstance(arg, Request):
            request = arg
            break

    user_id = None
    session_id = None
    ip_address = None

    if request:
        user_id = _extract_user(request)
        session_id = _extract_session(request)
        ip_address = _extract_ip(request)

    return request, user_id, session_id, ip_address


def _determine_resource(resource_handler: Callable[..., str] | None, args: tuple, kwargs: dict) -> str | None:
    """
    Determine resource from handler if provided.

    Issue #281: Extracted helper for resource determination.

    Args:
        resource_handler: Optional function to determine resource
        args: Function arguments
        kwargs: Function keyword arguments

    Returns:
        Resource string or None
    """
    if not resource_handler:
        return None

    try:
        return resource_handler(*args, **kwargs)
    except Exception:
        return None


def _schedule_audit_log(
    operation: str,
    result: AuditResult,
    user_id: str | None,
    session_id: str | None,
    ip_address: str | None,
    resource: str | None,
    performance_ms: float,
    error_details: str | None,
) -> None:
    """Schedule audit log entry as a non-blocking background task.

    Handles two calling contexts (issue #1568):
    - Async context (async endpoints / AuditMiddleware.dispatch): uses
      asyncio.create_task() so the task runs on the current loop.
    - Thread-pool context (sync endpoints wrapped by _create_sync_audit_wrapper):
      no running event loop exists in the worker thread, so the coroutine is
      submitted to the main event loop via asyncio.run_coroutine_threadsafe().

    Issue #281: Extracted helper for audit log scheduling.

    Args:
        operation: Operation type
        result: Operation result
        user_id: User identifier
        session_id: Session identifier
        ip_address: Client IP address
        resource: Resource being accessed
        performance_ms: Execution time in milliseconds
        error_details: Error message if any
    """
    coro = _log_audit_async(
        operation=operation,
        result=result,
        user_id=user_id,
        session_id=session_id,
        ip_address=ip_address,
        resource=resource,
        performance_ms=performance_ms,
        details={"error": error_details} if error_details else {},
    )

    try:
        loop = asyncio.get_running_loop()
        # We are inside an async context — schedule as a tracked task.
        task = loop.create_task(coro)
        _audit_background_tasks.add(task)
        task.add_done_callback(_audit_background_tasks.discard)
    except RuntimeError:
        # No running event loop: called from a thread-pool (sync endpoint).
        # Submit the coroutine to the main event loop stored at startup.
        if _main_event_loop is None or _main_event_loop.is_closed():
            logger.warning("Audit log dropped for %s: main event loop unavailable", operation)
            return
        asyncio.run_coroutine_threadsafe(coro, _main_event_loop)


def _create_async_audit_wrapper(
    func: Callable,
    operation: str,
    result_handler: Callable[[Any], AuditResult] | None,
    resource_handler: Callable[..., str] | None,
) -> Callable:
    """
    Create async wrapper function with audit logging.

    Issue #281: Extracted helper for async wrapper creation.

    Args:
        func: Function to wrap
        operation: Operation type for audit
        result_handler: Optional result handler
        resource_handler: Optional resource handler

    Returns:
        Wrapped async function
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        """Async wrapper that executes function with audit logging and timing."""
        start_time = time.time()

        # Extract context (Issue #281: uses helper)
        request, user_id, session_id, ip_address = _extract_request_context(args)

        result: AuditResult = "success"
        error_details = None

        try:
            return_value = await func(*args, **kwargs)
            result = result_handler(return_value) if result_handler else "success"
            return return_value

        except Exception as e:
            result = "error"
            error_details = str(e)
            raise

        finally:
            performance_ms = (time.time() - start_time) * 1000
            resource = _determine_resource(resource_handler, args, kwargs)
            _schedule_audit_log(
                operation,
                result,
                user_id,
                session_id,
                ip_address,
                resource,
                performance_ms,
                error_details,
            )

    return async_wrapper


def _create_sync_audit_wrapper(
    func: Callable,
    operation: str,
    result_handler: Callable[[Any], AuditResult] | None,
    resource_handler: Callable[..., str] | None,
) -> Callable:
    """
    Create sync wrapper function with audit logging.

    Issue #281: Extracted helper for sync wrapper creation.

    Args:
        func: Function to wrap
        operation: Operation type for audit
        result_handler: Optional result handler
        resource_handler: Optional resource handler

    Returns:
        Wrapped sync function
    """

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        """Sync wrapper that executes function with audit logging and timing."""
        start_time = time.time()

        result: AuditResult = "success"
        error_details = None

        try:
            return_value = func(*args, **kwargs)
            result = result_handler(return_value) if result_handler else "success"
            return return_value

        except Exception as e:
            result = "error"
            error_details = str(e)
            raise

        finally:
            performance_ms = (time.time() - start_time) * 1000
            resource = _determine_resource(resource_handler, args, kwargs)
            _schedule_audit_log(
                operation,
                result,
                None,
                None,
                None,
                resource,
                performance_ms,
                error_details,
            )

    return sync_wrapper


def audit_operation(
    operation: str,
    result_handler: Callable[[Any], AuditResult] | None = None,
    resource_handler: Callable[..., str] | None = None,
):
    """
    Decorator for audit logging function/endpoint calls.

    Issue #281: Refactored from 146 lines to use extracted helper methods.

    Args:
        operation: Operation type (e.g., "auth.login", "file.delete")
        result_handler: Function to determine result from return value
        resource_handler: Function to determine resource from function args

    Example:
        @audit_operation("auth.login")
        async def login(request: Request, username: str):
            ...

        @audit_operation(
            "file.delete",
            result_handler=lambda r: "success" if r else "failed",
            resource_handler=lambda file_path: file_path
        )
        async def delete_file(file_path: str):
            ...
    """

    def decorator(func: Callable):
        """Create wrapper function with audit logging and result tracking."""
        if asyncio.iscoroutinefunction(func):
            return _create_async_audit_wrapper(func, operation, result_handler, resource_handler)
        else:
            return _create_sync_audit_wrapper(func, operation, result_handler, resource_handler)

    return decorator


async def audit_log_from_request(
    request: Request,
    operation: str,
    result: AuditResult = "success",
    resource: str | None = None,
    user_role: str | None = None,
    details: dict | None = None,
):
    """
    Manual audit logging from within an endpoint

    Args:
        request: FastAPI request object
        operation: Operation type
        result: Operation result
        resource: Resource affected
        user_role: User role override
        details: Additional details

    Example:
        async def my_endpoint(request: Request):
            # ... do work ...
            await audit_log_from_request(
                request,
                operation="custom.operation",
                result="success",
                resource="/api/custom",
                details={"custom_field": "value"}
            )
    """
    audit_logger = await get_audit_logger()

    await audit_logger.log(
        operation=operation,
        result=result,
        user_id=_extract_user(request),
        session_id=_extract_session(request),
        ip_address=_extract_ip(request),
        resource=resource or request.url.path,
        user_role=user_role,
        details=details or {},
    )


# Helper functions
def _extract_user(request: Request) -> str | None:
    """Extract user ID from request"""
    if hasattr(request.state, "user"):
        user = request.state.user
        if isinstance(user, dict):
            return user.get("username")
        return str(user)
    return request.headers.get("X-User-ID") or request.headers.get("X-Username")


def _extract_session(request: Request) -> str | None:
    """Extract session ID from request"""
    if hasattr(request.state, "session_id"):
        return request.state.session_id
    return request.headers.get("X-Session-ID") or request.headers.get("X-Session")


def _extract_ip(request: Request) -> str | None:
    """Extract client IP from request.

    Only trusts X-Forwarded-For when TCP peer is a known reverse proxy
    (Issue #2252).  Delegates to the shared get_client_ip() helper.
    """
    return get_client_ip(request)


async def _log_audit_async(
    operation: str,
    result: AuditResult,
    user_id: str | None,
    session_id: str | None,
    ip_address: str | None,
    resource: str | None,
    performance_ms: float,
    details: dict,
):
    """Async helper for audit logging"""
    try:
        audit_logger = await get_audit_logger()
        await audit_logger.log(
            operation=operation,
            result=result,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            resource=resource,
            performance_ms=performance_ms,
            details=details,
        )
    except Exception as e:
        logger.error("Audit logging failed: %s", e)
