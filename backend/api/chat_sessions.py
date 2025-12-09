# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

import json
import logging
from typing import Dict, Optional

from backend.type_defs.common import Metadata
from fastapi import APIRouter, Depends, Request, Response

# CRITICAL SECURITY FIX: Import session ownership validation
from backend.security.session_ownership import validate_session_ownership

# Import reusable chat utilities
from backend.utils.chat_utils import (
    create_success_response,
    generate_chat_session_id,
    generate_request_id,
    get_chat_history_manager,
    log_chat_event,
    validate_chat_session_id,
)

# Import shared exception classes (Issue #292 - Eliminate duplicate code)
from backend.utils.chat_exceptions import get_exceptions_lazy
from pydantic import BaseModel, Field
from src.auth_middleware import auth_middleware
from src.utils.error_boundaries import ErrorCategory, with_error_handling


# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["chat-sessions"])
logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for valid export formats (Issue #326)
VALID_EXPORT_FORMATS = {"json", "txt", "csv"}

# Issue #380: Module-level frozenset for valid file actions
_VALID_FILE_ACTIONS = frozenset({"delete", "transfer_kb", "transfer_shared"})

# ====================================================================
# Helper Functions
# ====================================================================


async def _handle_session_file_action(
    conversation_file_manager,
    session_id: str,
    file_action: str,
    parsed_file_options: Metadata,
) -> Metadata:
    """Handle file action for session deletion (Issue #315: extracted).

    Args:
        conversation_file_manager: File manager instance
        session_id: Session ID
        file_action: Action to take ("delete", "transfer_kb", "transfer_shared")
        parsed_file_options: Parsed options for transfer

    Returns:
        Dict with file handling result
    """
    if file_action == "delete":
        deleted_count = await conversation_file_manager.delete_session_files(session_id)
        logger.info(f"Deleted {deleted_count} files for session {session_id}")
        return {
            "files_handled": True,
            "action_taken": "delete",
            "files_deleted": deleted_count,
        }

    if file_action == "transfer_kb":
        transfer_result = await conversation_file_manager.transfer_session_files(
            session_id=session_id,
            destination="kb",
            target_path=parsed_file_options.get("target_path"),
            tags=parsed_file_options.get("tags", ["conversation_archive"]),
            copy=False,
        )
        logger.info(
            f"Transferred {transfer_result.get('total_transferred', 0)} files "
            f"to KB for session {session_id}"
        )
        return {
            "files_handled": True,
            "action_taken": "transfer_kb",
            "files_transferred": transfer_result.get("total_transferred", 0),
            "files_failed": transfer_result.get("total_failed", 0),
        }

    # file_action == "transfer_shared"
    transfer_result = await conversation_file_manager.transfer_session_files(
        session_id=session_id,
        destination="shared",
        target_path=parsed_file_options.get("target_path"),
        copy=False,
    )
    logger.info(
        f"Transferred {transfer_result.get('total_transferred', 0)} files "
        f"to shared storage for session {session_id}"
    )
    return {
        "files_handled": True,
        "action_taken": "transfer_shared",
        "files_transferred": transfer_result.get("total_transferred", 0),
        "files_failed": transfer_result.get("total_failed", 0),
    }


def log_request_context(request, endpoint, request_id):
    """Log request context for debugging"""
    logger.info(f"[{request_id}] {endpoint} - {request.method} {request.url.path}")


# ====================================================================
# Request/Response Models
# ====================================================================


class SessionCreate(BaseModel):
    """Session creation model"""

    title: Optional[str] = Field(None, max_length=200, description="Session title")
    metadata: Optional[Metadata] = Field(
        default_factory=dict, description="Session metadata"
    )


class SessionUpdate(BaseModel):
    """Session update model"""

    title: Optional[str] = Field(None, max_length=200, description="New session title")
    metadata: Optional[Metadata] = Field(None, description="Updated metadata")


# ====================================================================
# Configuration Constants
# ====================================================================

DEFAULT_SESSION_TITLE = "New Chat Session"


# ====================================================================
# API Endpoints - Session Management
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_messages",
    error_code_prefix="CHAT",
)
@router.get("/chat/sessions/{session_id}")
async def get_session_messages(
    session_id: str,
    request: Request,
    ownership: Dict = Depends(
        validate_session_ownership
    ),  # SECURITY: Validate ownership
    page: int = 1,
    per_page: int = 50,
):
    """Get messages for a specific chat session"""
    request_id = generate_request_id()
    log_request_context(request, "get_session_messages", request_id)

    # Validate session ID
    if not validate_chat_session_id(session_id):
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Invalid session ID format")

    # Validate pagination parameters
    if page < 1 or per_page < 1 or per_page > 100:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Invalid pagination parameters")

    # Get dependencies from request state
    chat_history_manager = get_chat_history_manager(request)

    # Get session messages
    # NOTE: get_session_messages doesn't support pagination yet - uses limit parameter
    messages = await chat_history_manager.get_session_messages(
        session_id, limit=per_page
    )

    if messages is None:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ResourceNotFoundError(f"Session {session_id} not found")

    total_count = await chat_history_manager.get_session_message_count(session_id)

    response_data = {
        "messages": messages,
        "session_id": session_id,
        "total_count": total_count,
        "page": page,
        "per_page": per_page,
    }

    return create_success_response(
        data=response_data,
        message="Session messages retrieved successfully",
        request_id=request_id,
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_sessions",
    error_code_prefix="CHAT",
)
@router.get("/chat/sessions")
async def list_sessions(request: Request):
    """List all available chat sessions (REST-compliant endpoint)"""
    request_id = generate_request_id()
    chat_history_manager = get_chat_history_manager(request)

    if chat_history_manager is None:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise InternalError(
            "Chat history manager not initialized",
            details={"component": "chat_history_manager"},
        )

    # Use fast mode for listing (no decryption)
    sessions = chat_history_manager.list_sessions_fast()

    return create_success_response(
        data={"sessions": sessions, "count": len(sessions)},
        message="Sessions retrieved successfully",
        request_id=request_id,
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_session",
    error_code_prefix="CHAT",
)
@router.post("/chat/sessions")
async def create_session(session_data: SessionCreate, request: Request):
    """Create a new chat session"""
    request_id = generate_request_id()
    log_request_context(request, "create_session", request_id)

    # Get dependencies from request state
    chat_history_manager = get_chat_history_manager(request)

    # Generate new session
    session_id = generate_chat_session_id()
    session_title = session_data.title or DEFAULT_SESSION_TITLE

    # SECURITY: Extract authenticated user and add to metadata as owner
    user_data = auth_middleware.get_user_from_request(request)
    metadata = session_data.metadata or {}
    if user_data and user_data.get("username"):
        metadata["owner"] = user_data["username"]
        metadata["username"] = user_data["username"]  # For backward compatibility
        logger.info(f"Session {session_id} created with owner: {user_data['username']}")

    # Create session
    session = await chat_history_manager.create_session(
        session_id=session_id,
        title=session_title,
        metadata=metadata,
    )

    log_chat_event(
        "session_created",
        session_id,
        {"title": session_title, "request_id": request_id},
    )

    return create_success_response(
        data=session,
        message="Session created successfully",
        request_id=request_id,
        status_code=201,
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_session",
    error_code_prefix="CHAT",
)
@router.put("/chat/sessions/{session_id}")
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    request: Request,
    ownership: Dict = Depends(
        validate_session_ownership
    ),  # SECURITY: Validate ownership
):
    """Update a chat session"""
    request_id = generate_request_id()
    log_request_context(request, "update_session", request_id)

    # Validate session ID
    if not validate_chat_session_id(session_id):
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Invalid session ID format")

    # Get dependencies from request state
    chat_history_manager = get_chat_history_manager(request)

    # Update session
    updated_session = await chat_history_manager.update_session(
        session_id=session_id,
        title=session_data.title,
        metadata=session_data.metadata,
    )

    if updated_session is None:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ResourceNotFoundError(f"Session {session_id} not found")

    log_chat_event(
        "session_updated",
        session_id,
        {"title": session_data.title, "request_id": request_id},
    )

    return create_success_response(
        data=updated_session,
        message="Session updated successfully",
        request_id=request_id,
    )


