"""
Improved Chat API with Specific Error Handling

This is a demonstration of improved error handling patterns
to be applied across the codebase.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from src.error_handler import log_error, safe_api_error, with_error_handling
from src.exceptions import (
    AutoBotError,
    InternalError,
    ResourceNotFoundError,
    ValidationError,
    get_error_code,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None


def generate_request_id() -> str:
    """Generate a unique request ID for tracking."""
    return str(uuid.uuid4())


@router.get("/chats")
async def list_chats(request: Request):
    """List all chat sessions with improved error handling."""
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


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, request: Request):
    """Get a specific chat session with improved error handling."""
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

        # Load session with proper error handling
        try:
            history = chat_history_manager.load_session(chat_id)

            if history is None:
                raise ResourceNotFoundError(
                    "Chat session not found", resource_type="chat", resource_id=chat_id
                )

            return JSONResponse(
                status_code=200, content={"chat_id": chat_id, "history": history}
            )

        except FileNotFoundError:
            # Handle specific case of missing file
            raise ResourceNotFoundError(
                "Chat session file not found", resource_type="chat", resource_id=chat_id
            )
        except PermissionError as e:
            # Handle permission issues
            logger.error(f"Permission denied accessing chat {chat_id}: {e}")
            raise InternalError("Unable to access chat session")
        except ValueError as e:
            # Handle corrupted data
            logger.error(f"Corrupted chat data for {chat_id}: {e}")
            raise InternalError("Chat session data is corrupted")

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
async def delete_chat(chat_id: str, request: Request):
    """Delete a specific chat session with improved error handling."""
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


@router.post("/chat")
async def process_chat(request: ChatRequest, http_request: Request):
    """Process a chat message with improved error handling."""
    request_id = generate_request_id()

    try:
        # Validate request
        if not request.message.strip():
            raise ValidationError("Message cannot be empty", field="message")

        if len(request.message) > 10000:  # Reasonable limit
            raise ValidationError(
                "Message too long (max 10000 characters)",
                field="message",
                value=len(request.message),
            )

        # Get required components with specific errors
        orchestrator = getattr(http_request.app.state, "orchestrator", None)
        if orchestrator is None:
            raise InternalError("Chat orchestrator not initialized")

        # Process message with timeout and specific error handling
        try:
            import asyncio

            # Add timeout to prevent hanging
            response = await asyncio.wait_for(
                orchestrator.process_message(
                    message=request.message, chat_id=request.chat_id
                ),
                timeout=30.0,  # 30 second timeout
            )

            return JSONResponse(status_code=200, content=response)

        except asyncio.TimeoutError:
            logger.error(f"Chat processing timeout for request {request_id}")
            raise InternalError("Request processing timed out")
        except ValueError as e:
            # Handle validation errors from orchestrator
            raise ValidationError(f"Invalid message format: {str(e)}")
        except ConnectionError as e:
            # Handle external service failures
            logger.error(f"External service connection failed: {e}")
            raise InternalError(
                "Unable to process message due to service unavailability"
            )

    except PydanticValidationError as e:
        # Handle Pydantic validation errors
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
async def health_check():
    """Simple health check endpoint with decorator-based error handling."""
    # This will automatically handle and log any errors
    return JSONResponse(
        status_code=200, content={"status": "healthy", "service": "chat"}
    )
