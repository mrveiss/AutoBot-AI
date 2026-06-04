# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration layer for context overflow protection in chat history. Issue #9043.

Provides helper functions to integrate context overflow protection
into the chat message flow without tightly coupling to specific endpoints.
"""

import os
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger

from .context_overflow import ContextOverflowProtection

logger = get_logger(__name__)

# Environment variable for default protection mode
# Values: "auto", "warn_only", "disabled"
_DEFAULT_MODE = os.environ.get("AUTOBOT_CONTEXT_OVERFLOW_MODE", "auto")

# Singleton instance
_protection_instance: Optional[ContextOverflowProtection] = None


def get_overflow_protection() -> ContextOverflowProtection:
    """Get the shared ContextOverflowProtection instance (lazy init).

    Returns:
        Shared protection instance.
    """
    global _protection_instance
    if _protection_instance is None:
        _protection_instance = ContextOverflowProtection()
        logger.info(
            "✅ Context overflow protection initialized (default mode: %s)",
            _DEFAULT_MODE,
        )
    return _protection_instance


async def handle_message_completion(
    session_id: str,
    model_name: str,
    llm_response: Any,
    messages: Optional[List[Dict[str, Any]]] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle completion response and check for context overflow.

    Call this after each LLM completion to track tokens and check thresholds.

    Args:
        session_id: Chat session identifier.
        model_name: Active LLM model name.
        llm_response: LLMResponse object with usage field.
        messages: Optional full message history (needed for summarization).
        mode: Optional override for protection mode (auto/warn_only/disabled).

    Returns:
        Status dict with:
            - warning_triggered: bool
            - summary_created: bool
            - summary_text: str (if summary created)
            - current_fill_percentage: float
            - total_tokens: int
            - context_limit: int

    Example:
        >>> response = await llm_gateway.chat_completion(...)
        >>> status = await handle_message_completion(
        ...     session_id="abc-123",
        ...     model_name="gpt-4",
        ...     llm_response=response,
        ...     messages=all_messages,
        ... )
        >>> if status["warning_triggered"]:
        ...     # Emit warning event to frontend
        ...     await emit_context_warning(session_id, status)
        >>> if status["summary_created"]:
        ...     # Inject summary into conversation
        ...     await inject_summary_message(session_id, status["summary_text"])
    """
    protection = get_overflow_protection()

    # Extract usage from LLMResponse
    usage = None
    if hasattr(llm_response, "usage") and llm_response.usage:
        usage = llm_response.usage

    # Use configured mode if not overridden
    effective_mode = mode or _DEFAULT_MODE

    # Check and apply protection
    status = await protection.check_and_protect(
        session_id=session_id,
        model_name=model_name,
        usage=usage,
        mode=effective_mode,
        messages=messages,
    )

    # Log warnings
    if status["warning_triggered"]:
        logger.warning(
            "Context overflow warning for session %s: %.1f%% full (%d/%d tokens)",
            session_id,
            status["current_fill_percentage"] * 100,
            status["total_tokens"],
            status["context_limit"],
        )

    if status["summary_created"]:
        logger.info(
            "Context auto-compressed for session %s: summary created",
            session_id,
        )

    return status


async def create_summary_message(summary_text: str) -> Dict[str, Any]:
    """Create a system message dict for injecting summary into conversation.

    Args:
        summary_text: The generated summary content.

    Returns:
        Message dict compatible with chat history format.

    Example:
        >>> summary_msg = await create_summary_message(status["summary_text"])
        >>> await chat_history.add_message(
        ...     sender="system",
        ...     text=summary_msg["text"],
        ...     message_type="system",
        ...     raw_data=summary_msg["metadata"],
        ... )
    """
    import time
    import uuid

    return {
        "id": str(uuid.uuid4()),
        "sender": "system",
        "text": summary_text,
        "messageType": "context_summary",
        "metadata": {
            "summarized_at": time.time(),
            "reason": "context_overflow_protection",
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sources": [],
    }


def get_protection_mode_from_config() -> str:
    """Get protection mode from environment configuration.

    Returns:
        One of: "auto", "warn_only", "disabled"
    """
    return _DEFAULT_MODE


def set_protection_mode(mode: str) -> None:
    """Set protection mode for the current process.

    Args:
        mode: One of "auto", "warn_only", "disabled"

    Raises:
        ValueError: If mode is invalid.
    """
    valid_modes = {"auto", "warn_only", "disabled"}
    if mode not in valid_modes:
        raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")

    global _DEFAULT_MODE
    _DEFAULT_MODE = mode
    logger.info("Context overflow protection mode set to: %s", mode)


__all__ = [
    "get_overflow_protection",
    "handle_message_completion",
    "create_summary_message",
    "get_protection_mode_from_config",
    "set_protection_mode",
]
