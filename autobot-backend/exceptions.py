# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Custom Exception Hierarchy

This module defines specific exception types for better error handling
and debugging across the AutoBot platform.
"""

from typing import Any, Callable, Dict, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class AutoBotError(Exception):
    """Base exception class for all AutoBot-specific errors."""

    def __init__(self, message: str, details: Dict[str, Any] | None = None):
        """Initialize AutoBotError with message and optional details dictionary."""
        super().__init__(message)
        self.message = message
        self.details = details or {}

    @property
    def safe_message(self) -> str:
        """Return a user-safe error message without internal details."""
        return self.message


class ConfigurationError(AutoBotError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str, config_key: str | None = None):
        """Initialize ConfigurationError with message and optional config key."""
        super().__init__(message)
        self.config_key = config_key
        if config_key:
            self.details["config_key"] = config_key


class LLMError(AutoBotError):
    """Base class for LLM-related errors."""

    def __init__(self, message: str, model: str | None = None):
        """Initialize LLMError with message and optional model name."""
        super().__init__(message)
        self.model = model
        if model:
            self.details["model"] = model


class LLMConnectionError(LLMError):
    """Raised when unable to connect to LLM service."""


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""


class LLMResponseError(LLMError):
    """Raised when LLM returns invalid or unexpected response."""

    def __init__(self, message: str, status_code: int | None = None, **kwargs):
        """Initialize LLMResponseError with message and optional HTTP status code."""
        super().__init__(message, **kwargs)
        self.status_code = status_code
        if status_code:
            self.details["status_code"] = status_code


class WorkflowError(AutoBotError):
    """Base class for workflow-related errors."""

    def __init__(
        self,
        message: str,
        workflow_id: str | None = None,
        step_id: str | None = None,
    ):
        """Initialize WorkflowError with message and optional workflow/step identifiers."""
        super().__init__(message)
        self.workflow_id = workflow_id
        self.step_id = step_id
        if workflow_id:
            self.details["workflow_id"] = workflow_id
        if step_id:
            self.details["step_id"] = step_id


class WorkflowExecutionError(WorkflowError):
    """Raised when workflow execution fails."""


class WorkflowValidationError(WorkflowError):
    """Raised when workflow validation fails."""


class ValidationError(AutoBotError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str | None = None, value: Any | None = None):
        """Initialize ValidationError with message and optional field/value info."""
        super().__init__(message)
        self.field = field
        self.value = value
        if field:
            self.details["field"] = field
        # Don't include actual value in details for security

    @property
    def safe_message(self) -> str:
        """Return a user-safe validation error message."""
        if self.field:
            return f"Invalid value for field '{self.field}'"
        return "Validation failed"


class KnowledgeBaseError(AutoBotError):
    """Base class for knowledge base errors."""


class DatabaseError(KnowledgeBaseError):
    """Raised when database operations fail."""

    def __init__(self, message: str, operation: str | None = None):
        """Initialize DatabaseError with message and optional operation name."""
        super().__init__(message)
        self.operation = operation
        if operation:
            self.details["operation"] = operation


class VectorStoreError(KnowledgeBaseError):
    """Raised when vector store operations fail."""


class AgentError(AutoBotError):
    """Base class for agent-related errors."""

    def __init__(self, message: str, agent_name: str | None = None):
        """Initialize AgentError with message and optional agent name."""
        super().__init__(message)
        self.agent_name = agent_name
        if agent_name:
            self.details["agent_name"] = agent_name


class AgentExecutionError(AgentError):
    """Raised when agent execution fails."""


class AgentTimeoutError(AgentError):
    """Raised when agent execution times out."""


class SecurityError(AutoBotError):
    """Base class for security-related errors."""

    @property
    def safe_message(self) -> str:
        """Never expose security error details to users."""
        return "A security error occurred"


class AuthenticationError(SecurityError):
    """Raised when authentication fails."""


class AuthorizationError(SecurityError):
    """Raised when authorization fails."""


class EncryptionError(SecurityError):
    """Raised when encryption/decryption operations fail."""


class ResourceError(AutoBotError):
    """Base class for resource-related errors."""


class ResourceNotFoundError(ResourceError):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        message: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ):
        """Initialize ResourceNotFoundError with message and resource identifiers."""
        super().__init__(message)
        self.resource_type = resource_type
        self.resource_id = resource_id
        if resource_type:
            self.details["resource_type"] = resource_type
        if resource_id:
            self.details["resource_id"] = resource_id


class ResourceLimitError(ResourceError):
    """Raised when resource limits are exceeded."""

    def __init__(self, message: str, limit: int | None = None, current: int | None = None):
        """Initialize ResourceLimitError with message and limit/current values."""
        super().__init__(message)
        self.limit = limit
        self.current = current
        if limit:
            self.details["limit"] = limit
        if current:
            self.details["current"] = current


class IntegrationError(AutoBotError):
    """Base class for external integration errors."""

    def __init__(self, message: str, service: str | None = None):
        """Initialize IntegrationError with message and optional service name."""
        super().__init__(message)
        self.service = service
        if service:
            self.details["service"] = service


class WebSocketError(AutoBotError):
    """Base class for WebSocket-related errors."""


class InternalError(AutoBotError):
    """Raised for unexpected internal errors."""

    @property
    def safe_message(self) -> str:
        """Never expose internal error details to users."""
        return "An internal error occurred"


class NetworkError(AutoBotError):
    """Base class for network-related errors."""

    def __init__(
        self,
        message: str,
        service: str | None = None,
        url: str | None = None,
        details: Dict[str, Any] | None = None,
    ):
        """Initialize network error with message, service name, URL, and details."""
        super().__init__(message, details)
        self.service = service
        self.url = url
        if service:
            self.details["service"] = service
        if url:
            self.details["url"] = url


class ServiceUnavailableError(NetworkError):
    """Raised when an upstream service is unavailable or unreachable."""


class ServiceTimeoutError(NetworkError):
    """Raised when a service request times out."""


class HTTPClientError(NetworkError):
    """Raised for HTTP 4xx client errors from backend services."""

    def __init__(
        self,
        message: str,
        status_code: int,
        service: str | None = None,
        url: str | None = None,
        details: Dict[str, Any] | None = None,
    ):
        """Initialize HTTP client error with status code and network details."""
        super().__init__(message, service, url, details)
        self.status_code = status_code
        self.details["status_code"] = status_code


class HTTPServerError(NetworkError):
    """Raised for HTTP 5xx server errors from backend services."""

    def __init__(
        self,
        message: str,
        status_code: int,
        service: str | None = None,
        url: str | None = None,
        details: Dict[str, Any] | None = None,
    ):
        """Initialize HTTP server error with status code and network details."""
        super().__init__(message, service, url, details)
        self.status_code = status_code
        self.details["status_code"] = status_code


class SubprocessError(AutoBotError):
    """Raised when a subprocess operation fails."""

    def __init__(
        self,
        message: str,
        command: str | None = None,
        return_code: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ):
        """Initialize subprocess error with command details and output."""
        super().__init__(message)
        self.command = command
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        if command:
            self.details["command"] = command
        if return_code is not None:
            self.details["return_code"] = return_code


class FileOperationError(AutoBotError):
    """Raised when a file I/O operation fails."""

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        operation: str | None = None,
        details: Dict[str, Any] | None = None,
    ):
        """Initialize file operation error with path, operation type, and details."""
        super().__init__(message, details)
        self.file_path = file_path
        self.operation = operation
        if file_path:
            self.details["file_path"] = file_path
        if operation:
            self.details["operation"] = operation


# Error code mapping for API responses
ERROR_CODES = {
    ValidationError: 400,
    AuthenticationError: 401,
    AuthorizationError: 403,
    ResourceNotFoundError: 404,
    ResourceLimitError: 429,
    WorkflowValidationError: 422,
    WorkflowExecutionError: 422,
    LLMTimeoutError: 504,
    InternalError: 500,
}


def get_error_code(error: AutoBotError) -> int:
    """Get the appropriate HTTP status code for an error."""
    for error_class, code in ERROR_CODES.items():
        if isinstance(error, error_class):
            return code
    return 500  # Default to internal server error


def get_exceptions_lazy() -> Tuple[type, type, type, type, Callable[[str], str]]:
    """
    Return the canonical exception classes as a tuple.

    Maintained for backward compatibility with callers that use tuple unpacking.
    New code should import exception classes directly.

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


def log_exception(error: Exception, context: str = "chat") -> None:
    """Log an exception with context label."""
    logger.error("[%s] Exception: %s", context, str(error))
