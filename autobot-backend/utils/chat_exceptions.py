# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
chat_exceptions — re-exports from the canonical exceptions module.

This module previously defined a parallel AutoBotError hierarchy alongside
autobot-backend/exceptions.py. Both trees have been unified under exceptions.py
(GitHub #6521). This shim re-exports all names so existing imports continue to
work without change; new code should import directly from ``exceptions``.
"""

from exceptions import (  # noqa: F401
    AutoBotError,
    FileOperationError,
    HTTPClientError,
    HTTPServerError,
    InternalError,
    NetworkError,
    ResourceNotFoundError,
    ServiceTimeoutError,
    ServiceUnavailableError,
    SubprocessError,
    ValidationError,
    get_error_code,
    get_exceptions_lazy,
    log_exception,
)

__all__ = [
    "AutoBotError",
    "FileOperationError",
    "HTTPClientError",
    "HTTPServerError",
    "InternalError",
    "NetworkError",
    "ResourceNotFoundError",
    "ServiceTimeoutError",
    "ServiceUnavailableError",
    "SubprocessError",
    "ValidationError",
    "get_error_code",
    "get_exceptions_lazy",
    "log_exception",
]
