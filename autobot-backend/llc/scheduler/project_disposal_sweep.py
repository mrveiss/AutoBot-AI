# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Celery-beat sweep: dispose due + approved pending_disposal projects (#11129 P2).

Runs nightly at 01:00 UTC. Selects LLCProject rows where lifecycle_state ==
'pending_disposal' and disposal_scheduled_at <= now(UTC), then disposes each
that passes the approval gate (no approval required, or LLCApproval.status ==
APPROVED).

Beat schedule entry:
    "llc-project-disposal-sweep": {
        "task": "llc.scheduler.project_disposal_sweep.run_disposal_sweep",
        "schedule": crontab(hour=1, minute=0),
    }

The schedule is registered in celery_app.py so that beat picks it up.
"""
import asyncio
import logging
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import or_, select

from llc.models.approval import LLCApproval
from llc.models.enums import ApprovalStatus
from llc.models.sprint import LLCProject
from llc.services.project_disposal import dispose
from user_management.database import get_async_session_factory

logger = logging.getLogger(__name__)


@shared_task(name="llc.scheduler.project_disposal_sweep.run_disposal_sweep", bind=True, max_retries=3)
def run_disposal_sweep(self: object) -> dict:  # type: ignore[type-arg]
    """Sync Celery entry point — disposes projects whose retention has elapsed."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    disposed = loop.run_until_complete(_async_sweep())
    return {"disposed": disposed}


async def _async_sweep() -> int:
    """Inner async body — select due pending_disposal projects and dispose them."""
    factory = get_async_session_factory()
    disposed = 0
    async with factory() as session:
        # A NULL disposal_scheduled_at means "no retention window" (approval-only
        # path): treat it as immediately due. A bare ``<= now`` would exclude NULL
        # rows via SQL three-valued logic, stranding approval-only projects forever.
        result = await session.execute(
            select(LLCProject).where(
                LLCProject.lifecycle_state == "pending_disposal",
                or_(
                    LLCProject.disposal_scheduled_at.is_(None),
                    LLCProject.disposal_scheduled_at <= datetime.now(timezone.utc),
                ),
            )
        )
        for project in result.scalars().all():
            if not await _is_disposal_allowed(project, session):
                continue
            await dispose(project, session)
            disposed += 1
        await session.commit()
    logger.info("Disposal sweep disposed %d project(s)", disposed)
    return disposed


async def _is_disposal_allowed(project: LLCProject, session: object) -> bool:
    """Approval-gated projects dispose only once their LLCApproval is APPROVED."""
    if project.disposal_approval_id is None:
        return True
    result = await session.execute(
        select(LLCApproval).where(LLCApproval.id == project.disposal_approval_id)
    )
    approval = result.scalar_one_or_none()
    return approval is not None and approval.status == ApprovalStatus.APPROVED.value


__all__ = ["run_disposal_sweep"]
