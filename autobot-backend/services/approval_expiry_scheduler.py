# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The periodic sweep that expires unanswered approvals (#18412).

``ApprovalGateService.expire_stale`` moves every pending approval past ``expires_at`` to EXPIRED
and resumes the work waiting on it, once. Without a caller, a request nobody answered kept its
source waiting for ever. This is that caller, on the shared ``PollLoopScheduler`` so it has the
same cancellation-safe drain as every other scheduler.

A sweep is a status transition. It deletes no approval, comment or link.
"""

from __future__ import annotations

from fastapi import FastAPI

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger
from llc.scheduler.base import PollLoopScheduler

logger = get_logger(__name__)

APPROVAL_EXPIRY_SWEEP_INTERVAL_S: float = env_float_clamped("AUTOBOT_APPROVAL_EXPIRY_SWEEP_INTERVAL_S", 60.0, min_v=1.0)


class ApprovalExpiryScheduler(PollLoopScheduler):
    """Calls ``ApprovalGateService.expire_stale`` every ``poll_interval`` seconds."""

    _task_name = "ApprovalExpiryScheduler"

    def __init__(self, poll_interval: float = APPROVAL_EXPIRY_SWEEP_INTERVAL_S) -> None:
        super().__init__(poll_interval)

    async def _tick(self) -> None:
        # A failed sweep is logged and the next tick retries: rows stay pending and are still
        # refused at decision time, so a missed sweep delays the resume, never the safety check.
        try:
            from services.approval_gate_service import ApprovalGateService
            from user_management.database import get_async_session_factory

            async with get_async_session_factory()() as session:
                expired = await ApprovalGateService(session).expire_stale()
            if expired:
                logger.info("ApprovalExpiryScheduler: expired %d stale approval(s)", expired)
        except Exception:
            logger.exception("ApprovalExpiryScheduler: sweep failed, retrying next interval")


async def start_approval_expiry_scheduler(app: FastAPI) -> None:
    """Start the sweep and keep it on ``app.state``; non-fatal, but loud when it does not start."""
    try:
        scheduler = ApprovalExpiryScheduler()
        scheduler.start()
        app.state.approval_expiry_scheduler = scheduler
        logger.info("Approval expiry scheduler: started, every %.0fs", scheduler._poll_interval)
    except Exception:
        app.state.approval_expiry_scheduler = None
        logger.exception("Approval expiry scheduler NOT started; unanswered approvals stay pending (#18412)")


async def stop_approval_expiry_scheduler(app: FastAPI) -> None:
    """Drain the sweep (bounded, shielded) at shutdown."""
    scheduler = getattr(app.state, "approval_expiry_scheduler", None)
    if scheduler:
        await scheduler.aclose()
