# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A hire's manager is checked again when the board approves it, not only when it was requested (#20422)."""

# flake8: noqa: F811 -- fixtures imported from the support module are re-bound as parameters
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, update

from llc.models.enums import ApprovalStatus, ApprovalType
from llc.services.approval import ApprovalHookError
from llc.tests.approval_enforcement_support_test import _edges  # noqa: F401 -- autouse fixture
from llc.tests.approval_enforcement_support_test import activity  # noqa: F401 -- fixture
from llc.tests.approval_enforcement_support_test import session_factory  # noqa: F401 -- fixture
from llc.tests.approval_enforcement_support_test import _ORG, _decide, _request, _rows
from models.agent_org import AgentOrgNode
from models.approval import Approval


def _payload(reports_to: str) -> dict:
    return {
        "agent_id": "newbie",
        "agent_name": "Newbie",
        "org_role": "worker",
        "reports_to": reports_to,
        "adapter_config": {},
        "model": "m",
        "instructions_file_path": "/x",
    }


async def _seed_manager(session_factory) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(AgentOrgNode(id=uuid.uuid4(), agent_id="boss", name="Boss", company_id=_ORG))
        await session.commit()


async def _assert_refused_and_pending(session_factory, approval_id) -> None:  # noqa: ANN001
    with pytest.raises(ApprovalHookError, match="no longer an agent of this company"):
        await _decide(session_factory, approval_id, ApprovalStatus.APPROVED)
    assert all(n.agent_id != "newbie" for n in await _rows(session_factory, AgentOrgNode))
    assert [a.status for a in await _rows(session_factory, Approval)] == [ApprovalStatus.PENDING.value]


@pytest.mark.asyncio
async def test_a_manager_deleted_before_approval_leaves_the_hire_pending(session_factory) -> None:  # noqa: ANN001
    await _seed_manager(session_factory)
    approval_id = await _request(session_factory, ApprovalType.HIRE, _payload("boss"))
    async with session_factory() as session:
        await session.execute(delete(AgentOrgNode).where(AgentOrgNode.agent_id == "boss"))
        await session.commit()
    await _assert_refused_and_pending(session_factory, approval_id)


@pytest.mark.asyncio
async def test_a_manager_moved_to_another_company_leaves_the_hire_pending(session_factory) -> None:  # noqa: ANN001
    await _seed_manager(session_factory)
    approval_id = await _request(session_factory, ApprovalType.HIRE, _payload("boss"))
    async with session_factory() as session:
        await session.execute(
            update(AgentOrgNode).where(AgentOrgNode.agent_id == "boss").values(company_id=uuid.uuid4())
        )
        await session.commit()
    await _assert_refused_and_pending(session_factory, approval_id)


@pytest.mark.asyncio
async def test_a_manager_still_in_the_company_lets_the_hire_through(session_factory) -> None:  # noqa: ANN001
    await _seed_manager(session_factory)
    approval_id = await _request(session_factory, ApprovalType.HIRE, _payload("boss"))
    await _decide(session_factory, approval_id, ApprovalStatus.APPROVED)
    hired = [n for n in await _rows(session_factory, AgentOrgNode) if n.agent_id == "newbie"]
    assert [n.reports_to for n in hired] == ["boss"]
