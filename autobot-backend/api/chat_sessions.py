# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""
REST endpoints for chat session lifecycle management.

Exposes CRUD operations over persistent chat sessions, delegating
storage to the chat_history subsystem.
"""

import json
from typing import Dict, List

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from api.schemas_chat import (
    ActivityAddData,
    ActivityBatchCreate,
    ActivityBatchData,
    ActivityCreate,
    ChatResetData,
    ChatResetRequest,
    SessionActivitiesData,
    SessionCheckpointClearData,
    SessionCreate,
    SessionCreateData,
    SessionDeleteData,
    SessionListData,
    SessionMessagesData,
    SessionShareData,
    SessionSharePreviewData,
    SessionShareRequest,
    SessionUpdate,
    SessionUpdateData,
)
from api.schemas_common import DataResponse
from auth_middleware import get_auth_middleware, get_current_user
from autobot_memory_graph import AutoBotMemoryGraph
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

# Import session lifecycle hooks (Issue #4260)
from chat_workflow.session_handler import _emit_session_create, _emit_session_destroy

# Import shared exception classes (Issue #292 - Eliminate duplicate code)
from exceptions import get_exceptions_lazy

# CRITICAL SECURITY FIX: Import session ownership validation
from security.session_ownership import validate_session_ownership

# Issue #6559: Wire audit_record into session create/delete/export endpoints
from services.audit.unified_audit import AuditAction, audit_record  # GH#8290 Phase 2
from type_defs.common import Metadata

# Import reusable chat utilities
from utils.chat_utils import (
    create_chat_response,
    create_error_response,
    generate_chat_session_id,
    generate_request_id,
    get_chat_history_manager,
    log_chat_event,
    validate_chat_session_id,
)
from utils.response_helpers import create_success_response

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["chat-sessions"])
logger = get_logger(__name__)

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
            f"Transferred {transfer_result.get('total_transferred', 0)} files " f"to KB for session {session_id}"
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
# Configuration Constants
# ====================================================================

DEFAULT_SESSION_TITLE = "New Chat Session"


# ====================================================================
# Validation Helpers (Issue #620)
# ====================================================================


def _validate_session_id_or_raise(session_id: str) -> None:
    """
    Validate session ID format and raise ValidationError if invalid.

    Issue #620.

    Args:
        session_id: Session ID to validate

    Raises:
        ValidationError: If session ID format is invalid
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


def _validate_pagination_params(page: int, per_page: int) -> None:
    """
    Validate pagination parameters and raise ValidationError if invalid.

    Issue #620.

    Args:
        page: Page number (must be >= 1)
        per_page: Items per page (must be 1-100)

    Raises:
        ValidationError: If parameters are invalid
    """
    if page < 1 or per_page < 1 or per_page > 100:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Invalid pagination parameters")


async def _fetch_session_messages_or_raise(chat_history_manager, session_id: str, limit: int) -> List:
    """
    Fetch session messages and raise ResourceNotFoundError if session not found.

    Issue #620.
    Issue #1797: Granular exception mapping for session load failures.

    Args:
        chat_history_manager: Chat history manager instance
        session_id: Session ID to fetch messages for
        limit: Maximum messages to return

    Returns:
        List of messages

    Raises:
        ResourceNotFoundError: If session does not exist
        ValidationError: If session data is corrupted (ValueError)
        InternalError: If session cannot be accessed (PermissionError)
    """
    (
        AutoBotError,
        InternalError,
        ResourceNotFoundError,
        ValidationError,
        get_error_code,
    ) = get_exceptions_lazy()

    try:
        messages = await chat_history_manager.get_session_messages(session_id, limit=limit)
    except FileNotFoundError:
        logger.warning("Session file not found for session %s", session_id)
        raise ResourceNotFoundError(f"Session {session_id} not found")
    except PermissionError:
        logger.error("Permission denied accessing session %s", session_id)
        raise InternalError("Unable to access chat session")
    except ValueError as exc:
        logger.error("Corrupted session data for session %s: %s", session_id, exc)
        raise ValidationError("Chat session data is corrupted")

    if messages is None:
        raise ResourceNotFoundError(f"Session {session_id} not found")

    return messages


def _validate_export_format_or_raise(export_format: str) -> None:
    """
    Validate export format and raise ValidationError if invalid.

    Issue #620.

    Args:
        export_format: Format to validate (json, txt, csv)

    Raises:
        ValidationError: If format is not supported
    """
    if export_format not in VALID_EXPORT_FORMATS:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Invalid export format. Supported: json, txt, csv")