# =============================================================================
# Helper Functions for delete_session (Issue #281)
# =============================================================================


def _validate_delete_session_params(
    session_id: str, file_action: str, file_options: Optional[str]
) -> dict:
    """Validate and parse delete_session parameters (Issue #281: extracted)."""
    # Validate session ID
    if not validate_chat_session_id(session_id):
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Invalid session ID format")

    # Validate file_action (Issue #380: use module-level constant)
    if file_action not in _VALID_FILE_ACTIONS:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError(
            f"Invalid file_action. Must be one of: {sorted(_VALID_FILE_ACTIONS)}"
        )

    # Parse file_options if provided
    parsed_file_options = {}
    if file_options:
        try:
            parsed_file_options = json.loads(file_options)
        except json.JSONDecodeError:
            (
                AutoBotError,
                InternalError,
                ResourceNotFoundError,
                ValidationError,
                get_error_code,
            ) = get_exceptions_lazy()
            raise ValidationError("Invalid file_options JSON format")

    return parsed_file_options


async def _handle_conversation_files(
    request: Request, session_id: str, file_action: str, parsed_file_options: dict
) -> dict:
    """Handle conversation files during session deletion (Issue #281: extracted)."""
    file_deletion_result = {"files_handled": False, "action_taken": file_action}
    conversation_file_manager = getattr(
        request.app.state, "conversation_file_manager", None
    )

    if conversation_file_manager:
        try:
            file_deletion_result = await _handle_session_file_action(
                conversation_file_manager, session_id, file_action, parsed_file_options
            )
        except Exception as file_error:
            logger.error(f"Error handling files for session {session_id}: {file_error}")
            file_deletion_result = {
                "files_handled": False,
                "action_taken": file_action,
                "error": str(file_error),
            }
    else:
        logger.warning(
            f"ConversationFileManager not available, "
            f"skipping file handling for session {session_id}"
        )

    return file_deletion_result


