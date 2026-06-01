# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Thinking mode preferences API for chat sessions (#8993).

Provides endpoints to get and set per-conversation thinking mode preferences
for reasoning models like Claude 3.7+ extended thinking and DeepSeek R1.
"""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas_chat import ThinkingPreferences, ThinkingPreferencesData
from api.schemas_common import DataResponse
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from security.session_ownership import validate_session_ownership
from utils.chat_utils import get_chat_history_manager
from utils.response_helpers import create_success_response

router = APIRouter(tags=["chat-thinking"])
logger = get_logger(__name__)


@router.get(
    "/sessions/{session_id}/thinking-preferences",
    response_model=DataResponse[ThinkingPreferencesData],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_thinking_preferences",
    error_code_prefix="CHAT_THINKING",
)
async def get_thinking_preferences(
    session_id: str,
    current_user: Dict = Depends(get_current_user),
    request: Request = None,
    ownership: Dict = Depends(validate_session_ownership),
):
    """Get thinking mode preferences for a conversation (#8993).

    Returns the per-conversation settings for extended thinking mode,
    including whether it's enabled and the thinking budget in tokens.
    """
    chat_history_manager = get_chat_history_manager(request)
    if not chat_history_manager:
        raise HTTPException(status_code=500, detail="Chat history manager not available")

    # Load session to get metadata
    session_data = await chat_history_manager.get_session(session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Extract thinking preferences from session metadata
    metadata = session_data.get("metadata", {})
    thinking_prefs = metadata.get("thinking_preferences", {})

    return create_success_response(
        data={
            "session_id": session_id,
            "enabled": thinking_prefs.get("enabled", False),
            "budget_tokens": thinking_prefs.get("budget_tokens", 10000),
        },
        message="Thinking preferences retrieved",
    )


@router.put(
    "/sessions/{session_id}/thinking-preferences",
    response_model=DataResponse[ThinkingPreferencesData],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_thinking_preferences",
    error_code_prefix="CHAT_THINKING",
)
async def update_thinking_preferences(
    session_id: str,
    preferences: ThinkingPreferences,
    current_user: Dict = Depends(get_current_user),
    request: Request = None,
    ownership: Dict = Depends(validate_session_ownership),
):
    """Update thinking mode preferences for a conversation (#8993).

    Allows users to enable/disable extended thinking mode and set the
    thinking budget (1k-128k tokens) per conversation.
    """
    chat_history_manager = get_chat_history_manager(request)
    if not chat_history_manager:
        raise HTTPException(status_code=500, detail="Chat history manager not available")

    # Load current session data
    session_data = await chat_history_manager.get_session(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Update thinking preferences in metadata
    metadata = session_data.get("metadata", {})
    metadata["thinking_preferences"] = {
        "enabled": preferences.enabled,
        "budget_tokens": preferences.budget_tokens,
    }

    # Save updated session
    await chat_history_manager.update_session_metadata(session_id, metadata)

    logger.info(
        "Updated thinking preferences for session %s: enabled=%s, budget=%d",
        session_id,
        preferences.enabled,
        preferences.budget_tokens,
    )

    return create_success_response(
        data={
            "session_id": session_id,
            "enabled": preferences.enabled,
            "budget_tokens": preferences.budget_tokens,
        },
        message="Thinking preferences updated",
    )
