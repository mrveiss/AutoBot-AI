# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which sprints a request may reach."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.sprint import LLCSprint


async def require_sprint_in_org(session: AsyncSession, sprint_id: uuid.UUID, org_id: object) -> None:
    """404 unless the sprint belongs to the caller's org (IDOR guard, #10148)."""
    sprint = (await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id))).scalar_one_or_none()
    if sprint is None or str(sprint.company_id) != str(org_id):
        raise HTTPException(status_code=404, detail="Sprint not found")
