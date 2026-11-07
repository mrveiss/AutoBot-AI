# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Seed a ``blocked_by`` relation in the one direction the model defines (#15931, #20187).

``blocked_by`` reads source-is-blocked-by-target, so the blocked item is the source. Both the service-level
and the route-level tests seed through this, so they cannot disagree about it.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.enums import WorkItemRelationType
from llc.services.work_item_relations import WorkItemRelationService


async def block(session: AsyncSession, company: str, blocker, blocked) -> None:  # noqa: ANN001
    """Record that *blocked* is blocked by *blocker*, and commit."""
    await WorkItemRelationService().add(
        session,
        company_id=company,
        source_id=str(blocked.id),
        target_id=str(blocker.id),
        relation_type=WorkItemRelationType.BLOCKED_BY,
    )
    await session.commit()
