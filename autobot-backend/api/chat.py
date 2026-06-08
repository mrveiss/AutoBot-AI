# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat API with basic functionality and AI Stack enhanced capabilities.

This module provides:
- Core chat operations (message sending, streaming, session management)
- AI Stack enhanced chat with knowledge base integration
- Streaming responses for real-time communication

Consolidated from chat.py and chat_enhanced.py per Issue #708.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

# Phase 4 (#7590): feature flag — default-off; enable in staging then flip to default-on.
# Reads env at import time (process restart required to change).
_CHAT_SSOT_STRICT = config.chat_ssot_strict.lower() == "true"

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.schemas_chat import (
    ChatDeleteData,
    ChatHealthData,
    ChatMessage,
    ChatMessageData,
    ChatPreferences,
    ChatSaveData,
    ChatStatsData,
    ConversationSummarizeRequest,
    DetectLanguageData,
    DetectLanguageRequest,
    EnhancedChatCapabilitiesData,
    EnhancedChatData,
    EnhancedChatHealthData,
    EnhancedChatMessage,
    TranslateData,
    TranslateRequest,
)
from api.schemas_common import DataResponse
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.error_utils import safe_http_detail
from autobot_shared.time_utils import parse_utc_iso, utc_timestamp

# Import context overflow protection (#9043)
from chat_history.overflow_integration import create_summary_message, handle_message_completion
from constants.threshold_constants import TimingConstants

# Import dependencies and utilities - Using available dependencies
from dependencies import get_config, get_knowledge_base

# Import shared exception classes (Issue #292 - Eliminate duplicate code)
from exceptions import get_exceptions_lazy

# CRITICAL SECURITY FIX: Import session ownership validation
from security.session_ownership import validate_session_ownership
from services.ai_stack_client import AIStackError, get_ai_stack_client
from type_defs.common import STREAMING_MESSAGE_TYPES, Metadata

# Import reusable chat utilities - Phase 1 Utility Extraction
from utils.chat_utils import (
    create_chat_response,
    create_error_response,
    generate_message_id,
    generate_request_id,
    get_chat_history_manager,
    log_chat_event,
    validate_chat_session_id,
)

# Import models - DISABLED: Models don't exist yet
# from backend.models.conversation import ConversationModel
# from backend.models.message import MessageModel


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


def get_system_state(request: Request) -> Dict:
    """Get system state from app state"""
    return getattr(request.app.state, "system_state", {})


def get_memory_interface(request: Request) -> Any | None:
    """Get memory interface from app state"""
    return getattr(request.app.state, "memory_interface", None)


def get_llm_service(request: Request) -> Any:
    """Get LLM service from app state, with lazy initialization"""
    from services.llm_service import LLMService
    from utils.lazy_singleton import lazy_init_singleton

    return lazy_init_singleton(request.app.state, "llm_service", LLMService)


async def get_chat_workflow_manager(request: Request) -> Any:
    """Get ChatWorkflowManager from app state, with async lazy initialization"""
    from chat_workflow import ChatWorkflowManager
    from utils.lazy_singleton import lazy_init_singleton_async

    async def create_workflow_manager() -> Any:
        """
        Factory function to create and initialize ChatWorkflowManager.

        Returns:
            ChatWorkflowManager: Initialized workflow manager instance
        """
        manager = ChatWorkflowManager()
        await manager.initialize()
        return manager

    return await lazy_init_singleton_async(request.app.state, "chat_workflow_manager", create_workflow_manager)


# Simple utility functions to replace missing imports
def handle_api_error(error: Exception, request_id: str = "unknown") -> Dict[str, str]:
    """Simple error handler replacement"""
    logger.exception("[%s] API error", request_id)
    return {"error": "An internal error occurred"}


def log_request_context(request: Request, endpoint: str, request_id: str) -> None:
    """Log request context for debugging"""
    logger.info("[%s] %s - %s %s", request_id, endpoint, request.method, request.url.path)


# ====================================================================
# Message Merge Helpers (Issue #315 - Reduced nesting)
# ====================================================================


