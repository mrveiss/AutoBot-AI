# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC RoutineService — CRUD and run recording for recurring agent tasks (GH#8229).

Env overlay order enforced by resolve_env():
  agent_env < project_env < routine_env < system_keys (SYSTEM_* prefixed keys)

Secret resolution: env values matching "secret:<NAME>" are resolved via SecretService.
Soft-delete: delete() sets status=ARCHIVED; the row is never removed.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import RoutineStatus
from ..models.routine import LLCRoutine, LLCRoutineRun
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_SYSTEM_KEY_PREFIXES = ("SYSTEM_",)


class RoutineNotFoundError(Exception):
    """Raised when a requested routine cannot be located."""


class RoutineService(LLCServiceBase):
    """CRUD + run-recording service for LLC routines."""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        agent_id: uuid.UUID,
        name: str,
        cron_schedule: str,
        description: Optional[str] = None,
        env: Optional[Dict[str, Any]] = None,
    ) -> LLCRoutine:
        routine = LLCRoutine(
            company_id=company_id,
            agent_id=agent_id,
            name=name,
            cron_schedule=cron_schedule,
            description=description,
            env=env or {},
            status=RoutineStatus.ACTIVE,
        )
        session.add(routine)
        await session.flush()
        return routine

    async def get(self, session: AsyncSession, routine_id: uuid.UUID) -> LLCRoutine:
        row = await session.get(LLCRoutine, routine_id)
        if row is None:
            raise RoutineNotFoundError(str(routine_id))
        return row

    async def list(
        self,
        session: AsyncSession,
        *,
        company_id: Optional[uuid.UUID] = None,
        status: Optional[RoutineStatus] = None,
    ) -> List[LLCRoutine]:
        stmt = select(LLCRoutine)
        if company_id is not None:
            stmt = stmt.where(LLCRoutine.company_id == company_id)
        if status is not None:
            stmt = stmt.where(LLCRoutine.status == status)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        session: AsyncSession,
        routine_id: uuid.UUID,
        *,
        cron_schedule: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        env: Optional[Dict[str, Any]] = None,
        status: Optional[RoutineStatus] = None,
    ) -> LLCRoutine:
        routine = await self.get(session, routine_id)
        if cron_schedule is not None:
            routine.cron_schedule = cron_schedule
        if name is not None:
            routine.name = name
        if description is not None:
            routine.description = description
        if env is not None:
            routine.env = env
        if status is not None:
            routine.status = status
        await session.flush()
        return routine

    async def delete(self, session: AsyncSession, routine_id: uuid.UUID) -> LLCRoutine:
        """Soft-delete: set status=ARCHIVED, never remove the row."""
        return await self.update(session, routine_id, status=RoutineStatus.ARCHIVED)

    # ------------------------------------------------------------------
    # Env resolution
    # ------------------------------------------------------------------

    async def resolve_env(
        self,
        session: AsyncSession,
        routine: LLCRoutine,
        *,
        agent_env: Optional[Dict[str, Any]] = None,
        project_env: Optional[Dict[str, Any]] = None,
        secret_service: Any = None,
    ) -> Dict[str, Any]:
        """Merge env layers (agent < project < routine < system) and resolve secrets."""
        merged: Dict[str, Any] = {}
        for layer in (agent_env or {}, project_env or {}, routine.env):
            merged.update(layer)

        # system keys always win
        import os
        for key, val in os.environ.items():
            if any(key.startswith(pfx) for pfx in _SYSTEM_KEY_PREFIXES):
                merged[key] = val

        # resolve "secret:<NAME>" references
        if secret_service is not None:
            for key, val in list(merged.items()):
                if isinstance(val, str) and val.startswith("secret:"):
                    secret_name = val[len("secret:"):]
                    try:
                        merged[key] = await secret_service.get(
                            session, str(routine.company_id), secret_name
                        )
                    except Exception as exc:
                        logger.warning("Secret resolution failed for %s: %s", key, exc)

        return merged

    # ------------------------------------------------------------------
    # Run recording
    # ------------------------------------------------------------------

    async def record_run(
        self,
        session: AsyncSession,
        routine_id: uuid.UUID,
        *,
        status: str = "queued",
    ) -> LLCRoutineRun:
        run = LLCRoutineRun(
            routine_id=routine_id,
            status=status,
            triggered_at=datetime.now(tz=timezone.utc),
        )
        session.add(run)
        await session.flush()
        return run

    async def list_runs(
        self,
        session: AsyncSession,
        routine_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> List[LLCRoutineRun]:
        stmt = (
            select(LLCRoutineRun)
            .where(LLCRoutineRun.routine_id == routine_id)
            .order_by(LLCRoutineRun.triggered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
