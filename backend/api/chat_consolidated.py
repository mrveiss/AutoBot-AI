import os
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

import aiofiles
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.responses import Response as StarletteResponse

from src.utils.redis_utils import get_redis_client

# Import models
from src.models.conversation import ConversationModel
from src.models.message import MessageModel

# Import dependencies and utilities
from backend.dependencies.auth import get_current_user
from backend.dependencies.chat import get_chat_history_manager
from backend.dependencies.config import get_config
from backend.dependencies.llm import get_llm_service
from backend.dependencies.system import get_system_state

# Memory and knowledge base integration
from backend.dependencies.memory import get_memory_interface
from backend.dependencies.knowledge import get_knowledge_base

from backend.utils.error_handling import (
    get_exceptions_lazy,
    handle_api_error,
    log_error_context,
    ErrorCode,
    get_error_code,
)
from backend.utils.request_helpers import generate_request_id, log_request_context
from backend.utils.response_helpers import create_success_response, create_error_response
from backend.utils.validation import validate_session_id, validate_message_content

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)

# ====================================================================
# Request/Response Models
# ====================================================================

class ChatMessage(BaseModel):
    """Chat message model for requests"""
    content: str = Field(..., min_length=1, max_length=50000, description="Message content")
    role: str = Field(default="user", pattern="^(user|assistant|system)$", description="Message role")
    session_id: Optional[str] = Field(None, description="Chat session ID")
    message_type: Optional[str] = Field("text", description="Message type")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

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
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Session metadata")

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
    try:
        uuid.UUID(session_id)
        return True
    except ValueError:
        return False

def generate_chat_session_id() -> str:
    """Generate a new chat session ID"""
    return str(uuid4())

def generate_message_id() -> str:
    """Generate a new message ID"""
    return str(uuid4())

async def log_chat_event(event_type: str, session_id: str = None, details: Dict[str, Any] = None):
    """Log chat-related events for monitoring and debugging"""
    try:
        event_data = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "details": details or {}
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
    request_id: str
) -> Dict[str, Any]:
    """Process a chat message and generate response"""
    try:
        # Validate session ID
        if message.session_id and not validate_chat_session_id(message.session_id):
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
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
            "session_id": session_id
        }

        # Add to session history
        if hasattr(chat_history_manager, 'add_message'):
            await chat_history_manager.add_message(session_id, user_message_data)

        # Log chat event
        await log_chat_event("message_received", session_id, {
            "message_id": user_message_id,
            "content_length": len(message.content),
            "role": message.role
        })

        # Get chat context from history
        chat_context = []
        if hasattr(chat_history_manager, 'get_session_messages'):
            try:
                recent_messages = await chat_history_manager.get_session_messages(session_id, limit=20)
                chat_context = recent_messages or []
            except Exception as e:
                logger.warning(f"Could not retrieve chat context: {e}")

        # Generate AI response
        try:
            # Prepare context for LLM
            llm_context = []
            for msg in chat_context[-10:]:  # Last 10 messages for context
                llm_context.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

            # Add current message to context
            llm_context.append({
                "role": message.role,
                "content": message.content
            })

            # Generate response using LLM service
            if hasattr(llm_service, 'generate_response'):
                ai_response = await llm_service.generate_response(
                    messages=llm_context,
                    session_id=session_id,
                    request_id=request_id
                )
            else:
                # Fallback response
                ai_response = {
                    "content": "I'm currently unable to generate a response. Please try again.",
                    "role": "assistant"
                }

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            ai_response = {
                "content": "I encountered an error processing your message. Please try again.",
                "role": "assistant"
            }

        # Store AI response
        ai_message_id = generate_message_id()
        ai_message_data = {
            "id": ai_message_id,
            "content": ai_response.get("content", ""),
            "role": "assistant",
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": ai_response.get("metadata", {}),
            "session_id": session_id
        }

        # Add AI response to session history
        if hasattr(chat_history_manager, 'add_message'):
            await chat_history_manager.add_message(session_id, ai_message_data)

        # Log response event
        await log_chat_event("response_generated", session_id, {
            "message_id": ai_message_id,
            "content_length": len(ai_response.get("content", "")),
            "request_id": request_id
        })

        return {
            "content": ai_response.get("content", ""),
            "role": "assistant",
            "session_id": session_id,
            "message_id": ai_message_id,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": ai_response.get("metadata", {})
        }

    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
        raise InternalError(
            "Failed to process chat message",
            details={"error": str(e), "request_id": request_id}
        )

