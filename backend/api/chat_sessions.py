# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

import json
import logging
from typing import Dict, List, Optional

from backend.type_defs.common import Metadata
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

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
from src.autobot_memory_graph import AutoBotMemoryGraph
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
        logger.info("Deleted %s files for session %s", deleted_count, session_id)
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
    logger.info("[%s] %s - %s %s", request_id, endpoint, request.method, request.url.path)


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


# Issue #608: Activity tracking models
class ActivityCreate(BaseModel):
    """Single activity creation model"""

    activity_id: str = Field(..., description="Frontend-generated activity ID")
    type: str = Field(..., description="Activity type: terminal, file, browser, desktop")
    user_id: str = Field(..., description="User who performed the activity")
    content: str = Field(..., max_length=10000, description="Activity content/description")
    secrets_used: list[str] = Field(default_factory=list, description="Secret IDs used")
    metadata: Optional[Metadata] = Field(default_factory=dict, description="Activity metadata")
    timestamp: str = Field(..., description="ISO format timestamp from frontend")


class ActivityBatchCreate(BaseModel):
    """Batch activity creation model"""

    activities: list[ActivityCreate] = Field(..., description="List of activities to create")


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
    # list_sessions_fast is async (uses asyncio.to_thread internally)
    sessions = await chat_history_manager.list_sessions_fast()

    return create_success_response(
        data={"sessions": sessions, "count": len(sessions)},
        message="Sessions retrieved successfully",
        request_id=request_id,
    )


