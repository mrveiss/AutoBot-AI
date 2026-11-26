# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One agent record: identity and capability, with health and presence as attributes (#22275).

``agent_records`` is the one place an agent is described. Its sources, joined on the unified agent
id (#11251):

- the declared profile (``AgentCapabilityRegistry``: capabilities, work boundary);
- live attributes written by their producers into ``autobot_shared.agent_attributes``: ``health``
  (``AgentHealthRegistry`` after each check) and ``presence`` (``AgentPresenceRegistry`` on each
  heartbeat). Both registries keep their own behaviour (the check throttle, the TTL, squat and tenant
  rules) and are producers of an attribute, not a second place to read an agent from;
- the DB-backed agents table (``AgentRegistryService``) as ``registered``;
- the Company OS org nodes (the rows ``llc.kb.capability_indexer`` indexes) as ``company_os``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select

from autobot_shared.agent_attributes import HEALTH_ATTR, PRESENCE_ATTR, get_agent_attribute_store
from autobot_shared.db_session import async_session_scope
from autobot_shared.service_registry_core import SERVICE_DEFINITIONS
from models.agent_org import AgentOrgNode
from orchestration.agent_registry import get_default_capability_registry
from orchestration.types import AgentProfile
from services.agent_registry_service import AgentRegistryService
from user_management.database import get_async_session_factory

AGENT_RECORD_KIND = "agent"
_SERVING_SERVICE = SERVICE_DEFINITIONS["backend"].name


def _profile_fields(profile: AgentProfile) -> Dict[str, Any]:
    """The declared identity/capability fields of one profile."""
    return {
        "agent_type": profile.agent_type,
        "capabilities": sorted(c.value for c in profile.capabilities),
        "specializations": list(profile.specializations),
        "allowed_work": list(profile.allowed_work),
        "forbidden_work": list(profile.forbidden_work),
        "availability_status": profile.availability_status,
        "max_concurrent_tasks": profile.max_concurrent_tasks,
    }


def _live_attrs(profile: AgentProfile, live: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """The health and presence attributes of one profile (None when its producer has not written one)."""
    own, by_type = live.get(profile.agent_id, {}), live.get(profile.agent_type, {})
    return {
        HEALTH_ATTR: own.get(HEALTH_ATTR, by_type.get(HEALTH_ATTR)),
        PRESENCE_ATTR: own.get(PRESENCE_ATTR),
    }


def _record(name: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """One agent as a catalogue record."""
    return {"kind": AGENT_RECORD_KIND, "name": name, "serving_service": _SERVING_SERVICE, "fields": fields}


def _registered_attr(agent: Any) -> Dict[str, Any]:
    """An agents-table row as the ``registered`` attribute."""
    return {
        "name": agent.name,
        "description": agent.description,
        "agent_type": agent.agent_type,
        "status": agent.status,
    }


def _company_os_attr(node: AgentOrgNode) -> Dict[str, Any]:
    """A Company OS org node as the ``company_os`` attribute."""
    return {
        "company_id": str(node.company_id) if node.company_id else None,
        "title": node.title,
        "org_role": node.org_role,
        "reports_to": node.reports_to,
        "capabilities": node.capabilities,
        "status": node.status,
    }


async def _stored_agents() -> Dict[str, Dict[str, Any]]:
    """``agent id -> {registered, company_os}`` from the agents table and the Company OS org nodes."""
    stored: Dict[str, Dict[str, Any]] = {}
    async with async_session_scope(get_async_session_factory()) as session:
        for agent in await AgentRegistryService(session).list_agents(limit=1000):
            stored.setdefault(agent.agent_id, {})["registered"] = _registered_attr(agent)
        for node in (await session.execute(select(AgentOrgNode))).scalars().all():
            stored.setdefault(node.agent_id, {})["company_os"] = _company_os_attr(node)
    return stored


async def agent_records() -> List[Dict[str, Any]]:
    """Every agent as one plain record (kind, stable name, serving service, declared fields).

    The union of the declared profiles, the agents table and the Company OS org nodes, one record per
    unified agent id. A stored agent with no declared profile carries only its stored and live attributes.
    """
    live = get_agent_attribute_store().snapshot()
    stored = await _stored_agents()
    profiles = get_default_capability_registry().get_all()
    records = {
        aid: {**_profile_fields(p), **_live_attrs(p, live), **stored.get(aid, {})} for aid, p in profiles.items()
    }
    for aid, attrs in stored.items():
        records.setdefault(aid, {PRESENCE_ATTR: live.get(aid, {}).get(PRESENCE_ATTR), HEALTH_ATTR: None, **attrs})
    return [_record(aid, fields) for aid, fields in sorted(records.items())]
