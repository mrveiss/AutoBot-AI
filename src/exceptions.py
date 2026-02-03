# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Custom Exception Hierarchy

This module defines specific exception types for better error handling
and debugging across the AutoBot platform.
"""

from typing import Any, Dict, Optional


class AutoBotError(Exception):
    """Base exception class for all AutoBot-specific errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
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

    def __init__(self, message: str, config_key: Optional[str] = None):
        """Initialize ConfigurationError with message and optional config key."""
        super().__init__(message)
        self.config_key = config_key
        if config_key:
            self.details["config_key"] = config_key


class LLMError(AutoBotError):
    """Base class for LLM-related errors."""

    def __init__(self, message: str, model: Optional[str] = None):
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

    def __init__(self, message: str, status_code: Optional[int] = None, **kwargs):
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
        workflow_id: Optional[str] = None,
        step_id: Optional[str] = None,
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

    def __init__(
        self, message: str, field: Optional[str] = None, value: Optional[Any] = None
    ):
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

    def __init__(self, message: str, operation: Optional[str] = None):
        """Initialize DatabaseError with message and optional operation name."""
        super().__init__(message)
        self.operation = operation
        if operation:
            self.details["operation"] = operation


class VectorStoreError(KnowledgeBaseError):
    """Raised when vector store operations fail."""


class AgentError(AutoBotError):
    """Base class for agent-related errors."""

    def __init__(self, message: str, agent_name: Optional[str] = None):
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
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
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

    def __init__(
        self, message: str, limit: Optional[int] = None, current: Optional[int] = None
    ):
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

    def __init__(self, message: str, service: Optional[str] = None):
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