async def _export_session_data_or_raise(chat_history_manager, session_id: str, export_format: str) -> str:
    """
    Export session data and raise ResourceNotFoundError if session not found.

    Issue #620.

    Args:
        chat_history_manager: Chat history manager instance
        session_id: Session ID to export
        export_format: Export format (json, txt, csv)

    Returns:
        Exported session data as string

    Raises:
        ResourceNotFoundError: If session does not exist
    """
    session_data = await chat_history_manager.export_session(session_id, export_format)

    if session_data is None:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ResourceNotFoundError(f"Session {session_id} not found")

    return session_data


# Content type mapping for export formats (Issue #620)
_EXPORT_CONTENT_TYPES = {
    "json": "application/json",
    "txt": "text/plain",
    "csv": "text/csv",
}


# ====================================================================
# API Endpoints - Session Management
# ====================================================================


@router.get("/chat/sessions/{session_id}", response_model=DataResponse[SessionMessagesData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_messages",
    error_code_prefix="CHAT_SESSIONS",
)
async def get_session_messages(
    session_id: str,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),  # SECURITY: Validate ownership
    page: int = 1,
    per_page: int = 50,
):
    """
    Get messages for a specific chat session.

    Issue #620: Refactored using Extract Method pattern.
    """
    request_id = generate_request_id()
    log_request_context(request, "get_session_messages", request_id)

    # Validate inputs (Issue #620: use helpers)
    _validate_session_id_or_raise(session_id)
    _validate_pagination_params(page, per_page)

    chat_history_manager = get_chat_history_manager(request)

    messages = await _fetch_session_messages_or_raise(chat_history_manager, session_id, per_page)
    total_count = await chat_history_manager.get_session_message_count(session_id)

    return create_chat_response(
        data={
            "messages": messages,
            "session_id": session_id,
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
        },
        message="Session messages retrieved successfully",
        request_id=request_id,
    )


@router.get("/chat/sessions", response_model=DataResponse[SessionListData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_sessions",
    error_code_prefix="CHAT_SESSIONS",
)
async def list_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    scope: str | None = None,
    team_id: str | None = None,
):
    """List chat sessions with optional org/team/shared scope filtering (#684, #689).

    Issue #1543: Requires authentication.

    Query params:
        scope: "user" (default) | "org" | "team" | "shared"
        team_id: required when scope=team
    """
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

    # Issue #689: Shared session listing
    if scope == "shared":
        return await _list_shared_sessions(request, request_id, chat_history_manager)

    # Issue #684: Scoped session listing
    if scope in ("org", "team"):
        return await _list_scoped_sessions(request, request_id, chat_history_manager, scope, team_id)

    # Default: list all sessions (fast mode, no decryption)
    sessions = await chat_history_manager.list_sessions_fast()

    # Filter to authenticated user's own sessions
    username = current_user.get("username")
    if username:
        sessions = await _filter_user_sessions(sessions, username)

    # Issue #4352: Signal intentional empty to distinguish from API failure.
    # When an authenticated request returns 0 sessions, mark it explicitly so
    # the frontend can clear local sessions instead of preserving them.
    response_data: dict = {"sessions": sessions, "count": len(sessions)}
    if len(sessions) == 0:
        response_data["intentional_empty"] = True

    return create_chat_response(
        data=response_data,
        message="Sessions retrieved successfully",
        request_id=request_id,
    )


async def _filter_user_sessions(sessions: list, username: str) -> list:
    """Filter sessions to those owned by the user.

    Uses Redis ownership data. Falls back to all sessions
    if Redis is unavailable.

    Helper for list_sessions (#684).
    """
    from autobot_shared.redis_client import get_redis_client as get_redis_mgr

    try:
        redis = await get_redis_mgr(async_client=True, database="main")
        validator = _build_ownership_validator(redis)
        user_session_ids = set(await validator.get_user_sessions(username))
        if not user_session_ids:
            return sessions  # No ownership data yet; return all
        return [s for s in sessions if s.get("id") in user_session_ids]
    except Exception as e:
        logger.debug("Could not filter by user ownership: %s", e)
        return sessions


def _build_ownership_validator(redis):
    """Build a SessionOwnershipValidator instance (#684)."""
    from security.session_ownership import SessionOwnershipValidator

    return SessionOwnershipValidator(redis)


async def _list_scoped_sessions(
    request: Request,
    request_id: str,
    chat_history_manager,
    scope: str,
    team_id: str | None,
):
    """List sessions scoped to org or team.

    Requires admin role for org scope.

    Helper for list_sessions (#684).
    """
    user_data = get_auth_middleware().get_user_from_request(request)
    if not user_data:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Authentication required for scoped listing")

    from autobot_shared.redis_client import get_redis_client as get_redis_mgr

    redis = await get_redis_mgr(async_client=True, database="main")
    validator = _build_ownership_validator(redis)

    if scope == "org":
        return await _list_org_sessions(user_data, validator, chat_history_manager, request_id)

    # scope == "team"
    if not team_id:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("team_id required for team scope")

    return await _list_team_sessions(team_id, validator, chat_history_manager, request_id)


