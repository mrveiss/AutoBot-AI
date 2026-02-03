# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Exceptions - Centralized exception classes for chat modules.

This module provides shared exception classes used across chat-related
API modules. Extracted to eliminate code duplication (Issue #292).
"""

import logging
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class AutoBotError(Exception):
    """Base exception class for AutoBot errors."""


class InternalError(AutoBotError):
    """Internal server error with optional details."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize internal error with message and optional details dictionary."""
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ResourceNotFoundError(AutoBotError):
    """Resource not found error."""


class ValidationError(AutoBotError):
    """Validation error."""


class NetworkError(AutoBotError):
    """Base class for network-related errors."""

    def __init__(
        self,
        message: str,
        service: Optional[str] = None,
        url: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize network error with message, service name, URL, and details."""
        self.message = message
        self.service = service
        self.url = url
        self.details = details or {}
        super().__init__(message)


class ServiceUnavailableError(NetworkError):
    """Raised when an upstream service is unavailable or unreachable."""


class ServiceTimeoutError(NetworkError):
    """Raised when a service request times out."""


class HTTPClientError(NetworkError):
    """Raised for HTTP 4xx client errors from services."""

    def __init__(
        self,
        message: str,
        status_code: int,
        service: Optional[str] = None,
        url: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize HTTP client error with status code and network details."""
        super().__init__(message, service, url, details)
        self.status_code = status_code


class HTTPServerError(NetworkError):
    """Raised for HTTP 5xx server errors from services."""

    def __init__(
        self,
        message: str,
        status_code: int,
        service: Optional[str] = None,
        url: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize HTTP server error with status code and network details."""
        super().__init__(message, service, url, details)
        self.status_code = status_code


class SubprocessError(AutoBotError):
    """Raised when a subprocess operation fails."""

    def __init__(
        self,
        message: str,
        command: Optional[str] = None,
        return_code: Optional[int] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
    ):
        """Initialize subprocess error with command details and output."""
        self.message = message
        self.command = command
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(message)


class FileOperationError(AutoBotError):
    """Raised when a file I/O operation fails."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize file operation error with path, operation type, and details."""
        self.message = message
        self.file_path = file_path
        self.operation = operation
        self.details = details or {}
        super().__init__(message)


def get_error_code(error_type: str) -> str:
    """Get standardized error code for error type."""
    error_codes = {
        "INTERNAL_ERROR": "INTERNAL_ERROR",
        "VALIDATION_ERROR": "VALIDATION_ERROR",
        "NOT_FOUND": "NOT_FOUND",
    }
    return error_codes.get(error_type, "UNKNOWN_ERROR")


def get_exceptions_lazy() -> Tuple[type, type, type, type, Callable[[str], str]]:
    """
    Lazy load exception classes to avoid import errors.

    This function is maintained for backward compatibility with code that
    expects the tuple pattern. New code should import the classes directly.

    Returns:
        Tuple of (AutoBotError, InternalError, ResourceNotFoundError,
                  ValidationError, get_error_code)
    """
    return (
        AutoBotError,
        InternalError,
        ResourceNotFoundError,
        ValidationError,
        get_error_code,
    )


# Export all exception types for convenience
__all__ = [
    "AutoBotError",
    "InternalError",
    "ResourceNotFoundError",
    "ValidationError",
    "NetworkError",
    "ServiceUnavailableError",
    "ServiceTimeoutError",
    "HTTPClientError",
    "HTTPServerError",
    "SubprocessError",
    "FileOperationError",
    "get_error_code",
    "get_exceptions_lazy",
    "log_exception",
]


def log_exception(error: Exception, context: str = "chat") -> None:
    """Simple exception logger replacement."""
    logger.error("[%s] Exception: %s", context, str(error))
