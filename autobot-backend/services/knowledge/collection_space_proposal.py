# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PROPOSE stamping a collection's embedding space on its metadata; never stamp it (#18143, #17038).

A collection that records no (model, dim) is searched on a dimension match alone. This raises one
approval-gate request asking a human to record the space on the collection; an already-pending request for
the same collection is reused, so a restart or a second process never files a duplicate. Nothing here
writes to the collection.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from models.approval import Approval, ApprovalStatus, ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.knowledge.collection_space_stamp_action import ACTION
from user_management.database import get_async_session_factory

logger = get_logger(__name__)

REQUESTER = "collection-space-proposal"
_TASKS: set[asyncio.Task] = set()


async def propose_stamp(collection: str, model: str, dim: int) -> bool:
    """File (or reuse) the pending stamp proposal for ``collection``. True when one is now pending."""
    try:
        async with get_async_session_factory()() as session:
            pending = await session.execute(
                select(Approval).where(
                    Approval.approval_type == ApprovalType.DESTRUCTIVE_ACTION.value,
                    Approval.status == ApprovalStatus.PENDING.value,
                    Approval.requested_by_agent == REQUESTER,
                )
            )
            if any((a.context or {}).get("collection") == collection for a in pending.scalars().all()):
                return True
            await ApprovalGateService(session).create_approval(
                title=f"Record INFERRED embedding space on '{collection}' (dimension match only, model unverified)",
                approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
                requested_by_agent=REQUESTER,
                description=(
                    f"The model '{model}' is INFERRED from a {dim}-d dimension match, not observed: the collection "
                    "records no model, and another model of the same dimension would match too. Approving writes "
                    f"({model}, {dim}-d) into its metadata as the recorded fact; existing keys are kept."
                ),
                context={"action": ACTION, "collection": collection, "model": model, "dim": dim},
            )
            return True
    except Exception as exc:
        logger.error("Could not raise the embedding-space stamp proposal for '%s': %s", collection, exc)
        return False


def schedule_stamp_proposal(collection: str, model: str, dim: int) -> None:
    """Raise the proposal from sync code: as a task on the running loop, else on a fresh one."""
    coro = propose_stamp(collection, model, dim)
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        asyncio.run(coro)
        return
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