async def _list_org_sessions(
    user_data: dict,
    validator,
    chat_history_manager,
    request_id: str,
):
    """List all sessions in the user's organization.

    Requires admin or org_admin role.

    Helper for _list_scoped_sessions (#684).
    """
    org_id = user_data.get("org_id")
    user_role = user_data.get("role", "")
    if not org_id:
        return create_chat_response(
            data={"sessions": [], "count": 0, "scope": "org"},
            message="User has no organization",
            request_id=request_id,
        )
    if user_role not in ("admin", "org_admin"):
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Admin role required for org-scoped listing")

    session_ids = set(await validator.get_org_sessions(org_id))
    all_sessions = await chat_history_manager.list_sessions_fast()
    filtered = [s for s in all_sessions if s.get("id") in session_ids]
    filtered.sort(key=lambda x: x.get("lastModified", ""), reverse=True)

    return create_chat_response(
        data={
            "sessions": filtered,
            "count": len(filtered),
            "scope": "org",
            "org_id": org_id,
        },
        message="Organization sessions retrieved",
        request_id=request_id,
    )


async def _list_team_sessions(
    team_id: str,
    validator,
    chat_history_manager,
    request_id: str,
):
    """List all sessions for a specific team.

    Helper for _list_scoped_sessions (#684).
    """
    session_ids = set(await validator.get_team_sessions(team_id))
    all_sessions = await chat_history_manager.list_sessions_fast()
    filtered = [s for s in all_sessions if s.get("id") in session_ids]
    filtered.sort(key=lambda x: x.get("lastModified", ""), reverse=True)

    return create_chat_response(
        data={
            "sessions": filtered,
            "count": len(filtered),
            "scope": "team",
            "team_id": team_id,
        },
        message="Team sessions retrieved",
        request_id=request_id,
    )


async def _list_shared_sessions(
    request: Request,
    request_id: str,
    chat_history_manager,
):
    """List sessions shared with the authenticated user (#689).

    Helper for list_sessions.
    """
    user_data = get_auth_middleware().get_user_from_request(request)
    if not user_data:
        return create_chat_response(
            data={"sessions": [], "count": 0, "scope": "shared"},
            message="Authentication required",
            request_id=request_id,
        )

    from autobot_shared.redis_client import get_redis_client as get_redis_mgr

    redis = await get_redis_mgr(async_client=True, database="main")
    from security.session_ownership import SessionOwnershipValidator

    validator = SessionOwnershipValidator(redis)
    user_id = user_data.get("user_id", user_data.get("username"))
    session_ids = set(await validator.get_shared_sessions(user_id))

    if not session_ids:
        return create_chat_response(
            data={"sessions": [], "count": 0, "scope": "shared"},
            message="No shared sessions",
            request_id=request_id,
        )

    all_sessions = await chat_history_manager.list_sessions_fast()
    filtered = [s for s in all_sessions if s.get("id") in session_ids]
    filtered.sort(key=lambda x: x.get("lastModified", ""), reverse=True)

    return create_chat_response(
        data={
            "sessions": filtered,
            "count": len(filtered),
            "scope": "shared",
        },
        message="Shared sessions retrieved",
        request_id=request_id,
    )


async def _register_session_ownership(
    user_data: dict | None,
    session_id: str,
    team_id: str | None,
) -> None:
    """Register session ownership with org/team indices in Redis.

    Helper for create_session (#684).
    """
    if not user_data or not user_data.get("username"):
        return
    try:
        from autobot_shared.redis_client import get_redis_client as get_redis_mgr

        redis = await get_redis_mgr(async_client=True, database="main")
        validator = _build_ownership_validator(redis)
        await validator.set_session_owner(
            session_id=session_id,
            username=user_data["username"],
            org_id=user_data.get("org_id"),
            team_id=team_id,
        )
    except Exception as e:
        logger.warning("Failed to register session ownership: %s", e)


