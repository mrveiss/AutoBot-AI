import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

import aiofiles
import uvicorn
from fastapi import (
    APIRouter,
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.responses import Response as StarletteResponse

# Import dependencies and utilities - Using available dependencies
from backend.dependencies import get_config, get_knowledge_base

# CRITICAL SECURITY FIX: Import session ownership validation
from backend.security.session_ownership import validate_session_ownership
from src.constants.network_constants import NetworkConstants
from src.utils.redis_database_manager import get_redis_client

# Import models - DISABLED: Models don't exist yet
# from src.models.conversation import ConversationModel
# from src.models.message import MessageModel




# Create placeholder dependency functions for missing imports
def get_current_user():
    """Placeholder for auth dependency"""
    return {"user_id": "default"}


# Wrapper dependency to validate chat ownership using chat_id
async def validate_chat_ownership(chat_id: str, request: Request) -> Dict:
    """
    Wrapper dependency that validates chat ownership by mapping chat_id to session_id.

    Args:
        chat_id: Chat ID from URL path parameter
        request: FastAPI request object

    Returns:
        Dict with authorization status and user data
    """
    # chat_id IS the session_id - just pass it through with the correct name
    return await validate_session_ownership(session_id=chat_id, request=request)


def get_chat_history_manager(request):
    """Get chat history manager from app state, with lazy initialization"""
    manager = getattr(request.app.state, "chat_history_manager", None)
    if manager is None:
        # Lazy initialize if not yet available
        try:
            from src.chat_history_manager import ChatHistoryManager

            manager = ChatHistoryManager()
            request.app.state.chat_history_manager = manager
            logger.info("✅ Lazy-initialized chat_history_manager")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize chat_history_manager: {e}")
    return manager


def get_system_state(request):
    """Get system state from app state"""
    return getattr(request.app.state, "system_state", {})


def get_memory_interface(request):
    """Get memory interface from app state"""
    return getattr(request.app.state, "memory_interface", None)


def get_llm_service(request):
    """Get LLM service from app state, with lazy initialization"""
    llm_service = getattr(request.app.state, "llm_service", None)
    if llm_service is None:
        # Lazy initialize if not yet available
        try:
            from src.llm_service import LLMService

            llm_service = LLMService()
            request.app.state.llm_service = llm_service
            logger.info("✅ Lazy-initialized llm_service")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize llm_service: {e}")
    return llm_service


# Simple utility functions to replace missing imports
def generate_request_id():
    """Generate a unique request ID"""
    return str(uuid4())


def handle_api_error(error, request_id="unknown"):
    """Simple error handler replacement"""
    logger.error(f"[{request_id}] API error: {str(error)}")
    return {"error": str(error)}


def log_exception(error, context="chat"):
    """Simple exception logger replacement"""
    logger.error(f"[{context}] Exception: {str(error)}")


def create_success_response(data, message="Success", request_id=None, status_code=200):
    """Create success response"""
    response = {"success": True, "data": data, "message": message}
    if request_id:
        response["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=response)


def validate_message_content(content):
    """Validate message content"""
    return content and len(content.strip()) > 0


def get_exceptions_lazy():
    """Lazy load exception classes to avoid import errors"""

    class AutoBotError(Exception):
        pass

    class InternalError(AutoBotError):
        def __init__(self, message, details=None):
            self.message = message
            self.details = details or {}
            super().__init__(message)

    class ResourceNotFoundError(AutoBotError):
        pass

    class ValidationError(AutoBotError):
        pass

    def get_error_code(error_type):
        error_codes = {
            "INTERNAL_ERROR": "INTERNAL_ERROR",
            "VALIDATION_ERROR": "VALIDATION_ERROR",
            "NOT_FOUND": "NOT_FOUND",
        }
        return error_codes.get(error_type, "UNKNOWN_ERROR")

    return (
        AutoBotError,
        InternalError,
        ResourceNotFoundError,
        ValidationError,
        get_error_code,
    )


def log_request_context(request, endpoint, request_id):
    """Log request context for debugging"""
    logger.info(f"[{request_id}] {endpoint} - {request.method} {request.url.path}")


def create_error_response(
    error_code="INTERNAL_ERROR",
    message="An error occurred",
    request_id="unknown",
    status_code=500,
):
    """Create standardized error response"""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {"code": error_code, "message": message, "request_id": request_id},
        },
    )


# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

# ====================================================================
# Request/Response Models
# ====================================================================


class ChatMessage(BaseModel):
    """Chat message model for requests"""

    content: str = Field(
        ..., min_length=1, max_length=50000, description="Message content"
    )
    role: str = Field(
        default="user", pattern="^(user|assistant|system)$", description="Message role"
    )
    session_id: Optional[str] = Field(None, description="Chat session ID")
    message_type: Optional[str] = Field("text", description="Message type")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )


class ChatResponse(BaseModel):
    """Chat response model"""

    content: str
    role: str = "assistant"
    session_id: str
    message_id: str
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionCreate(BaseModel):
    """Session creation model"""

    title: Optional[str] = Field(None, max_length=200, description="Session title")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Session metadata"
    )


class SessionUpdate(BaseModel):
    """Session update model"""

    title: Optional[str] = Field(None, max_length=200, description="New session title")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")


class MessageHistory(BaseModel):
    """Message history response model"""

    messages: List[Dict[str, Any]]
    session_id: str
    total_count: int
    page: int = 1
    per_page: int = 50


# ====================================================================
# Configuration and State Management
# ====================================================================

# Chat configuration constants
MAX_MESSAGE_LENGTH = 50000
MAX_HISTORY_SIZE = 1000
DEFAULT_SESSION_TITLE = "New Chat Session"
STREAMING_CHUNK_SIZE = 1024

# ====================================================================
# Utility Functions
# ====================================================================


def validate_chat_session_id(session_id: str) -> bool:
    """Validate chat session ID format"""
    if not session_id:
        return False

    # Allow UUIDs with optional suffixes (e.g., "uuid-imported-timestamp")
    # Check if it starts with a valid UUID pattern
    try:
        # Try to parse as pure UUID first
        uuid.UUID(session_id)
        return True
    except ValueError:
        # If that fails, check if it starts with a UUID followed by additional text
        parts = session_id.split("-")
        if len(parts) >= 5:  # UUID has 5 parts separated by hyphens
            # Try to reconstruct and validate first 5 parts as UUID
            try:
                uuid_part = "-".join(parts[:5])
                uuid.UUID(uuid_part)
                return True  # Valid UUID prefix with additional suffix
            except ValueError:
                pass
        return False


def generate_chat_session_id() -> str:
    """Generate a new chat session ID"""
    return str(uuid4())


def generate_message_id() -> str:
    """Generate a new message ID"""
    return str(uuid4())


async def log_chat_event(
    event_type: str, session_id: str = None, details: Dict[str, Any] = None
):
    """Log chat-related events for monitoring and debugging"""
    try:
        event_data = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "details": details or {},
        }
        logger.info(f"Chat Event: {event_type}", extra=event_data)
    except Exception as e:
        logger.error(f"Failed to log chat event: {e}")


# ====================================================================
# Core Chat Functions
# ====================================================================


