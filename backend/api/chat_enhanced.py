# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Chat API with AI Stack Integration.

This module provides enhanced chat capabilities by integrating with the AI Stack VM,
while maintaining backward compatibility with existing chat endpoints.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from backend.type_defs.common import Metadata
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.dependencies import get_config, get_knowledge_base
from backend.services.ai_stack_client import AIStackError, get_ai_stack_client
from src.constants.threshold_constants import CategoryDefaults, TimingConstants

# Import reusable chat utilities - Phase 1 Utility Extraction
from backend.utils.chat_utils import (
    create_error_response,
    create_success_response,
    generate_chat_session_id,
    generate_request_id,
    get_chat_history_manager,
    log_chat_event,
    validate_chat_session_id,
)
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["chat-enhanced"])

# ====================================================================
# Request/Response Models
# ====================================================================


class EnhancedChatMessage(BaseModel):
    """Enhanced chat message model with AI Stack integration."""

    content: str = Field(
        ..., min_length=1, max_length=50000, description="Message content"
    )
    role: str = Field(
        default=CategoryDefaults.ROLE_USER, pattern="^(user|assistant|system)$", description="Message role"
    )
    session_id: Optional[str] = Field(None, description="Chat session ID")
    message_type: Optional[str] = Field("text", description="Message type")
    metadata: Optional[Metadata] = Field(
        default_factory=dict, description="Additional metadata"
    )

    # AI Stack specific fields
    use_ai_stack: bool = Field(
        True, description="Whether to use AI Stack for enhanced responses"
    )
    use_knowledge_base: bool = Field(
        True, description="Whether to include knowledge base context"
    )
    response_style: str = Field(
        "conversational", description="Response style preference"
    )
    include_sources: bool = Field(
        True, description="Whether to include source citations"
    )


class ChatPreferences(BaseModel):
    """Chat preferences for customizing AI behavior."""

    response_length: str = Field(
        "medium", description="Preferred response length (short, medium, long)"
    )
    technical_level: str = Field("adaptive", description="Technical complexity level")
    include_reasoning: bool = Field(
        False, description="Include reasoning steps in responses"
    )
    fact_checking: bool = Field(
        True, description="Enable fact checking against knowledge base"
    )


# ====================================================================
# Helper Functions for process_enhanced_chat_message (Issue #281)
# ====================================================================


async def _store_user_message(
    message: EnhancedChatMessage,
    session_id: str,
    chat_history_manager,
) -> str:
    """Store user message and log event (Issue #281: extracted)."""
    user_message_id = str(uuid4())
    user_message_data = {
        "id": user_message_id,
        "content": message.content,
        "role": message.role,
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": {**message.metadata, "ai_stack_enabled": message.use_ai_stack},
        "session_id": session_id,
    }

    if hasattr(chat_history_manager, "add_message"):
        await chat_history_manager.add_message(session_id, user_message_data)

    log_chat_event(
        "enhanced_message_received",
        session_id,
        {
            "message_id": user_message_id,
            "content_length": len(message.content),
            "ai_stack_enabled": message.use_ai_stack,
            "use_knowledge_base": message.use_knowledge_base,
        },
    )

    return user_message_id


async def _get_chat_context(
    message: EnhancedChatMessage,
    session_id: str,
    chat_history_manager,
) -> list:
    """Retrieve chat context from history (Issue #281: extracted)."""
    chat_context = []
    if hasattr(chat_history_manager, "get_session_messages"):
        try:
            model_name = message.metadata.get("model") if message.metadata else None
            recent_messages = await chat_history_manager.get_session_messages(
                session_id, model_name=model_name
            )
            chat_context = recent_messages or []
            logger.info(
                f"Retrieved {len(chat_context)} messages for model {model_name or 'default'}"
            )
        except Exception as e:
            logger.warning("Could not retrieve chat context: %s", e)

    return chat_context


async def _enhance_with_knowledge_base(
    message: EnhancedChatMessage,
    knowledge_base,
) -> tuple:
    """Enhance context with knowledge base search (Issue #281: extracted)."""
    enhanced_context = None
    knowledge_sources = []

    if message.use_knowledge_base and knowledge_base:
        try:
            kb_results = await knowledge_base.search(query=message.content, top_k=5)
            if kb_results:
                knowledge_sources = kb_results
                kb_summary = "\n".join(
                    [
                        f"- {item.get('content', '')[:300]}..."
                        for item in kb_results[:3]
                    ]
                )
                enhanced_context = f"Relevant knowledge context:\n{kb_summary}"
                logger.info("Enhanced context with %s KB results", len(kb_results))
        except Exception as e:
            logger.warning("Knowledge base context enhancement failed: %s", e)

    return enhanced_context, knowledge_sources


