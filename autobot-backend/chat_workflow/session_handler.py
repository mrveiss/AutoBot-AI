# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session management for chat workflow.

Handles session creation, initialization, cleanup, and session information retrieval.
"""

import time
from typing import Any, Dict

from async_chat_workflow import AsyncChatWorkflow
from autobot_shared.error_boundaries import error_boundary
from autobot_shared.logging_manager import get_logger
from conversation_context import ConversationContext, ConversationContextAnalyzer
from conversation_safety import ConversationSafetyGuards, SafetyCheckResult
from intent_classifier import ConversationIntent, IntentClassification, IntentClassifier
from middleware.base import HookContext
from middleware.hooks import HookPoint
from middleware.manager import get_extension_manager

from .models import WorkflowSession

logger = get_logger(__name__)


class SessionHandlerMixin:
    """Mixin for session management."""

    @error_boundary(component="chat_workflow_manager", function="get_or_create_session")
    async def get_or_create_session(self, session_id: str) -> WorkflowSession:
        """Get existing session or create new one, loading history from Redis."""
        async with self._lock:
            if session_id not in self.sessions:
                # Create new workflow for this session
                workflow = AsyncChatWorkflow()

                # Load conversation history from Redis
                conversation_history = await self._load_conversation_history(session_id)

                self.sessions[session_id] = WorkflowSession(
                    session_id=session_id,
                    workflow=workflow,
                    conversation_history=conversation_history,
                )

                logger.info(
                    "Created new workflow session: %s with %d messages from history",
                    session_id,
                    len(conversation_history),
                )

            # Update last activity
            self.sessions[session_id].last_activity = time.time()
            return self.sessions[session_id]

    def _determine_exit_intent(self, classification: IntentClassification, safety_check: SafetyCheckResult) -> bool:
        """Determine if user wants to exit conversation (Issue #332 - extracted helper).

        Returns:
            True if user wants to exit and it's safe to do so
        """
        if classification.intent != ConversationIntent.END:
            logger.debug(
                "Intent classified as: %s (confidence: %.2f)",
                classification.intent.value,
                classification.confidence,
            )
            return False

        if safety_check.is_safe_to_end:
            logger.info(
                "User wants to exit conversation - Intent: %s, Confidence: %.2f, Reason: %s",
                classification.intent.value,
                classification.confidence,
                classification.reasoning,
            )
            return True

        # Safety guard overrides END intent
        logger.info(
            "Exit intent detected but blocked by safety guards - %s",
            safety_check.reason,
        )
        logger.info("Violated rules: %s", ", ".join(safety_check.violated_rules))
        return False

    async def _get_or_create_terminal_session(self, session_id: str) -> str | None:
        """Get or create terminal session for conversation (Issue #332 - extracted helper).

        Returns:
            Terminal session ID or None if unavailable
        """
        if not self.terminal_tool or not session_id:
            return None

        # Return existing session
        if session_id in self.terminal_tool.active_sessions:
            terminal_session_id = self.terminal_tool.active_sessions.get(session_id)
            logger.info(
                "Terminal session ID for conversation %s: %s",
                session_id,
                terminal_session_id,
            )
            return terminal_session_id

        # Create new terminal session
        session_result = await self.terminal_tool.create_session(
            agent_id=f"chat_agent_{session_id}",
            conversation_id=session_id,
            agent_role="chat_agent",
            host="main",
        )

        terminal_session_id = None
        if session_result.get("status") == "success":
            terminal_session_id = self.terminal_tool.active_sessions.get(session_id)

        logger.info(
            "Terminal session ID for conversation %s: %s",
            session_id,
            terminal_session_id,
        )
        return terminal_session_id

    async def _initialize_chat_session(self, session_id: str, message: str) -> tuple:
        """
        Initialize session and terminal, detect exit intent.

        Args:
            session_id: Session identifier
            message: User message to check for exit intent

        Returns:
            Tuple of (session, terminal_session_id, should_exit)
        """
        logger.debug(
            "[ChatWorkflowManager] Starting process_message_stream for session=%s",
            session_id,
        )
        logger.debug("[ChatWorkflowManager] Message: %s...", message[:100])

        session = await self.get_or_create_session(session_id)
        session.message_count += 1
        logger.debug("[ChatWorkflowManager] Session message_count: %d", session.message_count)

        # Comprehensive intent classification with safety guards (Issue #159)
        conversation_history_formatted = self._convert_conversation_history_format(session.conversation_history)

        # Initialize classifiers and analyze
        intent_classifier = IntentClassifier()
        context_analyzer = ConversationContextAnalyzer()
        safety_guards = ConversationSafetyGuards()

        classification: IntentClassification = intent_classifier.classify(message, conversation_history_formatted)
        context: ConversationContext = context_analyzer.analyze(conversation_history_formatted, message)
        safety_check: SafetyCheckResult = safety_guards.check(classification, context)

        # Determine exit intent (uses helper)
        user_wants_exit = self._determine_exit_intent(classification, safety_check)

        # Get or create terminal session (uses helper)
        terminal_session_id = await self._get_or_create_terminal_session(session_id)

        return session, terminal_session_id, user_wants_exit

    async def get_session_info(self, session_id: str) -> Dict[str, Any] | None:
        """Get information about a session."""
        async with self._lock:
            if session_id not in self.sessions:
                return None

            session = self.sessions[session_id]
            return {
                "session_id": session.session_id,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
                "message_count": session.message_count,
                "uptime": time.time() - session.created_at,
                "metadata": session.metadata,
            }

    async def cleanup_inactive_sessions(self, max_age_seconds: int = 3600) -> int:
        """Clean up inactive sessions older than max_age_seconds."""
        current_time = time.time()
        removed_count = 0

        async with self._lock:
            sessions_to_remove = []

            for session_id, session in self.sessions.items():
                if current_time - session.last_activity > max_age_seconds:
                    sessions_to_remove.append(session_id)

            for session_id in sessions_to_remove:
                del self.sessions[session_id]
                removed_count += 1
                logger.info("Cleaned up inactive session: %s", session_id)

        if removed_count > 0:
            logger.info("Cleaned up %d inactive sessions", removed_count)

        return removed_count

    async def get_active_sessions_count(self) -> int:
        """Get count of active sessions."""
        async with self._lock:
            return len(self.sessions)


async def _emit_session_create(session_id: str, context: Dict[str, Any]) -> None:
    """Emit SESSION_CREATE hook to registered extensions.

    Issue #4181: Fires when a new chat session is created so extensions
    can initialize resources or perform setup.

    Args:
        session_id: ID of created session
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={"session_id": session_id, "context": context},
    )
    await get_extension_manager().invoke_hook(HookPoint.SESSION_CREATE, ctx)


async def _emit_session_destroy(session_id: str, message_count: int, context: Dict[str, Any]) -> None:
    """Emit SESSION_DESTROY hook to registered extensions.

    Issue #4181: Fires when a chat session is closed so extensions
    can clean up resources or perform final processing.

    Args:
        session_id: ID of destroyed session
        message_count: Total messages in session
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={"session_id": session_id, "message_count": message_count, "context": context},
    )
    await get_extension_manager().invoke_hook(HookPoint.SESSION_DESTROY, ctx)


async def _emit_before_rag_query(query: str, session_id: str, context: Dict[str, Any]) -> str:
    """Emit BEFORE_RAG_QUERY hook to registered extensions.

    Issue #4181: Fires before executing RAG query so extensions can
    inspect or modify the query.

    Args:
        query: The RAG query string
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Possibly modified query
    """
    ctx = HookContext(
        session_id=session_id,
        data={"query": query, "context": context},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.BEFORE_RAG_QUERY, ctx, "query")
    return result if isinstance(result, str) else query


async def _emit_after_rag_results(results: list, query: str, session_id: str, context: Dict[str, Any]) -> list:
    """Emit AFTER_RAG_RESULTS hook to registered extensions.

    Issue #4181: Fires after RAG returns results so extensions can
    filter, rank, or modify the results.

    Args:
        results: List of RAG results
        query: Original query
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Possibly modified results list
    """
    ctx = HookContext(
        session_id=session_id,
        data={"results": results, "query": query, "context": context},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.AFTER_RAG_RESULTS, ctx, "results")
    return result if isinstance(result, list) else results


async def _emit_approval_required(request_id: str, action: str, session_id: str, context: Dict[str, Any]) -> bool:
    """Emit APPROVAL_REQUIRED hook to registered extensions.

    Issue #4181: Fires when an action requires approval so extensions
    can implement approval workflows.

    Args:
        request_id: Unique ID for this approval request
        action: Description of action requiring approval
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        True if approved, False otherwise
    """
    ctx = HookContext(
        session_id=session_id,
        data={"request_id": request_id, "action": action, "context": context},
    )
    result = await get_extension_manager().invoke_until_handled(HookPoint.APPROVAL_REQUIRED, ctx)
    return result is not None


async def _emit_approval_received(request_id: str, approved: bool, session_id: str, context: Dict[str, Any]) -> None:
    """Emit APPROVAL_RECEIVED hook to registered extensions.

    Issue #4181: Fires when approval is received so extensions can
    proceed with the approved action or log the decision.

    Args:
        request_id: ID of approval request
        approved: Whether action was approved
        session_id: Session identifier
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={"request_id": request_id, "approved": approved, "context": context},
    )
    await get_extension_manager().invoke_hook(HookPoint.APPROVAL_RECEIVED, ctx)
