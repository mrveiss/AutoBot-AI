# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""When A blocks B, B is the blocked item: the advancement check follows the mirror's direction (#20187)."""

# flake8: noqa: F811 -- imported pytest fixtures are redefined as test arguments
from __future__ import annotations

import uuid

import pytest

from llc.models.enums import WorkItemRelationType, WorkItemStatus
from llc.services.work_item_relations import WorkItemRelationService
from llc.tests.test_blocked_by_rule_fires_15931 import _item, engine, session  # noqa: F401 -- fixtures by name

pytestmark = pytest.mark.asyncio


async def _a_blocks_b(session, company, a_status, b_status):
    a = await _item(session, company, status=a_status, title="A, the blocker")
    b = await _item(session, company, status=b_status, title="B, the blocked")
    await WorkItemRelationService().add(
        session,
        company_id=company,
        source_id=str(a.id),
        target_id=str(b.id),
        relation_type=WorkItemRelationType.BLOCKS,
    )
    await session.commit()
    return a, b


async def test_the_blocked_item_has_an_unresolved_blocker_and_the_blocker_has_none(session):
    company = str(uuid.uuid4())
    a, b = await _a_blocks_b(session, company, WorkItemStatus.READY, WorkItemStatus.BLOCKED)
    svc = WorkItemRelationService()
    assert await svc.has_unresolved_blockers(session, str(b.id), company) is True
    assert await svc.has_unresolved_blockers(session, str(a.id), company) is False


async def test_a_finished_blocker_no_longer_holds_the_blocked_item(session):
    company = str(uuid.uuid4())
    _, b = await _a_blocks_b(session, company, WorkItemStatus.DONE, WorkItemStatus.BLOCKED)
    assert await WorkItemRelationService().has_unresolved_blockers(session, str(b.id), company) is False