def _parse_message_timestamp(msg_ts_str: str) -> datetime | None:
    """Parse message timestamp from various formats (Issue #315)."""
    if not isinstance(msg_ts_str, str) or not msg_ts_str:
        return None
    try:
        if "T" in msg_ts_str:
            return parse_utc_iso(msg_ts_str)
        return datetime.strptime(msg_ts_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _should_start_new_streaming_group(current_ts: datetime, last_streaming_ts: datetime | None) -> bool:
    """Check if a new streaming group should start (Issue #315)."""
    if last_streaming_ts is None:
        return False
    time_diff = abs((current_ts - last_streaming_ts).total_seconds())
    return time_diff > 120  # 2 minutes = new streaming session


def _has_longer_streaming_response(
    msg: Dict,
    msg_sender: str,
    msg_content_len: int,
    messages: List[Dict],
    is_streaming_fn,
) -> bool:
    """Check if any message has longer streaming content (Issue #315)."""
    return any(
        m.get("sender", "") == msg_sender
        and is_streaming_fn(m)
        and len(m.get("text", "") or m.get("content", "")) > msg_content_len
        for m in messages
        if m is not msg
    )


def _is_streaming_response(msg: Dict) -> bool:
    """Check if message is a streaming LLM response (Issue #281: module-level helper)."""
    message_type = msg.get("messageType", msg.get("type", "default"))
    return message_type in STREAMING_MESSAGE_TYPES


def _get_message_signature(msg: Dict) -> tuple:
    """
    Create a unique signature for message deduplication (Issue #281: extracted).

    Issue #716: Fixed to deduplicate assistant messages with identical content.
    Previously, streaming messages with same content but different IDs would
    both be kept, causing duplicate "Hello there!" type issues.

    For user messages, use sender + content for deduplication.
    For assistant messages, use sender + content (truncated) for deduplication.
    For terminal/system messages, use ID if available, else timestamp + content prefix.
    """
    message_type = msg.get("messageType", msg.get("type", "default"))
    sender = msg.get("sender", "")
    text_content = msg.get("text", "") or msg.get("content", "")

    # For USER messages: deduplicate by sender + content
    if sender == "user":
        return ("user", text_content[:200])

    # Issue #716: For ASSISTANT messages, use content for deduplication
    # This prevents duplicate messages with same content but different IDs
    if sender == "assistant":
        # Use first 300 chars of content - enough to identify unique messages
        # while handling minor whitespace differences
        normalized_content = text_content.strip()[:300]
        return ("assistant", message_type, normalized_content)

    # For TERMINAL/SYSTEM messages: use ID if available
    msg_id = msg.get("id") or msg.get("messageId")
    if msg_id:
        return ("id", msg_id)

    return (msg.get("timestamp", ""), sender, text_content[:100])


def _filter_preserved_messages(existing: List[Dict], new: List[Dict], new_sigs: set, new_by_id: Dict) -> List[Dict]:
    """Filter existing messages to preserve backend-added ones (Issue #281: extracted)."""
    preserved = []
    for msg in existing:
        sig = _get_message_signature(msg)
        msg_id = msg.get("id") or msg.get("messageId")

        # If message has an ID and new set has same ID, skip (use new version)
        if msg_id and msg_id in new_by_id:
            continue

        # If signature matches, skip (deduplicate)
        if sig in new_sigs:
            continue

        # For streaming responses without IDs, check if there's a longer version
        if _is_streaming_response(msg):
            msg_sender = msg.get("sender", "")
            msg_content_len = len(msg.get("text", "") or msg.get("content", ""))

            has_longer_existing = _has_longer_streaming_response(
                msg, msg_sender, msg_content_len, existing, _is_streaming_response
            )
            has_longer_new = _has_longer_streaming_response(
                msg, msg_sender, msg_content_len, new, _is_streaming_response
            )
            if has_longer_existing or has_longer_new:
                continue

        preserved.append(msg)
    return preserved


def _process_streaming_groups(merged: List[Dict]) -> List[Dict]:
    """
    Process merged messages, grouping streaming responses by time window (Issue #281: extracted).

    Groups streaming messages by 2-minute windows and keeps only the longest per group.
    This preserves multiple LLM responses across different conversation turns.
    """
    final_merged = []
    streaming_groups: List[List[Dict]] = []
    current_group: List[Dict] = []
    last_streaming_ts = None

    for msg in merged:
        if _is_streaming_response(msg):
            msg_ts_str = msg.get("timestamp", "")
            current_ts = _parse_message_timestamp(msg_ts_str)

            if current_ts and _should_start_new_streaming_group(current_ts, last_streaming_ts):
                if current_group:
                    streaming_groups.append(current_group)
                current_group = []

            if current_ts:
                last_streaming_ts = current_ts

            current_group.append(msg)
        else:
            # Non-streaming message - finalize current streaming group
            if current_group:
                streaming_groups.append(current_group)
                current_group = []
                last_streaming_ts = None
            final_merged.append(msg)

    # Don't forget the last group
    if current_group:
        streaming_groups.append(current_group)

    # Keep only the longest streaming message from each group
    for group in streaming_groups:
        if group:
            longest = max(group, key=lambda m: len(m.get("text", "") or m.get("content", "")))
            final_merged.append(longest)

    return final_merged


# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)

# Phase 4 (#7590): log feature flag state at startup so operators know which mode is active
logger.info(
    "AUTOBOT_CHAT_SSOT_STRICT=%s",
    "true" if _CHAT_SSOT_STRICT else "false (default — session_id enforcement via schema only)",
)

# Include session management router
from api.chat_sessions import router as sessions_router

router.include_router(sessions_router)

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


def _validate_session_id(session_id: str | None) -> None:
    """
    Validate session ID format if provided.

    Issue #281: Extracted helper for session validation.
    Phase 4 (#7590): in SSOT strict mode also reject missing session_id so
    every message is tied to a known session (AUTOBOT_CHAT_SSOT_STRICT).

    Args:
        session_id: Session ID to validate

    Raises:
        ValidationError: If session ID format is invalid
    """
    (
        AutoBotError,
        InternalError,
        ResourceNotFoundError,
        ValidationError,
        get_error_code,
    ) = get_exceptions_lazy()

    if _CHAT_SSOT_STRICT and not session_id:
        raise ValidationError("session_id is required (AUTOBOT_CHAT_SSOT_STRICT)")

    if session_id and not validate_chat_session_id(session_id):
        raise ValidationError("Invalid session ID format")


def _to_persisted_message(api_data: Dict[str, Any], default_type: str) -> Dict[str, Any]:
    """Translate API-shape (role/content) to disk-shape (sender/content/type).

    #6744: api/chat.py historically called ``add_message(session_id, dict)``
    but the method signature is ``add_message(sender, text, ...)``. Python
    silently accepted the type mismatch and the message ended up in the
    in-memory default-history bucket because ``session_id`` defaulted to
    None. Persistence only worked when the streaming workflow path
    (``chat_workflow/manager.py:add_messages_batch``) flushed at end-of-
    stream — so any failed/interrupted stream lost both user and assistant
    messages. This helper produces the canonical disk-shape dict; callers
    then use ``add_messages_batch(session_id, [msg])`` (correct signature).

    Schema mapping:
        role     → sender
        content  → content (unchanged)
        metadata → metadata (unchanged, defaults to ``{}``)
        + type   ← caller's default ("message" for user, "response" for assistant)
        + sources ← [] (RAG citations; populated elsewhere)
        authorId → authorId (preserved for shared-session attribution, #3282)
    """
    sender = api_data.get("role") or api_data.get("sender") or "system"
    persisted: Dict[str, Any] = {
        "id": api_data["id"],
        "sender": sender,
        "content": api_data.get("content", ""),
        "timestamp": api_data.get("timestamp"),
        "type": default_type,
        "metadata": api_data.get("metadata") or {},
        "sources": api_data.get("sources", []),
    }
    if "authorId" in api_data:
        persisted["authorId"] = api_data["authorId"]
    return persisted


async def _store_and_log_user_message(
    message: "ChatMessage",
    session_id: str,
    chat_history_manager,
    author_id: str | None = None,
) -> str:
    """
    Store user message and log the event.

    Issue #281: Extracted helper for user message handling.
    Issue #3282: author_id added for multi-user message attribution.

    Args:
        message: Chat message object
        session_id: Session ID
        chat_history_manager: Chat history manager instance
        author_id: Optional user ID of the message author for shared sessions

    Returns:
        Generated message ID
    """
    user_message_id = generate_message_id()
    user_message_data = {
        "id": user_message_id,
        "content": message.content,
        "role": message.role,
        "timestamp": utc_timestamp(),
        "metadata": message.metadata,
        "session_id": session_id,
    }
    if author_id:
        user_message_data["authorId"] = author_id

    if hasattr(chat_history_manager, "add_messages_batch"):
        # #6744: was add_message(session_id, dict) — wrong-signature silent no-op.
        await chat_history_manager.add_messages_batch(session_id, [_to_persisted_message(user_message_data, "message")])

    # Issue #3282: Broadcast new user message to all session collaborators
    try:
        from websocket.presence import presence_manager

        await presence_manager.broadcast_to_session(
            session_id,
            {
                "type": "new_message",
                "session_id": session_id,
                "message_id": user_message_id,
                "author_id": author_id,
                "role": message.role,
                "timestamp": utc_timestamp(),
            },
        )
    except Exception:
        pass  # Broadcast failure must never break message storage

    log_chat_event(
        "message_received",
        session_id,
        {
            "message_id": user_message_id,
            "content_length": len(message.content),
            "role": message.role,
        },
    )

    # Phase 4 (#7590): structured JSON telemetry for SSOT cardinality query.
    # Log query: count(distinct session_id where event="chat_send") per request — P99 ≤ 1.0.
    logger.info(json.dumps({"event": "chat_send", "session_id": session_id, "message_id": user_message_id}))
    try:
        from monitoring.prometheus_metrics import get_metrics_manager

        get_metrics_manager().record_chat_message_sent("chat_send")
    except Exception as e:
        logger.warning("chat_send Prometheus metrics update failed: %s", e)

    return user_message_id


async def _get_chat_context(chat_history_manager, session_id: str, model_name: str | None) -> List[Dict]:
    """
    Get chat context from history with model-aware retrieval.

    Issue #281: Extracted helper for context retrieval.

    Args:
        chat_history_manager: Chat history manager instance
        session_id: Session ID
        model_name: Optional model name for context optimization

    Returns:
        List of chat context messages
    """
    if not hasattr(chat_history_manager, "get_session_messages"):
        return []

    try:
        recent_messages = await chat_history_manager.get_session_messages(session_id, model_name=model_name)
        chat_context = recent_messages or []
        logger.info(f"Retrieved {len(chat_context)} messages for model {model_name or 'default'}")
        return chat_context
    except Exception as e:
        logger.warning("Could not retrieve chat context: %s", e)
        return []


def _build_llm_context(
    chat_context: List[Dict],
    message: "ChatMessage",
    chat_history_manager,
    model_name: str | None,
) -> List[Dict]:
    """
    Build LLM context with model-aware message limits.

    Issue #281: Extracted helper for LLM context building.

    Args:
        chat_context: Chat history context
        message: Current chat message
        chat_history_manager: Chat history manager instance
        model_name: Optional model name for context optimization

    Returns:
        List of messages for LLM context
    """
    context_manager = getattr(chat_history_manager, "context_manager", None)

    if context_manager:
        message_limit = context_manager.get_message_limit(model_name)
        logger.info(f"Using {message_limit} messages for LLM context (model: {model_name or 'default'})")
    else:
        message_limit = 20
        logger.warning("Context manager not available, using default limit")

    llm_context = [
        {"role": msg.get("role", "user"), "content": msg.get("content", "")} for msg in chat_context[-message_limit:]
    ]
    llm_context.append({"role": message.role, "content": message.content})

    return llm_context


async def _generate_ai_response(
    llm_service, llm_context: List[Dict], session_id: str, request_id: str
) -> tuple[Dict, Any]:
    """
    Generate AI response using LLM service with fallback handling.

    Issue #281: Extracted helper for AI response generation.
    Issue #9043: Returns full LLMResponse for token tracking.

    Args:
        llm_service: LLM service instance
        llm_context: Context messages for LLM
        session_id: Session ID
        request_id: Request ID

    Returns:
        Tuple of (AI response dict with content and role, LLMResponse object or None)
    """
    try:
        # LLMService.chat() accepts OpenAI-format messages and uses
        # conversation_id for per-conversation provider/model overrides.
        # request_id flows through via **kwargs for tracing.
        response = await llm_service.chat(
            messages=llm_context,
            conversation_id=session_id,
            request_id=request_id,
        )
        if response.error:
            logger.warning("LLM returned error for request %s: %s", request_id, response.error)
            return {
                "content": "I encountered an error processing your message. Please try again.",
                "role": "assistant",
            }, None
        return {"content": response.content, "role": "assistant"}, response
    except Exception as e:
        logger.error("LLM generation failed: %s", e)
        return {
            "content": "I encountered an error processing your message. Please try again.",
            "role": "assistant",
        }, None


async def _store_and_log_ai_response(
    ai_response: Dict,
    session_id: str,
    request_id: str,
    chat_history_manager,
) -> str:
    """
    Store AI response and log the event.

    Issue #281: Extracted helper for AI response handling.

    Args:
        ai_response: AI response dict
        session_id: Session ID
        request_id: Request ID
        chat_history_manager: Chat history manager instance

    Returns:
        Generated message ID
    """
    ai_message_id = generate_message_id()
    ai_message_data = {
        "id": ai_message_id,
        "content": ai_response.get("content", ""),
        "role": "assistant",
        "timestamp": utc_timestamp(),
        "metadata": ai_response.get("metadata", {}),
        "session_id": session_id,
    }

    if hasattr(chat_history_manager, "add_messages_batch"):
        # #6744: was add_message(session_id, dict) — wrong-signature silent no-op.
        await chat_history_manager.add_messages_batch(session_id, [_to_persisted_message(ai_message_data, "response")])

    log_chat_event(
        "response_generated",
        session_id,
        {
            "message_id": ai_message_id,
            "content_length": len(ai_response.get("content", "")),
            "request_id": request_id,
        },
    )

    # Phase 4 (#7590): structured JSON telemetry — mirrors chat_send shape for Loki correlation.
    logger.info(json.dumps({"event": "chat_response_stored", "session_id": session_id, "message_id": ai_message_id}))
    try:
        from monitoring.prometheus_metrics import get_metrics_manager

        get_metrics_manager().record_chat_message_sent("chat_response_stored")
    except Exception as e:
        logger.warning("chat_response_stored Prometheus metrics update failed: %s", e)

    return ai_message_id


async def process_chat_message(
    message: ChatMessage,
    chat_history_manager,
    llm_service,
    memory_interface,
    knowledge_base,
    config: Metadata,
    request_id: str,
    author_id: str | None = None,
) -> ChatMessageData:
    """Process a chat message and generate response (Issue #398: refactored,
    Issue #3282: author_id for multi-user attribution, Issue #6502: typed return,
    Issue #9043: context overflow protection)."""
    _validate_session_id(message.session_id)

    session_id = message.session_id

    # Store user message (Issue #281: uses helper, Issue #3282: author_id)
    await _store_and_log_user_message(message, session_id, chat_history_manager, author_id)

    # Get chat context (Issue #281: uses helper)
    model_name = message.metadata.get("model") if message.metadata else None
    chat_context = await _get_chat_context(chat_history_manager, session_id, model_name)

    # Build LLM context (Issue #281: uses helper)
    llm_context = _build_llm_context(chat_context, message, chat_history_manager, model_name)

    # Generate AI response (Issue #281: uses helper, Issue #9043: returns LLMResponse for token tracking)
    ai_response, llm_response = await _generate_ai_response(llm_service, llm_context, session_id, request_id)

    # Store AI response (Issue #281: uses helper)
    ai_message_id = await _store_and_log_ai_response(ai_response, session_id, request_id, chat_history_manager)

    # Issue #9043: Check for context overflow and handle auto-summarization
    overflow_status = await handle_message_completion(
        session_id=session_id,
        model_name=model_name or "gpt-4",  # Fallback to default if not specified
        llm_response=llm_response,
        messages=chat_context,  # Full history for summarization
    )

    # Handle context overflow summary injection
    if overflow_status.get("summary_created"):
        summary_msg = await create_summary_message(overflow_status["summary_text"])
        if hasattr(chat_history_manager, "add_messages_batch"):
            await chat_history_manager.add_messages_batch(
                session_id, [_to_persisted_message(summary_msg, "context_summary")]
            )
        logger.info(
            "Context overflow: auto-summarized session %s (%d%% full)",
            session_id,
            int(overflow_status.get("current_fill_percentage", 0) * 100),
        )

    # Add overflow warning to metadata if triggered
    metadata = ai_response.get("metadata", {})
    if overflow_status.get("warning_triggered"):
        metadata["context_warning"] = {
            "fill_percentage": overflow_status.get("current_fill_percentage", 0),
            "total_tokens": overflow_status.get("total_tokens", 0),
            "context_limit": overflow_status.get("context_limit", 0),
        }

    # MVA-3090: Extract thinking metadata from LLM response
    thinking_metadata = None
    if llm_response and llm_response.usage:
        # Check for thinking_tokens in usage dict (Anthropic extended thinking)
        thinking_tokens = llm_response.usage.get("thinking_tokens") or llm_response.usage.get("cache_read_input_tokens")
        if thinking_tokens and thinking_tokens > 0:
            from api.schemas_chat import ThinkingMetadata

            thinking_metadata = ThinkingMetadata(used=True, tokens_used=thinking_tokens)
        else:
            from api.schemas_chat import ThinkingMetadata

            thinking_metadata = ThinkingMetadata(used=False, tokens_used=None)

    return ChatMessageData(
        content=ai_response.get("content", ""),
        role="assistant",
        session_id=session_id,
        message_id=ai_message_id,
        timestamp=utc_timestamp(),
        metadata=metadata,
        thinking_metadata=thinking_metadata,
    )


# ====================================================================
# Streaming Response Functions
# ====================================================================


async def _generate_llm_stream(
    message: ChatMessage,
    chat_history_manager,
    llm_service,
    request_id: str,
):
    """Generate LLM streaming response chunks (Issue #398: extracted, MVA-3090: thinking metadata).

    Note: thinking_metadata is included in non-streaming responses via process_chat_message.
    For streaming responses, thinking_metadata would need to be extracted from the LLM stream's
    final usage information and included in the 'end' event. Currently not implemented for
    the streaming path due to llm_service.stream_response() only yielding text chunks.
    """
    try:
        session_id = message.session_id
        yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"

        if hasattr(llm_service, "stream_response"):
            # MVA-3090: Streaming path - thinking_metadata not yet extracted from stream
            # TODO: Extract usage/thinking_metadata from stream final message and include in end event
            async for chunk in llm_service.stream_response(message.content, session_id):
                chunk_data = {
                    "type": "chunk",
                    "content": chunk.get("content", ""),
                    "session_id": session_id,
                    "timestamp": utc_timestamp(),
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"
        else:
            # Non-streaming path - thinking_metadata included via process_chat_message
            response_data = await process_chat_message(
                message, chat_history_manager, llm_service, None, None, {}, request_id
            )
            yield f"data: {json.dumps({'type': 'complete', **response_data.model_dump()})}\n\n"

        # MVA-3090: End event could include thinking_metadata here for streaming responses
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    except Exception as e:
        logger.error("Streaming error: %s", e)
        error_data = {
            "type": "error",
            "content": "Error generating response",
            "timestamp": utc_timestamp(),
        }
        yield f"data: {json.dumps(error_data)}\n\n"


async def stream_chat_response(
    message: ChatMessage, chat_history_manager, llm_service, request_id: str
) -> StreamingResponse:
    """Stream chat response for real-time communication (Issue #398: refactored)."""
    return StreamingResponse(
        _generate_llm_stream(message, chat_history_manager, llm_service, request_id),
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


@router.get("/chats", response_model=DataResponse[List[Dict[str, Any]]])
@router.get("/chat/chats", response_model=DataResponse[List[Dict[str, Any]]])  # Frontend compatibility alias
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_chats",
    error_code_prefix="CHAT",
)
async def list_chats(
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    List all available chat sessions with improved error handling (consolidated).

    Issue #744: Requires authenticated user.
    """
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
    # list_sessions_fast is async (uses asyncio.to_thread internally)
    sessions = await chat_history_manager.list_sessions_fast()
    return create_chat_response(
        data=sessions,
        message="Chat sessions retrieved successfully",
        request_id=request_id,
    )


@router.post("/chat", response_model=DataResponse[ChatMessageData])
@router.post("/chat/message", response_model=DataResponse[ChatMessageData])  # Alternative endpoint
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_message",
    error_code_prefix="CHAT",
)
async def send_message(
    current_user: dict = Depends(get_current_user),
    message: ChatMessage = None,
    request: Request = None,
    config=Depends(get_config),
    knowledge_base=Depends(get_knowledge_base),
):
    """
    Send a chat message and get AI response.

    Issue #744: Requires authenticated user.
    """
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

    # Issue #3282: Carry author identity for shared-session message attribution
    author_id = current_user.get("user_id") if current_user else None

    # Process the chat message with a configurable timeout (Issue #1907).
    # Override via AUTOBOT_CHAT_TIMEOUT env var (seconds, float). Default: 30.0.
    chat_timeout = float(config.chat_timeout)
    try:
        response_data = await asyncio.wait_for(
            process_chat_message(
                message,
                chat_history_manager,
                llm_service,
                memory_interface,
                knowledge_base,
                config,
                request_id,
                author_id=author_id,
            ),
            timeout=chat_timeout,
        )
    except asyncio.TimeoutError:
        logger.error(
            "[%s] Chat message processing timed out after %.1fs",
            request_id,
            chat_timeout,
        )
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise InternalError("Chat message processing timed out. Please try again.")

    return JSONResponse(
        status_code=200,
        media_type="application/json; charset=utf-8",
        content={
            "success": True,
            "data": response_data.model_dump(),
            "message": "Message processed successfully",
            "request_id": request_id,
        },
    )


@router.post("/chat/stream", response_model=None)  # StreamingResponse — no Pydantic schema
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stream_message",
    error_code_prefix="CHAT",
)
async def stream_message(
    current_user: dict = Depends(get_current_user),
    message: ChatMessage = None,
    request: Request = None,
):
    """
    Stream chat response for real-time communication.

    Issue #744: Requires authenticated user.
    """
    request_id = generate_request_id()
    log_request_context(request, "stream_message", request_id)

    # Validate message content
    if not message.content or not message.content.strip():
        return JSONResponse(
            status_code=400,
            media_type="application/json; charset=utf-8",
            content={
                "error": "Message content cannot be empty",
                "request_id": request_id,
            },
        )

    # Get dependencies from request state
    chat_history_manager = get_chat_history_manager(request)
    llm_service = get_llm_service(request)

    # Return streaming response
    return await stream_chat_response(message, chat_history_manager, llm_service, request_id)


# ====================================================================
# Health Check and Status Endpoints
# ====================================================================


@router.get("/chat/health", response_model=ChatHealthData)
@with_error_handling(
    category=ErrorCategory.SERVICE_UNAVAILABLE,
    operation="chat_health_check",
    error_code_prefix="CHAT",
)
async def chat_health_check(
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Health check for chat service.

    Note: llm_service is lazily initialized on first chat request, so we report
    it as 'available' (can be initialized) rather than requiring it to exist.
    Only chat_history_manager is critical for the health check.

    Issue #744: Requires authenticated user.
    """
    chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
    llm_service = getattr(request.app.state, "llm_service", None)

    # chat_history_manager is critical - must be present
    chat_history_status = "healthy" if chat_history_manager else "unavailable"

    # llm_service is lazily initialized - report as "available" if not yet created
    llm_status = "healthy" if llm_service else "available"

    health_status = {
        "status": "healthy",
        "timestamp": utc_timestamp(),
        "components": {
            "chat_history_manager": chat_history_status,
            "llm_service": llm_status,
        },
    }

    # Only chat_history_manager is critical for health
    if chat_history_status != "healthy":
        health_status["status"] = "unavailable"
        return JSONResponse(
            status_code=503,
            media_type="application/json; charset=utf-8",
            content=health_status,
        )

    return JSONResponse(
        status_code=200,
        media_type="application/json; charset=utf-8",
        content=health_status,
    )


@router.get("/chat/stats", response_model=DataResponse[ChatStatsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="chat_statistics",
    error_code_prefix="CHAT",
)
async def chat_statistics(
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Get chat service statistics.

    Issue #744: Requires authenticated user.
    """
    request_id = generate_request_id()
    log_request_context(request, "chat_statistics", request_id)

    # Get dependencies from request state
    chat_history_manager = get_chat_history_manager(request)

    # Get basic statistics
    stats = await chat_history_manager.get_statistics()

    return create_chat_response(
        data=stats,
        message="Statistics retrieved successfully",
        request_id=request_id,
    )


# MISSING ENDPOINTS FOR FRONTEND COMPATIBILITY

# ====================================================================
# Chat Message Streaming Helpers (Issue #398 - Extract from long methods)
# ====================================================================


def _validate_chat_message(request_data: dict) -> str:
    """Validate and extract message from request data (Issue #398: extracted)."""
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
    return message


def _validate_chat_services(chat_history_manager, chat_workflow_manager) -> None:
    """Validate that chat services are available (Issue #398: extracted)."""
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


async def _stream_chat_workflow_messages(
    chat_workflow_manager, chat_id: str, message: str, context: dict, request_id: str
):
    """Stream chat workflow messages as SSE events (Issue #398: extracted)."""
    try:
        logger.debug("[%s] Starting stream for chat_id=%s", request_id, chat_id)
        evt = {"type": "start", "session_id": chat_id, "request_id": request_id}
        yield f"data: {json.dumps(evt)}\n\n"

        logger.debug("[%s] Processing message: %s...", request_id, message[:50])
        message_count = 0
        async for msg in chat_workflow_manager.process_message_stream(
            session_id=chat_id, message=message, context=context
        ):
            message_count += 1
            msg_data = msg.to_dict() if hasattr(msg, "to_dict") else msg
            yield f"data: {json.dumps(msg_data)}\n\n"

        logger.info("[%s] Stream complete: %d messages", request_id, message_count)
        yield f"data: {json.dumps({'type': 'end', 'request_id': request_id})}\n\n"

    except Exception as e:
        logger.error("[%s] Streaming error: %s", request_id, e, exc_info=True)
        evt = {"type": "error", "content": safe_http_detail(e, "stream_error"), "request_id": request_id}
        yield f"data: {json.dumps(evt)}\n\n"


def _create_streaming_response(generator):
    """Create a StreamingResponse with SSE headers (Issue #398: extracted)."""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_direct_response(
    chat_workflow_manager,
    chat_id: str,
    message: str,
    remember_choice: bool,
    request_id: str,
):
    """Stream direct response for approvals/denials (Issue #398: extracted)."""
    try:
        start_evt = {"type": "start", "session_id": chat_id, "request_id": request_id}
        yield f"data: {json.dumps(start_evt)}\n\n"

        async for msg in chat_workflow_manager.process_message_stream(
            session_id=chat_id,
            message=message,
            context={"remember_choice": remember_choice},
        ):
            msg_data = msg.to_dict() if hasattr(msg, "to_dict") else msg
            yield f"data: {json.dumps(msg_data)}\n\n"

        yield f"data: {json.dumps({'type': 'end', 'request_id': request_id})}\n\n"

    except Exception as e:
        logger.error("[%s] Direct response streaming error: %s", request_id, e, exc_info=True)
        error_data = {
            "type": "error",
            "content": "Error processing command approval",
            "request_id": request_id,
        }
        yield f"data: {json.dumps(error_data)}\n\n"


def _validate_workflow_manager(chat_workflow_manager) -> None:
    """Validate workflow manager is available (Issue #398: extracted)."""
    if not chat_workflow_manager:
        (
            AutoBotError,
            InternalError,
            ResourceNotFoundError,
            ValidationError,
            get_error_code,
        ) = get_exceptions_lazy()
        raise InternalError(
            "Workflow manager not available",
            details={"initialization_error": "Lazy initialization failed"},
        )


@router.post("/chats/{chat_id}/message", response_model=None)  # StreamingResponse — no Pydantic schema
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_chat_message_by_id",
    error_code_prefix="CHAT",
)
async def send_chat_message_by_id(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
    request_data: dict = Body(default={}),  # Issue #1302: was None, preventing context/knowledge
    request: Request = None,
    ownership: Dict = Depends(validate_chat_ownership),  # SECURITY: Validate ownership
):
    """
    Send message to specific chat by ID (Issue #398: refactored).

    Issue #744: Requires authenticated user.
    """
    request_id = generate_request_id()
    log_request_context(request, "send_chat_message_by_id", request_id)

    message = _validate_chat_message(request_data)

    chat_history_manager = get_chat_history_manager(request)
    chat_workflow_manager = await get_chat_workflow_manager(request)
    _validate_chat_services(chat_history_manager, chat_workflow_manager)

    # Issue #1325: Inject language into context for system prompt resolution
    # Issue #8993: Inject thinking mode parameters into context
    context = request_data.get("context", {})
    language = request_data.get("language")
    if language:
        context["language"] = language

    thinking_mode_enabled = request_data.get("thinking_mode_enabled")
    thinking_budget_tokens = request_data.get("thinking_budget_tokens")
    if thinking_mode_enabled is not None:
        context["thinking_mode_enabled"] = thinking_mode_enabled
    if thinking_budget_tokens is not None:
        context["thinking_budget_tokens"] = thinking_budget_tokens

    return _create_streaming_response(
        _stream_chat_workflow_messages(
            chat_workflow_manager,
            chat_id,
            message,
            context,
            request_id,
        )
    )


async def _stream_graph_resume(
    chat_workflow_manager,
    chat_id: str,
    decision: dict,
    request_id: str,
):
    """Stream graph resume after command approval interrupt (#1043)."""
    try:
        evt = {"type": "start", "session_id": chat_id, "request_id": request_id}
        yield f"data: {json.dumps(evt)}\n\n"

        async for msg in chat_workflow_manager.resume_graph(session_id=chat_id, decision=decision):
            msg_data = msg.to_dict() if hasattr(msg, "to_dict") else msg
            yield f"data: {json.dumps(msg_data)}\n\n"

        yield (f"data: {json.dumps({'type': 'end', 'request_id': request_id})}\n\n")

    except Exception as e:
        logger.error("[%s] Graph resume error: %s", request_id, e, exc_info=True)
        evt = {
            "type": "error",
            "content": "An internal error occurred",
            "request_id": request_id,
        }
        yield f"data: {json.dumps(evt)}\n\n"


@router.post("/chats/{chat_id}/resume", response_model=None)  # StreamingResponse — no Pydantic schema
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_chat_graph",
    error_code_prefix="CHAT",
)
async def resume_chat_graph(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
    request_data: dict = Body(default={}),
    request: Request = None,
    ownership: Dict = Depends(validate_chat_ownership),
):
    """Resume a paused chat graph after command approval (#1043).

    The graph pauses via LangGraph interrupt when a command needs
    approval. This endpoint resumes it with the user's decision.

    Body:
        approved (bool): Whether the command was approved
        reason (str, optional): Reason for denial
    """
    request_id = generate_request_id()
    log_request_context(request, "resume_chat_graph", request_id)

    chat_workflow_manager = await get_chat_workflow_manager(request)
    _validate_workflow_manager(chat_workflow_manager)

    decision = {
        "approved": request_data.get("approved", False),
        "reason": request_data.get("reason", ""),
    }

    return _create_streaming_response(
        _stream_graph_resume(
            chat_workflow_manager,
            chat_id,
            decision,
            request_id,
        )
    )


async def merge_messages(existing: List[Dict], new: List[Dict]) -> List[Dict]:
    """
    Merge message lists with deduplication to prevent race conditions.
    Issue #281: Refactored from 159 lines to use extracted helper methods.

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
    # Build set of new message signatures (Issue #281: uses helper)
    new_sigs = {_get_message_signature(msg) for msg in new}

    # Track new messages by ID for update detection
    new_by_id = {}
    for msg in new:
        msg_id = msg.get("id") or msg.get("messageId")
        if msg_id:
            new_by_id[msg_id] = msg

    # Filter preserved messages (Issue #281: uses helper)
    preserved = _filter_preserved_messages(existing, new, new_sigs, new_by_id)

    # Combine: preserved messages + new messages
    merged = preserved + new

    # Process streaming groups (Issue #281: uses helper)
    final_merged = _process_streaming_groups(merged)

    # Sort by timestamp to maintain chronological order
    final_merged.sort(key=lambda m: m.get("timestamp", ""))

    logger.debug(
        f"Merged messages: {len(existing)} existing + {len(new)} new = "
        f"{len(final_merged)} total (deduped from {len(merged)})"
    )

    return final_merged


async def _merge_chat_messages(
    chat_history_manager, chat_id: str, new_messages: List[Dict], request_id: str
) -> List[Dict]:
    """Merge new messages with existing to preserve backend-added ones (Issue #398: extracted).

    Issue #1797: Granular exception mapping for session load failures.
    """
    try:
        existing_messages = await chat_history_manager.load_session(chat_id)
        merged_messages = await merge_messages(existing_messages, new_messages)
        logger.info(
            "[%s] Merged %d existing + %d new = %d total messages",
            request_id,
            len(existing_messages),
            len(new_messages),
            len(merged_messages),
        )
        return merged_messages
    except FileNotFoundError:
        logger.warning(
            "[%s] Session file not found for %s, using new messages",
            request_id,
            chat_id,
        )
        return new_messages
    except PermissionError:
        logger.warning(
            "[%s] Unable to access chat session %s, using new messages",
            request_id,
            chat_id,
        )
        return new_messages
    except ValueError:
        logger.warning(
            "[%s] Chat session data is corrupted for %s, using new messages",
            request_id,
            chat_id,
        )
        return new_messages
    except Exception as merge_error:
        logger.warning(
            "[%s] Message merge failed, using new messages only: %s",
            request_id,
            merge_error,
        )
        return new_messages


@router.post("/chats/{chat_id}/save", response_model=DataResponse[ChatSaveData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_chat_by_id",
    error_code_prefix="CHAT",
)
async def save_chat_by_id(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
    request_data: dict = None,
    request: Request = None,
    ownership: Dict = Depends(validate_chat_ownership),  # SECURITY: Validate ownership
):
    """
    Save chat session by ID (Issue #398: refactored).

    Issue #744: Requires authenticated user.
    """
    request_id = generate_request_id()
    log_request_context(request, "save_chat_by_id", request_id)

    chat_history_manager = get_chat_history_manager(request)
    if not chat_history_manager:
        return create_error_response(
            error_code="SERVICE_UNAVAILABLE",
            message="Chat history service not available",
            request_id=request_id,
            status_code=503,
        )

    save_data = request_data.get("data", {})
    merged_messages = await _merge_chat_messages(
        chat_history_manager, chat_id, save_data.get("messages", []), request_id
    )

    result = await chat_history_manager.save_session(
        session_id=chat_id, messages=merged_messages, name=save_data.get("name", "")
    )

    return JSONResponse(
        status_code=200,
        media_type="application/json; charset=utf-8",
        content={
            "success": True,
            "data": result,
            "message": "Chat saved successfully",
            "request_id": request_id,
        },
    )


@router.delete("/chats/{chat_id}", response_model=DataResponse[ChatDeleteData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_chat_by_id",
    error_code_prefix="CHAT",
)
async def delete_chat_by_id(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
    request: Request = None,
    ownership: Dict = Depends(validate_chat_ownership),  # SECURITY: Validate ownership
):
    """
    Delete chat session by ID (frontend compatibility endpoint).

    Issue #744: Requires authenticated user.
    """
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
        media_type="application/json; charset=utf-8",
        content={
            "success": True,
            "data": {"session_id": chat_id, "deleted": result},
            "message": "Chat deleted successfully",
            "request_id": request_id,
        },
    )


@router.post("/chat/direct", response_model=None)  # StreamingResponse — no Pydantic schema
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_direct_chat_response",
    error_code_prefix="CHAT",
)
async def send_direct_chat_response(
    current_user: dict = Depends(get_current_user),
    request: Request = None,
    message: str = Body(...),
    chat_id: str = Body(...),
    remember_choice: bool = Body(default=False),
):
    """
    Send direct user response to chat (Issue #398: refactored).

    Issue #744: Requires authenticated user.
    """
    request_id = generate_request_id()
    log_request_context(request, "send_direct_response", request_id)

    chat_workflow_manager = await get_chat_workflow_manager(request)
    _validate_workflow_manager(chat_workflow_manager)

    return _create_streaming_response(
        _stream_direct_response(chat_workflow_manager, chat_id, message, remember_choice, request_id)
    )


# ====================================================================
# Enhanced Chat Functions with AI Stack Integration (Issue #708 consolidation)
# ====================================================================


async def _store_enhanced_user_message(
    message: EnhancedChatMessage,
    session_id: str,
    chat_history_manager,
) -> str:
    """Store user message and log event for enhanced chat."""
    user_message_id = str(uuid4())
    user_message_data = {
        "id": user_message_id,
        "content": message.content,
        "role": message.role,
        "timestamp": utc_timestamp(),
        "metadata": {
            **(message.metadata or {}),
            "ai_stack_enabled": message.use_ai_stack,
        },
        "session_id": session_id,
    }

    if hasattr(chat_history_manager, "add_messages_batch"):
        # #6744: was add_message(session_id, dict) — wrong-signature silent no-op.
        await chat_history_manager.add_messages_batch(session_id, [_to_persisted_message(user_message_data, "message")])

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


async def _get_enhanced_chat_context(
    message: EnhancedChatMessage,
    session_id: str,
    chat_history_manager,
) -> list:
    """Retrieve chat context from history for enhanced chat."""
    chat_context = []
    if hasattr(chat_history_manager, "get_session_messages"):
        try:
            model_name = message.metadata.get("model") if message.metadata else None
            recent_messages = await chat_history_manager.get_session_messages(session_id, model_name=model_name)
            chat_context = recent_messages or []
            logger.info(
                "Retrieved %s messages for model %s",
                len(chat_context),
                model_name or "default",
            )
        except Exception as e:
            logger.warning("Could not retrieve chat context: %s", e)

    return chat_context


async def _enhance_with_knowledge_base(
    message: EnhancedChatMessage,
    knowledge_base,
) -> tuple:
    """Enhance context with knowledge base search."""
    enhanced_context = None
    knowledge_sources = []

    if message.use_knowledge_base and knowledge_base:
        try:
            kb_results = await knowledge_base.search(query=message.content, top_k=5)
            if kb_results:
                knowledge_sources = kb_results
                kb_summary = "\n".join([f"- {item.get('content', '')[:300]}..." for item in kb_results[:3]])
                enhanced_context = f"Relevant knowledge context:\n{kb_summary}"
                logger.info("Enhanced context with %s KB results", len(kb_results))
        except Exception as e:
            logger.warning("Knowledge base context enhancement failed: %s", e)

    return enhanced_context, knowledge_sources


def _get_ai_stack_message_limit(chat_history_manager, model_name: str | None) -> int:
    """Helper for _generate_ai_stack_chat_response. Ref: #1088."""
    context_manager = getattr(chat_history_manager, "context_manager", None)
    if context_manager:
        limit = context_manager.get_message_limit(model_name)
        logger.info(
            "Using %s messages for LLM context (model: %s)",
            limit,
            model_name or "default",
        )
        return limit
    logger.warning("Context manager not available, using default limit")
    return 20


async def _generate_ai_stack_chat_response(
    message: EnhancedChatMessage,
    chat_context: list,
    enhanced_context: str | None,
    chat_history_manager,
    preferences: ChatPreferences | None,
) -> Metadata:
    """Generate response using AI Stack."""
    try:
        ai_client = await get_ai_stack_client()
        model_name = message.metadata.get("model") if message.metadata else None
        message_limit = _get_ai_stack_message_limit(chat_history_manager, model_name)

        formatted_history = [
            {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            for msg in chat_context[-message_limit:]
        ]

        ai_stack_response = await ai_client.chat_message(
            message=message.content,
            context=enhanced_context,
            chat_history=formatted_history,
        )

        return {
            "content": ai_stack_response.get("response", ai_stack_response.get("content", "")),
            "role": "assistant",
            "metadata": {
                "source": "ai_stack",
                "agent_used": ai_stack_response.get("agent", "chat"),
                "confidence": ai_stack_response.get("confidence", 0.8),
                "reasoning": (
                    ai_stack_response.get("reasoning") if preferences and preferences.include_reasoning else None
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


def _create_basic_chat_response() -> Metadata:
    """Create basic response without AI Stack."""
    return {
        "content": (
            "Thank you for your message. I'm currently running in basic mode " "without enhanced AI capabilities."
        ),
        "role": "assistant",
        "metadata": {"source": "basic_chat"},
    }


def _enhance_response_with_sources(
    ai_response: Metadata,
    knowledge_sources: list,
    include_sources: bool,
) -> None:
    """Add knowledge sources to response metadata."""
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


async def _store_enhanced_ai_response(
    ai_response: Metadata,
    session_id: str,
    request_id: str,
    chat_history_manager,
) -> str:
    """Store AI response and log event for enhanced chat."""
    ai_message_id = str(uuid4())
    ai_message_data = {
        "id": ai_message_id,
        "content": ai_response.get("content", ""),
        "role": "assistant",
        "timestamp": utc_timestamp(),
        "metadata": ai_response.get("metadata", {}),
        "session_id": session_id,
    }

    if hasattr(chat_history_manager, "add_messages_batch"):
        # #6744: was add_message(session_id, dict) — wrong-signature silent no-op.
        await chat_history_manager.add_messages_batch(session_id, [_to_persisted_message(ai_message_data, "response")])

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


async def _execute_enhanced_chat_pipeline(
    message: EnhancedChatMessage,
    session_id: str,
    chat_history_manager,
    knowledge_base,
    request_id: str,
    preferences: ChatPreferences | None,
) -> EnhancedChatData:
    """Helper for process_enhanced_chat_message. Ref: #1088, #6502 (typed return).

    Runs the full enhanced chat pipeline: store user message, retrieve context,
    enrich with knowledge base, generate AI response, attach sources, store response,
    and return the final result.
    """
    await _store_enhanced_user_message(message, session_id, chat_history_manager)

    chat_context = await _get_enhanced_chat_context(message, session_id, chat_history_manager)

    enhanced_context, knowledge_sources = await _enhance_with_knowledge_base(message, knowledge_base)

    if message.use_ai_stack:
        ai_response = await _generate_ai_stack_chat_response(
            message,
            chat_context,
            enhanced_context,
            chat_history_manager,
            preferences,
        )
        if ai_response.get("metadata", {}).get("source") == "ai_stack":
            logger.info("AI Stack response generated successfully")
    else:
        ai_response = _create_basic_chat_response()

    _enhance_response_with_sources(ai_response, knowledge_sources, message.include_sources)

    ai_message_id = await _store_enhanced_ai_response(ai_response, session_id, request_id, chat_history_manager)

    return EnhancedChatData(
        content=ai_response.get("content", ""),
        role="assistant",
        session_id=session_id,
        message_id=ai_message_id,
        timestamp=utc_timestamp(),
        metadata=ai_response.get("metadata", {}),
        knowledge_sources=knowledge_sources if message.include_sources else None,
    )


async def process_enhanced_chat_message(
    message: EnhancedChatMessage,
    chat_history_manager,
    knowledge_base,
    config: Metadata,
    request_id: str,
    preferences: ChatPreferences | None = None,
) -> EnhancedChatData:
    """
    Process a chat message with AI Stack enhanced capabilities.

    This function combines local knowledge base search with AI Stack's
    intelligent chat agents for superior conversational experience.
    """
    try:
        if not validate_chat_session_id(message.session_id):
            raise HTTPException(status_code=422, detail="Invalid session ID format")

        session_id = message.session_id

        return await _execute_enhanced_chat_pipeline(
            message,
            session_id,
            chat_history_manager,
            knowledge_base,
            request_id,
            preferences,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing enhanced chat message: %s", e)
        raise HTTPException(status_code=500, detail="Failed to process enhanced chat message")


# ====================================================================
# Enhanced Chat Streaming Helpers (Issue #708 consolidation)
# ====================================================================


def _format_sse_event(data: dict) -> str:
    """Format data as Server-Sent Event."""
    return f"data: {json.dumps(data)}\n\n"


async def _stream_ai_stack_response(
    message: EnhancedChatMessage,
    session_id: str,
    chat_history_manager,
    request_id: str,
    preferences: ChatPreferences | None,
):
    """Stream AI Stack enhanced response in chunks."""
    try:
        response_data = await process_enhanced_chat_message(
            message, chat_history_manager, None, {}, request_id, preferences
        )

        content = response_data.content or ""
        chunk_size = 50

        for i in range(0, len(content), chunk_size):
            chunk = content[i : i + chunk_size]
            yield _format_sse_event(
                {
                    "type": "chunk",
                    "content": chunk,
                    "session_id": session_id,
                    "timestamp": utc_timestamp(),
                }
            )
            await asyncio.sleep(TimingConstants.STREAMING_CHUNK_DELAY)

        yield _format_sse_event(
            {
                "type": "metadata",
                "metadata": response_data.metadata or {},
                "sources": response_data.knowledge_sources,
                "session_id": session_id,
            }
        )

    except Exception as e:
        logger.error("Enhanced streaming error: %s", e)
        yield _format_sse_event(
            {
                "type": "error",
                "content": "Error generating enhanced response",
                "timestamp": utc_timestamp(),
            }
        )


def _stream_enhanced_fallback_response(session_id: str):
    """Stream fallback response when AI Stack not enabled."""
    fallback_msg = "Thank you for your message. Enhanced streaming requires AI Stack " "integration."
    return _format_sse_event(
        {
            "type": "chunk",
            "content": fallback_msg,
            "session_id": session_id,
            "timestamp": utc_timestamp(),
        }
    )


async def _generate_enhanced_stream(
    message: EnhancedChatMessage,
    request: Request,
    request_id: str,
    preferences: ChatPreferences | None,
):
    """Generate streaming response with AI Stack integration."""
    try:
        session_id = message.session_id
        yield _format_sse_event({"type": "start", "session_id": session_id, "enhanced": True})

        chat_history_manager = get_chat_history_manager(request)

        if message.use_ai_stack:
            async for event in _stream_ai_stack_response(
                message, session_id, chat_history_manager, request_id, preferences
            ):
                yield event
        else:
            yield _stream_enhanced_fallback_response(session_id)

        yield _format_sse_event({"type": "end"})

    except Exception as e:
        logger.error("Streaming error: %s", e)
        yield _format_sse_event(
            {
                "type": "error",
                "content": "Error in enhanced streaming",
                "timestamp": utc_timestamp(),
            }
        )


# ====================================================================
# Enhanced Chat API Endpoints (Issue #708 consolidation)
# ====================================================================


@router.post("/enhanced", response_model=DataResponse[EnhancedChatData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_chat",
    error_code_prefix="CHAT",
)
async def enhanced_chat(
    current_user: dict = Depends(get_current_user),
    message: EnhancedChatMessage = None,
    request: Request = None,
    preferences: ChatPreferences | None = None,
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

    Issue #744: Requires authenticated user.
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

        return create_chat_response(
            response_data.model_dump(),
            "Enhanced chat message processed successfully",
            request_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Enhanced chat error: %s", request_id, e)
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message="Operation failed",
            request_id=request_id,
            status_code=500,
        )


@router.post("/stream-enhanced", response_model=None)  # StreamingResponse — no Pydantic schema
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stream_enhanced_chat",
    error_code_prefix="CHAT",
)
async def stream_enhanced_chat(
    current_user: dict = Depends(get_current_user),
    message: EnhancedChatMessage = None,
    request: Request = None,
    preferences: ChatPreferences | None = None,
):
    """
    Stream enhanced chat response for real-time communication.

    Provides real-time streaming of AI Stack enhanced responses
    with knowledge base integration.

    Issue #744: Requires authenticated user.
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


@router.get("/health-enhanced", response_model=EnhancedChatHealthData)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_chat_health_check",
    error_code_prefix="CHAT",
)
async def enhanced_chat_health_check(
    current_user: dict = Depends(get_current_user),
):
    """
    Health check for enhanced chat service including AI Stack connectivity.

    Issue #744: Requires authenticated user.
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": utc_timestamp(),
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
            status_code=200 if overall_healthy else 503,
            media_type="application/json; charset=utf-8",
            content=health_status,
        )

    except Exception as e:
        logger.error("Enhanced chat health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            media_type="application/json; charset=utf-8",
            content={
                "status": "unhealthy",
                "error": "Internal server error",
                "timestamp": utc_timestamp(),
            },
        )


@router.get("/capabilities", response_model=DataResponse[EnhancedChatCapabilitiesData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_enhanced_chat_capabilities",
    error_code_prefix="CHAT",
)
async def get_enhanced_chat_capabilities(
    current_user: dict = Depends(get_current_user),
):
    """
    Get enhanced chat capabilities and available features.

    Issue #744: Requires authenticated user.
    """
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
            "supported_languages": ["en"],
            "max_message_length": 50000,
            "context_window": 10,
        }

        return create_chat_response(capabilities, "Enhanced chat capabilities retrieved successfully")

    except Exception as e:
        logger.warning("Failed to get full capabilities: %s", e)
        # Return basic capabilities as fallback
        return create_chat_response(
            {
                "enhanced_chat": True,
                "ai_stack_integration": False,
                "knowledge_base_integration": True,
                "error": ("Partial capabilities due to" " AI Stack unavailability"),
            }
        )


# ====================================================================
# Issue #1328: Translation Shortcut Endpoint
# ====================================================================


@router.post("/translate", response_model=TranslateData)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="translate_text",
    error_code_prefix="TRANSLATE",
)
async def translate_text(
    body: TranslateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Translate text via TranslationAgent (#1328)."""
    from agents.base_agent import AgentRequest
    from agents.translation_agent import get_translation_agent

    agent = get_translation_agent()
    req = AgentRequest(
        request_id=str(uuid4()),
        agent_type="translation",
        action="translate",
        payload={
            "text": body.text,
            "target_language": body.target_language,
            "source_language": (body.source_language or "auto-detect"),
        },
    )
    result = await agent.handle_translate(req)
    return JSONResponse(content=result, media_type="application/json; charset=utf-8")  # codeql[py/stack-trace-exposure]


@router.post("/detect-language", response_model=DetectLanguageData)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_language",
    error_code_prefix="TRANSLATE",
)
async def detect_language(
    body: DetectLanguageRequest,
    current_user: dict = Depends(get_current_user),
):
    """Detect language via TranslationAgent (#1328)."""
    from agents.base_agent import AgentRequest
    from agents.translation_agent import get_translation_agent

    agent = get_translation_agent()
    req = AgentRequest(
        request_id=str(uuid4()),
        agent_type="translation",
        action="detect_language",
        payload={"text": body.text},
    )
    result = await agent.handle_detect_language(req)
    return JSONResponse(content=result, media_type="application/json; charset=utf-8")  # codeql[py/stack-trace-exposure]


@router.post("/chat/summarize", response_model=DataResponse[Dict[str, Any]])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="summarize_conversation",
    error_code_prefix="CHAT_SUMMARIZE",
)
async def summarize_conversation(
    body: "ConversationSummarizeRequest",
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Summarize a range of conversation messages for context overflow protection (GH#9043).

    When a conversation approaches the model's context window limit, this endpoint
    generates a compact summary of the earliest messages to enable a rolling window
    approach without losing essential context.
    """
    from api.schemas_chat import ConversationSummarizeData

    request_id = generate_request_id()
    logger.info("[%s] Summarizing %d messages from session %s", request_id, len(body.message_ids), body.session_id)

    # Validate session ownership
    await validate_chat_ownership(body.session_id, request)

    # Get chat history manager and retrieve messages
    chat_history = get_chat_history_manager()
    all_messages = await chat_history.get_messages(body.session_id)

    # Filter to requested message IDs
    messages_to_summarize = [msg for msg in all_messages if msg.get("message_id") in body.message_ids]

    if not messages_to_summarize:
        raise HTTPException(status_code=404, detail="No messages found with the provided IDs")

    # Build prompt for summarization
    conversation_text = "\n\n".join(
        [f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}" for msg in messages_to_summarize]
    )

    summarization_prompt = f"""Summarize the following conversation segment concisely.
Preserve key context, decisions, and technical details that would be needed to continue the conversation naturally.

Target length: approximately {body.target_length or 500} tokens.

Conversation:
{conversation_text}

Summary:"""

    # Get LLM service and generate summary
    llm_service = get_llm_service(request)

    try:
        summary_response = await llm_service.generate_response(
            messages=[{"role": "user", "content": summarization_prompt}],
            model="gpt-4o-mini",  # Fast, cheap model for summarization
            max_tokens=body.target_length or 500,
            temperature=0.3,  # Lower temperature for focused summarization
        )

        summary_text = summary_response.get("content", "")
        summary_tokens = summary_response.get("usage", {}).get("total_tokens", 0)

    except Exception as e:
        logger.exception("[%s] Failed to generate summary", request_id)
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")

    result_data = ConversationSummarizeData(
        summary=summary_text,
        original_message_count=len(messages_to_summarize),
        summary_token_count=summary_tokens,
        timestamp=utc_timestamp(),
    )

    logger.info(
        "[%s] Generated summary: %d messages → %d tokens",
        request_id,
        result_data.original_message_count,
        result_data.summary_token_count or 0,
    )

    return DataResponse(data=result_data.model_dump())
