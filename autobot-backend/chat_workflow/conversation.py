# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Conversation history management for chat workflow.

The LLM context of a session is a projection of ``chat_sessions``, the one
system of record for conversation turns (#18293): read through
``ChatHistoryManager.load_session`` and cached under ``chat:conversation:{id}``.
This module writes no durable copy of a turn. The completed turn reaches
``chat_sessions`` through ``ChatWorkflowManager._persist_workflow_messages``
(and ``LLMHandlerMixin._save_to_chat_history`` for terminal interpretations).

It never reads the retired legacy transcripts: ownership of a legacy file cannot
be proven from current state, and an ownerless session id is granted to whoever
asks (``legacy_migration``), so serving one as context would hand another user's
conversation to a claimer. A session with no turns in ``chat_sessions`` starts
with no prior context until an approved #17038 backfill moves its legacy turns in.
"""

import asyncio
import json
from typing import Dict, List

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from autobot_shared.ssot_constants import REDIS_KEY
from autobot_shared.store_authority import system_of_record

from .models import WorkflowSession

logger = get_logger(__name__)

#: This module writes the chat:conversation:* LLM-context cache, a projection
#: of chat_sessions; the lookup fails loudly if that declaration ever goes away.
SYSTEM_OF_RECORD = system_of_record("chat_sessions")


class ConversationHandlerMixin:
    """Mixin for conversation history management."""

    def _get_conversation_key(self, session_id: str) -> str:
        """Generate Redis key for conversation history."""
        return f"{REDIS_KEY.CHAT_CONVERSATION_PREFIX}{session_id}"

    async def _try_redis_history(self, session_id: str) -> List[Dict[str, str]] | None:
        """Try to load conversation history from Redis (Issue #332 - extracted helper).

        Returns:
            History list if found, None if not found or error
        """
        if self.redis_client is None:
            return None

        key = self._get_conversation_key(session_id)
        try:
            history_json = await asyncio.wait_for(self.redis_client.get(key), timeout=config.timeout.redis_op)
            if history_json:
                logger.debug("Loaded conversation history from Redis for session %s", session_id)
                return json.loads(history_json)
        except asyncio.TimeoutError:
            logger.warning(
                "Redis get timeout after %.1fs for session %s, falling back to file",
                config.timeout.redis_op,
                session_id,
            )
        return None

    async def _project_from_chat_sessions(self, session_id: str) -> List[Dict[str, str]] | None:
        """The session's completed exchanges from chat_sessions, or None if it cannot be read.

        None (an unreadable session) is kept apart from ``[]`` (a session with no
        completed turns) so the first is logged as the error it is.
        """
        from chat_history import ChatHistoryManager
        from chat_history.turn_projection import LLM_CONTEXT_TURN_LIMIT, project_turn_pairs

        try:
            messages = await ChatHistoryManager().load_session(session_id)
        except (PermissionError, ValueError, OSError) as exc:
            logger.error("Cannot read chat session %s for LLM context: %s", session_id, exc)
            return None
        return project_turn_pairs(messages, LLM_CONTEXT_TURN_LIMIT)

    async def _load_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        """LLM context: the Redis cache, else projected from chat_sessions, else nothing (#18293)."""
        try:
            redis_history = await self._try_redis_history(session_id)
            if redis_history is not None:
                return redis_history

            history = await self._project_from_chat_sessions(session_id)
            if not history:
                return []  # unreadable, or no completed turns: never a legacy transcript

            if self.redis_client is not None:
                fire_and_forget(
                    self._save_conversation_history(session_id, history),
                    name="conversation-history-cache-refill",
                )
            return history

        except Exception as e:
            logger.error("Failed to load conversation history: %s", e)
            return []

    async def _save_conversation_history(self, session_id: str, history: List[Dict[str, str]]):
        """Save conversation history to Redis with TTL."""
        try:
            if self.redis_client is None:
                return

            key = self._get_conversation_key(session_id)
            history_json = json.dumps(history)

            # Save with 24-hour expiration and 2s timeout
            try:
                await asyncio.wait_for(
                    self.redis_client.set(key, history_json, ex=self.conversation_history_ttl),
                    timeout=2.0,
                )
                logger.debug("Saved conversation history for session %s to Redis", session_id)
            except asyncio.TimeoutError:
                logger.warning(
                    "Redis set timeout after 2s for session %s - data may not be cached",
                    session_id,
                )

        except Exception as e:
            logger.error("Failed to save conversation history to Redis: %s", e)

    def _handle_existing_user_entry(
        self,
        last_entry: Dict[str, str],
        llm_response: str,
        session_id: str,
    ) -> None:
        """Handle case where last entry has same user message.

        Issue #620.

        Args:
            last_entry: The last entry in conversation history
            llm_response: New LLM response to merge
            session_id: Session identifier for logging
        """
        existing_response = last_entry.get("assistant", "")
        if not existing_response:
            last_entry["assistant"] = llm_response
            logger.debug(
                "[_persist_conversation] Filled placeholder entry for session %s",
                session_id,
            )
        elif llm_response not in existing_response:
            last_entry["assistant"] = f"{existing_response}\n\n{llm_response}"
            logger.debug(
                "[_persist_conversation] Appended to existing entry for session %s (deduplication)",
                session_id,
            )
        else:
            logger.debug(
                "[_persist_conversation] Skipped duplicate response for session %s",
                session_id,
            )

    def _update_conversation_history(
        self,
        session: WorkflowSession,
        message: str,
        llm_response: str,
        session_id: str,
    ) -> None:
        """Update session conversation history with deduplication.

        Issue #620.

        Args:
            session: Workflow session object
            message: User message
            llm_response: LLM response
            session_id: Session identifier for logging
        """
        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                self._handle_existing_user_entry(last_entry, llm_response, session_id)
            else:
                session.conversation_history.append({"user": message, "assistant": llm_response})
        else:
            session.conversation_history.append({"user": message, "assistant": llm_response})

        if len(session.conversation_history) > 10:
            session.conversation_history = session.conversation_history[-10:]

    async def _persist_conversation(
        self,
        session_id: str,
        session: WorkflowSession,
        message: str,
        llm_response: str,
    ):
        """Record a completed exchange in the session's LLM context and its cache.

        Issue #620. #18293: this writes no durable copy of the turn -- the turn's
        one durable home is chat_sessions, written by the caller's
        ``_persist_workflow_messages`` (or ``_save_to_chat_history``). The
        in-process history and the ``chat:conversation:*`` cache updated here
        are projections of it, re-derived by ``_load_conversation_history``.

        Args:
            session_id: Session identifier
            session: Workflow session object
            message: User message
            llm_response: LLM response
        """
        self._update_conversation_history(session, message, llm_response, session_id)

        await self._save_conversation_history(session_id, session.conversation_history)

    def _register_user_message_in_history(self, session: WorkflowSession, message: str) -> None:
        """
        Register user message in session history immediately (before LLM call).

        Issue #715: Fixes race condition where concurrent messages don't see
        each other's context. By adding the user message to conversation_history
        immediately (with empty assistant placeholder), subsequent concurrent
        messages will at least see the user part of previous messages in context.

        This is called before the LLM generates a response. The placeholder
        assistant response will be updated by _persist_conversation once the
        actual response is ready.

        Args:
            session: Workflow session object
            message: User message to register
        """
        # Check if this message is already registered (deduplication)
        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                # Already registered (possibly from a retry or rapid double-send)
                logger.debug("[_register_user_message] Message already in history, skipping")
                return

        # Add user message with empty placeholder for assistant response
        # The placeholder will be filled by _persist_conversation
        session.conversation_history.append(
            {
                "user": message,
                "assistant": "",  # Placeholder, will be updated when response is ready
            }
        )
        logger.debug(
            "[_register_user_message] Registered user message in history " "(history length: %d)",
            len(session.conversation_history),
        )
