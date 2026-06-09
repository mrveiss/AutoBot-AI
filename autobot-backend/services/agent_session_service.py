# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Session Persistence Service (#1406)

Saves and restores agent session state across process restarts.
Sessions have a configurable TTL; expired sessions are treated as
absent and are cleaned up by cleanup_expired_sessions().
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from models.process_run import AgentSession

logger = get_logger(__name__)

_DEFAULT_TTL = 3600


class AgentSessionService:
    """Persist and restore per-agent session state with TTL (#1406)."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_session(
        self,
        agent_id: str,
        task_id: str,
        state: Dict[str, Any],
        ttl_seconds: int = _DEFAULT_TTL,
    ) -> str:
        """
        Upsert a session for (agent_id, task_id) (#1406).

        Overwrites any existing session for the same (agent_id, task_id) pair.
        Returns the UUID of the saved row.
        """
        now = now_utc()
        expires_at = now + timedelta(seconds=ttl_seconds)
        session_id = await self._upsert_session(agent_id, task_id, state, ttl_seconds, expires_at)
        logger.info("Session saved: agent=%s task=%s ttl=%ss", agent_id, task_id, ttl_seconds)
        return str(session_id)

    async def load_session(self, agent_id: str, task_id: str) -> Dict[str, Any] | None:
        """
        Return session state for (agent_id, task_id), or None if absent/expired (#1406).

        Expired sessions are not deleted here; use cleanup_expired_sessions().
        """
        async with self._session_factory() as session:
            row = await _fetch_session(session, agent_id, task_id)
        if row is None:
            return None
        if row.expires_at.replace(tzinfo=timezone.utc) < now_utc():
            logger.debug("Session expired for agent=%s task=%s", agent_id, task_id)
            return None
        return row.session_state

    async def cleanup_expired_sessions(self) -> int:
        """
        Delete all expired AgentSession rows (#1406).

        Returns the number of rows deleted.
        """
        now = now_utc()
        async with self._session_factory() as session:
            result = await session.execute(delete(AgentSession).where(AgentSession.expires_at < now))
            await session.commit()
            count = result.rowcount
        logger.info("Cleaned up %s expired agent sessions", count)
        return count

    # -- Internal helpers --------------------------------------------------

    async def _upsert_session(
        self,
        agent_id: str,
        task_id: str,
        state: Dict[str, Any],
        ttl_seconds: int,
        expires_at: datetime,
    ) -> uuid.UUID:
        """Insert or update a session row. Returns the row UUID (#1406)."""
        async with self._session_factory() as session:
            existing = await _fetch_session(session, agent_id, task_id)
            if existing is not None:
                existing.session_state = state
                existing.ttl_seconds = ttl_seconds
                existing.expires_at = expires_at
                row_id = existing.id
            else:
                row_id = uuid.uuid4()
                session.add(
                    AgentSession(
                        id=row_id,
                        agent_id=agent_id,
                        task_id=task_id,
                        session_state=state,
                        ttl_seconds=ttl_seconds,
                        expires_at=expires_at,
                    )
                )
            await session.commit()
        return row_id


# -- Module-level helpers --------------------------------------------------


async def _fetch_session(session: Any, agent_id: str, task_id: str) -> AgentSession | None:
    """Fetch an AgentSession row for (agent_id, task_id) (#1406)."""
    result = await session.execute(
        select(AgentSession)
        .where(
            AgentSession.agent_id == agent_id,
            AgentSession.task_id == task_id,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()
