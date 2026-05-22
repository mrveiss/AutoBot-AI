# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Export and Import API (#1808)

FastAPI router for conversation export and import endpoints.

Registered in feature_routers.py as:
    ("api.conversation_export", "/conversations", ["conversation-export"], "conversation_export")

Endpoints:
    GET  /api/conversations/{session_id}/export?format=json|markdown
    GET  /api/conversations/export-all
    POST /api/conversations/import
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from api.schemas_agent import ConversationImportRequest, ConversationImportResponse
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from exceptions import get_exceptions_lazy
from services.conversation_export import (
    export_all_conversations_json,
    export_conversation_json,
    export_conversation_markdown,
    import_conversation,
)
from utils.chat_utils import get_chat_history_manager, validate_chat_session_id

logger = get_logger(__name__)

router = APIRouter(tags=["conversation-export"])

# Valid export format set for O(1) lookup
_VALID_EXPORT_FORMATS = frozenset({"json", "markdown"})

# Content-type mapping keyed by format string
_CONTENT_TYPES = {
    "json": "application/json",
    "markdown": "text/markdown",
}

# File extension mapping keyed by format string
_FILE_EXTENSIONS = {
    "json": "json",
    "markdown": "md",
}

# Valid on_conflict values
_VALID_ON_CONFLICT = frozenset({"skip", "replace", "rename"})


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_format_or_raise(export_format: str) -> None:
    """Raise ValidationError when the requested format is not supported."""
    if export_format not in _VALID_EXPORT_FORMATS:
        _, _, _, ValidationError, _ = get_exceptions_lazy()
        raise ValidationError(f"Invalid format {export_format!r}. Supported: json, markdown")


def _validate_session_id_or_raise(session_id: str) -> None:
    """Raise ValidationError when session_id is not well-formed."""
    if not validate_chat_session_id(session_id):
        _, _, _, ValidationError, _ = get_exceptions_lazy()
        raise ValidationError(f"Invalid session_id: {session_id!r}")


def _validate_on_conflict_or_raise(on_conflict: str) -> None:
    """Raise ValidationError when on_conflict value is not recognised."""
    if on_conflict not in _VALID_ON_CONFLICT:
        _, _, _, ValidationError, _ = get_exceptions_lazy()
        raise ValidationError(f"Invalid on_conflict {on_conflict!r}. Supported: skip, replace, rename")


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


async def _run_export(
    chat_history_manager,
    session_id: str,
    export_format: str,
) -> str:
    """Run the appropriate exporter and raise ResourceNotFoundError on None."""
    _, _, ResourceNotFoundError, _, _ = get_exceptions_lazy()

    if export_format == "json":
        result = await export_conversation_json(chat_history_manager, session_id)
    else:
        result = await export_conversation_markdown(chat_history_manager, session_id)

    if result is None:
        raise ResourceNotFoundError(f"Session {session_id!r} not found")
    return result


def _build_export_response(content: str, session_id: str, export_format: str) -> Response:
    """Wrap export content in a download Response with correct headers."""
    ext = _FILE_EXTENSIONS[export_format]
    return Response(
        content=content.encode("utf-8"),
        media_type=_CONTENT_TYPES[export_format],
        headers={"Content-Disposition": (f"attachment; filename=conversation_{session_id}.{ext}")},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/conversations/{session_id}/export", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_conversation",
    error_code_prefix="CONVERSATION_EXPORT",
)
async def export_conversation(
    session_id: str,
    request: Request,
    format: str = Query(default="json", description="Export format: json or markdown"),
    current_user: dict = Depends(get_current_user),
):
    """
    Export a single conversation in JSON or Markdown format (#1808).

    - **json**: Enriched AutoBot JSON envelope with metadata and messages.
    - **markdown**: Human-readable Markdown with message headers.
    """
    _validate_session_id_or_raise(session_id)
    _validate_format_or_raise(format)

    chat_history_manager = get_chat_history_manager(request)
    content = await _run_export(chat_history_manager, session_id, format)

    logger.info(
        "Exported conversation %s as %s for user %s",
        session_id,
        format,
        current_user.get("username", "unknown"),
    )
    return _build_export_response(content, session_id, format)


@router.get("/conversations/export-all", response_class=Response)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_all_conversations",
    error_code_prefix="CONVERSATION_EXPORT",
)
async def export_all_conversations(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Export all conversations as a bulk JSON archive (#1808).

    Returns a JSON file containing every conversation stored on this instance.
    """
    chat_history_manager = get_chat_history_manager(request)
    archive = await export_all_conversations_json(chat_history_manager)

    if archive is None:
        _, InternalError, _, _, _ = get_exceptions_lazy()
        raise InternalError("Failed to build conversation archive")

    logger.info(
        "Bulk conversation export requested by user %s",
        current_user.get("username", "unknown"),
    )
    return Response(
        content=archive.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=conversations_export.json"},
    )


@router.post("/conversations/import", response_model=ConversationImportResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="import_conversation_endpoint",
    error_code_prefix="CONVERSATION_EXPORT",
)
async def import_conversation_endpoint(
    body: ConversationImportRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Import a conversation from an AutoBot JSON export document (#1808).

    The ``on_conflict`` field controls what happens when the session_id already
    exists:
    - **skip** (default): return without modifying existing data.
    - **replace**: overwrite the existing session with the imported data.
    - **rename**: save under a new session_id with a timestamped suffix.
    """
    _validate_on_conflict_or_raise(body.on_conflict)

    chat_history_manager = get_chat_history_manager(request)
    result = await import_conversation(
        chat_history_manager,
        document=body.document,
        on_conflict=body.on_conflict,
    )

    logger.info(
        "Conversation import by user %s: success=%s session=%s conflict=%s",
        current_user.get("username", "unknown"),
        result.get("success"),
        result.get("session_id"),
        result.get("conflict"),
    )
    return result