async def _track_session_in_memory_graph(
    request: Request,
    session_id: str,
    session_title: str,
    user_data: dict | None,
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
    memory_graph: AutoBotMemoryGraph | None = getattr(request.app.state, "memory_graph", None)
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


@router.post("/chat/sessions", response_model=DataResponse[SessionCreateData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_session",
    error_code_prefix="CHAT_SESSIONS",
)
async def create_session(session_data: SessionCreate, request: Request):
    """
    Create a new chat session.

    Issue #665: Refactored to use extracted helper for memory graph tracking.
    """
    request_id = generate_request_id()
    log_request_context(request, "create_session", request_id)

    chat_history_manager = get_chat_history_manager(request)
    # #6746: accept client-supplied session_id when provided and well-formed,
    # so the frontend's locally-minted UUID survives the round-trip and
    # frontend/backend stay aligned. Falls back to server-mint when absent
    # (legacy callers, CLI, tests).
    if session_data.id and validate_chat_session_id(session_data.id):
        session_id = session_data.id
    else:
        session_id = generate_chat_session_id()
    session_title = session_data.title or DEFAULT_SESSION_TITLE

    # SECURITY: Extract authenticated user and add to metadata as owner
    user_data = get_auth_middleware().get_user_from_request(request)
    metadata = session_data.metadata or {}
    if user_data and user_data.get("username"):
        metadata["owner"] = user_data["username"]
        metadata["username"] = user_data["username"]  # For backward compatibility
        # Issue #684: Capture org/team hierarchy in session metadata
        if user_data.get("user_id"):
            metadata["user_id"] = user_data["user_id"]
        if user_data.get("org_id"):
            metadata["org_id"] = user_data["org_id"]
        if session_data.team_id:
            metadata["team_id"] = session_data.team_id
        logger.info(
            "Session %s created with owner: %s (org: %s)",
            session_id,
            user_data["username"],
            user_data.get("org_id", "none"),
        )

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

    # Issue #684: Register session ownership with org/team context
    await _register_session_ownership(user_data, session_id, session_data.team_id)

    # Issue #665: Use helper for memory graph tracking
    await _track_session_in_memory_graph(request, session_id, session_title, user_data, request_id)

    # Issue #4260: Wire SESSION_CREATE hook for extensions
    context = getattr(request.app.state, "context", {})
    await _emit_session_create(session_id, context)

    # Issue #6559: Audit session creation
    audit_record(
        user_id=str((user_data or {}).get("user_id", "unknown")),
        action=AuditAction.SESSION_CREATE,
        resource_type="chat_session",
        resource_id=session_id,
        ip_address=request.client.host if request.client else "unknown",
        session_id=session_id,
        metadata={
            "title": session_title,
            "team_id": session_data.team_id,
            "request_id": request_id,
        },
        outcome="success",
    )

    return create_chat_response(
        data=session,
        message="Session created successfully",
        request_id=request_id,
        status_code=201,
    )


@router.put("/chat/sessions/{session_id}", response_model=DataResponse[SessionUpdateData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_session",
    error_code_prefix="CHAT_SESSIONS",
)
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),  # SECURITY: Validate ownership
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

    return create_chat_response(
        data=updated_session,
        message="Session updated successfully",
        request_id=request_id,
    )


# =============================================================================
# Helper Functions for delete_session (Issue #281, #665)
# =============================================================================


def _validate_delete_session_params(session_id: str, file_action: str, file_options: str | None) -> dict:
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
        raise ValidationError(f"Invalid file_action. Must be one of: {sorted(_VALID_FILE_ACTIONS)}")

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
    conversation_file_manager = getattr(request.app.state, "conversation_file_manager", None)

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
        logger.warning(f"ConversationFileManager not available, " f"skipping file handling for session {session_id}")

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
            f"AgentTerminalService not available, " f"skipping terminal session cleanup for session {session_id}"
        )
        return terminal_cleanup_result

    try:
        terminal_sessions = await agent_terminal_service.list_sessions(conversation_id=session_id)

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
            f"Failed to cleanup terminal sessions for chat {session_id}: " f"{terminal_cleanup_error}",
            exc_info=True,
        )
        terminal_cleanup_result["error"] = str(terminal_cleanup_error)

    return terminal_cleanup_result


def _get_knowledge_base_or_none(request: Request):
    """
    Get knowledge base from app state or None if unavailable.

    Issue #620.
    """
    return getattr(request.app.state, "knowledge_base", None)


def _create_kb_cleanup_result() -> dict:
    """
    Create initial KB cleanup result dictionary.

    Issue #620.
    """
    return {
        "facts_deleted": 0,
        "facts_preserved": 0,
        "cleanup_error": None,
    }


def _process_kb_deletion_result(result: dict, kb_cleanup_result: dict) -> None:
    """
    Process and update cleanup result from knowledge base deletion.

    Issue #620.

    Args:
        result: Result from knowledge_base.delete_facts_by_session
        kb_cleanup_result: Result dict to update in place
    """
    kb_cleanup_result["facts_deleted"] = result.get("deleted_count", 0)
    kb_cleanup_result["facts_preserved"] = result.get("preserved_count", 0)

    if result.get("errors"):
        kb_cleanup_result["cleanup_error"] = f"{len(result['errors'])} errors during cleanup"