async def process_chat_message(
    message: ChatMessage,
    chat_history_manager,
    llm_service,
    memory_interface,
    knowledge_base,
    config: Dict[str, Any],
    request_id: str,
) -> Dict[str, Any]:
    """Process a chat message and generate response"""
    try:
        # Validate session ID
        if message.session_id and not validate_chat_session_id(message.session_id):
            (
                AutoBotError,
                InternalError,
                ResourceNotFoundError,
                ValidationError,
                get_error_code,
            ) = get_exceptions_lazy()
            raise ValidationError("Invalid session ID format")

        # Get or create session
        session_id = message.session_id or generate_chat_session_id()

        # Store user message
        user_message_id = generate_message_id()
        user_message_data = {
            "id": user_message_id,
            "content": message.content,
            "role": message.role,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": message.metadata,
            "session_id": session_id,
        }

        # Add to session history
        if hasattr(chat_history_manager, "add_message"):
            await chat_history_manager.add_message(session_id, user_message_data)

        # Log chat event
        await log_chat_event(
            "message_received",
            session_id,
            {
                "message_id": user_message_id,
                "content_length": len(message.content),
                "role": message.role,
            },
        )

        # Get chat context from history (Redis-backed, efficient retrieval)
        chat_context = []
        if hasattr(chat_history_manager, "get_session_messages"):
            try:
                # Use model-aware message retrieval for optimal context window usage
                # Context manager calculates efficient limits based on model capabilities
                model_name = message.metadata.get("model") if message.metadata else None
                recent_messages = await chat_history_manager.get_session_messages(
                    session_id, model_name=model_name
                )
                chat_context = recent_messages or []
                logger.info(
                    f"Retrieved {len(chat_context)} messages for model {model_name or 'default'}"
                )
            except Exception as e:
                logger.warning(f"Could not retrieve chat context: {e}")

        # Generate AI response
        try:
            # Prepare context for LLM
            # Use model-aware message limit for optimal context window usage
            model_name = message.metadata.get("model") if message.metadata else None
            context_manager = getattr(chat_history_manager, "context_manager", None)

            if context_manager:
                message_limit = context_manager.get_message_limit(model_name)
                logger.info(
                    f"Using {message_limit} messages for LLM context (model: {model_name or 'default'})"
                )
            else:
                message_limit = 20  # Fallback default
                logger.warning("Context manager not available, using default limit")

            llm_context = []
            for msg in chat_context[-message_limit:]:  # Model-aware message limit
                llm_context.append(
                    {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                )

            # Add current message to context
            llm_context.append({"role": message.role, "content": message.content})

            # Generate response using LLM service
            if hasattr(llm_service, "generate_response"):
                ai_response = await llm_service.generate_response(
                    messages=llm_context, session_id=session_id, request_id=request_id
                )
            else:
                # Fallback response
                ai_response = {
                    "content": "I'm currently unable to generate a response. Please try again.",
                    "role": "assistant",
                }

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            ai_response = {
                "content": "I encountered an error processing your message. Please try again.",
                "role": "assistant",
            }

        # Store AI response
        ai_message_id = generate_message_id()
        ai_message_data = {
            "id": ai_message_id,
            "content": ai_response.get("content", ""),
            "role": "assistant",
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": ai_response.get("metadata", {}),
            "session_id": session_id,
        }

        # Add AI response to session history
        if hasattr(chat_history_manager, "add_message"):
            await chat_history_manager.add_message(session_id, ai_message_data)

        # Log response event
        await log_chat_event(
            "response_generated",
            session_id,
            {
                "message_id": ai_message_id,
                "content_length": len(ai_response.get("content", "")),
                "request_id": request_id,
            },
        )

        return {
            "content": ai_response.get("content", ""),
            "role": "assistant",
            "session_id": session_id,
            "message_id": ai_message_id,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": ai_response.get("metadata", {}),
        }

    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise InternalError(
            "Failed to process chat message",
            details={"error": str(e), "request_id": request_id},
        )


# ====================================================================
# Streaming Response Functions
# ====================================================================


async def stream_chat_response(
    message: ChatMessage, chat_history_manager, llm_service, request_id: str
) -> StreamingResponse:
    """Stream chat response for real-time communication"""

    async def generate_stream():
        try:
            # Initial setup
            session_id = message.session_id or generate_chat_session_id()

            # Send initial message acknowledgment
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"

            # Process message and stream response
            if hasattr(llm_service, "stream_response"):
                async for chunk in llm_service.stream_response(
                    message.content, session_id
                ):
                    chunk_data = {
                        "type": "chunk",
                        "content": chunk.get("content", ""),
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
            else:
                # Fallback to non-streaming
                response_data = await process_chat_message(
                    message,
                    chat_history_manager,
                    llm_service,
                    None,
                    None,
                    {},
                    request_id,
                )
                yield f"data: {json.dumps({'type': 'complete', **response_data})}\n\n"

            # Send completion signal
            yield f"data: {json.dumps({'type': 'end'})}\n\n"

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            error_data = {
                "type": "error",
                "message": "Error generating response",
                "timestamp": datetime.utcnow().isoformat(),
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


# ====================================================================
# API Endpoints
# ====================================================================


@router.get("/chats")
@router.get("/chat/chats")  # Frontend compatibility alias
async def list_chats(request: Request):
    """List all available chat sessions with improved error handling (consolidated)"""
    request_id = generate_request_id()

    try:
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
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

        try:
            # CRITICAL FIX: Remove await - list_sessions_fast is synchronous
            sessions = chat_history_manager.list_sessions_fast()
            return JSONResponse(status_code=200, content=sessions)
        except AttributeError as e:
            (
                AutoBotError,
                InternalError,
                ResourceNotFoundError,
                ValidationError,
                get_error_code,
            ) = get_exceptions_lazy()
            raise InternalError(
                "Chat history manager is misconfigured",
                details={"missing_method": "list_sessions"},
            )
        except Exception as e:
            logger.error(f"Failed to retrieve chat sessions: {e}")
            (
                AutoBotError,
                InternalError,
                ResourceNotFoundError,
                ValidationError,
                get_error_code,
            ) = get_exceptions_lazy()
            raise InternalError(
                "Failed to retrieve chat sessions",
                details={"error": str(e)},
            )

    except Exception as e:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        logger.critical(
            f"Unexpected error listing chat sessions: {e.__class__.__name__}"
        )
        logger.exception(e)

        return create_error_response(
            error_code=get_error_code("INTERNAL_ERROR"),
            message="Failed to retrieve chat sessions",
            request_id=request_id,
            status_code=500,
        )


@router.post("/chat")
@router.post("/chat/message")  # Alternative endpoint
async def send_message(
    message: ChatMessage,
    request: Request,
    config=Depends(get_config),
    knowledge_base=Depends(get_knowledge_base),
):
    """Send a chat message and get AI response"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "send_message", request_id)

        # Validate message content
        if not message.content or not message.content.strip():
            (
                AutoBotError,
                InternalError,
                ResourceNotFoundError,
                ValidationError,
                get_error_code,
            ) = get_exceptions_lazy()
            raise ValidationError("Message content cannot be empty")

        # Get dependencies from request state
        chat_history_manager = get_chat_history_manager(request)
        llm_service = get_llm_service(request)
        memory_interface = get_memory_interface(request)

        # Process the chat message
        response_data = await process_chat_message(
            message,
            chat_history_manager,
            llm_service,
            memory_interface,
            knowledge_base,
            config,
            request_id,
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": response_data,
                "message": "Message processed successfully",
                "request_id": request_id,
            },
        )

    except Exception as e:
        logger.error(f"[{request_id}] send_message error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


@router.post("/chat/stream")
async def stream_message(message: ChatMessage, request: Request):
    """Stream chat response for real-time communication"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "stream_message", request_id)

        # Validate message content
        if not message.content or not message.content.strip():
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Message content cannot be empty",
                    "request_id": request_id,
                },
            )

        # Get dependencies from request state
        chat_history_manager = get_chat_history_manager(request)
        llm_service = get_llm_service(request)

        # Return streaming response
        return await stream_chat_response(
            message, chat_history_manager, llm_service, request_id
        )

    except Exception as e:
        logger.error(f"[{request_id}] stream_message error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
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

    try:
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
        messages = await chat_history_manager.get_session_messages(
            session_id, page=page, per_page=per_page
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

    except Exception as e:
        logger.error(f"[{request_id}] get_session_messages error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


@router.get("/chat/sessions")
async def list_sessions(request: Request):
    """List all available chat sessions (REST-compliant endpoint)"""
    request_id = generate_request_id()

    try:
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

        return JSONResponse(
            status_code=200,
            content={"success": True, "sessions": sessions, "count": len(sessions)},
        )

    except Exception as e:
        logger.error(f"[{request_id}] list_sessions error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


@router.post("/chat/sessions")
async def create_session(session_data: SessionCreate, request: Request):
    """Create a new chat session"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "create_session", request_id)

        # Get dependencies from request state
        chat_history_manager = get_chat_history_manager(request)

        # Generate new session
        session_id = generate_chat_session_id()
        session_title = session_data.title or DEFAULT_SESSION_TITLE

        # Create session
        session = await chat_history_manager.create_session(
            session_id=session_id,
            title=session_title,
            metadata=session_data.metadata or {},
        )

        await log_chat_event(
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

    except Exception as e:
        logger.error(f"[{request_id}] create_session error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
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

    try:
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

        await log_chat_event(
            "session_updated",
            session_id,
            {"title": session_data.title, "request_id": request_id},
        )

        return create_success_response(
            data=updated_session,
            message="Session updated successfully",
            request_id=request_id,
        )

    except Exception as e:
        logger.error(f"[{request_id}] update_session error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
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
    Delete a chat session with optional file handling

    Args:
        session_id: Chat session ID to delete
        file_action: How to handle conversation files ("delete", "transfer_kb", "transfer_shared")
        file_options: JSON string with transfer options (e.g., '{"target_path": "archive/", "tags": ["archived"]}')

    Returns:
        Success response with deletion details
    """
    request_id = generate_request_id()

    try:
        log_request_context(request, "delete_session", request_id)

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

        # Validate file_action
        valid_file_actions = ["delete", "transfer_kb", "transfer_shared"]
        if file_action not in valid_file_actions:
            (
                AutoBotError,
                InternalError,
                ResourceNotFoundError,
                ValidationError,
                get_error_code,
            ) = get_exceptions_lazy()
            raise ValidationError(
                f"Invalid file_action. Must be one of: {valid_file_actions}"
            )

        # Parse file_options if provided
        parsed_file_options = {}
        if file_options:
            try:
                import json

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

        # Get dependencies from request state
        chat_history_manager = get_chat_history_manager(request)

        # Handle conversation files if file manager is available
        file_deletion_result = {"files_handled": False, "action_taken": file_action}
        conversation_file_manager = getattr(
            request.app.state, "conversation_file_manager", None
        )

        if conversation_file_manager:
            try:
                if file_action == "delete":
                    # Delete all files in conversation
                    deleted_count = (
                        await conversation_file_manager.delete_session_files(session_id)
                    )
                    file_deletion_result = {
                        "files_handled": True,
                        "action_taken": "delete",
                        "files_deleted": deleted_count,
                    }
                    logger.info(
                        f"Deleted {deleted_count} files for session {session_id}"
                    )

                elif file_action == "transfer_kb":
                    # Transfer files to knowledge base
                    transfer_result = (
                        await conversation_file_manager.transfer_session_files(
                            session_id=session_id,
                            destination="kb",
                            target_path=parsed_file_options.get("target_path"),
                            tags=parsed_file_options.get(
                                "tags", ["conversation_archive"]
                            ),
                            copy=False,  # Move, not copy
                        )
                    )
                    file_deletion_result = {
                        "files_handled": True,
                        "action_taken": "transfer_kb",
                        "files_transferred": transfer_result.get(
                            "total_transferred", 0
                        ),
                        "files_failed": transfer_result.get("total_failed", 0),
                    }
                    logger.info(
                        f"Transferred {transfer_result.get('total_transferred', 0)} files to KB for session {session_id}"
                    )

                elif file_action == "transfer_shared":
                    # Transfer files to shared storage
                    transfer_result = (
                        await conversation_file_manager.transfer_session_files(
                            session_id=session_id,
                            destination="shared",
                            target_path=parsed_file_options.get("target_path"),
                            copy=False,  # Move, not copy
                        )
                    )
                    file_deletion_result = {
                        "files_handled": True,
                        "action_taken": "transfer_shared",
                        "files_transferred": transfer_result.get(
                            "total_transferred", 0
                        ),
                        "files_failed": transfer_result.get("total_failed", 0),
                    }
                    logger.info(
                        f"Transferred {transfer_result.get('total_transferred', 0)} files to shared storage for session {session_id}"
                    )

            except Exception as file_error:
                logger.error(
                    f"Error handling files for session {session_id}: {file_error}"
                )
                file_deletion_result = {
                    "files_handled": False,
                    "action_taken": file_action,
                    "error": str(file_error),
                }
        else:
            logger.warning(
                f"ConversationFileManager not available, skipping file handling for session {session_id}"
            )

        # Delete session from chat history (synchronous method)
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

        await log_chat_event(
            "session_deleted",
            session_id,
            {
                "request_id": request_id,
                "file_action": file_action,
                "file_deletion_result": file_deletion_result,
            },
        )

        return create_success_response(
            data={
                "session_id": session_id,
                "deleted": True,
                "file_handling": file_deletion_result,
            },
            message="Session deleted successfully",
            request_id=request_id,
        )

    except Exception as e:
        logger.error(f"[{request_id}] delete_session error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


@router.get("/chat/sessions/{session_id}/export")
async def export_session(session_id: str, request: Request, format: str = "json"):
    """Export a chat session in various formats"""
    request_id = generate_request_id()

    try:
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
        if format not in ["json", "txt", "csv"]:
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

        await log_chat_event(
            "session_exported", session_id, {"format": format, "request_id": request_id}
        )

        return Response(
            content=session_data,
            media_type=content_types[format],
            headers={
                "Content-Disposition": f"attachment; filename=chat_session_{session_id}.{format}"
            },
        )

    except Exception as e:
        logger.error(f"[{request_id}] export_session error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


# ====================================================================
# Health Check and Status Endpoints
# ====================================================================


@router.get("/chat/health")
async def chat_health_check(request: Request):
    """Health check for chat service"""
    try:
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        llm_service = getattr(request.app.state, "llm_service", None)

        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "chat_history_manager": (
                    "healthy" if chat_history_manager else "unavailable"
                ),
                "llm_service": "healthy" if llm_service else "unavailable",
            },
        }

        overall_healthy = all(
            status == "healthy" for status in health_status["components"].values()
        )

        if not overall_healthy:
            health_status["status"] = "degraded"

        return JSONResponse(
            status_code=200 if overall_healthy else 503, content=health_status
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.get("/chat/stats")
async def chat_statistics(request: Request):
    """Get chat service statistics"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "chat_statistics", request_id)

        # Get dependencies from request state
        chat_history_manager = get_chat_history_manager(request)

        # Get basic statistics
        stats = await chat_history_manager.get_statistics()

        return create_success_response(
            data=stats,
            message="Statistics retrieved successfully",
            request_id=request_id,
        )

    except Exception as e:
        logger.error(f"[{request_id}] chat_statistics error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


# MISSING ENDPOINTS FOR FRONTEND COMPATIBILITY


@router.post("/chats/{chat_id}/message")
async def send_chat_message_by_id(
    chat_id: str,
    request_data: dict,
    request: Request,
    ownership: Dict = Depends(validate_chat_ownership),  # SECURITY: Validate ownership
):
    """Send message to specific chat by ID (frontend compatibility endpoint)"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "send_chat_message_by_id", request_id)

        # Extract message from request data
        message = request_data.get("message", "")
        if not message:
            return create_error_response(
                error_code="MISSING_MESSAGE",
                message="Message content is required",
                request_id=request_id,
                status_code=400,
            )

        # Get dependencies from request state with lazy initialization
        chat_history_manager = get_chat_history_manager(request)

        # Lazy initialize chat_workflow_manager if needed
        chat_workflow_manager = getattr(
            request.app.state, "chat_workflow_manager", None
        )
        if chat_workflow_manager is None:
            try:
                from src.chat_workflow_manager import ChatWorkflowManager

                chat_workflow_manager = ChatWorkflowManager()
                await chat_workflow_manager.initialize()
                request.app.state.chat_workflow_manager = chat_workflow_manager
                logger.info(
                    "✅ Lazy-initialized chat_workflow_manager with async Redis"
                )
            except Exception as e:
                logger.error(f"Failed to lazy-initialize chat_workflow_manager: {e}")

        if not chat_history_manager or not chat_workflow_manager:
            return create_error_response(
                error_code="SERVICE_UNAVAILABLE",
                message="Chat services not available",
                request_id=request_id,
                status_code=503,
            )

        # Process the message using ChatWorkflowManager and stream response
        async def generate_stream():
            try:
                print(
                    f"[STREAM {request_id}] Starting stream generation for chat_id={chat_id}",
                    flush=True,
                )
                logger.debug(
                    f"[{request_id}] Starting stream generation for chat_id={chat_id}"
                )

                # Send initial acknowledgment
                yield f"data: {json.dumps({'type': 'start', 'session_id': chat_id, 'request_id': request_id})}\n\n"
                print(f"[STREAM {request_id}] Sent start event", flush=True)
                logger.debug(f"[{request_id}] Sent start event")

                # Process message and stream workflow messages as they arrive
                print(
                    f"[STREAM {request_id}] Calling chat_workflow_manager.process_message_stream() with message: {message[:50]}...",
                    flush=True,
                )
                logger.debug(
                    f"[{request_id}] Calling chat_workflow_manager.process_message_stream()"
                )

                message_count = 0
                async for msg in chat_workflow_manager.process_message_stream(
                    session_id=chat_id,
                    message=message,
                    context=request_data.get("context", {}),
                ):
                    message_count += 1
                    print(
                        f"[STREAM {request_id}] Processing message {message_count}: type={type(msg)}",
                        flush=True,
                    )
                    logger.debug(
                        f"[{request_id}] Processing message {message_count}: type={type(msg)}"
                    )
                    msg_data = msg.to_dict() if hasattr(msg, "to_dict") else msg
                    print(
                        f"[STREAM {request_id}] Message data: {str(msg_data)[:200]}...",
                        flush=True,
                    )
                    logger.debug(f"[{request_id}] Message data: {msg_data}")
                    yield f"data: {json.dumps(msg_data)}\n\n"
                    print(
                        f"[STREAM {request_id}] Sent message {message_count}",
                        flush=True,
                    )
                    logger.debug(f"[{request_id}] Sent message {message_count}")

                print(
                    f"[STREAM {request_id}] Got {message_count} messages from workflow manager",
                    flush=True,
                )
                logger.debug(
                    f"[{request_id}] Got {message_count} messages from workflow manager"
                )

                # Send completion signal
                print(f"[STREAM {request_id}] Sending end event", flush=True)
                logger.debug(f"[{request_id}] Sending end event")
                yield f"data: {json.dumps({'type': 'end', 'request_id': request_id})}\n\n"
                print(f"[STREAM {request_id}] Stream generation completed", flush=True)
                logger.debug(f"[{request_id}] Stream generation completed")

            except Exception as e:
                print(f"[STREAM {request_id}] ERROR: {e}", flush=True)
                logger.error(f"[{request_id}] Streaming error: {e}", exc_info=True)
                error_data = {
                    "type": "error",
                    "content": f"Error processing message: {str(e)}",
                    "request_id": request_id,
                }
                yield f"data: {json.dumps(error_data)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        logger.error(f"[{request_id}] send_chat_message_by_id error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


@router.post("/chats/{chat_id}/save")
async def save_chat_by_id(
    chat_id: str,
    request_data: dict,
    request: Request,
    ownership: Dict = Depends(validate_chat_ownership),  # SECURITY: Validate ownership
):
    """Save chat session by ID (frontend compatibility endpoint)"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "save_chat_by_id", request_id)

        # Get dependencies from request state
        chat_history_manager = get_chat_history_manager(request)

        if not chat_history_manager:
            return create_error_response(
                error_code="SERVICE_UNAVAILABLE",
                message="Chat history service not available",
                request_id=request_id,
                status_code=503,
            )

        # Save the chat session
        save_data = request_data.get("data", {})
        result = await chat_history_manager.save_session(
            session_id=chat_id,
            messages=save_data.get("messages"),
            name=save_data.get("name", ""),
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": result,
                "message": "Chat saved successfully",
                "request_id": request_id,
            },
        )

    except Exception as e:
        logger.error(f"[{request_id}] save_chat_by_id error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


@router.delete("/chats/{chat_id}")
async def delete_chat_by_id(
    chat_id: str,
    request: Request,
    ownership: Dict = Depends(
        validate_session_ownership
    ),  # SECURITY: Validate ownership
):
    """Delete chat session by ID (frontend compatibility endpoint)"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "delete_chat_by_id", request_id)

        # Get dependencies from request state
        chat_history_manager = get_chat_history_manager(request)

        if not chat_history_manager:
            return create_error_response(
                error_code="SERVICE_UNAVAILABLE",
                message="Chat history service not available",
                request_id=request_id,
                status_code=503,
            )

        # Delete the chat session
        result = chat_history_manager.delete_session(session_id=chat_id)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {"session_id": chat_id, "deleted": result},
                "message": "Chat deleted successfully",
                "request_id": request_id,
            },
        )

    except Exception as e:
        logger.error(f"[{request_id}] delete_chat_by_id error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


@router.post("/chat/direct")
async def send_direct_chat_response(
    request: Request,
    message: str = Body(...),
    chat_id: str = Body(...),
    remember_choice: bool = Body(default=False),
):
    """
    Send direct user response to chat (for command approvals, etc.)
    This endpoint accepts 'yes' or 'no' responses to system prompts
    """
    request_id = generate_request_id()

    try:
        log_request_context(request, "send_direct_response", request_id)

        # Get ChatWorkflowManager from app state
        chat_workflow_manager = getattr(
            request.app.state, "chat_workflow_manager", None
        )

        if chat_workflow_manager is None:
            # Lazy initialize
            try:
                from src.chat_workflow_manager import ChatWorkflowManager

                chat_workflow_manager = ChatWorkflowManager()
                await chat_workflow_manager.initialize()
                request.app.state.chat_workflow_manager = chat_workflow_manager
                logger.info(
                    "✅ Lazy-initialized chat_workflow_manager for /chat/direct"
                )
            except Exception as e:
                logger.error(f"Failed to lazy-initialize chat_workflow_manager: {e}")
                return create_error_response(
                    error_code="SERVICE_UNAVAILABLE",
                    message="Workflow manager not available",
                    request_id=request_id,
                    status_code=503,
                )

        # Stream the response (command approval/denial response)
        async def generate_stream():
            try:
                # Send start event
                yield f"data: {json.dumps({'type': 'start', 'session_id': chat_id, 'request_id': request_id})}\n\n"

                # Process the approval/denial message through workflow
                async for msg in chat_workflow_manager.process_message_stream(
                    session_id=chat_id,
                    message=message,  # "yes" or "no"
                    context={"remember_choice": remember_choice},
                ):
                    msg_data = msg.to_dict() if hasattr(msg, "to_dict") else msg
                    yield f"data: {json.dumps(msg_data)}\n\n"

                # Send completion
                yield f"data: {json.dumps({'type': 'end', 'request_id': request_id})}\n\n"

            except Exception as e:
                logger.error(
                    f"[{request_id}] Direct response streaming error: {e}",
                    exc_info=True,
                )
                error_data = {
                    "type": "error",
                    "content": f"Error processing command approval: {str(e)}",
                    "request_id": request_id,
                }
                yield f"data: {json.dumps(error_data)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        logger.error(f"[{request_id}] send_direct_response error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )
