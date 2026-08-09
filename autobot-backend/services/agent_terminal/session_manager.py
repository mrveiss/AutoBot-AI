# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Terminal Session Manager

Manages agent terminal session lifecycle: create, get, list, close, persist.
"""

import asyncio
import json
import uuid
from typing import Dict, List

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_1_HOUR

# #13478: how long a session holding a pending approval survives in Redis.
# Deliberately long: the thing it is waiting for is a person, and #13481
# established that an approval does not expire on a timer. This bounds the
# stored session, not the approval's validity.
APPROVAL_PENDING_SESSION_TTL: int = env_int("AUTOBOT_APPROVAL_PENDING_SESSION_TTL_SECONDS", default=7 * 24 * 60 * 60)
from services.command_approval_manager import AgentRole
from type_defs.common import Metadata

from .models import AgentSessionState, AgentTerminalSession

logger = get_logger(__name__)

# O(1) lookup optimization constants (Issue #326)
APPROVAL_RESPONSE_KEYWORDS = {"approved", "denied", "executed", "rejected"}


def _find_latest_approval_request(messages: List[Dict]) -> Dict | None:
    """
    Find the most recent command_approval_request message (Issue #665: extracted helper).

    Args:
        messages: List of chat messages to search

    Returns:
        Most recent approval request message or None
    """
    for msg in reversed(messages):  # Search newest first
        if msg.get("message_type") == "command_approval_request":
            return msg
    return None


def _is_approval_already_responded(messages: List[Dict], request_timestamp: float) -> bool:
    """
    Check if approval request was already responded to (Issue #665: extracted helper).

    Searches for approval/denial response messages after the request timestamp.

    Args:
        messages: List of chat messages to search
        request_timestamp: Timestamp of the approval request

    Returns:
        True if approval was already handled, False if still pending
    """
    for msg in reversed(messages):
        msg_time = msg.get("timestamp", 0)
        if msg_time > request_timestamp:
            content = msg.get("text", "").lower()
            if any(keyword in content for keyword in APPROVAL_RESPONSE_KEYWORDS):
                return True
    return False


def _apply_restored_approval_state(
    session: "AgentTerminalSession",
    approval_request: Dict,
    conversation_id: str,
    request_timestamp: float,
) -> None:
    """
    Apply restored approval state to session from approval request metadata.

    Issue #665: Extracted from _restore_pending_approval to reduce function length.

    Args:
        session: Agent terminal session to update
        approval_request: Approval request message with metadata
        conversation_id: Chat conversation ID
        request_timestamp: Timestamp of the approval request
    """
    metadata = approval_request.get("metadata", {})
    command = metadata.get("command")

    if command:
        session.pending_approval = {
            "command": command,
            "risk": metadata.get("risk_level", "MEDIUM"),
            "reasons": metadata.get("reasons", []),
            "description": metadata.get("description", ""),
            "terminal_session_id": metadata.get("terminal_session_id"),
            "conversation_id": conversation_id,
            "timestamp": request_timestamp,
        }
        session.state = AgentSessionState.AWAITING_APPROVAL

        logger.info(
            f"✅ [APPROVAL RESTORED] Restored pending approval "
            f"for session {session.session_id}: "
            f"command='{command}', risk={metadata.get('risk_level')}"
        )
    else:
        logger.warning(f"Found approval request but no command in metadata " f"for conversation {conversation_id}")


class SessionManager:
    """Manages agent terminal session lifecycle"""

    def __init__(self, redis_client=None, chat_history_manager=None) -> None:
        """
        Initialize session manager.

        Args:
            redis_client: Redis client for session persistence
            chat_history_manager: ChatHistoryManager instance for approval restoration
        """
        self.redis_client = redis_client
        self.chat_history_manager = chat_history_manager
        self.sessions: Dict[str, AgentTerminalSession] = {}
        self._sessions_lock = asyncio.Lock()  # Protect concurrent session access

    def _create_or_reuse_pty_session(self, pty_session_id: str, session_id: str) -> str | None:
        """
        Create a new PTY session or reuse an existing alive one.

        Issue #281: Extracted helper for PTY session creation/recovery.

        Args:
            pty_session_id: Desired PTY session ID
            session_id: Agent session ID for logging

        Returns:
            PTY session ID if successful, None otherwise
        """
        from constants.path_constants import PATH
        from services.simple_pty import simple_pty_manager

        existing_pty = simple_pty_manager.get_session(pty_session_id)

        if not existing_pty or not existing_pty.is_alive():
            if existing_pty and not existing_pty.is_alive():
                logger.warning(
                    f"PTY session {pty_session_id} exists but is dead " f"(killed during restart). Recreating..."
                )
                simple_pty_manager.close_session(pty_session_id)

            pty = simple_pty_manager.create_session(pty_session_id, initial_cwd=str(PATH.PROJECT_ROOT))
            if pty:
                logger.info(f"Created PTY session {pty_session_id} for agent terminal {session_id}")
                return pty_session_id
            else:
                logger.warning(f"Failed to create PTY session for agent terminal {session_id}")
                return None
        else:
            logger.info(f"Reusing existing ALIVE PTY session {pty_session_id} " f"for agent terminal {session_id}")
            return pty_session_id

    def _register_pty_with_terminal_manager(self, pty_session_id: str, conversation_id: str) -> None:
        """
        Register PTY session with terminal session_manager for WebSocket logging.

        Issue #281: Extracted helper for PTY registration.

        Args:
            pty_session_id: PTY session ID to register
            conversation_id: Conversation ID for logging linkage
        """
        try:
            from api.terminal import session_manager

            session_manager.session_configs[pty_session_id] = {
                "security_level": "standard",
                "conversation_id": conversation_id,
            }
            logger.info(
                f"Registered PTY session {pty_session_id} with " f"conversation_id {conversation_id} for logging"
            )
        except Exception as e:
            logger.error(f"Failed to register PTY session with session_manager: {e}")

    async def _setup_pty_for_session(
        self,
        session_id: str,
        conversation_id: str | None,
    ) -> str | None:
        """Helper for create_session. Ref: #1088.

        Creates or reuses a PTY session and registers it for WebSocket logging.

        Args:
            session_id: Agent session ID
            conversation_id: Optional conversation ID for logging linkage

        Returns:
            PTY session ID if successful, None otherwise
        """
        try:
            desired_pty_id = conversation_id or session_id
            pty_session_id = self._create_or_reuse_pty_session(desired_pty_id, session_id)
            if pty_session_id and conversation_id:
                self._register_pty_with_terminal_manager(pty_session_id, conversation_id)
            return pty_session_id
        except Exception as e:
            logger.error("Error creating PTY session: %s", e)
            return None

    async def create_session(
        self,
        agent_id: str,
        agent_role: AgentRole,
        conversation_id: str | None = None,
        host: str = "main",
        metadata: Metadata | None = None,
    ) -> AgentTerminalSession:
        """
        Create a new agent terminal session with PTY integration.

        Issue #281: Refactored from 113 lines to use extracted helper methods.
        Issue #1088: Extracted _setup_pty_for_session to reduce to <=65 lines.

        Args:
            agent_id: Unique identifier for the agent
            agent_role: Role of the agent (determines permissions)
            conversation_id: Optional chat conversation ID to link
            host: Target host for command execution
            metadata: Additional session metadata

        Returns:
            Created session
        """
        session_id = str(uuid.uuid4())
        pty_session_id = await self._setup_pty_for_session(session_id, conversation_id)

        session = AgentTerminalSession(
            session_id=session_id,
            agent_id=agent_id,
            agent_role=agent_role,
            conversation_id=conversation_id,
            host=host,
            metadata=metadata or {},
            pty_session_id=pty_session_id,
        )

        async with self._sessions_lock:
            self.sessions[session_id] = session

        logger.info(
            f"Created agent terminal session {session_id} "
            f"for agent {agent_id} (role: {agent_role.value}), "
            f"PTY session: {pty_session_id}"
        )

        if conversation_id and self.chat_history_manager:
            await self._restore_pending_approval(session, conversation_id)

        if self.redis_client:
            await self._persist_session(session)

        return session

    async def get_session(self, session_id: str) -> AgentTerminalSession | None:
        """
        Get session by ID. Checks memory first, then loads from Redis if needed.

        Args:
            session_id: Session identifier

        Returns:
            Session if found, None otherwise
        """
        # Fast path: check in-memory sessions first (protected by lock)
        async with self._sessions_lock:
            session = self.sessions.get(session_id)
            if session:
                logger.debug(
                    f"[GET_SESSION] Returning in-memory session {session_id}: "
                    f"pending_approval={session.pending_approval is not None}"
                )
                return session

        # Slow path: try loading from Redis if available
        if self.redis_client:
            try:
                key = f"agent_terminal:session:{session_id}"
                session_json = await asyncio.wait_for(self.redis_client.get(key), timeout=2.0)

                if session_json:
                    session_data = json.loads(session_json)

                    # Reconstruct session object from Redis data
                    session = AgentTerminalSession(
                        session_id=session_data["session_id"],
                        agent_id=session_data["agent_id"],
                        agent_role=AgentRole(session_data["agent_role"]),
                        conversation_id=session_data.get("conversation_id"),
                        host=session_data.get("host"),
                        metadata=session_data.get("metadata", {}),
                        pty_session_id=session_data.get("pty_session_id"),
                    )

                    # Restore session state
                    session.state = AgentSessionState(session_data["state"])
                    session.created_at = session_data["created_at"]
                    session.last_activity = session_data["last_activity"]
                    session.pending_approval = session_data.get(
                        "pending_approval"
                    )  # CRITICAL: Restore pending approvals

                    # Add back to memory cache (protected by lock)
                    async with self._sessions_lock:
                        self.sessions[session_id] = session

                    logger.info("Loaded session %s from Redis persistence", session_id)
                    return session

            except asyncio.TimeoutError:
                logger.warning("Redis timeout loading session %s", session_id)
            except Exception as e:
                logger.error("Failed to load session from Redis: %s", e)

        # #13478: last resort — the session record is gone, but it may have been
        # holding a pending approval. `_restore_pending_approval` can rebuild
        # that from chat history and is documented as surviving restarts, yet it
        # only ran inside `create_session`, which mints a NEW session_id. The
        # approve endpoint is addressed by the OLD id (it is what the persisted
        # approval message and the GUI button carry), so the restore was
        # unreachable from the one path that needed it.
        return await self._rebuild_session_from_pending_approval(session_id)

    async def _rebuild_session_from_pending_approval(self, session_id: str) -> AgentTerminalSession | None:
        """Reconstruct a vanished session that still has an unanswered approval.

        Returns None when the session simply does not exist — the ordinary case
        for a bad id, and it must stay cheap and quiet.
        """
        conversation_id = await self._conversation_for_expired_session(session_id)
        if not conversation_id or not self.chat_history_manager:
            return None

        session = AgentTerminalSession(
            session_id=session_id,
            agent_id="restored",
            # Lowest privilege on purpose. The role the original session ran
            # under is not recorded in the restored approval, and a rebuilt
            # session exists only to let a human resolve a decision that was
            # already gated — it must never be the thing that widens what the
            # command is allowed to do.
            agent_role=AgentRole.CHAT_AGENT,
            conversation_id=conversation_id,
        )
        await self._restore_pending_approval(session, conversation_id)

        if not session.has_pending_approval():
            # Nothing outstanding: the approval was already answered, so there is
            # no session worth resurrecting.
            return None

        async with self._sessions_lock:
            self.sessions[session_id] = session

        logger.info(
            "Rebuilt session %s from its pending approval in conversation %s (#13478)",
            session_id,
            conversation_id,
        )
        return session

    async def list_sessions(
        self,
        agent_id: str | None = None,
        conversation_id: str | None = None,
    ) -> List[AgentTerminalSession]:
        """
        List agent terminal sessions.

        Args:
            agent_id: Filter by agent ID
            conversation_id: Filter by conversation ID

        Returns:
            List of matching sessions
        """
        sessions = list(self.sessions.values())

        if agent_id:
            sessions = [s for s in sessions if s.agent_id == agent_id]

        if conversation_id:
            sessions = [s for s in sessions if s.conversation_id == conversation_id]

        return sessions

    async def close_session(self, session_id: str) -> bool:
        """
        Close an agent terminal session.

        Args:
            session_id: Session to close

        Returns:
            True if closed successfully
        """
        # CRITICAL: Atomic check-and-delete with lock to prevent race conditions
        async with self._sessions_lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
            else:
                return False

        logger.info("Closed agent terminal session %s", session_id)

        # Remove from Redis (outside lock since Redis has its own concurrency control)
        if self.redis_client:
            try:
                key = f"agent_terminal:session:{session_id}"
                await self.redis_client.delete(key)
            except Exception as e:
                logger.error("Failed to remove session from Redis: %s", e)

        return True

    async def _persist_session(self, session: AgentTerminalSession) -> None:
        """Persist session to Redis.

        #13478: the TTL depends on whether the session is *idle* or *waiting on a
        human*. TTL_1_HOUR garbage-collects abandoned sessions, which is right —
        but it was applied to a session holding a pending approval too, and
        nothing refreshed it. `set_pending_approval` re-persists immediately
        (service.py:213), so the clock started the moment the prompt was raised
        and ran out an hour later. `_approve_command_internal` then hit
        `if not session: return {"error": "Session not found"}` and the approval
        was unrecoverable.

        That was the real expiry behind #13216 — not the 30-minute poll budget,
        which only bounds the turn, and not a restart, which the session
        survives. A person taking longer than an hour to answer a prompt is the
        normal case this feature exists for, so the wait must not be what kills
        it (#13481: approval does not expire on a timer).
        """
        try:
            key = f"agent_terminal:session:{session.session_id}"
            # Issue #372: Use model method to reduce feature envy
            session_data = session.to_persist_dict()

            ttl = APPROVAL_PENDING_SESSION_TTL if session.has_pending_approval() else TTL_1_HOUR
            json_data = json.dumps(session_data)
            await self.redis_client.setex(key, ttl, json_data)

            # #13478: a companion pointer so the approve path can still find the
            # conversation after the session itself is gone. `get_session` takes
            # a session_id and `_restore_pending_approval` needs a
            # conversation_id, so without this the chat-history restore — which
            # exists and works — is unreachable from the approve endpoint.
            if session.has_pending_approval() and session.conversation_id:
                await self.redis_client.setex(
                    f"agent_terminal:approval_conversation:{session.session_id}",
                    APPROVAL_PENDING_SESSION_TTL,
                    session.conversation_id,
                )

            logger.debug("Persisted session %s to Redis with key %s (ttl=%ds)", session.session_id, key, ttl)

        except Exception as e:
            logger.error("Failed to persist session to Redis: %s", e)

    async def _conversation_for_expired_session(self, session_id: str) -> str | None:
        """The conversation a vanished session was serving, if it had an approval."""
        if not self.redis_client:
            return None
        try:
            raw = await asyncio.wait_for(
                self.redis_client.get(f"agent_terminal:approval_conversation:{session_id}"),
                timeout=2.0,
            )
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            logger.warning("Could not read approval-conversation pointer for %s: %s", session_id, exc)
            return None

        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)

    async def _restore_pending_approval(self, session: AgentTerminalSession, conversation_id: str) -> None:
        """
        Restore pending approval from chat history (survives backend restarts).

        Issue #665: Refactored to use extracted helper functions for
        finding approval requests and checking response status.

        Scans recent chat messages for unapproved command_approval_request messages
        and restores the pending_approval state so users can approve after restart.

        Args:
            session: Agent terminal session to restore state for
            conversation_id: Chat conversation ID to check
        """
        if not self.chat_history_manager:
            return

        try:
            # Get recent messages from chat history (last 50 messages)
            messages = await self.chat_history_manager.get_session_messages(session_id=conversation_id, limit=50)

            if not messages:
                logger.debug(f"No messages found for conversation {conversation_id}, " f"skipping approval restoration")
                return

            # Search for most recent command_approval_request (Issue #665: uses helper)
            approval_request = _find_latest_approval_request(messages)

            if not approval_request:
                logger.debug(f"No pending approval requests found in conversation {conversation_id}")
                return

            # Check if this approval was already responded to (Issue #665: uses helper)
            request_timestamp = approval_request.get("timestamp", 0)
            if _is_approval_already_responded(messages, request_timestamp):
                logger.info(
                    f"Approval request already responded to in " f"conversation {conversation_id}, skipping restoration"
                )
                return

            # Approval is still pending! Restore state (Issue #665: uses helper)
            _apply_restored_approval_state(session, approval_request, conversation_id, request_timestamp)

        except Exception as e:
            logger.error("Failed to restore pending approval from chat history: %s", e)
            import traceback

            logger.error("Traceback: %s", traceback.format_exc())
