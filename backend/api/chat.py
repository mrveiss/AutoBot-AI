# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from backend.type_defs.common import Metadata, STREAMING_MESSAGE_TYPES
from fastapi import (
    APIRouter,
    Body,
    Depends,
    Request,
)
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Import dependencies and utilities - Using available dependencies
from backend.dependencies import get_config, get_knowledge_base

# CRITICAL SECURITY FIX: Import session ownership validation
from backend.security.session_ownership import validate_session_ownership

# Import reusable chat utilities - Phase 1 Utility Extraction
from backend.utils.chat_utils import (
    create_error_response,
    create_success_response,
    generate_chat_session_id,
    generate_message_id,
    generate_request_id,
    get_chat_history_manager,
    log_chat_event,
    validate_chat_session_id,
)
from src.utils.error_boundaries import ErrorCategory, with_error_handling

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
def handle_api_error(error, request_id="unknown"):
    """Simple error handler replacement"""
    logger.error(f"[{request_id}] API error: {str(error)}")
    return {"error": str(error)}


def log_exception(error, context="chat"):
    """Simple exception logger replacement"""
    logger.error(f"[{context}] Exception: {str(error)}")


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


# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

# Include session management router
from backend.api.chat_sessions import router as sessions_router
router.include_router(sessions_router)

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
    metadata: Optional[Metadata] = Field(
        default_factory=dict, description="Additional metadata"
    )


class ChatResponse(BaseModel):
    """Chat response model"""

    content: str
    role: str = "assistant"
    session_id: str
    message_id: str
    timestamp: datetime
    metadata: Metadata = Field(default_factory=dict)


class MessageHistory(BaseModel):
    """Message history response model"""

    messages: List[Metadata]
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
STREAMING_CHUNK_SIZE = 1024

# ====================================================================
# Core Chat Functions
# ====================================================================


async def process_chat_message(
    message: ChatMessage,
    chat_history_manager,
    llm_service,
    memory_interface,
    knowledge_base,
    config: Metadata,
    request_id: str,
) -> Metadata:
    """Process a chat message and generate response"""
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
    log_chat_event(
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
                "content": (
                    "I'm currently unable to generate a response. Please try again."
                ),
                "role": "assistant",
            }

    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        ai_response = {
            "content": (
                "I encountered an error processing your message. Please try again."
            ),
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
    log_chat_event(
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_chats",
    error_code_prefix="CHAT",
)
@router.get("/chats")
@router.get("/chat/chats")  # Frontend compatibility alias
async def list_chats(request: Request):
    """List all available chat sessions with improved error handling (consolidated)"""
    request_id = generate_request_id()

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

    # Get sessions directly - decorator handles all errors
    # CRITICAL FIX: Remove await - list_sessions_fast is synchronous
    sessions = chat_history_manager.list_sessions_fast()
    return create_success_response(
        data=sessions,
        message="Chat sessions retrieved successfully",
        request_id=request_id,
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_message",
    error_code_prefix="CHAT",
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stream_message",
    error_code_prefix="CHAT",
)
@router.post("/chat/stream")
async def stream_message(message: ChatMessage, request: Request):
    """Stream chat response for real-time communication"""
    request_id = generate_request_id()
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


# ====================================================================
# Health Check and Status Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVICE_UNAVAILABLE,
    operation="chat_health_check",
    error_code_prefix="CHAT",
)
@router.get("/chat/health")
async def chat_health_check(request: Request):
    """Health check for chat service"""
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="chat_statistics",
    error_code_prefix="CHAT",
)
@router.get("/chat/stats")
async def chat_statistics(request: Request):
    """Get chat service statistics"""
    request_id = generate_request_id()
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