async def _generate_ai_stack_response(
    message: EnhancedChatMessage,
    chat_context: list,
    enhanced_context: Optional[str],
    chat_history_manager,
    preferences: Optional[ChatPreferences],
) -> Metadata:
    """Generate response using AI Stack (Issue #281: extracted)."""
    try:
        ai_client = await get_ai_stack_client()

        model_name = message.metadata.get("model") if message.metadata else None
        context_manager = getattr(chat_history_manager, "context_manager", None)

        if context_manager:
            message_limit = context_manager.get_message_limit(model_name)
            logger.info(
                f"Using {message_limit} messages for LLM context (model: {model_name or 'default'})"
            )
        else:
            message_limit = 20
            logger.warning("Context manager not available, using default limit")

        formatted_history = []
        for msg in chat_context[-message_limit:]:
            formatted_history.append(
                {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                }
            )

        ai_stack_response = await ai_client.chat_message(
            message=message.content,
            context=enhanced_context,
            chat_history=formatted_history,
        )

        return {
            "content": ai_stack_response.get(
                "response", ai_stack_response.get("content", "")
            ),
            "role": "assistant",
            "metadata": {
                "source": "ai_stack",
                "agent_used": ai_stack_response.get("agent", "chat"),
                "confidence": ai_stack_response.get("confidence", 0.8),
                "reasoning": (
                    ai_stack_response.get("reasoning")
                    if preferences and preferences.include_reasoning
                    else None
                ),
            },
        }

    except AIStackError as e:
        logger.error("AI Stack chat failed: %s", e)
        return {
            "content": (
                "I apologize, but I'm experiencing technical difficulties with my "
                "enhanced AI capabilities. Please try again in a moment."
            ),
            "role": "assistant",
            "metadata": {"source": "fallback", "error": "ai_stack_unavailable"},
        }


def _create_basic_response() -> Metadata:
    """Create basic response without AI Stack (Issue #281: extracted)."""
    return {
        "content": (
            "Thank you for your message. I'm currently running in basic mode "
            "without enhanced AI capabilities."
        ),
        "role": "assistant",
        "metadata": {"source": "basic_chat"},
    }


def _enhance_response_with_sources(
    ai_response: Metadata,
    knowledge_sources: list,
    include_sources: bool,
) -> None:
    """Add knowledge sources to response metadata (Issue #281: extracted)."""
    if include_sources and knowledge_sources:
        sources_info = []
        for source in knowledge_sources[:3]:
            sources_info.append(
                {
                    "title": source.get("title", "Unknown"),
                    "snippet": source.get("content", "")[:150] + "...",
                    "score": source.get("score", 0.0),
                }
            )
        ai_response["metadata"]["sources"] = sources_info


async def _store_ai_response(
    ai_response: Metadata,
    session_id: str,
    request_id: str,
    chat_history_manager,
) -> str:
    """Store AI response and log event (Issue #281: extracted)."""
    ai_message_id = str(uuid4())
    ai_message_data = {
        "id": ai_message_id,
        "content": ai_response.get("content", ""),
        "role": "assistant",
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": ai_response.get("metadata", {}),
        "session_id": session_id,
    }

    if hasattr(chat_history_manager, "add_message"):
        await chat_history_manager.add_message(session_id, ai_message_data)

    log_chat_event(
        "enhanced_response_generated",
        session_id,
        {
            "message_id": ai_message_id,
            "content_length": len(ai_response.get("content", "")),
            "source": ai_response.get("metadata", {}).get("source", "unknown"),
            "request_id": request_id,
        },
    )

    return ai_message_id


# ====================================================================
# Core Enhanced Chat Functions
# ====================================================================


