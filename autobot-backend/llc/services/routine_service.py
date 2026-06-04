# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC RoutineService — CRUD, env overlay, and secret resolution (GH#8229).

Env overlay order: agent_env < project_env < routine.env < system keys.
System keys injected unconditionally: ROUTINE_ID, COMPANY_ID, ROUTINE_NAME.
Secret resolution: env values matching "secret:<NAME>" resolved via SecretService.get().
Soft-delete: delete() sets status=archived; the row is never removed.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import RoutineStatus
from ..models.routine import LLCRoutine, LLCRoutineRun
from .base import LLCServiceBase
from .secret import SecretNotFound, SecretService

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(r"^secret:(.+)$")


class RoutineService(LLCServiceBase):
    """CRUD + run-recording + env resolution for LLC routines."""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        name: str,
        cron_schedule: str,
        produces: str,
        work_item_template: dict[str, Any],
        *,
        assignee_agent_id: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        env: Optional[dict[str, Any]] = None,
        recurring_work_item_id: Optional[uuid.UUID] = None,
    ) -> LLCRoutine:
        routine = LLCRoutine(
            company_id=company_id,
            name=name,
            cron_schedule=cron_schedule,
            produces=produces,
            work_item_template=work_item_template,
            assignee_agent_id=assignee_agent_id,
            description=description,
            env=env or {},
            recurring_work_item_id=recurring_work_item_id,
            status=RoutineStatus.ACTIVE,
        )
        session.add(routine)
        await session.flush()
        return routine

    async def get(
        self,
        session: AsyncSession,
        routine_id: uuid.UUID,
    ) -> Optional[LLCRoutine]:
        return await session.get(LLCRoutine, routine_id)

    async def list(
        self,
        session: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
        status: Optional[RoutineStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LLCRoutine]:
        stmt = select(LLCRoutine).limit(limit).offset(offset)
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
        **kwargs: Any,
    ) -> LLCRoutine:
        routine = await self.get(session, routine_id)
        if routine is None:
            raise ValueError(f"Routine {routine_id} not found")
        for key, value in kwargs.items():
            setattr(routine, key, value)
        await session.flush()
        return routine

    async def delete(
        self,
        session: AsyncSession,
        routine_id: uuid.UUID,
    ) -> None:
        routine = await self.get(session, routine_id)
        if routine is None:
            return
        routine.status = RoutineStatus.ARCHIVED
        await session.flush()
        try:
            from autobot_shared.redis_client import get_async_redis_client

            from ..scheduler.routine_scheduler import _SCHEDULE_KEY

            redis = await get_async_redis_client()
            if redis is not None:
                await redis.zrem(_SCHEDULE_KEY, f"routine:{routine_id}")
        except Exception as exc:
            logger.warning("Failed to remove routine %s from Redis schedule: %s", routine_id, exc)

    # ------------------------------------------------------------------
    # Run recording
    # ------------------------------------------------------------------

    async def record_run(
        self,
        session: AsyncSession,
        routine_id: uuid.UUID,
        status: str,
        *,
        heartbeat_run_id: Optional[uuid.UUID] = None,
        work_item_id: Optional[uuid.UUID] = None,
    ) -> LLCRoutineRun:
        run = LLCRoutineRun(
            routine_id=routine_id,
            status=status,
            heartbeat_run_id=heartbeat_run_id,
            work_item_id=work_item_id,
        )
        session.add(run)
        await session.flush()
        return run

    async def list_runs(
        self,
        session: AsyncSession,
        routine_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LLCRoutineRun]:
        stmt = (
            select(LLCRoutineRun)
            .where(LLCRoutineRun.routine_id == routine_id)
            .order_by(LLCRoutineRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Env overlay + secret resolution
    # ------------------------------------------------------------------

    async def resolve_env(
        self,
        session: AsyncSession,
        routine: LLCRoutine,
        *,
        agent_env: Optional[dict[str, Any]] = None,
        project_env: Optional[dict[str, Any]] = None,
        secret_service: Optional[SecretService] = None,
    ) -> dict[str, str]:
        """Merge env layers and resolve secret references.

        Layer order (later wins): agent_env → project_env → routine.env
        System keys always overwrite: ROUTINE_ID, COMPANY_ID, ROUTINE_NAME.
        Values matching "secret:<NAME>" are resolved via SecretService.get();
        if resolution fails, a WARNING is logged and the key is skipped.
        """
        merged: dict[str, Any] = {}
        for layer in (agent_env or {}, project_env or {}, routine.env or {}):
            merged.update(layer)

        # Inject system keys unconditionally
        merged["ROUTINE_ID"] = str(routine.id)
        merged["COMPANY_ID"] = str(routine.company_id)
        merged["ROUTINE_NAME"] = routine.name

        # Resolve secret references
        company_id_str = str(routine.company_id)
        resolved: dict[str, str] = {}
        for key, val in merged.items():
            if isinstance(val, str):
                m = _SECRET_RE.match(val)
                if m:
                    secret_name = m.group(1)
                    if secret_service is None:
                        logger.warning(
                            "Secret ref '%s' in env key '%s' skipped — no SecretService",
                            secret_name,  # codeql[py/clear-text-logging-sensitive-data]
                            key,
                        )
                        continue
                    try:
                        resolved[key] = await secret_service.get(session, company_id_str, secret_name)
                    except SecretNotFound:
                        logger.warning(
                            "Secret '%s' not found for company %s (env key '%s') — skipping",
                            secret_name,  # codeql[py/clear-text-logging-sensitive-data]
                            company_id_str,
                            key,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Secret resolution error for key '%s': %s — skipping",
                            key,
                            exc,
                        )
                    continue
            resolved[key] = str(val)

        return resolved