async def _track_session_in_memory_graph(
    request: Request,
    session_id: str,
    session_title: str,
    user_data: Optional[dict],
    request_id: str,
) -> None:
    """
    Track session creation in memory graph.

    Issue #665: Extracted from create_session to reduce function length.
    Issue #608: Memory graph tracking for sessions.

    Args:
        request: FastAPI request with app state
        session_id: Created session ID
        session_title: Session title
        user_data: Authenticated user data
        request_id: Request tracking ID
    """
    memory_graph: Optional[AutoBotMemoryGraph] = getattr(
        request.app.state, "memory_graph", None
    )
    if not memory_graph or not user_data:
        return

    try:
        user_id = user_data.get("user_id") or user_data.get("username", "anonymous")
        username = user_data.get("username", "anonymous")

        # Create user entity (idempotent - returns existing if found)
        await memory_graph.create_user_entity(
            user_id=user_id,
            username=username,
            metadata={"source": "session_creation"},
        )

        # Create chat session entity linked to user
        await memory_graph.create_chat_session_entity(
            session_id=session_id,
            owner_id=user_id,
            title=session_title,
            metadata={
                "created_via": "api",
                "request_id": request_id,
            },
        )
        logger.debug(
            "Memory graph entities created for session %s, user %s",
            session_id,
            username,
        )
    except Exception as graph_error:
        # Non-critical: log warning but don't fail session creation
        logger.warning(
            "Failed to create memory graph entities for session %s: %s",
            session_id,
            graph_error,
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_session",
    error_code_prefix="CHAT",
)
@router.post("/chat/sessions")
async def create_session(session_data: SessionCreate, request: Request):
    """
    Create a new chat session.

    Issue #665: Refactored to use extracted helper for memory graph tracking.
    """
    request_id = generate_request_id()
    log_request_context(request, "create_session", request_id)

    chat_history_manager = get_chat_history_manager(request)
    session_id = generate_chat_session_id()
    session_title = session_data.title or DEFAULT_SESSION_TITLE

    # SECURITY: Extract authenticated user and add to metadata as owner
    user_data = auth_middleware.get_user_from_request(request)
    metadata = session_data.metadata or {}
    if user_data and user_data.get("username"):
        metadata["owner"] = user_data["username"]
        metadata["username"] = user_data["username"]  # For backward compatibility
        logger.info("Session %s created with owner: %s", session_id, user_data['username'])

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

    # Issue #665: Use helper for memory graph tracking
    await _track_session_in_memory_graph(
        request, session_id, session_title, user_data, request_id
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
# Helper Functions for delete_session (Issue #281, #665)
# =============================================================================


def _validate_delete_session_params(
    session_id: str, file_action: str, file_options: Optional[str]
) -> dict:
    """Validate and parse delete_session parameters.

    Issue #281: Extracted from delete_session for better organization.

    Args:
        session_id: Chat session ID to validate
        file_action: Action to take on files ("delete", "transfer_kb", "transfer_shared")
        file_options: Optional JSON string with file handling options

    Returns:
        Parsed file options dictionary

    Raises:
        ValidationError: If session_id, file_action, or file_options are invalid
    """
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
    """Handle conversation files during session deletion.

    Issue #281: Extracted from delete_session for better organization.

    Args:
        request: FastAPI request object with app state
        session_id: Chat session ID being deleted
        file_action: Action to take ("delete", "transfer_kb", "transfer_shared")
        parsed_file_options: Parsed options for transfer operations

    Returns:
        Dict with file handling results including success status and counts
    """
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
            logger.error("Error handling files for session %s: %s", session_id, file_error)
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
    """Clean up associated terminal sessions.

    Issue #281: Extracted from delete_session for better organization.

    Args:
        request: FastAPI request object with app state
        session_id: Chat session ID being deleted

    Returns:
        Dict with cleanup statistics including sessions closed and approvals cleared
    """
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


async def _cleanup_knowledge_base_facts(request: Request, session_id: str) -> dict:
    """
    Clean up knowledge base facts created during this session.

    Issue #547: Fixes orphaned KB data when conversations are deleted.

    This function:
    1. Finds all facts created during this session (via session:facts:{session_id})
    2. Deletes them from Redis and ChromaDB
    3. Preserves facts marked as 'important' or 'preserve' in metadata
    4. Cleans up session-fact relationship tracking keys

    Args:
        request: FastAPI request object with app.state
        session_id: Chat session ID being deleted

    Returns:
        Dict with cleanup statistics:
        - facts_deleted: Number of facts removed
        - facts_preserved: Number of important facts kept
        - cleanup_error: Error message if any
    """
    kb_cleanup_result = {
        "facts_deleted": 0,
        "facts_preserved": 0,
        "cleanup_error": None,
    }

    # Get knowledge base from app state
    knowledge_base = getattr(request.app.state, "knowledge_base", None)
    if not knowledge_base:
        logger.warning(
            f"Knowledge base not available, "
            f"skipping KB cleanup for session {session_id}"
        )
        return kb_cleanup_result

    try:
        # Delete facts associated with this session
        # Uses the new delete_facts_by_session method from Issue #547
        result = await knowledge_base.delete_facts_by_session(
            session_id=session_id,
            preserve_important=True  # Keep user-marked important facts
        )

        kb_cleanup_result["facts_deleted"] = result.get("deleted_count", 0)
        kb_cleanup_result["facts_preserved"] = result.get("preserved_count", 0)

        if result.get("errors"):
            kb_cleanup_result["cleanup_error"] = f"{len(result['errors'])} errors during cleanup"
            logger.warning(
                f"KB cleanup completed with errors for session {session_id}: "
                f"{result['errors']}"
            )

        if kb_cleanup_result["facts_deleted"] > 0 or kb_cleanup_result["facts_preserved"] > 0:
            logger.info(
                f"KB cleanup for session {session_id}: "
                f"deleted={kb_cleanup_result['facts_deleted']}, "
                f"preserved={kb_cleanup_result['facts_preserved']}"
            )

    except Exception as kb_cleanup_error:
        logger.error(
            f"Failed to cleanup KB facts for session {session_id}: {kb_cleanup_error}",
            exc_info=True,
        )
        kb_cleanup_result["cleanup_error"] = str(kb_cleanup_error)

    return kb_cleanup_result


async def _cleanup_conversation_transcript(session_id: str) -> dict:
    """
    Clean up conversation transcript file from data/conversation_transcripts/.

    This removes the duplicate transcript storage used by ChatWorkflowManager.

    Args:
        session_id: Chat session ID being deleted

    Returns:
        Dict with cleanup result
    """
    import os
    from pathlib import Path

    result = {"transcript_deleted": False, "error": None}

    try:
        transcript_path = Path("data/conversation_transcripts") / f"{session_id}.json"

        if transcript_path.exists():
            os.remove(transcript_path)
            result["transcript_deleted"] = True
            logger.info("Deleted conversation transcript for session %s", session_id)
        else:
            logger.debug(
                "No conversation transcript found for session %s (may not exist)",
                session_id,
            )

    except Exception as e:
        logger.warning(
            "Failed to delete conversation transcript for session %s: %s",
            session_id,
            e,
        )
        result["error"] = str(e)

    return result


async def _perform_all_session_cleanup(
    request: Request,
    session_id: str,
    file_action: str,
    parsed_file_options: dict,
) -> tuple[dict, dict, dict, dict]:
    """Perform all cleanup operations for session deletion.

    Issue #665: Extracted from delete_session to reduce function complexity.

    Args:
        request: FastAPI request object with app state
        session_id: Chat session ID being deleted
        file_action: How to handle conversation files
        parsed_file_options: Parsed options for file transfer

    Returns:
        Tuple of (file_result, terminal_result, kb_result, transcript_result)
    """
    # Handle conversation files
    file_deletion_result = await _handle_conversation_files(
        request, session_id, file_action, parsed_file_options
    )

    # Clean up terminal sessions
    terminal_cleanup_result = await _cleanup_terminal_sessions(request, session_id)

    # Clean up knowledge base facts
    kb_cleanup_result = await _cleanup_knowledge_base_facts(request, session_id)

    # Clean up conversation transcript
    transcript_cleanup_result = await _cleanup_conversation_transcript(session_id)

    return (
        file_deletion_result,
        terminal_cleanup_result,
        kb_cleanup_result,
        transcript_cleanup_result,
    )


async def _delete_session_and_verify(
    chat_history_manager, session_id: str
) -> None:
    """Delete session from chat history and verify success.

    Issue #665: Extracted from delete_session to reduce function complexity.

    Args:
        chat_history_manager: Chat history manager instance
        session_id: Chat session ID being deleted

    Raises:
        ResourceNotFoundError: If session doesn't exist or deletion failed
    """
    deleted = await chat_history_manager.delete_session(session_id)

    if not deleted:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ResourceNotFoundError(f"Session {session_id} not found")


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
    """Delete a chat session with comprehensive cleanup.

    Issue #281: Refactored from 176 lines to use extracted helper methods.
    Issue #547: Added knowledge base facts cleanup to prevent orphaned data.
    Issue #665: Further refactored to reduce function below 50 lines.

    Args:
        session_id: Chat session ID to delete
        file_action: How to handle conversation files ("delete", "transfer_kb", "transfer_shared")
        file_options: JSON string with transfer options

    Returns:
        Success response with deletion details including KB cleanup stats
    """
    request_id = generate_request_id()
    log_request_context(request, "delete_session", request_id)

    # Validate parameters and parse options
    parsed_file_options = _validate_delete_session_params(
        session_id, file_action, file_options
    )

    # Get chat history manager
    chat_history_manager = get_chat_history_manager(request)

    # Perform all cleanup operations (Issue #665: orchestration via helper)
    (
        file_deletion_result,
        terminal_cleanup_result,
        kb_cleanup_result,
        transcript_cleanup_result,
    ) = await _perform_all_session_cleanup(
        request, session_id, file_action, parsed_file_options
    )

    # Delete session and verify success (Issue #665: verification via helper)
    await _delete_session_and_verify(chat_history_manager, session_id)

    # Log deletion event with all cleanup results
    log_chat_event(
        "session_deleted",
        session_id,
        {
            "request_id": request_id,
            "file_action": file_action,
            "file_deletion_result": file_deletion_result,
            "terminal_cleanup_result": terminal_cleanup_result,
            "kb_cleanup_result": kb_cleanup_result,
            "transcript_cleanup_result": transcript_cleanup_result,
        },
    )

    return create_success_response(
        data={
            "session_id": session_id,
            "deleted": True,
            "file_handling": file_deletion_result,
            "terminal_cleanup": terminal_cleanup_result,
            "kb_cleanup": kb_cleanup_result,
            "transcript_cleanup": transcript_cleanup_result,
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


# =============================================================================
# Issue #549: Chat Reset Endpoint
# =============================================================================


class ChatResetRequest(BaseModel):
    """Request model for chat reset"""

    session_id: Optional[str] = Field(None, description="Session ID to reset (optional)")
    clear_context: bool = Field(True, description="Clear conversation context")
    keep_system_prompt: bool = Field(True, description="Keep system prompt after reset")


def _preserve_system_messages(chat_manager, session_id: str) -> List[Dict]:
    """
    Extract system messages from session for preservation.

    Issue #665: Extracted helper for system message preservation during reset.
    """
    try:
        existing_data = chat_manager.get_session(session_id)
        if existing_data and "messages" in existing_data:
            return [m for m in existing_data["messages"] if m.get("role") == "system"]
    except Exception as e:
        logger.warning("Could not preserve system prompt: %s", e)
    return []


def _clear_and_restore_session(
    chat_manager, session_id: str, messages_to_restore: List[Dict]
) -> int:
    """
    Clear session and restore specified messages.

    Issue #665: Extracted helper for session clearing with message restoration.
    Returns number of messages restored.
    """
    chat_manager.clear_session(session_id)
    for msg in messages_to_restore:
        chat_manager.add_message(session_id, msg)
    return len(messages_to_restore)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_chat",
    error_code_prefix="CHAT",
)
@router.post("/chat/reset")
async def reset_chat(request: Request, reset_request: Optional[ChatResetRequest] = None):
    """
    Reset the current chat session.

    Issue #549: Created to match frontend POST /api/chat/reset
    Issue #665: Refactored to use extracted helpers for message preservation.
    """
    request_id = generate_request_id()
    chat_history_manager = get_chat_history_manager(request)

    if reset_request is None:
        reset_request = ChatResetRequest()

    session_id = reset_request.session_id
    clear_context = reset_request.clear_context
    keep_system_prompt = reset_request.keep_system_prompt

    if not session_id:
        session_id = generate_chat_session_id()
        logger.info("Creating new session for reset: %s", session_id)
    else:
        _validate_session_id_or_raise(session_id)

        if clear_context:
            messages_to_keep = (
                _preserve_system_messages(chat_history_manager, session_id)
                if keep_system_prompt else []
            )
            restored = _clear_and_restore_session(chat_history_manager, session_id, messages_to_keep)
            logger.info("Reset chat session: %s, kept %d system messages", session_id, restored)

    log_chat_event(
        "session_reset", session_id,
        {"request_id": request_id, "clear_context": clear_context, "keep_system_prompt": keep_system_prompt},
    )

    return create_success_response(
        data={"session_id": session_id, "reset": True, "clear_context": clear_context, "keep_system_prompt": keep_system_prompt},
        message="Chat session reset successfully",
        request_id=request_id,
    )


# ====================================================================
# API Endpoints - Activity Tracking (Issue #608)
# ====================================================================


def _validate_session_id_or_raise(session_id: str) -> None:
    """
    Validate session ID format and raise ValidationError if invalid.

    Issue #665: Extracted helper to reduce duplication in activity endpoints.
    """
    if not validate_chat_session_id(session_id):
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Invalid session ID format")


def _get_memory_graph_or_none(request: Request) -> Optional[AutoBotMemoryGraph]:
    """
    Get memory graph from app state or None if unavailable.

    Issue #665: Extracted helper for memory graph access.
    """
    return getattr(request.app.state, "memory_graph", None)


def _create_activity_unavailable_response(
    activity_count: int, request_id: str, *, is_batch: bool = False
) -> JSONResponse:
    """
    Create response when memory graph is unavailable.

    Issue #665: Extracted helper for unavailable response.
    """
    if is_batch:
        return create_success_response(
            data={"total": activity_count, "stored": 0, "failed": activity_count},
            message="Activities received but memory graph unavailable",
            request_id=request_id,
        )
    return create_success_response(
        data={"activity_id": None, "stored": False},
        message="Activity received but memory graph unavailable",
        request_id=request_id,
    )


async def _store_single_activity(
    memory_graph: AutoBotMemoryGraph,
    session_id: str,
    activity: ActivityCreate,
) -> Dict:
    """
    Store a single activity in memory graph.

    Issue #665: Extracted helper for activity storage.

    Returns:
        Entity creation result dict
    """
    return await memory_graph.create_activity_entity(
        activity_type=f"{activity.type}_activity",
        session_id=session_id,
        user_id=activity.user_id,
        content=activity.content,
        secrets_used=activity.secrets_used,
        metadata={
            "frontend_id": activity.activity_id,
            "frontend_timestamp": activity.timestamp,
            **(activity.metadata or {}),
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_session_activity",
    error_code_prefix="CHAT",
)
@router.post("/chat/sessions/{session_id}/activities")
async def add_session_activity(
    session_id: str,
    activity_data: ActivityCreate,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
):
    """
    Add a single activity to a chat session.

    Issue #608: User-Centric Session Tracking - Phase 3
    Issue #665: Refactored to use extracted helpers for validation and storage.
    """
    request_id = generate_request_id()
    log_request_context(request, "add_session_activity", request_id)

    _validate_session_id_or_raise(session_id)

    memory_graph = _get_memory_graph_or_none(request)
    if not memory_graph:
        logger.warning("[%s] Memory graph not available", request_id)
        return _create_activity_unavailable_response(1, request_id, is_batch=False)

    try:
        activity_entity = await _store_single_activity(
            memory_graph, session_id, activity_data
        )

        log_chat_event(
            "activity_created",
            session_id,
            {
                "activity_id": activity_data.activity_id,
                "type": activity_data.type,
                "user_id": activity_data.user_id,
                "request_id": request_id,
            },
        )

        return create_success_response(
            data={
                "activity_id": activity_data.activity_id,
                "entity_id": activity_entity.get("entity_id"),
                "stored": True,
            },
            message="Activity recorded successfully",
            request_id=request_id,
            status_code=201,
        )

    except Exception as graph_error:
        logger.warning("[%s] Failed to store activity: %s", request_id, graph_error)
        return create_success_response(
            data={"activity_id": activity_data.activity_id, "stored": False},
            message="Activity received but storage failed",
            request_id=request_id,
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_session_activities_batch",
    error_code_prefix="CHAT",
)
@router.post("/chat/sessions/{session_id}/activities/batch")
async def add_session_activities_batch(
    session_id: str,
    batch_data: ActivityBatchCreate,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
):
    """
    Add multiple activities to a chat session in a single request.

    Issue #608: User-Centric Session Tracking - Phase 3
    Issue #665: Refactored to use extracted helpers for validation and storage.
    """
    request_id = generate_request_id()
    log_request_context(request, "add_session_activities_batch", request_id)

    _validate_session_id_or_raise(session_id)

    memory_graph = _get_memory_graph_or_none(request)
    total_activities = len(batch_data.activities)

    if not memory_graph:
        logger.warning("[%s] Memory graph not available, %d activities not persisted", request_id, total_activities)
        return _create_activity_unavailable_response(total_activities, request_id, is_batch=True)

    stored_count = 0
    failed_count = 0
    stored_ids: List[str] = []

    for activity in batch_data.activities:
        try:
            await _store_single_activity(memory_graph, session_id, activity)
            stored_count += 1
            stored_ids.append(activity.activity_id)
        except Exception as activity_error:
            logger.warning("[%s] Failed to store activity %s: %s", request_id, activity.activity_id, activity_error)
            failed_count += 1

    log_chat_event(
        "activities_batch_created",
        session_id,
        {"total": total_activities, "stored": stored_count, "failed": failed_count, "request_id": request_id},
    )

    return create_success_response(
        data={"total": total_activities, "stored": stored_count, "failed": failed_count, "stored_ids": stored_ids},
        message=f"Batch processed: {stored_count} stored, {failed_count} failed",
        request_id=request_id,
        status_code=201 if stored_count > 0 else 200,
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_activities",
    error_code_prefix="CHAT",
)
@router.get("/chat/sessions/{session_id}/activities")
async def get_session_activities(
    session_id: str,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
    activity_type: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 100,
):
    """
    Get activities for a chat session with optional filtering.

    Issue #608: User-Centric Session Tracking - Phase 3
    Retrieves activities from memory graph.
    """
    request_id = generate_request_id()
    log_request_context(request, "get_session_activities", request_id)

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

    # Get memory graph from app state
    memory_graph: Optional[AutoBotMemoryGraph] = getattr(
        request.app.state, "memory_graph", None
    )

    if not memory_graph:
        return create_success_response(
            data={"activities": [], "total": 0},
            message="Memory graph unavailable",
            request_id=request_id,
        )

    try:
        # Get session activities from memory graph
        activities = await memory_graph.get_session_activities(
            session_id=session_id,
            activity_type=activity_type,
            user_id=user_id,
            limit=limit,
        )

        return create_success_response(
            data={
                "activities": activities,
                "total": len(activities),
                "session_id": session_id,
            },
            message="Activities retrieved successfully",
            request_id=request_id,
        )

    except Exception as graph_error:
        logger.warning(
            "[%s] Failed to retrieve activities: %s",
            request_id,
            graph_error,
        )
        return create_success_response(
            data={"activities": [], "total": 0},
            message="Failed to retrieve activities",
            request_id=request_id,
        )