# ====================================================================
# Streaming Response Functions
# ====================================================================

async def stream_chat_response(
    message: ChatMessage,
    chat_history_manager,
    llm_service,
    request_id: str
) -> StreamingResponse:
    """Stream chat response for real-time communication"""

    async def generate_stream():
        try:
            # Initial setup
            session_id = message.session_id or generate_chat_session_id()

            # Send initial message acknowledgment
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"

            # Process message and stream response
            if hasattr(llm_service, 'stream_response'):
                async for chunk in llm_service.stream_response(message.content, session_id):
                    chunk_data = {
                        "type": "chunk",
                        "content": chunk.get("content", ""),
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
            else:
                # Fallback to non-streaming
                response_data = await process_chat_message(
                    message, chat_history_manager, llm_service, None, None, {}, request_id
                )
                yield f"data: {json.dumps({'type': 'complete', **response_data})}\n\n"

            # Send completion signal
            yield f"data: {json.dumps({'type': 'end'})}\n\n"

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            error_data = {
                "type": "error",
                "message": "Error generating response",
                "timestamp": datetime.utcnow().isoformat()
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
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
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise InternalError(
                "Chat history manager not initialized",
                details={"component": "chat_history_manager"},
            )

        try:
            # CRITICAL FIX: Add await for async method
            sessions = await chat_history_manager.list_sessions_fast()
            return JSONResponse(status_code=200, content=sessions)
        except AttributeError as e:
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise InternalError(
                "Chat history manager is misconfigured",
                details={"missing_method": "list_sessions"},
            )
        except Exception as e:
            logger.error(f"Failed to retrieve chat sessions: {e}")
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise InternalError(
                "Failed to retrieve chat sessions",
                details={"error": str(e)},
            )

    except Exception as e:
        AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
        logger.critical(f"Unexpected error listing chat sessions: {e.__class__.__name__}")
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
    chat_history_manager=Depends(get_chat_history_manager),
    llm_service=Depends(get_llm_service),
    memory_interface=Depends(get_memory_interface),
    knowledge_base=Depends(get_knowledge_base),
    config=Depends(get_config)
):
    """Send a chat message and get AI response"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "send_message", request_id)

        # Validate message content
        if not message.content or not message.content.strip():
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ValidationError("Message content cannot be empty")

        # Process the chat message
        response_data = await process_chat_message(
            message,
            chat_history_manager,
            llm_service,
            memory_interface,
            knowledge_base,
            config,
            request_id
        )

        return create_success_response(
            data=response_data,
            message="Message processed successfully",
            request_id=request_id
        )

    except Exception as e:
        return handle_api_error(e, request_id, "send_message")

@router.post("/chat/stream")
async def stream_message(
    message: ChatMessage,
    request: Request,
    chat_history_manager=Depends(get_chat_history_manager),
    llm_service=Depends(get_llm_service)
):
    """Stream chat response for real-time communication"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "stream_message", request_id)

        # Validate message content
        if not message.content or not message.content.strip():
            return JSONResponse(
                status_code=400,
                content={"error": "Message content cannot be empty", "request_id": request_id}
            )

        # Return streaming response
        return await stream_chat_response(
            message,
            chat_history_manager,
            llm_service,
            request_id
        )

    except Exception as e:
        return handle_api_error(e, request_id, "stream_message")

@router.get("/chat/sessions/{session_id}")
async def get_session_messages(
    session_id: str,
    request: Request,
    page: int = 1,
    per_page: int = 50,
    chat_history_manager=Depends(get_chat_history_manager)
):
    """Get messages for a specific chat session"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "get_session_messages", request_id)

        # Validate session ID
        if not validate_chat_session_id(session_id):
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ValidationError("Invalid session ID format")

        # Validate pagination parameters
        if page < 1 or per_page < 1 or per_page > 100:
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ValidationError("Invalid pagination parameters")

        # Get session messages
        messages = await chat_history_manager.get_session_messages(
            session_id,
            page=page,
            per_page=per_page
        )

        if messages is None:
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ResourceNotFoundError(f"Session {session_id} not found")

        total_count = await chat_history_manager.get_session_message_count(session_id)

        response_data = {
            "messages": messages,
            "session_id": session_id,
            "total_count": total_count,
            "page": page,
            "per_page": per_page
        }

        return create_success_response(
            data=response_data,
            message="Session messages retrieved successfully",
            request_id=request_id
        )

    except Exception as e:
        return handle_api_error(e, request_id, "get_session_messages")

@router.post("/chat/sessions")
async def create_session(
    session_data: SessionCreate,
    request: Request,
    chat_history_manager=Depends(get_chat_history_manager)
):
    """Create a new chat session"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "create_session", request_id)

        # Generate new session
        session_id = generate_chat_session_id()
        session_title = session_data.title or DEFAULT_SESSION_TITLE

        # Create session
        session = await chat_history_manager.create_session(
            session_id=session_id,
            title=session_title,
            metadata=session_data.metadata or {}
        )

        await log_chat_event("session_created", session_id, {
            "title": session_title,
            "request_id": request_id
        })

        return create_success_response(
            data=session,
            message="Session created successfully",
            request_id=request_id,
            status_code=201
        )

    except Exception as e:
        return handle_api_error(e, request_id, "create_session")

@router.put("/chat/sessions/{session_id}")
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    request: Request,
    chat_history_manager=Depends(get_chat_history_manager)
):
    """Update a chat session"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "update_session", request_id)

        # Validate session ID
        if not validate_chat_session_id(session_id):
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ValidationError("Invalid session ID format")

        # Update session
        updated_session = await chat_history_manager.update_session(
            session_id=session_id,
            title=session_data.title,
            metadata=session_data.metadata
        )

        if updated_session is None:
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ResourceNotFoundError(f"Session {session_id} not found")

        await log_chat_event("session_updated", session_id, {
            "title": session_data.title,
            "request_id": request_id
        })

        return create_success_response(
            data=updated_session,
            message="Session updated successfully",
            request_id=request_id
        )

    except Exception as e:
        return handle_api_error(e, request_id, "update_session")

@router.delete("/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    chat_history_manager=Depends(get_chat_history_manager)
):
    """Delete a chat session"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "delete_session", request_id)

        # Validate session ID
        if not validate_chat_session_id(session_id):
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ValidationError("Invalid session ID format")

        # Delete session
        deleted = await chat_history_manager.delete_session(session_id)

        if not deleted:
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ResourceNotFoundError(f"Session {session_id} not found")

        await log_chat_event("session_deleted", session_id, {
            "request_id": request_id
        })

        return create_success_response(
            data={"session_id": session_id, "deleted": True},
            message="Session deleted successfully",
            request_id=request_id
        )

    except Exception as e:
        return handle_api_error(e, request_id, "delete_session")