async def process_enhanced_chat_message(
    message: EnhancedChatMessage,
    chat_history_manager,
    knowledge_base,
    config: Metadata,
    request_id: str,
    preferences: Optional[ChatPreferences] = None,
) -> Metadata:
    """
    Process a chat message with AI Stack enhanced capabilities.

    Issue #281: Refactored from 219 lines to use extracted helper methods.

    This function combines local knowledge base search with AI Stack's
    intelligent chat agents for superior conversational experience.
    """
    try:
        # Validate session ID
        if message.session_id and not validate_chat_session_id(message.session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID format")

        # Get or create session
        session_id = message.session_id or generate_chat_session_id()

        # Store user message (Issue #281: uses helper)
        await _store_user_message(message, session_id, chat_history_manager)

        # Get chat context (Issue #281: uses helper)
        chat_context = await _get_chat_context(message, session_id, chat_history_manager)

        # Enhance with knowledge base (Issue #281: uses helper)
        enhanced_context, knowledge_sources = await _enhance_with_knowledge_base(
            message, knowledge_base
        )

        # Generate AI response (Issue #281: uses helpers)
        if message.use_ai_stack:
            ai_response = await _generate_ai_stack_response(
                message, chat_context, enhanced_context, chat_history_manager, preferences
            )
            if ai_response.get("metadata", {}).get("source") == "ai_stack":
                logger.info("AI Stack response generated successfully")
        else:
            ai_response = _create_basic_response()

        # Enhance response with sources (Issue #281: uses helper)
        _enhance_response_with_sources(ai_response, knowledge_sources, message.include_sources)

        # Store AI response (Issue #281: uses helper)
        ai_message_id = await _store_ai_response(
            ai_response, session_id, request_id, chat_history_manager
        )

        return {
            "content": ai_response.get("content", ""),
            "role": "assistant",
            "session_id": session_id,
            "message_id": ai_message_id,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": ai_response.get("metadata", {}),
            "knowledge_sources": knowledge_sources if message.include_sources else None,
        }

    except Exception as e:
        logger.error("Error processing enhanced chat message: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to process enhanced chat message: {str(e)}"
        )


# ====================================================================
# Enhanced Chat API Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_chat",
    error_code_prefix="CHAT_ENHANCED",
)
@router.post("/enhanced")
async def enhanced_chat(
    message: EnhancedChatMessage,
    request: Request,
    preferences: Optional[ChatPreferences] = None,
    config=Depends(get_config),
    knowledge_base=Depends(get_knowledge_base),
):
    """
    Enhanced chat endpoint with AI Stack integration.

    This endpoint provides intelligent conversation with:
    - AI Stack enhanced reasoning capabilities
    - Knowledge base integration
    - Source citations
    - Customizable response preferences
    """
    request_id = generate_request_id()

    try:
        # Validate message content
        if not message.content or not message.content.strip():
            return create_error_response(
                error_code="VALIDATION_ERROR",
                message="Message content cannot be empty",
                request_id=request_id,
                status_code=400,
            )

        # Get dependencies from request state
        chat_history_manager = get_chat_history_manager(request)

        # Process the enhanced chat message
        response_data = await process_enhanced_chat_message(
            message,
            chat_history_manager,
            knowledge_base,
            config,
            request_id,
            preferences,
        )

        return JSONResponse(
            status_code=200,
            content=create_success_response(
                response_data,
                "Enhanced chat message processed successfully",
                request_id,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Enhanced chat error: %s", request_id, e)
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )


# ====================================================================
# Streaming Helpers (Issue #486: extracted from stream_enhanced_chat)
# ====================================================================


def _format_sse_event(data: dict) -> str:
    """Format data as Server-Sent Event (Issue #486: extracted helper)."""
    return f"data: {json.dumps(data)}\n\n"


async def _stream_ai_stack_response(
    message: EnhancedChatMessage,
    session_id: str,
    chat_history_manager,
    request_id: str,
    preferences: Optional[ChatPreferences],
):
    """Stream AI Stack enhanced response in chunks (Issue #486: extracted)."""
    try:
        response_data = await process_enhanced_chat_message(
            message, chat_history_manager, None, {}, request_id, preferences
        )

        content = response_data.get("content", "")
        chunk_size = 50

        for i in range(0, len(content), chunk_size):
            chunk = content[i : i + chunk_size]
            yield _format_sse_event({
                "type": "chunk",
                "content": chunk,
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            })
            await asyncio.sleep(TimingConstants.STREAMING_CHUNK_DELAY)

        yield _format_sse_event({
            "type": "metadata",
            "metadata": response_data.get("metadata", {}),
            "sources": response_data.get("knowledge_sources"),
            "session_id": session_id,
        })

    except Exception as e:
        logger.error("Enhanced streaming error: %s", e)
        yield _format_sse_event({
            "type": "error",
            "message": "Error generating enhanced response",
            "timestamp": datetime.utcnow().isoformat(),
        })


def _stream_fallback_response(session_id: str):
    """Stream fallback response when AI Stack not enabled (Issue #486: extracted)."""
    fallback_msg = (
        "Thank you for your message. Enhanced streaming requires AI Stack "
        "integration."
    )
    return _format_sse_event({
        "type": "chunk",
        "content": fallback_msg,
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def _generate_enhanced_stream(
    message: EnhancedChatMessage,
    request: Request,
    request_id: str,
    preferences: Optional[ChatPreferences],
):
    """Generate streaming response with AI Stack integration (Issue #486: extracted)."""
    try:
        session_id = message.session_id or generate_chat_session_id()
        yield _format_sse_event({
            "type": "start", "session_id": session_id, "enhanced": True
        })

        chat_history_manager = get_chat_history_manager(request)

        if message.use_ai_stack:
            async for event in _stream_ai_stack_response(
                message, session_id, chat_history_manager, request_id, preferences
            ):
                yield event
        else:
            yield _stream_fallback_response(session_id)

        yield _format_sse_event({"type": "end"})

    except Exception as e:
        logger.error("Streaming error: %s", e)
        yield _format_sse_event({
            "type": "error",
            "message": "Error in enhanced streaming",
            "timestamp": datetime.utcnow().isoformat(),
        })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stream_enhanced_chat",
    error_code_prefix="CHAT_ENHANCED",
)
@router.post("/stream-enhanced")
async def stream_enhanced_chat(
    message: EnhancedChatMessage,
    request: Request,
    preferences: Optional[ChatPreferences] = None,
):
    """
    Stream enhanced chat response for real-time communication (Issue #486: refactored).

    Provides real-time streaming of AI Stack enhanced responses
    with knowledge base integration.
    """
    request_id = generate_request_id()

    return StreamingResponse(
        _generate_enhanced_stream(message, request, request_id, preferences),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_chat_health_check",
    error_code_prefix="CHAT_ENHANCED",
)
@router.get("/health-enhanced")
async def enhanced_chat_health_check():
    """Health check for enhanced chat service including AI Stack connectivity."""
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {},
        }

        # Check AI Stack connectivity
        try:
            ai_client = await get_ai_stack_client()
            ai_stack_health = await ai_client.health_check()
            health_status["components"]["ai_stack"] = ai_stack_health["status"]
        except Exception as e:
            logger.warning("AI Stack health check failed: %s", e)
            health_status["components"]["ai_stack"] = "unavailable"

        # Overall health assessment
        overall_healthy = health_status["components"]["ai_stack"] == "healthy"
        if not overall_healthy:
            health_status["status"] = "degraded"

        return JSONResponse(
            status_code=200 if overall_healthy else 503, content=health_status
        )

    except Exception as e:
        logger.error("Enhanced chat health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_enhanced_chat_capabilities",
    error_code_prefix="CHAT_ENHANCED",
)
@router.get("/capabilities")
async def get_enhanced_chat_capabilities():
    """Get enhanced chat capabilities and available features."""
    try:
        ai_client = await get_ai_stack_client()
        agents_info = await ai_client.list_available_agents()

        capabilities = {
            "enhanced_chat": True,
            "ai_stack_integration": True,
            "knowledge_base_integration": True,
            "source_citations": True,
            "streaming_responses": True,
            "multi_agent_coordination": True,
            "available_agents": agents_info.get("agents", []),
            "response_styles": [
                "conversational",
                "technical",
                "creative",
                "analytical",
            ],
            "supported_languages": ["en"],  # Add more as needed
            "max_message_length": 50000,
            "context_window": 10,  # messages
        }

        return create_success_response(
            capabilities, "Enhanced chat capabilities retrieved successfully"
        )

    except Exception as e:
        logger.warning("Failed to get full capabilities: %s", e)
        # Return basic capabilities as fallback
        return create_success_response(
            {
                "enhanced_chat": True,
                "ai_stack_integration": False,
                "knowledge_base_integration": True,
                "error": "Partial capabilities due to AI Stack unavailability",
            }
        )


# ====================================================================
# Backward Compatibility Wrapper
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="compatible_chat_message",
    error_code_prefix="CHAT_ENHANCED",
)
@router.post("/compat/message")
async def compatible_chat_message(
    content: str,
    session_id: Optional[str] = None,
    request: Request = None,
    config=Depends(get_config),
    knowledge_base=Depends(get_knowledge_base),
):
    """
    Backward compatibility endpoint that wraps enhanced chat functionality
    with the original simple interface.
    """
    # Convert simple request to enhanced format
    enhanced_message = EnhancedChatMessage(
        content=content,
        session_id=session_id,
        use_ai_stack=True,
        use_knowledge_base=True,
        include_sources=False,  # Keep simple for compatibility
    )

    # Process through enhanced chat
    response = await enhanced_chat(
        enhanced_message, request, None, config, knowledge_base
    )

    # Extract just the essential fields for backward compatibility
    if isinstance(response, JSONResponse):
        response_data = json.loads(response.body) if hasattr(response, "body") else {}
        if response_data.get("success") and response_data.get("data"):
            data = response_data["data"]
            return {
                "message": data.get("content", ""),
                "session_id": data.get("session_id"),
                "timestamp": data.get("timestamp"),
            }

    return {"message": "Response processing failed", "session_id": session_id}
