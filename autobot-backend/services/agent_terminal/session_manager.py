# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Terminal Session Manager

Manages agent terminal session lifecycle: create, get, list, close, persist.
"""

import asyncio
import uuid
from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_1_HOUR
from services.command_approval_manager import AgentRole
from type_defs.common import Metadata

from .approval_restore import restore_pending_approval
from .conversation_owner import ConversationNotOwnedError, conversation_owner, verified_conversation_owner
from .decision_session import release_with_retry
from .models import AgentTerminalSession
from .pending_claim import drop_pending_slot, hold_pending_slot
from .redis_usability import usable_redis
from .session_state import (
    APPROVAL_PENDING_SESSION_TTL,
    ApprovalStateUnavailableError,
    apply_record,
    claim_decision,
    close_record,
    conversation_pointer_key,
    pending_decision_id,
    persist_if_current,
    read_record,
    session_from_record,
    session_is_closed,
    session_key,
)

logger = get_logger(__name__)


class SessionManager:
    """Manages agent terminal session lifecycle"""

    def __init__(self, redis_client=None, chat_history_manager=None) -> None:
        """
        Initialize session manager.

        Args:
            redis_client: Redis client for session persistence
            chat_history_manager: ChatHistoryManager instance for approval restoration
        """
        if redis_client is not None and not usable_redis(redis_client):
            # #17436: reached through a process-wide singleton, so a bad client
            # here poisons every later consumer. Refuse at the boundary.
            raise TypeError(
                f"redis_client is not a usable Redis client: {type(redis_client).__name__}. "
                "An un-awaited get_redis_client(async_client=True) returns a coroutine; "
                "use `await get_async_redis_client(...)`."
            )
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

    def _register_pty_with_terminal_manager(self, pty_session_id: str, conversation_id: str, owner: str | None) -> None:
        """
        Register PTY session with terminal session_manager for WebSocket logging.

        Issue #281: Extracted helper for PTY registration.
        Issue #14989: stamps `owner` -- the authenticated creator's username --
        so api.terminal._lookup_terminal_session (#14960) recognises the
        session's creator as its owner. Without this, this writer's own
        connections were denied by the ownership gate: this session_configs
        entry is the same in-process dict api.terminal.terminal_websocket
        reads, and an entry with no "owner" key is unowned by construction.

        Args:
            pty_session_id: PTY session ID to register
            conversation_id: Conversation ID for logging linkage
            owner: Authenticated creator's username, or None if unresolved
        """
        try:
            from api.terminal import session_manager

            session_manager.session_configs[pty_session_id] = {
                "security_level": "standard",
                "conversation_id": conversation_id,
                "owner": owner,
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
        owner: str | None = None,
    ) -> str | None:
        """Helper for create_session. Ref: #1088.

        Creates or reuses a PTY session and registers it for WebSocket logging.

        Args:
            session_id: Agent session ID
            conversation_id: Optional conversation ID for logging linkage
            owner: Authenticated creator's username (#14989/#14960)

        Returns:
            PTY session ID if successful, None otherwise
        """
        try:
            desired_pty_id = conversation_id or session_id
            pty_session_id = self._create_or_reuse_pty_session(desired_pty_id, session_id)
            if pty_session_id and conversation_id:
                self._register_pty_with_terminal_manager(pty_session_id, conversation_id, owner)
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
        owner: str | None = None,
        tenant_id: str | None = None,
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
            owner: Authenticated creator's username (#14989/#14960); None = the conversation's owner (#17053).
                An explicit owner must also own ``conversation_id`` (#17422).
            tenant_id: The creator's org_id, from the JWT claim only (#16975).
                None if it could not be determined -- never guessed here.

        Returns:
            Created session

        Raises:
            ConversationNotOwnedError: ``owner`` was given and does not own ``conversation_id``.
        """
        session_id = str(uuid.uuid4())
        owner = await self._owner_for(conversation_id, owner)
        pty_session_id = await self._setup_pty_for_session(session_id, conversation_id, owner)

        session = AgentTerminalSession(
            session_id=session_id,
            agent_id=agent_id,
            agent_role=agent_role,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            host=host,
            metadata=metadata or {},
            pty_session_id=pty_session_id,
            owner=owner,  # #17053: the one record the REST ownership checks read
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

        if usable_redis(self.redis_client):
            await self._persist_session(session)

        return session

    async def get_session(self, session_id: str) -> AgentTerminalSession | None:
        """Get a session for DISPLAY: Redis holds the record, the cache is refreshed from it (#20674).

        When Redis cannot answer, the cached copy is the fallback. A decision must not use this: it goes
        through ``decision_session.session_for_decision``, which never falls back.
        """
        async with self._sessions_lock:
            cached = self.sessions.get(session_id)
        if self.redis_client:
            refreshed = await self._refresh_from_redis(session_id, cached)
            if refreshed:
                return refreshed
            async with self._sessions_lock:
                cached = self.sessions.get(session_id)  # a refresh may have dropped a closed session
        if cached:
            return cached

        # #13478: last resort — the session record is gone, but it may have been
        # holding a pending approval. The approve endpoint is addressed by the OLD
        # id (what the persisted approval message and the GUI button carry), so the
        # chat-history restore has to be reachable from here.
        return await self._rebuild_session_from_pending_approval(session_id)

    async def _refresh_from_redis(
        self, session_id: str, cached: AgentTerminalSession | None
    ) -> AgentTerminalSession | None:
        """Bring *cached* up to date with the Redis record, or load the session from it (#20674)."""
        try:
            data = await read_record(self.redis_client, session_id)
        except Exception as e:  # noqa: BLE001 - a Redis outage falls back to the cached copy
            logger.warning("Could not read session %s from Redis: %s", session_id, e)
            return cached
        if data is None:
            return await self._cached_unless_closed(session_id, cached)
        if cached:
            apply_record(cached, data)
            return cached
        session = session_from_record(data)
        async with self._sessions_lock:
            session = self.sessions.setdefault(session_id, session)
        logger.info("Loaded session %s from Redis persistence", session_id)
        return session

    async def _cached_unless_closed(self, session_id: str, cached):
        """No record: a session closed on another worker is dropped from this one's cache (#21202)."""
        if cached is None:
            return None
        try:
            closed = await session_is_closed(self.redis_client, session_id)
        except ApprovalStateUnavailableError as e:
            logger.warning("Could not tell whether session %s was closed: %s", session_id, e)
            return cached
        if not closed:
            return cached
        async with self._sessions_lock:
            self.sessions.pop(session_id, None)
        return None

    async def _owner_for(self, conversation_id: str | None, owner: str | None) -> str | None:
        """The session's owner: ``owner`` if it owns the conversation, else the conversation's (#17422).

        ``conversation_id`` is caller-supplied; an explicit owner narrows authority
        and never stands in for checking it. An unowned conversation is refused
        too -- it is admin-only (#17053), and binding it would stamp the caller.
        So is one whose owner record cannot be read (``verified_conversation_owner``).
        """
        if owner is None:
            return await self._conversation_owner(conversation_id)
        if conversation_id and await verified_conversation_owner(self.chat_history_manager, conversation_id) != owner:
            raise ConversationNotOwnedError(conversation_id)
        return owner

    async def _conversation_owner(self, conversation_id: str | None) -> str | None:
        """Owner of the conversation driving a session, or None: admin-only (#17053)."""
        return await conversation_owner(self.chat_history_manager, conversation_id)

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
            owner=await self._conversation_owner(conversation_id),
        )
        await self._restore_pending_approval(session, conversation_id)

        if not session.has_pending_approval():
            # Nothing outstanding: the approval was already answered, so there is
            # no session worth resurrecting.
            return None

        # A rebuilt session is made authoritative before anything can decide it: the record is written first, and
        # a session whose record cannot be written is not handed out (#20674). Without Redis it is display-only,
        # and every decision fails closed.
        if usable_redis(self.redis_client) and not await self._persist_session(session):
            logger.error("Could not record the rebuilt session %s; not restoring it", session_id)
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
        """Close an agent terminal session, on the store whether or not this worker cached it (#21202).

        With Redis the tombstone and the record's removal land first, in one step; a failure there is
        ``False`` and the cached copy stays, so nothing is marked closed that the store still holds open.

        Returns:
            True if the session is closed
        """
        redis_closed = usable_redis(self.redis_client)
        if redis_closed and not await self._close_in_store(session_id):
            return False
        async with self._sessions_lock:
            cached = self.sessions.pop(session_id, None)
        if cached is None and not redis_closed:
            return False
        logger.info("Closed agent terminal session %s", session_id)
        return True

    async def _close_in_store(self, session_id: str) -> bool:
        """Tombstone the session in Redis; ``False`` if the store did not take it."""
        try:
            await close_record(self.redis_client, session_id)
        except Exception as e:  # noqa: BLE001 - the caller reports the session as not closed
            logger.error("Could not close session %s in Redis; it stays open: %s", session_id, e)
            return False
        try:
            await drop_pending_slot(self.redis_client, session_id)
        except Exception as e:  # noqa: BLE001 - the session is closed; the slot's TTL frees it
            logger.error("Session %s is closed but its pending slot was not freed: %s", session_id, e)
        return True

    async def _persist_session(self, session: AgentTerminalSession) -> bool:
        """Persist session to Redis; ``False`` if the session record was not written.

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
            key = session_key(session.session_id)
            ttl = APPROVAL_PENDING_SESSION_TTL if session.has_pending_approval() else TTL_1_HOUR
            if not await persist_if_current(self.redis_client, session, ttl):
                return await self._refuse_stale_persist(session)

            if not await self._write_pending_pointers(session, ttl):
                return False

            logger.debug("Persisted session %s to Redis with key %s (ttl=%ds)", session.session_id, key, ttl)

            return True
        except Exception as e:
            logger.error("Failed to persist session to Redis: %s", e)
            return False

    async def _write_pending_pointers(self, session: AgentTerminalSession, ttl: int) -> bool:
        """Write the pending slot and the conversation pointer of a saved approval (#13478).

        The pointer lets the approve endpoint reach the chat-history restore once the session is gone.
        A close can land between the save and these writes, so the tombstone is read again afterwards and
        whatever was written is taken back (#21202); a close that lands later removes them itself.
        """
        if not session.has_pending_approval():
            return True
        if session.conversation_id:
            await self.redis_client.setex(
                conversation_pointer_key(session.session_id), APPROVAL_PENDING_SESSION_TTL, session.conversation_id
            )
        await hold_pending_slot(self.redis_client, session.session_id, session.get_pending_command_id(), ttl)
        if not await session_is_closed(self.redis_client, session.session_id):
            return True
        await self.redis_client.delete(conversation_pointer_key(session.session_id))
        await drop_pending_slot(self.redis_client, session.session_id)
        async with self._sessions_lock:
            self.sessions.pop(session.session_id, None)
        return False

    async def persist_control(self, session: AgentTerminalSession, target) -> Metadata | None:
        """Move *session* to the control state *target* and save it so other workers see it (#20674).

        Returns the error to answer with if the save is refused; the copy then goes back to its old state unless
        the refused save already refreshed it from Redis.
        """
        previous, session.state = session.state, target
        if not usable_redis(self.redis_client) or await self._persist_session(session):
            return None
        if session.state == target:
            session.state = previous
        return {"status": "error", "error": "Control change not saved, retry"}

    async def _refuse_stale_persist(self, session: AgentTerminalSession) -> bool:
        """The record moved on since this copy was read (#20674): keep it, take it as the copy, report no save."""
        if await session_is_closed(self.redis_client, session.session_id):
            logger.warning("Session %s was closed on another worker; dropping this copy", session.session_id)
            async with self._sessions_lock:
                self.sessions.pop(session.session_id, None)
            return False
        logger.warning("Session %s changed in Redis since this copy was read; not overwriting it", session.session_id)
        await self._refresh_from_redis(session.session_id, session)
        return False

    async def claim_decision(self, session: AgentTerminalSession) -> bool:
        """Win the one decision on the session's pending approval, across workers (#20674)."""
        session.decision_token = await claim_decision(
            self.redis_client, session.session_id, pending_decision_id(session.pending_approval)
        )
        return session.decision_token is not None

    async def release_after_failed_run(self, session: AgentTerminalSession) -> None:
        """Log the failed run and give its decision claim back, so the user can approve again at once (#20674).

        A release Redis refuses is retried in the background with the same token and decision id; the caller
        still answers with the execution failure.
        """
        logger.error("Approved command execution error", exc_info=True)
        token, session.decision_token = session.decision_token, None
        if token and usable_redis(self.redis_client):
            await release_with_retry(
                self.redis_client, session.session_id, pending_decision_id(session.pending_approval), token
            )

    async def _conversation_for_expired_session(self, session_id: str) -> str | None:
        """The conversation a vanished session was serving, if it had an approval."""
        if not self.redis_client:
            return None
        try:
            raw = await asyncio.wait_for(
                self.redis_client.get(conversation_pointer_key(session_id)),
                timeout=2.0,
            )
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            logger.warning("Could not read approval-conversation pointer for %s: %s", session_id, exc)
            return None

        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)

    async def _restore_pending_approval(self, session: AgentTerminalSession, conversation_id: str) -> None:
        """Restore the session's own undecided approval from chat history (#13478, #21174); see approval_restore."""
        await restore_pending_approval(self, session, conversation_id)