@router.get("/chat/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    request: Request,
    format: str = "json",
    chat_history_manager=Depends(get_chat_history_manager)
):
    """Export a chat session in various formats"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "export_session", request_id)

        # Validate session ID
        if not validate_chat_session_id(session_id):
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ValidationError("Invalid session ID format")

        # Validate format
        if format not in ["json", "txt", "csv"]:
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ValidationError("Invalid export format. Supported: json, txt, csv")

        # Get session data
        session_data = await chat_history_manager.export_session(session_id, format)

        if session_data is None:
            AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = get_exceptions_lazy()
            raise ResourceNotFoundError(f"Session {session_id} not found")

        # Set appropriate content type
        content_types = {
            "json": "application/json",
            "txt": "text/plain",
            "csv": "text/csv"
        }

        await log_chat_event("session_exported", session_id, {
            "format": format,
            "request_id": request_id
        })

        return Response(
            content=session_data,
            media_type=content_types[format],
            headers={
                "Content-Disposition": f"attachment; filename=chat_session_{session_id}.{format}"
            }
        )

    except Exception as e:
        return handle_api_error(e, request_id, "export_session")

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
                "chat_history_manager": "healthy" if chat_history_manager else "unavailable",
                "llm_service": "healthy" if llm_service else "unavailable"
            }
        }

        overall_healthy = all(
            status == "healthy"
            for status in health_status["components"].values()
        )

        if not overall_healthy:
            health_status["status"] = "degraded"

        return JSONResponse(
            status_code=200 if overall_healthy else 503,
            content=health_status
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@router.get("/chat/stats")
async def chat_statistics(
    request: Request,
    chat_history_manager=Depends(get_chat_history_manager)
):
    """Get chat service statistics"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "chat_statistics", request_id)

        # Get basic statistics
        stats = await chat_history_manager.get_statistics()

        return create_success_response(
            data=stats,
            message="Statistics retrieved successfully",
            request_id=request_id
        )

    except Exception as e:
        return handle_api_error(e, request_id, "chat_statistics")