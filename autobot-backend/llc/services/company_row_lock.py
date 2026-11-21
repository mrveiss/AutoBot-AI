# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Row lock on a company's ``organizations`` row (#15907).

A company soft-delete and a heartbeat enable both read ``deleted_at`` and then write.
Each takes this lock first, so whichever commits second sees the other's effect and an
agent can never be left heartbeating under a deleted company.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.organization import Organization


async def lock_organization(session: AsyncSession, company_id: uuid.UUID) -> Optional[Organization]:
    """``SELECT ... FOR UPDATE`` the organization row; ``None`` when it does not exist."""
    stmt = select(Organization).where(Organization.id == company_id).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()
