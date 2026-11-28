# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A template import ends with exactly ONE CEO-role node (#19643).

Two paths used to leave the template's default CEO node beside the real CEO:
the target already holds ``ceo-<target>``, and an explicit ``ceo_agent_id`` names
a different agent. Decision: the surplus node is imported as a normal agent with
its CEO ``org_role`` reset to ``worker`` -- never dropped.

SQLite harness, as in ``test_portability_ceo_19588``; the stand-in agent insert
additionally carries the template's ``org_role``, which those tests do not need.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

from llc.models.company import CompanyCreate
from llc.services.company import CompanyService
from llc.services.company_ceo import DEFAULT_CEO_ORG_ROLE, CompanyCEOService, default_ceo_slug
from llc.services.portability import PortabilityService
from llc.services.portability_ceo import CEO_EXPORT_KEY
from llc.tests import test_llc_org_chart as _org_chart_harness
from models.agent_org import AgentOrgNode

# The SQLite harness fixtures, re-exported so pytest finds them in this module.
engine = _org_chart_harness.engine
session_factory = _org_chart_harness.session_factory

SOURCE_ID = uuid.uuid4()
SOURCE_CEO = default_ceo_slug(SOURCE_ID)


async def _stand_in_import_agent(
    self, agent, company_id, secret_mapping, warnings, agent_id_map=None
):  # noqa: ANN001, ANN202
    slug = (agent_id_map or {}).get(agent.get("agent_id", "")) or str(uuid.uuid4())
    node = AgentOrgNode(
        id=uuid.uuid4(),
        agent_id=slug,
        name=agent.get("name", ""),
        company_id=company_id,
        org_role=agent.get("org_role", "worker"),
    )
    self.session.add(node)
    await self.session.flush()
    return slug


def _template(*agents: Dict[str, Any], ceo: str | None = None) -> Dict[str, Any]:
    company: Dict[str, Any] = {"id": str(SOURCE_ID), "name": "Imported", "slug": f"imp-{uuid.uuid4().hex[:8]}"}
    if ceo is not None:
        company[CEO_EXPORT_KEY] = ceo
    return {"schema_version": "1.0", "company": company, "agents": list(agents)}


def _source_ceo_node() -> Dict[str, Any]:
    return {"agent_id": SOURCE_CEO, "name": "Founder CEO", "org_role": DEFAULT_CEO_ORG_ROLE}


async def _import(session_factory, template, target=None) -> str:  # noqa: ANN001
    async with session_factory() as session:
        with (
            patch.object(PortabilityService, "_agent_names_exist", AsyncMock(return_value=[])),
            patch.object(PortabilityService, "_import_agent", _stand_in_import_agent),
        ):
            result = await PortabilityService(session).execute_import(template, target_company_id=target)
        await session.commit()
    return result["company_id"]


async def _nodes_and_designated(session_factory, company_id: str):  # noqa: ANN001, ANN202
    cid = uuid.UUID(company_id)
    async with session_factory() as session:
        stmt = sa.select(AgentOrgNode).where(AgentOrgNode.company_id == cid)
        nodes = list((await session.execute(stmt)).scalars().all())
        holder = await CompanyCEOService().resolve(session, cid)
    return {n.name: n for n in nodes}, holder


@pytest.mark.asyncio
async def test_importing_into_a_company_holding_its_ceo_leaves_one_ceo_role_node(session_factory):  # noqa: ANN001
    async with session_factory() as session:
        org = await CompanyService(session).create(CompanyCreate(name="Target", slug="target"))
        await session.commit()
    cid = await _import(session_factory, _template(_source_ceo_node()), target=org.id)

    by_name, holder = await _nodes_and_designated(session_factory, cid)
    ceo_role = [n for n in by_name.values() if n.org_role == DEFAULT_CEO_ORG_ROLE]
    assert [n.agent_id for n in ceo_role] == [default_ceo_slug(org.id)], "only the existing CEO keeps the CEO role"
    assert holder is not None and holder.id == ceo_role[0].id
    surplus = by_name["Founder CEO"]
    assert surplus.org_role == "worker", "imported as a normal agent, not dropped"
    assert surplus.agent_id != default_ceo_slug(org.id)


@pytest.mark.asyncio
async def test_a_different_explicit_designee_leaves_one_ceo_role_node(session_factory):  # noqa: ANN001
    hired = {"agent_id": "hired", "name": "Hired Boss", "org_role": DEFAULT_CEO_ORG_ROLE}
    cid = await _import(session_factory, _template(_source_ceo_node(), hired, ceo="hired"))

    by_name, holder = await _nodes_and_designated(session_factory, cid)
    ceo_role = [n.name for n in by_name.values() if n.org_role == DEFAULT_CEO_ORG_ROLE]
    assert ceo_role == ["Hired Boss"]
    assert holder is not None and holder.id == by_name["Hired Boss"].id
    surplus = by_name["Founder CEO"]
    assert surplus.org_role == "worker", "imported as a normal agent, not dropped"
    assert surplus.agent_id != default_ceo_slug(uuid.UUID(cid)), "the ceo-<id> slug is not left on a non-CEO"
