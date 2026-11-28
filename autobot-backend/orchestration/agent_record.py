# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One agent record: identity and capability, with health and presence as attributes (#22275).

Agents were described by parallel registries: ``AgentCapabilityRegistry`` (identity and
capability profile), ``AgentHealthRegistry`` (is it alive), ``AgentPresenceRegistry`` (is it
busy). Each stays the *store* of its own facts; this module is the one *record* that joins
them on the agent id, so a reader (the self-model, an API) asks one question and gets one
plain dict per agent. ``AgentRegistryService`` (the durable DB rows) and the Company OS KB
index (``llc.kb.capability_indexer``) are persistence/index projections of the same
identity, not live registries, and are intentionally not read here (async, per-company).

#11251 already unified the agent-id namespace (routing ids are profile ids); this joins the
live-status stores onto those ids.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from autobot_shared.service_registry_core import SERVICE_DEFINITIONS
from orchestration.agent_registry import get_default_capability_registry
from orchestration.types import AgentProfile
from protocols.agent_presence import PresenceEntry, get_presence_registry

AGENT_RECORD_KIND = "agent"
_SERVING_SERVICE = SERVICE_DEFINITIONS["backend"].name


def _presence_attr(entry: PresenceEntry | None) -> Dict[str, Any] | None:
    """A presence entry as the record's ``presence`` attribute (None when not live)."""
    if entry is None:
        return None
    return {
        "busy": entry.busy,
        "instance_id": entry.instance_id,
        "last_seen": entry.last_seen,
        "detail": entry.detail,
        "task": {"id": entry.task.id, "title": entry.task.title} if entry.task else None,
    }


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


def _record(profile: AgentProfile, health: Mapping[str, Any], presence: Mapping[str, PresenceEntry]) -> Dict[str, Any]:
    """Join one profile with its health and presence attributes."""
    attrs = {
        "health": health[profile.agent_type].to_dict() if profile.agent_type in health else None,
        "presence": _presence_attr(presence.get(profile.agent_id)),
    }
    return {
        "kind": AGENT_RECORD_KIND,
        "name": profile.agent_id,
        "serving_service": _SERVING_SERVICE,
        "fields": {**_profile_fields(profile), **attrs},
    }


def agent_records(health_registry: Any | None = None) -> List[Dict[str, Any]]:
    """Every agent as one plain record (kind, stable name, serving service, declared fields).

    ``health_registry`` is the running ``AgentHealthRegistry`` (it lives on the ``AgentClient``
    instance, so the caller passes it); without one, ``health`` is None for every agent.
    Presence is read from the process presence registry (shared and unscoped by tenant here
    only for the install-wide projection, as ``snapshot_for_projection`` documents).
    """
    health = health_registry.agent_health if health_registry is not None else {}
    presence = {e.name: e for e in get_presence_registry().snapshot_for_projection()}
    profiles = get_default_capability_registry().get_all()
    return [_record(p, health, presence) for _, p in sorted(profiles.items())]