def _log_kb_cleanup_result(session_id: str, kb_cleanup_result: dict, errors: List | None = None) -> None:
    """
    Log KB cleanup results appropriately based on outcome.

    Issue #620.

    Args:
        session_id: Session being cleaned up
        kb_cleanup_result: Cleanup result dictionary
        errors: Optional list of errors from deletion
    """
    if errors:
        logger.warning(
            "KB cleanup completed with errors for session %s: %s",
            session_id,
            errors,
        )

    if kb_cleanup_result["facts_deleted"] > 0 or kb_cleanup_result["facts_preserved"] > 0:
        logger.info(
            "KB cleanup for session %s: deleted=%d, preserved=%d",
            session_id,
            kb_cleanup_result["facts_deleted"],
            kb_cleanup_result["facts_preserved"],
        )


async def _cleanup_knowledge_base_facts(request: Request, session_id: str) -> dict:
    """
    Clean up knowledge base facts created during this session.

    Issue #547: Fixes orphaned KB data when conversations are deleted.
    Issue #620: Refactored using Extract Method pattern.

    Args:
        request: FastAPI request object with app.state
        session_id: Chat session ID being deleted

    Returns:
        Dict with cleanup statistics
    """
    kb_cleanup_result = _create_kb_cleanup_result()

    knowledge_base = _get_knowledge_base_or_none(request)
    if not knowledge_base:
        logger.warning(
            "Knowledge base not available, skipping KB cleanup for session %s",
            session_id,
        )
        return kb_cleanup_result

    try:
        result = await knowledge_base.delete_facts_by_session(
            session_id=session_id,
            preserve_important=True,
        )
        _process_kb_deletion_result(result, kb_cleanup_result)
        _log_kb_cleanup_result(session_id, kb_cleanup_result, result.get("errors"))

    except Exception as kb_cleanup_error:
        logger.error(
            "Failed to cleanup KB facts for session %s: %s",
            session_id,
            kb_cleanup_error,
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

    from autobot_shared.security.path_validator import validate_relative_path
    from constants.path_constants import PATH

    result = {"transcript_deleted": False, "error": None}

    try:
        if "/" in session_id or "\\" in session_id or ".." in session_id:
            raise ValueError("Invalid session ID")

        transcript_path = validate_relative_path(
            f"{session_id}.json",
            PATH.DATA_DIR / "conversation_transcripts",
        )

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
    file_deletion_result = await _handle_conversation_files(request, session_id, file_action, parsed_file_options)

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


async def _delete_session_and_verify(chat_history_manager, session_id: str) -> None:
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


def _build_delete_session_response(
    session_id: str,
    request_id: str,
    file_deletion_result: dict,
    terminal_cleanup_result: dict,
    kb_cleanup_result: dict,
    transcript_cleanup_result: dict,
) -> dict:
    """
    Build response data for delete_session endpoint.

    Issue #620.

    Args:
        session_id: Deleted session ID
        request_id: Request tracking ID
        file_deletion_result: Result from file handling
        terminal_cleanup_result: Result from terminal cleanup
        kb_cleanup_result: Result from KB cleanup
        transcript_cleanup_result: Result from transcript cleanup

    Returns:
        Success response with deletion details
    """
    return create_chat_response(
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


@router.delete("/chat/sessions/{session_id}", response_model=DataResponse[SessionDeleteData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_session",
    error_code_prefix="CHAT_SESSIONS",
)
async def delete_session(
    session_id: str,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),  # SECURITY: Validate ownership
    file_action: str = "delete",
    file_options: str | None = None,
):
    """
    Delete a chat session with comprehensive cleanup.

    Issue #281, #547, #620: Refactored using Extract Method pattern.
    """
    request_id = generate_request_id()
    log_request_context(request, "delete_session", request_id)

    parsed_file_options = _validate_delete_session_params(session_id, file_action, file_options)

    chat_history_manager = get_chat_history_manager(request)

    # Issue #4260: Get message count before deletion for SESSION_DESTROY hook
    message_count = await chat_history_manager.get_session_message_count(session_id)
    # Perform all cleanup operations (Issue #620)
    (
        file_result,
        terminal_result,
        kb_result,
        transcript_result,
    ) = await _perform_all_session_cleanup(request, session_id, file_action, parsed_file_options)

    await _delete_session_and_verify(chat_history_manager, session_id)

    log_chat_event(
        "session_deleted",
        session_id,
        {"request_id": request_id, "file_action": file_action},
    )

    # Issue #4260: Wire SESSION_DESTROY hook for extensions
    context = getattr(request.app.state, "context", {})
    await _emit_session_destroy(session_id, message_count, context)

    # Issue #6559: Audit session deletion
    user_data = get_auth_middleware().get_user_from_request(request)
    audit_record(
        user_id=str((user_data or {}).get("user_id", "unknown")),
        action=AuditAction.SESSION_DELETE,
        resource_type="chat_session",
        resource_id=session_id,
        ip_address=request.client.host if request.client else "unknown",
        session_id=session_id,
        metadata={
            "file_action": file_action,
            "message_count": message_count,
            "request_id": request_id,
        },
        outcome="success",
    )

    return _build_delete_session_response(
        session_id,
        request_id,
        file_result,
        terminal_result,
        kb_result,
        transcript_result,
    )


@router.get("/chat/sessions/{session_id}/export", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_session",
    error_code_prefix="CHAT_SESSIONS",
)
async def export_session(session_id: str, request: Request, format: str = "json"):
    """
    Export a chat session in various formats.

    Issue #620: Refactored using Extract Method pattern.
    """
    request_id = generate_request_id()
    log_request_context(request, "export_session", request_id)

    # Validate inputs (Issue #620: use helpers)
    _validate_session_id_or_raise(session_id)
    _validate_export_format_or_raise(format)

    chat_history_manager = get_chat_history_manager(request)

    session_data = await _export_session_data_or_raise(chat_history_manager, session_id, format)

    log_chat_event("session_exported", session_id, {"format": format, "request_id": request_id})

    # Issue #6559: Audit session export
    user_data = get_auth_middleware().get_user_from_request(request)
    audit_record(
        user_id=str((user_data or {}).get("user_id", "unknown")),
        action=AuditAction.SESSION_EXPORT,
        resource_type="chat_session",
        resource_id=session_id,
        ip_address=request.client.host if request.client else "unknown",
        session_id=session_id,
        metadata={
            "format": format,
            "request_id": request_id,
        },
        outcome="success",
    )

    return Response(
        content=session_data,
        media_type=_EXPORT_CONTENT_TYPES[format],
        headers={"Content-Disposition": (f"attachment; filename=chat_session_{session_id}.{format}")},
    )


# =============================================================================
# Issue #549: Chat Reset Endpoint
# =============================================================================


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


def _to_persisted_system_message(msg: Dict) -> Dict:
    """Translate api-shape (role/content) to disk-shape (sender/content/type).

    #7025: ``_preserve_system_messages`` returns messages with ``role`` keys
    (filtered by ``role == "system"``). The disk schema (used by
    ``add_messages_batch`` and the JSON files in ``data/chats/``) expects
    ``sender``/``content``/``type``/``metadata``/``sources`` instead. Mirrors
    ``api/chat.py:_to_persisted_message`` for the system-message subset.
    """
    return {
        "id": msg.get("id", ""),
        "sender": msg.get("role") or msg.get("sender") or "system",
        "content": msg.get("content", ""),
        "timestamp": msg.get("timestamp"),
        "type": msg.get("type", "message"),
        "metadata": msg.get("metadata") or {},
        "sources": msg.get("sources", []),
    }


async def _clear_and_restore_session(chat_manager, session_id: str, messages_to_restore: List[Dict]) -> int:
    """
    Clear session and restore specified messages.

    Issue #665: Extracted helper for session clearing with message restoration.
    Issue #7025: previously called ``add_message(session_id, dict)`` — the
    same wrong-signature pattern that #6744 fixed in api/chat.py. Python
    silently accepted UUID as ``sender`` and dict as ``text``, leaving
    ``session_id=None`` so messages landed in the default in-memory
    bucket — restored messages were never written to disk. Now uses
    ``add_messages_batch(session_id, [...])`` (correct signature) with
    disk-shape conversion.

    Returns number of messages restored.
    """
    chat_manager.clear_session(session_id)
    if not messages_to_restore:
        return 0
    if hasattr(chat_manager, "add_messages_batch"):
        persisted = [_to_persisted_system_message(m) for m in messages_to_restore]
        await chat_manager.add_messages_batch(session_id, persisted)
    return len(messages_to_restore)


@router.post("/chat/reset", response_model=DataResponse[ChatResetData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_chat",
    error_code_prefix="CHAT_SESSIONS",
)
async def reset_chat(request: Request, reset_request: ChatResetRequest | None = None):
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
            messages_to_keep = _preserve_system_messages(chat_history_manager, session_id) if keep_system_prompt else []
            restored = await _clear_and_restore_session(chat_history_manager, session_id, messages_to_keep)
            logger.info("Reset chat session: %s, kept %d system messages", session_id, restored)

    log_chat_event(
        "session_reset",
        session_id,
        {
            "request_id": request_id,
            "clear_context": clear_context,
            "keep_system_prompt": keep_system_prompt,
        },
    )

    return create_chat_response(
        data={
            "session_id": session_id,
            "reset": True,
            "clear_context": clear_context,
            "keep_system_prompt": keep_system_prompt,
        },
        message="Chat session reset successfully",
        request_id=request_id,
    )


# ====================================================================
# API Endpoints - Activity Tracking (Issue #608)
# ====================================================================


def _get_memory_graph_or_none(request: Request) -> AutoBotMemoryGraph | None:
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
        return create_chat_response(
            data={"total": activity_count, "stored": 0, "failed": activity_count},
            message="Activities received but memory graph unavailable",
            request_id=request_id,
        )
    return create_chat_response(
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


async def _process_activity_batch(
    memory_graph: AutoBotMemoryGraph,
    session_id: str,
    activities: List[ActivityCreate],
    request_id: str,
) -> Dict:
    """
    Process a batch of activities and store them in memory graph.

    Issue #620.

    Args:
        memory_graph: Memory graph instance for storage
        session_id: Session ID for the activities
        activities: List of activities to process
        request_id: Request ID for logging

    Returns:
        Dict with stored_count, failed_count, and stored_ids
    """
    stored_count = 0
    failed_count = 0
    stored_ids: List[str] = []

    for activity in activities:
        try:
            await _store_single_activity(memory_graph, session_id, activity)
            stored_count += 1
            stored_ids.append(activity.activity_id)
        except Exception as activity_error:
            logger.warning(
                "[%s] Failed to store activity %s: %s",
                request_id,
                activity.activity_id,
                activity_error,
            )
            failed_count += 1

    return {
        "stored_count": stored_count,
        "failed_count": failed_count,
        "stored_ids": stored_ids,
    }


@router.post("/chat/sessions/{session_id}/activities", response_model=DataResponse[ActivityAddData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_session_activity",
    error_code_prefix="CHAT_SESSIONS",
)
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
        activity_entity = await _store_single_activity(memory_graph, session_id, activity_data)

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

        return create_chat_response(
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
        return create_chat_response(
            data={"activity_id": activity_data.activity_id, "stored": False},
            message="Activity received but storage failed",
            request_id=request_id,
        )


@router.post("/chat/sessions/{session_id}/activities/batch", response_model=DataResponse[ActivityBatchData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_session_activities_batch",
    error_code_prefix="CHAT_SESSIONS",
)
async def add_session_activities_batch(
    session_id: str,
    batch_data: ActivityBatchCreate,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
):
    """
    Add multiple activities to a chat session in a single request.

    Issue #608: User-Centric Session Tracking - Phase 3
    Issue #620: Refactored using Extract Method pattern.
    """
    request_id = generate_request_id()
    log_request_context(request, "add_session_activities_batch", request_id)

    _validate_session_id_or_raise(session_id)

    memory_graph = _get_memory_graph_or_none(request)
    total_activities = len(batch_data.activities)

    if not memory_graph:
        logger.warning(
            "[%s] Memory graph not available, %d activities not persisted",
            request_id,
            total_activities,
        )
        return _create_activity_unavailable_response(total_activities, request_id, is_batch=True)

    # Process batch using extracted helper (Issue #620)
    result = await _process_activity_batch(memory_graph, session_id, batch_data.activities, request_id)

    log_chat_event(
        "activities_batch_created",
        session_id,
        {
            "total": total_activities,
            "stored": result["stored_count"],
            "failed": result["failed_count"],
            "request_id": request_id,
        },
    )

    return create_chat_response(
        data={
            "total": total_activities,
            "stored": result["stored_count"],
            "failed": result["failed_count"],
            "stored_ids": result["stored_ids"],
        },
        message=f"Batch processed: {result['stored_count']} stored, {result['failed_count']} failed",
        request_id=request_id,
        status_code=201 if result["stored_count"] > 0 else 200,
    )


async def _fetch_activities_from_graph(
    memory_graph,
    session_id: str,
    activity_type,
    user_id,
    limit: int,
    request_id: str,
):
    """Helper for get_session_activities. Ref: #1088."""
    try:
        activities = await memory_graph.get_session_activities(
            session_id=session_id,
            activity_type=activity_type,
            user_id=user_id,
            limit=limit,
        )
        return create_chat_response(
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
        return create_chat_response(
            data={"activities": [], "total": 0},
            message="Failed to retrieve activities",
            request_id=request_id,
        )


@router.get("/chat/sessions/{session_id}/activities", response_model=DataResponse[SessionActivitiesData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_activities",
    error_code_prefix="CHAT_SESSIONS",
)
async def get_session_activities(
    session_id: str,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
    activity_type: str | None = None,
    user_id: str | None = None,
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
    memory_graph: AutoBotMemoryGraph | None = getattr(request.app.state, "memory_graph", None)

    if not memory_graph:
        return create_chat_response(
            data={"activities": [], "total": 0},
            message="Memory graph unavailable",
            request_id=request_id,
        )

    return await _fetch_activities_from_graph(memory_graph, session_id, activity_type, user_id, limit, request_id)


# ====================================================================
# Session Sharing (Issue #689)
# ====================================================================


async def _share_session_facts(
    request: Request,
    session_id: str,
    share_with: list[str],
    shared_by: str,
    knowledge_facts: list[str] | None,
) -> Dict:
    """Share KB facts from a session with other users.

    Helper for share_session (#689).
    """
    kb_manager = getattr(request.app.state, "kb_manager", None)
    if not kb_manager:
        return {"shared_count": 0, "errors": ["KB manager unavailable"]}

    if knowledge_facts:
        fact_ids = knowledge_facts
    else:
        fact_ids = await kb_manager.get_facts_by_session(session_id)

    if not fact_ids:
        return {"shared_count": 0, "errors": []}

    return await kb_manager.share_facts(fact_ids, share_with, shared_by)


@router.post("/chat/sessions/{session_id}/share", response_model=DataResponse[SessionShareData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="share_session",
    error_code_prefix="CHAT_SESSIONS",
)
async def share_session(
    session_id: str,
    share_data: SessionShareRequest,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
):
    """Share a conversation with other users, optionally including KB facts (#689)."""
    request_id = generate_request_id()
    log_request_context(request, "share_session", request_id)

    _validate_session_id_or_raise(session_id)

    user_data = ownership.get("user_data", {})
    shared_by = user_data.get("username", "unknown")

    # Share session access
    from autobot_shared.redis_client import get_redis_client as get_redis_mgr
    from security.session_ownership import SessionOwnershipValidator

    redis = await get_redis_mgr(async_client=True, database="main")
    validator = SessionOwnershipValidator(redis)
    await validator.share_session(session_id, share_data.share_with, shared_by)

    # Optionally share KB facts
    facts_result = None
    if share_data.include_knowledge:
        facts_result = await _share_session_facts(
            request,
            session_id,
            share_data.share_with,
            shared_by,
            share_data.knowledge_facts,
        )

    return create_chat_response(
        data={
            "session_id": session_id,
            "shared_with": share_data.share_with,
            "include_knowledge": share_data.include_knowledge,
            "facts_shared": facts_result,
        },
        message="Session shared successfully",
        request_id=request_id,
    )


@router.get("/chat/sessions/{session_id}/share/preview", response_model=DataResponse[SessionSharePreviewData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_share_preview",
    error_code_prefix="CHAT_SESSIONS",
)
async def get_share_preview(
    session_id: str,
    request: Request,
    ownership: Dict = Depends(validate_session_ownership),
):
    """Preview KB facts that would be shared with a session (#689)."""
    request_id = generate_request_id()
    _validate_session_id_or_raise(session_id)

    kb_manager = getattr(request.app.state, "kb_manager", None)
    facts = []
    if kb_manager:
        fact_ids = await kb_manager.get_facts_by_session(session_id)
        for fid in fact_ids:
            fact = kb_manager.get_fact(fid)
            if fact:
                facts.append(
                    {
                        "id": fact.get("fact_id", fid),
                        "content": fact.get("content", "")[:200],
                        "full_content": fact.get("content", ""),
                        "metadata": fact.get("metadata", {}),
                    }
                )

    return create_chat_response(
        data={
            "session_id": session_id,
            "fact_count": len(facts),
            "facts": facts,
        },
        message="Share preview retrieved",
        request_id=request_id,
    )


@router.delete("/sessions/{session_id}/checkpoints", response_model=DataResponse[SessionCheckpointClearData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_session_checkpoints",
    error_code_prefix="CHAT_SESSIONS",
)
async def clear_session_checkpoints(
    session_id: str,
    current_user: Dict = Depends(get_current_user),
):
    """Clear LangGraph checkpoints for a session (#1482).

    Admin-only endpoint for recovering broken sessions whose checkpoints
    are corrupted or stuck.  Delegates to ``delete_thread_checkpoints``
    which removes the Redis-backed LangGraph checkpoint data.
    """
    user_role = current_user.get("role", "")
    if user_role not in ("admin", "org_admin"):
        (
            _AutoBotError,
            _InternalError,
            _ResourceNotFoundError,
            ValidationError,
            _get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Admin role required to clear session checkpoints")
    try:
        from chat_workflow.graph import delete_thread_checkpoints

        await delete_thread_checkpoints(session_id)
        logger.info("Cleared checkpoints for session %s (#1482)", session_id)
        return create_success_response(
            data={"session_id": session_id},
            message=f"Checkpoints cleared for session {session_id}",
        )
    except Exception:
        logger.exception("Failed to clear checkpoints for %s", session_id)
        return create_error_response(
            error="Failed to clear checkpoints",
            status_code=500,
        )
