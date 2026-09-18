#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Live agent presence — one registry, all three internal kinds (#16947).

Discovery today is four unconnected registries (tagged #6828 throughout the
codebase), none of them a live, named "who is here and are they busy" view:
`agent_client.AgentHealthRegistry` tracks AI-stack health, not busy/idle;
`agent_orchestration.distributed_management.DistributedAgentManager` tracks
distributed AI-stack agents' active tasks; `services.agent_terminal`'s
`SessionManager` holds live terminal sessions; `models.agent_org.AgentOrgNode`
plus its heartbeat runs give Company OS agents' last-known state. This module
is the fifth thing #16946/#16947 explicitly say not to build: instead it is a
live table that each of those sources reports INTO (`report`/`heartbeat`),
not a duplicate store of what they already know.

`EXTERNAL` identities (admitted A2A peers) are refused at `report()` --
owner decision 3 on #16946: external peers get identity for attribution only
and never appear in discovery.

`report()`/`deregister()` enforce no caller identity of their own -- the
authoritative-source guarantee (#16946 §2) holds only because the three
adapters in `agent_presence_feeds` are the sole intended callers, each
reading a source that itself is the gate. Do not call either from anything
else without adding a real check here first.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from threading import Lock

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from protocols.agent_kind import AgentKind

logger = get_logger(__name__)

#: Reserved tenant_id for "we could not determine this entity's tenant" --
#: distinct from `None` (deliberately shared infrastructure, visible to every
#: tenant). Never returned by a tenant-scoped `list_live()` query: unlike
#: `None`, an unknown entry fails closed rather than becoming globally
#: visible by default (#16947 review).
UNKNOWN_TENANT = "__presence_unknown_tenant__"

#: How long a reporting agent's entry stays live with no further heartbeat.
#: An agent that stops reporting (crashed, network partition, clean exit that
#: skipped deregister) must leave the list within a bounded time, not linger
#: forever -- this is that bound.
PRESENCE_TTL_ENV = "AUTOBOT_AGENT_PRESENCE_TTL_SECONDS"
DEFAULT_PRESENCE_TTL_SECONDS = 90.0


def presence_ttl_seconds() -> float:
    """The staleness bound in seconds; the default when the var is unusable."""
    raw = os.getenv(PRESENCE_TTL_ENV, "")
    try:
        return float(raw or DEFAULT_PRESENCE_TTL_SECONDS)
    except ValueError:
        logger.warning("%s=%r is not a float; using default %.1fs", PRESENCE_TTL_ENV, raw, DEFAULT_PRESENCE_TTL_SECONDS)
        return DEFAULT_PRESENCE_TTL_SECONDS


class PresenceNameCollisionError(Exception):
    """Raised when `report()` would silently overwrite a *different* live entry.

    Design (#16946 §2): a name collision is rejected, never silently
    overwritten -- that is how a rogue or restarted-without-cleanup process
    would squat a name a caller still expects to reach the original holder.
    """


class ExternalIdentityExcludedError(Exception):
    """Raised when `report()` is called with `kind=AgentKind.EXTERNAL`.

    Owner decision 3 on #16946: external A2A peers get identity for
    attribution only and are never discoverable, never discover others.
    """


PresenceKey = tuple[AgentKind, str | None, str]


@dataclass(frozen=True)
class PresenceEntry:
    """One live agent, as `list_live()` reports it."""

    kind: AgentKind
    tenant_id: str | None
    name: str
    busy: bool
    instance_id: str
    detail: str | None = None
    last_seen: float = field(default_factory=time.time)


@dataclass
class _Record:
    instance_id: str
    busy: bool
    detail: str | None
    last_seen: float


class AgentPresenceRegistry:
    """One live table of `(kind, tenant_id, name) -> busy/idle`, TTL-bounded.

    In-memory and process-local, matching every one of the four registries
    it consolidates -- none of them is cross-process either (#16946 §6: this
    replaces overlapping *live-status* registries, not the durable identity
    or static-capability rows, which stay where they are).
    """

    def __init__(self, *, ttl_seconds: float | None = None) -> None:
        self._ttl = ttl_seconds if ttl_seconds is not None else presence_ttl_seconds()
        self._entries: dict[PresenceKey, _Record] = {}
        self._lock = Lock()

    def report(
        self,
        *,
        kind: AgentKind,
        tenant_id: str | None,
        name: str,
        instance_id: str,
        busy: bool,
        detail: str | None = None,
    ) -> None:
        """Upsert one agent's live status. Call again to heartbeat.

        A second `report()` for the same `(kind, tenant_id, name)` from a
        DIFFERENT `instance_id` is the squat case and is rejected -- the
        same instance re-reporting (the ordinary heartbeat) always succeeds.
        """
        if kind is AgentKind.EXTERNAL:
            logger.warning("presence report refused: %r is EXTERNAL (#16946 dec. 3)", name)
            raise ExternalIdentityExcludedError(f"{name!r} is EXTERNAL -- refused, not discoverable (#16946 dec. 3)")
        key = (kind, tenant_id, name)
        now = time.time()
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None and existing.instance_id != instance_id and now - existing.last_seen < self._ttl:
                logger.warning(
                    "presence report refused: %r (%s, tenant=%r) is live under instance %r; refusing %r",
                    name,
                    kind.value,
                    tenant_id,
                    existing.instance_id,
                    instance_id,
                )
                raise PresenceNameCollisionError(
                    f"{name!r} ({kind.value}, tenant={tenant_id!r}) is already live under instance "
                    f"{existing.instance_id!r}; refusing instance {instance_id!r}"
                )
            self._entries[key] = _Record(instance_id=instance_id, busy=busy, detail=detail, last_seen=now)

    def deregister(self, *, kind: AgentKind, tenant_id: str | None, name: str, instance_id: str) -> None:
        """Explicit removal (clean shutdown) -- only the reporting instance may do this."""
        key = (kind, tenant_id, name)
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None and existing.instance_id == instance_id:
                del self._entries[key]

    def list_live(self, tenant_id: str | None = None) -> list[PresenceEntry]:
        """Live agents visible to *tenant_id*: that tenant's own plus shared.

        Never returns an `UNKNOWN_TENANT` entry, regardless of *tenant_id* --
        unknown fails closed, it does not become visible to whoever happens
        to ask. Pass `None` (the default) for shared infrastructure only,
        with no tenant-owned entries -- there is no unscoped "every tenant"
        query here on purpose; a caller that needs one reimplements the leak
        this replaces.

        Stale entries (no heartbeat within `ttl_seconds`) are pruned here,
        not on a timer -- the bounded-time guarantee is enforced at read
        time, so it holds regardless of how often this is called.
        """
        if tenant_id == UNKNOWN_TENANT:
            tenant_id = None  # UNKNOWN_TENANT is never a valid query scope; fail closed to shared-only.
        now = time.time()
        with self._lock:
            live = {k: v for k, v in self._entries.items() if now - v.last_seen < self._ttl}
            self._entries = live
            return [
                PresenceEntry(
                    kind=kind,
                    tenant_id=key_tenant,
                    name=name,
                    busy=rec.busy,
                    instance_id=rec.instance_id,
                    detail=rec.detail,
                    last_seen=rec.last_seen,
                )
                for (kind, key_tenant, name), rec in live.items()
                if key_tenant is None or key_tenant == tenant_id
            ]


get_presence_registry = lazy_singleton(AgentPresenceRegistry)
