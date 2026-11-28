# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A company created by template import has exactly one CEO (#19588).

Owner decision: a template that carries a CEO keeps it, designated; one that
carries none gets the default; never both.

SQLite harness (``test_llc_org_chart``), like ``test_ceo_heartbeat_15907``. The
real ``execute_import`` runs -- savepoint, company creation, pass 1 minting and
the CEO step. Two helpers are swapped for SQLite: ``_agent_names_exist`` uses
Postgres' ``= ANY``, and ``_import_agent``'s raw INSERT binds UUIDs and casts to
``jsonb``. The stand-in inserts what the real one does: the pre-minted slug, the
name, and ``heartbeat_enabled`` exactly as the template carries it.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

from llc.models.company import CompanyCreate
from llc.services.company import CompanyService
from llc.services.company_ceo import CompanyCEOService, default_ceo_slug
from llc.services.portability import PortabilityService
from llc.services.portability_ceo import CEO_EXPORT_KEY, exported_ceo_agent_id
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
    node = AgentOrgNode(id=uuid.uuid4(), agent_id=slug, name=agent.get("name", ""), company_id=company_id)
    node.heartbeat_enabled = agent.get("heartbeat_enabled", False)
    self.session.add(node)
    await self.session.flush()
    return slug


def _template(*agents: Dict[str, Any], ceo: Optional[str] = None) -> Dict[str, Any]:
    company: Dict[str, Any] = {"id": str(SOURCE_ID), "name": "Imported", "slug": f"imp-{uuid.uuid4().hex[:8]}"}
    if ceo is not None:
        company[CEO_EXPORT_KEY] = ceo
    return {"schema_version": "1.0", "company": company, "agents": list(agents)}


async def _import(session_factory, template: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ANN001
    async with session_factory() as session:
        svc = PortabilityService(session)
        with (
            patch.object(PortabilityService, "_agent_names_exist", AsyncMock(return_value=[])),
            patch.object(PortabilityService, "_import_agent", _stand_in_import_agent),
        ):
            result = await svc.execute_import(template)
        await session.commit()
    return result


async def _state(session_factory, company_id: str):  # noqa: ANN001, ANN202
    """(every node in the company, the designated node or None)."""
    cid = uuid.UUID(company_id)
    async with session_factory() as session:
        nodes = (await session.execute(sa.select(AgentOrgNode).where(AgentOrgNode.company_id == cid))).scalars().all()
        holder = await CompanyCEOService().resolve(session, cid)
    designated = next((n for n in nodes if holder is not None and n.id == holder.id), None)
    return list(nodes), designated


def _template_with_its_ceo() -> Dict[str, Any]:
    return _template({"agent_id": SOURCE_CEO, "name": "Founder CEO"}, {"agent_id": "w1", "name": "Worker"})


@pytest.mark.asyncio
async def test_a_template_with_a_ceo_never_gets_a_second_one(session_factory):  # noqa: ANN001
    result = await _import(session_factory, _template_with_its_ceo())

    nodes, _ = await _state(session_factory, result["company_id"])
    assert sorted(n.name for n in nodes) == ["Founder CEO", "Worker"], "no default CEO is provisioned beside it"


@pytest.mark.asyncio
async def test_a_template_with_a_ceo_keeps_it_designated(session_factory):  # noqa: ANN001
    result = await _import(session_factory, _template_with_its_ceo())

    _, designated = await _state(session_factory, result["company_id"])
    assert designated is not None and designated.name == "Founder CEO", "the imported node is the CEO"
    assert designated.agent_id == default_ceo_slug(uuid.UUID(result["company_id"]))
    assert designated.heartbeat_enabled is False


@pytest.mark.asyncio
async def test_a_template_without_a_ceo_gets_the_default(session_factory):  # noqa: ANN001
    result = await _import(session_factory, _template({"agent_id": "w1", "name": "Worker"}))

    nodes, designated = await _state(session_factory, result["company_id"])
    assert designated is not None and designated.agent_id == default_ceo_slug(uuid.UUID(result["company_id"]))
    assert designated.heartbeat_enabled is False
    assert sorted(n.name for n in nodes) == ["CEO", "Worker"]


@pytest.mark.asyncio
async def test_an_explicit_designation_wins_and_the_heartbeat_is_the_templates(session_factory):  # noqa: ANN001
    """``company.ceo_agent_id`` names a hired agent: it is designated, nothing is provisioned."""
    tmpl = _template({"agent_id": "hired", "name": "Hired Boss", "heartbeat_enabled": True}, ceo="hired")
    result = await _import(session_factory, tmpl)

    nodes, designated = await _state(session_factory, result["company_id"])
    assert [n.name for n in nodes] == ["Hired Boss"]
    assert designated is nodes[0]
    assert designated.heartbeat_enabled is True, "the template's own value, never forced either way"


@pytest.mark.asyncio
async def test_an_export_names_its_ceo_and_a_round_trip_keeps_one(session_factory):  # noqa: ANN001
    async with session_factory() as session:
        org = await CompanyService(session).create(CompanyCreate(name="Src", slug=f"src-{uuid.uuid4().hex[:6]}"))
        await session.commit()
        exported = await exported_ceo_agent_id(session, org.id)
    assert exported == default_ceo_slug(org.id)

    tmpl = _template({"agent_id": exported, "name": "CEO"}, ceo=exported)
    tmpl["company"]["id"] = str(org.id)
    nodes, designated = await _state(session_factory, (await _import(session_factory, tmpl))["company_id"])
    assert len(nodes) == 1 and designated is nodes[0]
