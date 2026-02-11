# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Utilities - Reusable Functions for Chat System

This module provides reusable utility functions for the chat/conversation system.
Extracted from backend/api/chat.py and backend/api/chat_enhanced.py to eliminate
code duplication and improve maintainability.

Functions:
- ID Generation: generate_request_id, generate_chat_session_id, generate_message_id
- ID Validation: validate_chat_session_id
- Response Formatting: create_success_response, create_error_response
- Dependency Injection: get_chat_history_manager (FastAPI)

Usage:
    from backend.utils.chat_utils import (
        generate_request_id,
        create_success_response,
        get_chat_history_manager
    )

Related Issue: #40 - Chat/Conversation Targeted Refactoring
Created: 2025-01-14
"""

import logging
import re
from typing import Any, Optional
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from utils.path_validation import contains_injection_patterns

# Issue #756: Consolidated from utils/request_utils.py
from utils.request_utils import generate_request_id

from backend.type_defs.common import Metadata
from backend.utils.response_helpers import (
    create_error_response as _canonical_create_error_response,
)

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex for session ID validation
_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


# =============================================================================
# ID Generation Functions
# =============================================================================

# Note: generate_request_id is now imported from src/utils/request_utils.py (Issue #756)
# and re-exported here for backward compatibility (Issue #751)


def generate_chat_session_id() -> str:
    """
    Generate a new chat session ID.

    Returns:
        str: UUID4 string for session identification

    Example:
        >>> session_id = generate_chat_session_id()
        >>> print(session_id)
        'b2c3d4e5-f6a7-8901-bcde-f12345678901'
    """
    return str(uuid4())


def generate_message_id() -> str:
    """
    Generate a new message ID for chat messages.

    Returns:
        str: UUID4 string for message identification

    Example:
        >>> message_id = generate_message_id()
        >>> print(message_id)
        'c3d4e5f6-a7b8-9012-cdef-123456789012'
    """
    return str(uuid4())


# =============================================================================
# ID Validation Functions
# =============================================================================


def validate_chat_session_id(session_id: str) -> bool:
    """
    Validate chat session ID format with backward compatibility.

    Accepts:
    - Valid UUIDs (standard format)
    - UUIDs with suffixes (e.g., "uuid-imported-123")
    - Legacy/test IDs (alphanumeric with underscores/hyphens)

    Security:
    - Rejects path traversal attempts (/, \\, ..)
    - Rejects null bytes
    - Enforces maximum length (255 characters)

    Args:
        session_id: Session ID string to validate

    Returns:
        bool: True if valid, False otherwise

    Example:
        >>> validate_chat_session_id("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        True
        >>> validate_chat_session_id("test_session_123")
        True
        >>> validate_chat_session_id("../../../etc/passwd")
        False
        >>> validate_chat_session_id("")
        False
    """
    import uuid

    if not session_id or len(session_id) > 255:
        return False

    # Security: reject path traversal and null bytes (Issue #328 - uses shared validation)
    if contains_injection_patterns(session_id):
        return False

    # Accept if it's a valid UUID
    try:
        uuid.UUID(session_id)
        return True
    except ValueError:
        logger.debug("Session ID is not a valid UUID, checking other formats")

    # Accept if starts with UUID (with suffix like "uuid-imported-123")
    parts = session_id.split("-")
    if len(parts) >= 5:
        try:
            uuid_part = "-".join(parts[:5])
            uuid.UUID(uuid_part)
            return True
        except ValueError as e:
            logger.debug("Value parsing failed: %s", e)

    # Accept legacy/test session IDs (alphanumeric + underscore + hyphen)
    # This allows "test_conv" while rejecting malicious inputs
    if _SESSION_ID_RE.match(session_id):
        return True

    return False


def validate_message_content(content: str) -> bool:
    """
    Validate that message content is not empty.

    Args:
        content: Message content string to validate

    Returns:
        bool: True if content is non-empty after stripping whitespace

    Example:
        >>> validate_message_content("Hello world")
        True
        >>> validate_message_content("   ")
        False
        >>> validate_message_content("")
        False
    """
    return content and len(content.strip()) > 0


# =============================================================================
# Response Formatting Functions
# =============================================================================

# Note: _canonical_create_error_response imported at top of file (Issue #292)


def create_success_response(
    data: Any,
    message: str = "Success",
    request_id: Optional[str] = None,
    status_code: int = 200,
) -> JSONResponse:
    """
    Create a standardized success response.

    Args:
        data: Response data (any JSON-serializable type)
        message: Success message (default: "Success")
        request_id: Optional request ID for tracking
        status_code: HTTP status code (default: 200)

    Returns:
        JSONResponse: Formatted success response

    Example:
        >>> response = create_success_response(
        ...     data={"chat_id": "123"},
        ...     message="Chat created",
        ...     request_id="abc-123"
        ... )
        >>> response.status_code
        200
    """
    from datetime import datetime

    response = {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if request_id:
        response["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=response)


def create_error_response(
    error_code: str = "INTERNAL_ERROR",
    message: str = "An error occurred",
    request_id: str = "unknown",
    status_code: int = 500,
) -> JSONResponse:
    """
    Create a standardized error response.

    This is a wrapper around response_helpers.create_error_response that
    provides backward compatibility with the default request_id="unknown".

    Args:
        error_code: Error code identifier (default: "INTERNAL_ERROR")
        message: Human-readable error message
        request_id: Request ID for error tracking (default: "unknown")
        status_code: HTTP status code (default: 500)

    Returns:
        JSONResponse: Formatted error response

    Common Error Codes:
        - INTERNAL_ERROR: Server-side error (500)
        - VALIDATION_ERROR: Invalid input (400)
        - NOT_FOUND: Resource not found (404)
        - UNAUTHORIZED: Authentication required (401)
        - FORBIDDEN: Insufficient permissions (403)

    Example:
        >>> response = create_error_response(
        ...     error_code="VALIDATION_ERROR",
        ...     message="Invalid session ID",
        ...     request_id="abc-123",
        ...     status_code=400
        ... )
        >>> response.status_code
        400

    Note:
        Consolidated from duplicate in response_helpers.py (Issue #292).
        Uses canonical implementation from backend.utils.response_helpers.
    """
    return _canonical_create_error_response(
        error_code=error_code,
        message=message,
        status_code=status_code,
        request_id=request_id,
    )


# =============================================================================
# FastAPI Dependency Injection Functions
# =============================================================================


def get_chat_history_manager(request: Request):
    """
    Get chat history manager from FastAPI app state with lazy initialization.

    This is a FastAPI dependency that retrieves the ChatHistoryManager instance
    from the application state. If not yet initialized, it will be created and
    stored for subsequent requests.

    Args:
        request: FastAPI Request object

    Returns:
        ChatHistoryManager: Initialized chat history manager instance

    Usage (as FastAPI dependency):
        @router.post("/chat/message")
        async def send_message(
            chat_history: ChatHistoryManager = Depends(get_chat_history_manager)
        ):
            # Use chat_history...

    Example (direct call):
        >>> from fastapi import Request
        >>> manager = get_chat_history_manager(request)
        >>> # Use manager for chat operations...
    """
    from chat_history import ChatHistoryManager
    from utils.lazy_singleton import lazy_init_singleton

    return lazy_init_singleton(
        request.app.state, "chat_history_manager", ChatHistoryManager
    )


# =============================================================================
# Logging Helper Functions
# =============================================================================


def log_chat_error(
    error: Exception, context: str = "chat", request_id: str = "unknown"
) -> None:
    """
    Log chat-related errors with consistent formatting.

    Args:
        error: Exception that occurred
        context: Context where error occurred (e.g., "chat", "session", "message")
        request_id: Request ID for tracking

    Example:
        >>> try:
        ...     # Some chat operation
        ...     raise ValueError("Invalid input")
        ... except Exception as e:
        ...     log_chat_error(e, context="message_send", request_id="abc-123")
    """
    logger.error("[%s] [%s] Error: %s", context, request_id, str(error), exc_info=True)


def log_chat_event(
    event_type: str,
    session_id: Optional[str] = None,
    details: Optional[Metadata] = None,
    request_id: Optional[str] = None,
) -> None:
    """
    Log chat-related events for monitoring and debugging.

    Args:
        event_type: Type of event (e.g., "message_sent", "session_created")
        session_id: Optional session ID
        details: Optional event details dictionary
        request_id: Optional request ID for tracking

    Example:
        >>> log_chat_event(
        ...     event_type="message_sent",
        ...     session_id="session-123",
        ...     details={"message_length": 42},
        ...     request_id="req-456"
        ... )
    """
    event_data = {"event_type": event_type}
    if session_id:
        event_data["session_id"] = session_id
    if request_id:
        event_data["request_id"] = request_id
    if details:
        event_data["details"] = details

    logger.info("Chat Event: %s", event_data)


# =============================================================================
# Module Information
# =============================================================================

__all__ = [
    # ID Generation
    "generate_request_id",
    "generate_chat_session_id",
    "generate_message_id",
    # ID Validation
    "validate_chat_session_id",
    "validate_message_content",
    # Response Formatting
    "create_success_response",
    "create_error_response",
    # Dependency Injection
    "get_chat_history_manager",
    # Logging
    "log_chat_error",
    "log_chat_event",
]