# MISSING ENDPOINTS FOR FRONTEND COMPATIBILITY


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_chat_message_by_id",
    error_code_prefix="CHAT",
)
@router.post("/chats/{chat_id}/message")
async def send_chat_message_by_id(
    chat_id: str,
    request_data: dict,
    request: Request,
    ownership: Dict = Depends(validate_chat_ownership),  # SECURITY: Validate ownership
):
    """Send message to specific chat by ID (frontend compatibility endpoint)"""
    request_id = generate_request_id()
    log_request_context(request, "send_chat_message_by_id", request_id)

    # Extract message from request data
    message = request_data.get("message", "")
    if not message:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise ValidationError("Message content is required")

    # Get dependencies from request state with lazy initialization
    chat_history_manager = get_chat_history_manager(request)

    # Lazy initialize chat_workflow_manager if needed
    chat_workflow_manager = getattr(request.app.state, "chat_workflow_manager", None)
    if chat_workflow_manager is None:
        try:
            from src.chat_workflow_manager import ChatWorkflowManager

            chat_workflow_manager = ChatWorkflowManager()
            await chat_workflow_manager.initialize()
            request.app.state.chat_workflow_manager = chat_workflow_manager
            logger.info("✅ Lazy-initialized chat_workflow_manager with async Redis")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize chat_workflow_manager: {e}")

    if not chat_history_manager or not chat_workflow_manager:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise InternalError(
            "Chat services not available",
            details={
                "chat_history_manager": bool(chat_history_manager),
                "chat_workflow_manager": bool(chat_workflow_manager),
            },
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
            start_evt = {'type': 'start', 'session_id': chat_id, 'request_id': request_id}
            yield f"data: {json.dumps(start_evt)}\n\n"
            print(f"[STREAM {request_id}] Sent start event", flush=True)
            logger.debug(f"[{request_id}] Sent start event")

            # Process message and stream workflow messages as they arrive
            msg_preview = message[:50]
            print(
                f"[STREAM {request_id}] Calling chat_workflow_manager."
                f"process_message_stream() with message: {msg_preview}...",
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
                ),
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


async def merge_messages(existing: List[Dict], new: List[Dict]) -> List[Dict]:
    """
    Merge message lists with deduplication to prevent race conditions.

    This function prevents the race condition where frontend saves overwrite
    backend-added messages (terminal_command, terminal_output). It preserves
    backend-added messages that don't exist in the new message set.

    CRITICAL FIX: Uses message ID for deduplication when available to handle
    streaming scenarios where text content accumulates progressively.

    Args:
        existing: Existing messages from file/cache (may include backend-added messages)
        new: New messages from frontend save request

    Returns:
        Merged message list, sorted by timestamp, with duplicates removed
    """

    def msg_signature(msg: Dict) -> tuple:
        """
        Create a unique signature for message deduplication.

        CRITICAL FIX: Prioritizes message ID for deduplication to prevent
        streaming token accumulation from creating duplicate messages.
        Falls back to timestamp + sender + text prefix for legacy messages.
        """
        # Prefer message ID for stable identity during streaming
        msg_id = msg.get("id") or msg.get("messageId")
        if msg_id:
            return ("id", msg_id)

        # Fallback: Use timestamp + sender + messageType for streaming messages
        # This prevents each accumulated token state from being treated as unique
        message_type = msg.get("messageType", msg.get("type", "default"))
        if message_type in STREAMING_MESSAGE_TYPES:
            # For streaming responses, don't use text content in signature
            # as it changes with each accumulated token
            return (
                msg.get("timestamp", ""),
                msg.get("sender", ""),
                message_type,
            )

        # For other message types (terminal, system), use text prefix
        return (
            msg.get("timestamp", ""),
            msg.get("sender", ""),
            msg.get("text", "")[:100],  # First 100 chars to handle long outputs
        )

    def is_streaming_response(msg: Dict) -> bool:
        """Check if message is a streaming LLM response."""
        message_type = msg.get("messageType", msg.get("type", "default"))
        return message_type in STREAMING_MESSAGE_TYPES

    # Build set of new message signatures
    new_sigs = {msg_signature(msg) for msg in new}

    # For streaming responses, also track new messages by ID for update detection
    new_by_id = {}
    for msg in new:
        msg_id = msg.get("id") or msg.get("messageId")
        if msg_id:
            new_by_id[msg_id] = msg

    # Keep existing messages not in new set (e.g., terminal messages added by backend)
    # But skip streaming messages that have a newer version in the new set
    preserved = []
    for msg in existing:
        sig = msg_signature(msg)
        msg_id = msg.get("id") or msg.get("messageId")

        # If message has an ID and new set has same ID, skip (use new version)
        if msg_id and msg_id in new_by_id:
            continue

        # If signature matches, skip (deduplicate)
        if sig in new_sigs:
            continue

        # For streaming responses without IDs, check for timestamp overlap
        # to prevent duplicate accumulated states
        if is_streaming_response(msg):
            msg_ts = msg.get("timestamp", "")
            msg_sender = msg.get("sender", "")
            # Check if any new message has same timestamp and sender
            has_newer = any(
                n.get("timestamp", "") == msg_ts
                and n.get("sender", "") == msg_sender
                and is_streaming_response(n)
                and len(n.get("text", "")) >= len(msg.get("text", ""))
                for n in new
            )
            if has_newer:
                continue

        preserved.append(msg)

    # Combine: preserved messages + new messages
    merged = preserved + new

    # Sort by timestamp to maintain chronological order
    merged.sort(key=lambda m: m.get("timestamp", ""))

    logger.debug(
        f"Merged messages: {len(existing)} existing + {len(new)} new = "
        f"{len(merged)} total ({len(preserved)} preserved from existing)"
    )

    return merged


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_chat_by_id",
    error_code_prefix="CHAT",
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

    # CRITICAL FIX: Merge messages to prevent race condition
    # Load existing messages from file/cache to preserve backend-added messages
    save_data = request_data.get("data", {})
    new_messages = save_data.get("messages", [])

    try:
        # Load existing messages to check for backend-added terminal messages
        existing_messages = await chat_history_manager.load_session(chat_id)

        # Merge with deduplication to preserve backend-added messages
        merged_messages = await merge_messages(existing_messages, new_messages)

        logger.info(
            f"[{request_id}] Merged {len(existing_messages)} existing + "
            f"{len(new_messages)} new = {len(merged_messages)} total messages"
        )
    except Exception as merge_error:
        # Fallback to new messages only if merge fails
        logger.warning(
            f"[{request_id}] Message merge failed, using new messages only: {merge_error}"
        ),
        merged_messages = new_messages

    # Save the merged chat session
    result = await chat_history_manager.save_session(
        session_id=chat_id,
        messages=merged_messages,
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_chat_by_id",
    error_code_prefix="CHAT",
)
@router.delete("/chats/{chat_id}")
async def delete_chat_by_id(
    chat_id: str,
    request: Request,
    ownership: Dict = Depends(validate_chat_ownership),  # SECURITY: Validate ownership
):
    """Delete chat session by ID (frontend compatibility endpoint)"""
    request_id = generate_request_id()
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_direct_chat_response",
    error_code_prefix="CHAT",
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
    log_request_context(request, "send_direct_response", request_id)

    # Get ChatWorkflowManager from app state
    chat_workflow_manager = getattr(request.app.state, "chat_workflow_manager", None)

    if chat_workflow_manager is None:
        # Lazy initialize
        try:
            from src.chat_workflow_manager import ChatWorkflowManager

            chat_workflow_manager = ChatWorkflowManager()
            await chat_workflow_manager.initialize()
            request.app.state.chat_workflow_manager = chat_workflow_manager
            logger.info("✅ Lazy-initialized chat_workflow_manager for /chat/direct")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize chat_workflow_manager: {e}")
            (
                AutoBotError,
                InternalError,
                ResourceNotFoundError,
                ValidationError,
                get_error_code,
            ) = get_exceptions_lazy()
            raise InternalError(
                "Workflow manager not available",
                details={"initialization_error": str(e)},
            )

    # Stream the response (command approval/denial response)
    async def generate_stream():
        try:
            # Send start event
            start_evt = {
                'type': 'start',
                'session_id': chat_id,
                'request_id': request_id
            }
            yield f"data: {json.dumps(start_evt)}\n\n"

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
            ),
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
