# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading a chat session's messages for ``GET /chat/sessions/{id}`` (#620, #21022).

One read path: the stored page, then the card of a stall question the paused graph is still waiting on, so a
person who reloaded while it was open sees it again.
"""

from typing import List

from autobot_shared.logging_manager import get_logger
from chat_workflow.stall_pending import with_pending_question
from exceptions import get_exceptions_lazy

logger = get_logger(__name__)


async def _fetch_or_raise(chat_history_manager, session_id: str, limit: int, offset: int = 0) -> List:
    """
    Fetch session messages and raise ResourceNotFoundError if session not found.

    Issue #620.
    Issue #1797: Granular exception mapping for session load failures.

    Args:
        chat_history_manager: Chat history manager instance
        session_id: Session ID to fetch messages for
        limit: Maximum messages to return
        offset: Messages to skip, counting back from the newest (#15186)

    Returns:
        List of messages

    Raises:
        ResourceNotFoundError: If session does not exist
        ValidationError: If session data is corrupted (ValueError)
        InternalError: If session cannot be accessed (PermissionError)
    """
    (
        AutoBotError,
        InternalError,
        ResourceNotFoundError,
        ValidationError,
        get_error_code,
    ) = get_exceptions_lazy()

    try:
        messages = await chat_history_manager.get_session_messages(session_id, limit=limit, offset=offset)
    except FileNotFoundError:
        logger.warning("Session file not found for session %s", session_id)
        raise ResourceNotFoundError(f"Session {session_id} not found")
    except PermissionError:
        logger.error("Permission denied accessing session %s", session_id)
        raise InternalError("Unable to access chat session")
    except ValueError as exc:
        logger.error("Corrupted session data for session %s: %s", session_id, exc)
        raise ValidationError("Chat session data is corrupted")

    if messages is None:
        raise ResourceNotFoundError(f"Session {session_id} not found")

    return messages


async def fetch_session_messages(request, chat_history_manager, session_id: str, limit: int, offset: int = 0) -> List:
    """The session's stored messages (see ``_fetch_or_raise``) plus the open stall question's card, if any."""
    messages = await _fetch_or_raise(chat_history_manager, session_id, limit, offset)
    return await with_pending_question(request, session_id, messages)
