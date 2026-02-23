"""
Improved Chat API with Specific Error Handling

This is a demonstration of improved error handling patterns
to be applied across the codebase.
"""

import logging
from typing import Optional

from auth_middleware import get_current_user

# Issue #756: Consolidated from src/utils/request_utils.py
from backend.utils.request_utils import generate_request_id
from error_handler import log_error, safe_api_error, with_error_handling
from exceptions import (
    AutoBotError,
    InternalError,
    ResourceNotFoundError,
    ValidationError,
    get_error_code,
)
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None


@router.get("/chats")
async def list_chats(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    List all chat sessions with improved error handling.

    Issue #744: Requires authenticated user.
    """
    request_id = generate_request_id()

    try:
        # Get chat history manager with specific error
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        if chat_history_manager is None:
            raise InternalError(
                "Chat history manager not initialized",
                details={"component": "chat_history_manager"},
            )

        # Attempt to list sessions with proper error handling
        try:
            sessions = chat_history_manager.list_sessions()
            return JSONResponse(status_code=200, content={"chats": sessions})

        except AttributeError as e:
            # Handle case where list_sessions method doesn't exist
            raise InternalError(
                "Chat history manager is misconfigured",
                details={"missing_method": "list_sessions"},
            ) from e

        except Exception as e:
            # Log unexpected errors but don't expose details
            logger.critical(
                f"Unexpected error listing chat sessions: {type(e).__name__}",
                exc_info=True,
                extra={"request_id": request_id},
            )
            raise InternalError("Failed to retrieve chat sessions") from e

    except AutoBotError as e:
        # Handle our custom errors
        log_error(e, context="list_chats", include_traceback=False)
        return JSONResponse(
            status_code=get_error_code(e), content=safe_api_error(e, request_id)
        )
    except Exception as e:
        # Handle unexpected errors
        log_error(e, context="list_chats")
        return JSONResponse(
            status_code=500,
            content=safe_api_error(
                InternalError("An unexpected error occurred"), request_id
            ),
        )


def _load_chat_session(chat_history_manager, chat_id: str):
    """Helper for get_chat. Ref: #1088.

    Load a chat session from the history manager, mapping filesystem and
    data errors to AutoBot domain exceptions.
    """
    try:
        history = chat_history_manager.load_session(chat_id)
        if history is None:
            raise ResourceNotFoundError(
                "Chat session not found", resource_type="chat", resource_id=chat_id
            )
        return history
    except FileNotFoundError:
        raise ResourceNotFoundError(
            "Chat session file not found", resource_type="chat", resource_id=chat_id
        )
    except PermissionError as e:
        logger.error(f"Permission denied accessing chat {chat_id}: {e}")
        raise InternalError("Unable to access chat session")
    except ValueError as e:
        logger.error(f"Corrupted chat data for {chat_id}: {e}")
        raise InternalError("Chat session data is corrupted")


@router.get("/chats/{chat_id}")
async def get_chat(
    chat_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Get a specific chat session with improved error handling.

    Issue #744: Requires authenticated user.
    """
    request_id = generate_request_id()

    try:
        # Validate chat_id format
        if not chat_id or len(chat_id) > 100:
            raise ValidationError(
                "Invalid chat ID format",
                field="chat_id",
                value=chat_id[:50] if chat_id else None,  # Truncate for safety
            )

        # Get chat history manager
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        if chat_history_manager is None:
            raise InternalError("Chat history manager not initialized")

        history = _load_chat_session(chat_history_manager, chat_id)
        return JSONResponse(
            status_code=200, content={"chat_id": chat_id, "history": history}
        )

    except AutoBotError as e:
        log_error(e, context=f"get_chat:{chat_id}", include_traceback=False)
        return JSONResponse(
            status_code=get_error_code(e), content=safe_api_error(e, request_id)
        )
    except Exception as e:
        log_error(e, context=f"get_chat:{chat_id}")
        return JSONResponse(
            status_code=500,
            content=safe_api_error(
                InternalError("An unexpected error occurred"), request_id
            ),
        )


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Delete a specific chat session with improved error handling.

    Issue #744: Requires authenticated user.
    """
    request_id = generate_request_id()

    try:
        # Validate input
        if not chat_id:
            raise ValidationError("Chat ID is required", field="chat_id")

        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        if chat_history_manager is None:
            raise InternalError("Chat history manager not initialized")

        # Attempt deletion with specific error handling
        try:
            success = chat_history_manager.delete_session(chat_id)

            if not success:
                # Check if session exists before reporting not found
                if not chat_history_manager.load_session(chat_id):
                    raise ResourceNotFoundError(
                        "Chat session not found",
                        resource_type="chat",
                        resource_id=chat_id,
                    )
                else:
                    # Session exists but couldn't be deleted
                    raise InternalError("Failed to delete chat session")

            return JSONResponse(
                status_code=200,
                content={"success": True, "message": "Chat deleted successfully"},
            )

        except PermissionError:
            logger.error(f"Permission denied deleting chat {chat_id}")
            raise InternalError("Insufficient permissions to delete chat")
        except OSError as e:
            logger.error(f"OS error deleting chat {chat_id}: {e}")
            raise InternalError("System error while deleting chat")

    except AutoBotError as e:
        log_error(e, context=f"delete_chat:{chat_id}", include_traceback=False)
        return JSONResponse(
            status_code=get_error_code(e), content=safe_api_error(e, request_id)
        )
    except Exception as e:
        log_error(e, context=f"delete_chat:{chat_id}")
        return JSONResponse(
            status_code=500,
            content=safe_api_error(
                InternalError("An unexpected error occurred"), request_id
            ),
        )


def _validate_chat_message(message: str) -> None:
    """
    Validate chat message content.

    Issue #620: Extracted from process_chat.

    Args:
        message: Message to validate

    Raises:
        ValidationError: If message is invalid
    """
    if not message.strip():
        raise ValidationError("Message cannot be empty", field="message")

    if len(message) > 10000:  # Reasonable limit
        raise ValidationError(
            "Message too long (max 10000 characters)",
            field="message",
            value=len(message),
        )


async def _process_message_with_timeout(
    orchestrator, message: str, chat_id: Optional[str], request_id: str
) -> JSONResponse:
    """
    Process chat message with timeout handling.

    Issue #620: Extracted from process_chat.

    Args:
        orchestrator: Chat orchestrator instance
        message: User message
        chat_id: Optional chat session ID
        request_id: Request identifier for logging

    Returns:
        JSONResponse with chat response

    Raises:
        InternalError: On timeout or service unavailability
        ValidationError: On invalid message format
    """
    import asyncio

    try:
        response = await asyncio.wait_for(
            orchestrator.process_message(message=message, chat_id=chat_id),
            timeout=30.0,
        )
        return JSONResponse(status_code=200, content=response)

    except asyncio.TimeoutError:
        logger.error("Chat processing timeout for request %s", request_id)
        raise InternalError("Request processing timed out")
    except ValueError as e:
        raise ValidationError(f"Invalid message format: {str(e)}")
    except ConnectionError as e:
        logger.error("External service connection failed: %s", e)
        raise InternalError("Unable to process message due to service unavailability")


@router.post("/chat")
async def process_chat(
    request: ChatRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Process a chat message with improved error handling.

    Issue #744: Requires authenticated user.
    Issue #620: Refactored to use extracted helper methods.
    """
    request_id = generate_request_id()

    try:
        # Validate request (Issue #620: uses helper)
        _validate_chat_message(request.message)

        # Get required components with specific errors
        orchestrator = getattr(http_request.app.state, "orchestrator", None)
        if orchestrator is None:
            raise InternalError("Chat orchestrator not initialized")

        # Process message (Issue #620: uses helper)
        return await _process_message_with_timeout(
            orchestrator, request.message, request.chat_id, request_id
        )

    except PydanticValidationError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid request format",
                "details": e.errors(),
                "request_id": request_id,
            },
        )
    except AutoBotError as e:
        log_error(e, context="process_chat", include_traceback=False)
        return JSONResponse(
            status_code=get_error_code(e), content=safe_api_error(e, request_id)
        )
    except Exception as e:
        log_error(e, context="process_chat")
        return JSONResponse(
            status_code=500,
            content=safe_api_error(
                InternalError("An unexpected error occurred"), request_id
            ),
        )


# Example of using decorators for simpler endpoints
@router.get("/chat/health")
@with_error_handling(
    default_return=JSONResponse(
        status_code=503, content={"status": "unhealthy", "error": "Health check failed"}
    ),
    context="chat_health_check",
)
async def health_check(
    current_user: dict = Depends(get_current_user),
):
    """
    Simple health check endpoint with decorator-based error handling.

    Issue #744: Requires authenticated user.
    """
    # This will automatically handle and log any errors
    return JSONResponse(
        status_code=200, content={"status": "healthy", "service": "chat"}
    )