async def _cleanup_terminal_sessions(request: Request, session_id: str) -> dict:
    """Clean up associated terminal sessions (Issue #281: extracted)."""
    terminal_cleanup_result = {
        "terminal_sessions_closed": 0,
        "pending_approvals_cleared": 0,
    }

    agent_terminal_service = getattr(request.app.state, "agent_terminal_service", None)
    if not agent_terminal_service:
        logger.warning(
            f"AgentTerminalService not available, "
            f"skipping terminal session cleanup for session {session_id}"
        )
        return terminal_cleanup_result

    try:
        terminal_sessions = await agent_terminal_service.list_sessions(
            conversation_id=session_id
        )

        for terminal_session in terminal_sessions:
            if terminal_session.pending_approval is not None:
                terminal_cleanup_result["pending_approvals_cleared"] += 1
                logger.info(
                    f"Clearing pending approval for terminal session "
                    f"{terminal_session.session_id} "
                    f"(command: {terminal_session.pending_approval.get('command')})"
                )

            await agent_terminal_service.close_session(terminal_session.session_id)
            terminal_cleanup_result["terminal_sessions_closed"] += 1

        if terminal_cleanup_result["terminal_sessions_closed"] > 0:
            logger.info(
                f"Cleaned up {terminal_cleanup_result['terminal_sessions_closed']} "
                f"terminal session(s) for chat session {session_id}, "
                f"cleared {terminal_cleanup_result['pending_approvals_cleared']} "
                f"pending approval(s)"
            )
    except Exception as terminal_cleanup_error:
        logger.error(
            f"Failed to cleanup terminal sessions for chat {session_id}: "
            f"{terminal_cleanup_error}",
            exc_info=True,
        )
        terminal_cleanup_result["error"] = str(terminal_cleanup_error)

    return terminal_cleanup_result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_session",
    error_code_prefix="CHAT",
)
@router.delete("/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    ownership: Dict = Depends(
        validate_session_ownership
    ),  # SECURITY: Validate ownership
    file_action: str = "delete",
    file_options: Optional[str] = None,
):
    """
    Delete a chat session with optional file handling.

    Issue #281: Refactored from 176 lines to use extracted helper methods.

    Args:
        session_id: Chat session ID to delete
        file_action: How to handle conversation files ("delete", "transfer_kb", "transfer_shared")
        file_options: JSON string with transfer options

    Returns:
        Success response with deletion details
    """
    request_id = generate_request_id()
    log_request_context(request, "delete_session", request_id)

    # Validate parameters (Issue #281: uses helper)
    parsed_file_options = _validate_delete_session_params(
        session_id, file_action, file_options
    )

    # Get dependencies from request state
    chat_history_manager = get_chat_history_manager(request)

    # Handle conversation files (Issue #281: uses helper)
    file_deletion_result = await _handle_conversation_files(
        request, session_id, file_action, parsed_file_options
    )

    # Clean up terminal sessions (Issue #281: uses helper)
    terminal_cleanup_result = await _cleanup_terminal_sessions(request, session_id)

    # Delete session from chat history
    deleted = chat_history_manager.delete_session(session_id)

    if not deleted:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ResourceNotFoundError(f"Session {session_id} not found")

    log_chat_event(
        "session_deleted",
        session_id,
        {
            "request_id": request_id,
            "file_action": file_action,
            "file_deletion_result": file_deletion_result,
            "terminal_cleanup_result": terminal_cleanup_result,
        },
    )

    return create_success_response(
        data={
            "session_id": session_id,
            "deleted": True,
            "file_handling": file_deletion_result,
            "terminal_cleanup": terminal_cleanup_result,
        },
        message="Session deleted successfully",
        request_id=request_id,
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_session",
    error_code_prefix="CHAT",
)
@router.get("/chat/sessions/{session_id}/export")
async def export_session(session_id: str, request: Request, format: str = "json"):
    """Export a chat session in various formats"""
    request_id = generate_request_id()
    log_request_context(request, "export_session", request_id)

    # Validate session ID
    if not validate_chat_session_id(session_id):
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Invalid session ID format")

    # Validate format
    if format not in VALID_EXPORT_FORMATS:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Invalid export format. Supported: json, txt, csv")

    # Get dependencies from request state
    chat_history_manager = get_chat_history_manager(request)

    # Get session data
    session_data = await chat_history_manager.export_session(session_id, format)

    if session_data is None:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ResourceNotFoundError(f"Session {session_id} not found")

    # Set appropriate content type
    content_types = {
        "json": "application/json",
        "txt": "text/plain",
        "csv": "text/csv",
    }

    log_chat_event(
        "session_exported", session_id, {"format": format, "request_id": request_id}
    )

    return Response(
        content=session_data,
        media_type=content_types[format],
        headers={
            "Content-Disposition": (
                f"attachment; filename=chat_session_{session_id}.{format}"
            )
        },
    )
