# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Gateway Session Manager

Issue #732: Unified Gateway for multi-channel communication.
Manages session isolation, context persistence, and lifecycle.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .config import GatewayConfig
from .types import ChannelType, GatewaySession, SessionStatus

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages Gateway sessions with isolation per user/channel.

    Features:
    - Session isolation (one session per user+channel)
    - Context persistence (session data survives reconnects)
    - Automatic cleanup (idle session timeout)
    - Rate limiting (per-session token bucket)
    """

    def __init__(self, config: GatewayConfig):
        """
        Initialize the session manager.

        Args:
            config: Gateway configuration
        """
        self.config = config
        self._sessions: Dict[str, GatewaySession] = {}
        self._user_sessions: Dict[str, List[str]] = {}  # user_id -> [session_ids]
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the session manager (cleanup task)."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Session manager started")

    async def stop(self) -> None:
        """Stop the session manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Session manager stopped")

    async def create_session(
        self,
        user_id: str,
        channel: ChannelType,
        metadata: Optional[Dict] = None,
    ) -> GatewaySession:
        """
        Create a new session.

        Args:
            user_id: User identifier
            channel: Communication channel
            metadata: Optional session metadata

        Returns:
            Created session

        Raises:
            ValueError: If user has too many sessions
        """
        async with self._lock:
            # Check session limit
            user_sessions = self._user_sessions.get(user_id, [])
            active_sessions = [
                sid
                for sid in user_sessions
                if sid in self._sessions
                and self._sessions[sid].status == SessionStatus.ACTIVE
            ]

            if len(active_sessions) >= self.config.max_sessions_per_user:
                raise ValueError(
                    f"User {user_id} has too many active sessions "
                    f"({len(active_sessions)}/{self.config.max_sessions_per_user})"
                )

            # Create session
            session = GatewaySession(
                user_id=user_id,
                channel=channel,
                metadata=metadata or {},
                rate_limit_tokens=self.config.rate_limit_per_user,
            )

            self._sessions[session.session_id] = session

            # Track user sessions
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = []
            self._user_sessions[user_id].append(session.session_id)

            logger.info(
                "Created session %s for user %s on channel %s",
                session.session_id,
                user_id,
                channel.value,
            )
            return session

    async def get_session(self, session_id: str) -> Optional[GatewaySession]:
        """Get session by ID."""
        return self._sessions.get(session_id)

    async def update_session(
        self,
        session_id: str,
        status: Optional[SessionStatus] = None,
        context: Optional[Dict] = None,
    ) -> bool:
        """
        Update session status and/or context.

        Args:
            session_id: Session to update
            status: New status (optional)
            context: Context updates (optional)

        Returns:
            True if updated, False if session not found
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            if status:
                session.status = status
            if context:
                session.context.update(context)

            session.update_activity()
            return True

    async def close_session(self, session_id: str) -> bool:
        """
        Close a session.

        Args:
            session_id: Session to close

        Returns:
            True if closed, False if not found
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            session.status = SessionStatus.CLOSED

            # Remove from user sessions
            if session.user_id in self._user_sessions:
                try:
                    self._user_sessions[session.user_id].remove(session_id)
                except ValueError:
                    pass

            # Remove session
            del self._sessions[session_id]

            logger.info("Closed session %s", session_id)
            return True

    async def get_user_sessions(self, user_id: str) -> List[GatewaySession]:
        """Get all active sessions for a user."""
        session_ids = self._user_sessions.get(user_id, [])
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    async def consume_rate_limit(self, session_id: str) -> bool:
        """
        Consume a rate limit token for a session.

        Args:
            session_id: Session ID

        Returns:
            True if token consumed, False if rate limit exceeded
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            return session.consume_rate_limit_token()

    async def _cleanup_loop(self) -> None:
        """Background task to clean up idle sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._cleanup_idle_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in session cleanup: %s", e, exc_info=True)

    async def _cleanup_idle_sessions(self) -> None:
        """Clean up idle sessions that have exceeded timeout."""
        async with self._lock:
            now = datetime.utcnow()
            timeout_delta = timedelta(seconds=self.config.session_timeout_seconds)
            sessions_to_close = []

            for session_id, session in self._sessions.items():
                if session.status == SessionStatus.ACTIVE:
                    idle_time = now - session.last_activity
                    if idle_time > timeout_delta:
                        sessions_to_close.append(session_id)

            for session_id in sessions_to_close:
                logger.info("Cleaning up idle session %s", session_id)
                await self.close_session(session_id)

            if sessions_to_close:
                logger.info("Cleaned up %d idle sessions", len(sessions_to_close))

    async def get_stats(self) -> Dict:
        """Get session manager statistics."""
        total_sessions = len(self._sessions)
        active_sessions = sum(
            1 for s in self._sessions.values() if s.status == SessionStatus.ACTIVE
        )
        idle_sessions = sum(
            1 for s in self._sessions.values() if s.status == SessionStatus.IDLE
        )

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "idle_sessions": idle_sessions,
            "total_users": len(self._user_sessions),
        }
