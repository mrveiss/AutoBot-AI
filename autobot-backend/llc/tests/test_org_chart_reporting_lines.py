# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The org chart places people and agents in ONE hierarchy (#15763).

Split from ``test_llc_org_chart.py``, which is not grandfathered and was over
the plain 600-line limit — so the fix is a split by concern rather than a
ceiling entry. These tests cover reporting-line placement; that file keeps the
node-composition, status-mapping and lifecycle cases.

Fixtures are imported rather than duplicated. Re-exporting them is what makes
pytest resolve ``app`` / ``client`` / ``session_factory`` here, and it keeps one
definition of the harness: two copies would drift, and the copy that drifted
would still pass.
"""

from __future__ import annotations

import uuid

import pytest

from llc.tests.test_llc_org_chart import (  # noqa: F401
    _seed_org_node,
    app,
    client,
    engine,
    session_factory,
)
from models.agent_org import AgentOrgNode

# ---------------------------------------------------------------------------


async def _seed_person(session_factory, company_id: uuid.UUID, role: str = "member") -> uuid.UUID:  # noqa: ANN001
    """Seed one company membership and return its user id."""
    from llc.models.membership import LLCCompanyMembership

    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company_id, user_id=user_id, role=role))
        await session.commit()
    return user_id


async def _seed_reporting_line(  # noqa: ANN001
    session_factory,
    company_id: uuid.UUID,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    manager_type: str,
    manager_id: uuid.UUID,
) -> None:
    from llc.models.reporting_line import LLCReportingLine

    async with session_factory() as session:
        session.add(
            LLCReportingLine(
                id=uuid.uuid4(),
                company_id=company_id,
                subject_type=subject_type,
                subject_user_id=subject_id if subject_type == "user" else None,
                subject_agent_id=subject_id if subject_type == "agent" else None,
                manager_type=manager_type,
                manager_user_id=manager_id if manager_type == "user" else None,
                manager_agent_id=manager_id if manager_type == "agent" else None,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_a_person_is_placed_under_their_manager_not_appended_as_a_root(  # noqa: ANN001
    app, client, session_factory
):
    """People join the hierarchy instead of sitting beside it (#15763).

    Before this, memberships carried no reporting edge and every person was
    appended as a root — a company with twenty people rendered twenty roots
    with the agent hierarchy alongside, unconnected.

    The manager here is an **agent** and the report is a **person**, which is
    the combination that was previously unrepresentable in either direction:
    ``agent_org_nodes.reports_to`` holds an agent slug and could never name a
    person, and nothing placed a person at all.
    """
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    agent_slug = await _seed_org_node(session_factory, company_id, name="Chief Agent")
    async with session_factory() as session:
        from sqlalchemy import select as _select  # noqa: PLC0415

        row = (await session.execute(_select(AgentOrgNode).where(AgentOrgNode.agent_id == agent_slug))).scalar_one()
        agent_pk = row.id

    person_id = await _seed_person(session_factory, company_id)
    await _seed_reporting_line(
        session_factory,
        company_id,
        subject_type="user",
        subject_id=person_id,
        manager_type="agent",
        manager_id=agent_pk,
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]

    # One root, not two: the person is under the agent rather than beside it.
    assert len(nodes) == 1, nodes
    root = nodes[0]
    assert root["id"] == agent_slug
    assert len(root["children"]) == 1, root
    child = root["children"][0]
    assert child["id"] == f"user:{person_id}"
    assert child["is_human"] is True
    # The parent is the DISPLAY id. The reporting row stores the assignment
    # keyspace (AgentOrgNode.id), so a parent map built from that raw uuid
    # would render a node whose parent matches nothing and silently re-root it.
    assert child["parent_id"] == agent_slug


@pytest.mark.asyncio
async def test_a_person_with_no_reporting_line_still_appears(app, client, session_factory):  # noqa: ANN001
    """No line is not the same as no node.

    Until a CEO exists (#15770) an unplaced person has nothing to default to,
    and dropping them would lose the person entirely rather than showing them
    unplaced.
    """
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    person_id = await _seed_person(session_factory, company_id)

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]

    assert [n["id"] for n in nodes] == [f"user:{person_id}"]
    assert nodes[0]["parent_id"] is None


@pytest.mark.asyncio
async def test_another_companys_reporting_line_does_not_reparent_anyone(app, client, session_factory):  # noqa: ANN001
    """The reporting-line query is company-scoped.

    Without the filter, a line belonging to another company is loaded and
    applied here. It only bites when both ends happen to resolve in this
    chart — which is exactly what a shared user id across two companies
    produces, and it re-parents a real person using a relationship from a
    company the caller cannot see.
    """
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    app.state.tenant["org_id"] = str(mine)
    app.state.tenant["is_platform_admin"] = False

    boss_id = await _seed_person(session_factory, mine)
    # The same person is a member of both companies — the ordinary case for a
    # user who belongs to more than one.
    subject_id = await _seed_person(session_factory, mine)
    async with session_factory() as session:
        from llc.models.membership import LLCCompanyMembership

        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=theirs, user_id=subject_id, role="member"))
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=theirs, user_id=boss_id, role="member"))
        await session.commit()

    # The line exists only in the OTHER company.
    await _seed_reporting_line(
        session_factory,
        theirs,
        subject_type="user",
        subject_id=subject_id,
        manager_type="user",
        manager_id=boss_id,
    )

    resp = await client.get(f"/api/llc/companies/{mine}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]

    # Both people are roots here: this company records no reporting line.
    assert {n["id"] for n in nodes} == {f"user:{boss_id}", f"user:{subject_id}"}
    assert all(n["parent_id"] is None for n in nodes), nodes
