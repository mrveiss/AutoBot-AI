# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The CEO of a company created or filled by template import (#19588).

An export marks its CEO two ways, and import honours both:

* ``company.ceo_agent_id`` -- the agent slug holding the source company's CEO
  designation (:data:`CEO_EXPORT_KEY`), written by :func:`exported_ceo_agent_id`.
  Absent from templates exported before #19588, and ``None`` when the source's
  CEO is a user (a user is not portable).
* the ``ceo-<source company id>`` slug (:func:`default_ceo_slug`) of the source's
  provisioned default CEO node, which every export carries in ``agents``.

Owner decision (#19588): a template that carries a CEO keeps it -- that node is
designated, and no second default CEO is provisioned beside it. A template with
none gets the default. Either way the result goes through
:meth:`CompanyCEOService.sync_with_parent`, the single creation and move path.
The source's default CEO node is re-slugged to this company's ``ceo-<id>``, so
``sync_with_parent`` finds and designates it instead of creating another, and a
later demotion (#15907) retires it like any provisioned CEO.

The imported node's ``heartbeat_enabled`` is whatever the template carries
(off when absent); nothing here touches it.
"""

import uuid
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.agent_org import AgentOrgNode
from user_management.models.organization import Organization

from ..models.enums import RoleHolderType
from .company_ceo import CompanyCEOService, default_ceo_slug

logger = get_logger(__name__)

#: Where an export records which agent holds the CEO designation.
CEO_EXPORT_KEY = "ceo_agent_id"


async def exported_ceo_agent_id(session: AsyncSession, company_id: Any) -> Optional[str]:
    """The slug of the agent designated CEO of ``company_id``, or None.

    None when there is no designation, or its holder is a user: only agents
    travel in a template.
    """
    holder = await CompanyCEOService().resolve(session, uuid.UUID(str(company_id)))
    if holder is None or holder.type != RoleHolderType.AGENT.value:
        return None
    node = await session.get(AgentOrgNode, holder.id)
    return node.agent_id if node is not None else None


def _source_default_slug(template: Dict[str, Any]) -> Optional[str]:
    """The ``ceo-<id>`` slug the source company's default CEO node carried."""
    try:
        return default_ceo_slug(uuid.UUID(str((template.get("company") or {}).get("id"))))
    except ValueError:
        return None  # a hand-authored template with no (or no UUID) source id


async def mint_agent_ids(session: AsyncSession, template: Dict[str, Any], company_id: uuid.UUID) -> Dict[str, str]:
    """Pass 1 of import: a destination slug for every template agent, minted up front.

    Fresh UUIDs, except that the source's default CEO node takes this company's
    ``ceo-<id>`` slug -- unless the target already holds that slug (an import into
    an existing company), where the existing node stays the default CEO.
    """
    minted = {a["agent_id"]: str(uuid.uuid4()) for a in template.get("agents", []) if a.get("agent_id")}
    source_slug = _source_default_slug(template)
    if source_slug not in minted:
        return minted
    target_slug = default_ceo_slug(company_id)
    held = await session.execute(sa.select(AgentOrgNode.id).where(AgentOrgNode.agent_id == target_slug))
    if held.scalars().first() is None:
        minted[source_slug] = target_slug
    return minted


async def _landed_designee(
    session: AsyncSession, template: Dict[str, Any], company_id: uuid.UUID, landed: Dict[str, str]
) -> Optional[uuid.UUID]:
    """Row id of the agent the template designates CEO, if it landed in this company."""
    source = (template.get("company") or {}).get(CEO_EXPORT_KEY)
    dest_slug = landed.get(str(source)) if source else None
    if dest_slug is None:
        return None
    stmt = sa.select(AgentOrgNode.id).where(AgentOrgNode.agent_id == dest_slug, AgentOrgNode.company_id == company_id)
    return (await session.execute(stmt)).scalars().first()


async def settle_imported_ceo(
    session: AsyncSession, template: Dict[str, Any], company_id: uuid.UUID, landed: Dict[str, str]
) -> None:
    """Give the imported company exactly one CEO, in the import's transaction.

    An explicitly designated agent that landed is designated first, when the
    company is top-level and has no CEO yet -- an owner's existing choice is
    never displaced. ``sync_with_parent`` then settles the rest: it keeps that
    designation, designates the re-slugged imported default node, or provisions
    a fresh default when the template carried no CEO.
    """
    service = CompanyCEOService()
    org = await session.get(Organization, company_id)
    parent_org_id = org.parent_org_id if org is not None else None
    if parent_org_id is None and await service.designation(session, company_id) is None:
        designee = await _landed_designee(session, template, company_id, landed)
        if designee is not None:
            await service.set_ceo(session, company_id, RoleHolderType.AGENT.value, designee)
            logger.info("Imported company %s keeps its template's CEO %s", company_id, designee)
    await service.sync_with_parent(session, company_id, parent_org_id)
