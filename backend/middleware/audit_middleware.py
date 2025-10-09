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
from datetime import datetime
from typing import Callable, Optional, Any, Literal

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.services.audit_logger import get_audit_logger, AuditResult
import logging

logger = logging.getLogger(__name__)


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

    # Configuration
    "/api/config": "config.update",
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
        exclude_paths: Optional[list] = None
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
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/openapi.json",
            "/api/health",
            "/api/metrics",
            "/static"
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
        # Methods that modify data
        if method in ["POST", "PUT", "DELETE", "PATCH"]:
            return True

        # Specific sensitive read operations
        sensitive_patterns = [
            "/api/auth/",
            "/api/security/",
            "/api/elevation/",
            "/api/files/",
            "/api/config/"
        ]

        return any(path.startswith(pattern) for pattern in sensitive_patterns)

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

            # Determine result from response status
            if response.status_code < 300:
                result = "success"
            elif response.status_code == 401 or response.status_code == 403:
                result = "denied"
            elif response.status_code >= 400:
                result = "failed"

            return response

        except Exception as e:
            result = "error"
            error_details = str(e)
            raise

        finally:
            # Calculate performance
            performance_ms = (time.time() - start_time) * 1000

            # Log audit entry (async, non-blocking)
            asyncio.create_task(
                self._log_audit(
                    operation=operation,
                    result=result,
                    user_id=user_id,
                    session_id=session_id,
                    ip_address=ip_address,
                    resource=path,
                    performance_ms=performance_ms,
                    details={
                        "method": method,
                        "status_code": response.status_code if response else None,
                        "error": error_details,
                        "user_agent": request.headers.get("user-agent"),
                    }
                )
            )

    def _get_user_from_request(self, request: Request) -> Optional[str]:
        """Extract user ID from request"""
        # Try to get user from state (set by auth middleware)
        if hasattr(request.state, "user"):
            user = request.state.user
            if isinstance(user, dict):
                return user.get("username")
            return str(user)

        # Try to get from headers
        return request.headers.get("X-User-ID") or request.headers.get("X-Username")

    def _get_session_from_request(self, request: Request) -> Optional[str]:
        """Extract session ID from request"""
        # Try to get from state
        if hasattr(request.state, "session_id"):
            return request.state.session_id

        # Try to get from headers
        return request.headers.get("X-Session-ID") or request.headers.get("X-Session")

    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Extract client IP from request"""
        # Check for proxy headers first
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Get first IP (client)
            return forwarded.split(",")[0].strip()

        # Get from client directly
        if request.client:
            return request.client.host

        return None

    async def _log_audit(
        self,
        operation: str,
        result: AuditResult,
        user_id: Optional[str],
        session_id: Optional[str],
        ip_address: Optional[str],
        resource: Optional[str],
        performance_ms: float,
        details: dict
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
                details=details
            )
        except Exception as e:
            logger.error(f"Failed to log audit entry: {e}")


def audit_operation(
    operation: str,
    result_handler: Optional[Callable[[Any], AuditResult]] = None,
    resource_handler: Optional[Callable[..., str]] = None
):
    """
    Decorator for audit logging function/endpoint calls

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
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()

            # Extract request if available
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            # Get user context
            user_id = None
            session_id = None
            ip_address = None

            if request:
                user_id = _extract_user(request)
                session_id = _extract_session(request)
                ip_address = _extract_ip(request)

            # Execute function
            result: AuditResult = "success"
            resource = None
            error_details = None
            return_value = None

            try:
                return_value = await func(*args, **kwargs)

                # Determine result from return value
                if result_handler:
                    result = result_handler(return_value)
                else:
                    result = "success"

                return return_value

            except Exception as e:
                result = "error"
                error_details = str(e)
                raise

            finally:
                # Calculate performance
                performance_ms = (time.time() - start_time) * 1000

                # Determine resource
                if resource_handler:
                    try:
                        resource = resource_handler(*args, **kwargs)
                    except:
                        resource = None

                # Log audit entry (non-blocking)
                asyncio.create_task(
                    _log_audit_async(
                        operation=operation,
                        result=result,
                        user_id=user_id,
                        session_id=session_id,
                        ip_address=ip_address,
                        resource=resource,
                        performance_ms=performance_ms,
                        details={"error": error_details} if error_details else {}
                    )
                )

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For synchronous functions, create async logging task
            start_time = time.time()

            result: AuditResult = "success"
            error_details = None
            return_value = None

            try:
                return_value = func(*args, **kwargs)

                if result_handler:
                    result = result_handler(return_value)

                return return_value

            except Exception as e:
                result = "error"
                error_details = str(e)
                raise

            finally:
                performance_ms = (time.time() - start_time) * 1000

                # Log asynchronously
                asyncio.create_task(
                    _log_audit_async(
                        operation=operation,
                        result=result,
                        user_id=None,
                        session_id=None,
                        ip_address=None,
                        resource=None,
                        performance_ms=performance_ms,
                        details={"error": error_details} if error_details else {}
                    )
                )

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


async def audit_log_from_request(
    request: Request,
    operation: str,
    result: AuditResult = "success",
    resource: Optional[str] = None,
    user_role: Optional[str] = None,
    details: Optional[dict] = None
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
        details=details or {}
    )


# Helper functions
def _extract_user(request: Request) -> Optional[str]:
    """Extract user ID from request"""
    if hasattr(request.state, "user"):
        user = request.state.user
        if isinstance(user, dict):
            return user.get("username")
        return str(user)
    return request.headers.get("X-User-ID") or request.headers.get("X-Username")


def _extract_session(request: Request) -> Optional[str]:
    """Extract session ID from request"""
    if hasattr(request.state, "session_id"):
        return request.state.session_id
    return request.headers.get("X-Session-ID") or request.headers.get("X-Session")


def _extract_ip(request: Request) -> Optional[str]:
    """Extract client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


async def _log_audit_async(
    operation: str,
    result: AuditResult,
    user_id: Optional[str],
    session_id: Optional[str],
    ip_address: Optional[str],
    resource: Optional[str],
    performance_ms: float,
    details: dict
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
            details=details
        )
    except Exception as e:
        logger.error(f"Audit logging failed: {e}")
