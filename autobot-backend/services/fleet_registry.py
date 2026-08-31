# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fleet membership, as the SLM node registry reports it (#15227, #15228).

The fleet is defined in the SLM database and reached over ``GET /api/nodes``.
Before this module the backend answered "which hosts are ours?" from a literal
tuple of seven SSOT attribute names, so a node the fleet gained was not a fleet
node as far as any guard reading that tuple was concerned. The SLM frontend's
terminal had the same literal in TypeScript. One authority now answers for
both: the node registry.

Two properties this module exists to hold:

* **Membership is data, not code.** A node enrolled in the SLM appears here
  with no edit; a node removed disappears.
* **A failed fetch never reads as an empty fleet.** ``FleetSnapshot.source``
  says where the answer came from, and the fallback is labelled rather than
  silent — an unreachable registry degrades to the SSOT-configured core hosts
  and *says so*, so a caller can report the degradation instead of showing a
  stale set as though it were current.

The snapshot is deliberately *not* a security decision on its own. It reports
which hosts the fleet contains; whether reaching one is permitted is
``services/browser_url_guard.py``'s question.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import TTL_1_MINUTE
from constants.network_constants import NetworkConstants

logger = get_logger(__name__)

#: The registry route on the SLM. Paginated; the guard wants every node, and
#: ``per_page`` is capped server-side, so the fetch pages until it has them all.
NODES_PATH = "/api/nodes"

#: Page size requested from ``GET /api/nodes``. The route validates this
#: against its own ceiling; keep it at or under that.
_NODES_PER_PAGE = 100

#: Hard stop on paging, so a registry that keeps reporting a larger ``total``
#: than it serves cannot spin this loop forever.
_MAX_PAGES = 50

#: Env-var-backed cache TTL. ``is_url_allowed`` runs on every navigate, and the
#: fleet changes at enrolment speed, not request speed.
_FLEET_REGISTRY_TTL_ENV = "AUTOBOT_FLEET_REGISTRY_TTL"


def _resolve_registry_ttl() -> int:
    """Cache TTL in seconds, from the environment, falling back to one minute."""
    raw = os.getenv(_FLEET_REGISTRY_TTL_ENV)
    if raw is None:
        return TTL_1_MINUTE
    try:
        ttl = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; falling back to %ds",
            _FLEET_REGISTRY_TTL_ENV,
            raw,
            TTL_1_MINUTE,
        )
        return TTL_1_MINUTE
    if ttl <= 0:
        logger.warning(
            "%s=%d must be positive; falling back to %ds",
            _FLEET_REGISTRY_TTL_ENV,
            ttl,
            TTL_1_MINUTE,
        )
        return TTL_1_MINUTE
    return ttl


FLEET_REGISTRY_TTL_SECONDS = _resolve_registry_ttl()

#: Where a snapshot's membership came from. Callers surface this rather than
#: presenting a degraded answer as a current one.
SOURCE_REGISTRY = "slm_node_registry"
SOURCE_FALLBACK = "ssot_fallback"

#: The fallback, used only when the registry cannot be read. These are the
#: SSOT config keys for the fleet's core hosts — the set this module replaces
#: as the *primary* source. It stays as a labelled degradation so an
#: unreachable SLM does not lock an operator out of the fleet's own machines,
#: and every consumer is told, via ``FleetSnapshot.source``, that that is what
#: it is looking at.
_FALLBACK_HOST_ATTRS = (
    "MAIN_MACHINE_IP",
    "FRONTEND_VM_IP",
    "NPU_WORKER_VM_IP",
    "REDIS_VM_IP",
    "AI_STACK_VM_IP",
    "BROWSER_VM_IP",
    "SLM_VM_IP",
)


@dataclass(frozen=True)
class FleetSnapshot:
    """What the fleet contained when this was read, and who said so."""

    #: Normalised addresses and hostnames of every node in the fleet.
    hosts: frozenset[str]
    #: ``SOURCE_REGISTRY`` or ``SOURCE_FALLBACK`` — never inferred by a caller.
    source: str
    #: Nodes the registry reported. ``0`` with ``SOURCE_REGISTRY`` means a
    #: genuinely empty fleet, which is a different fact from a failed read.
    node_count: int
    #: Why the fallback was used, when it was. ``None`` on a registry read.
    degraded_reason: str | None = None

    @property
    def is_degraded(self) -> bool:
        """True when membership did not come from the registry."""
        return self.source != SOURCE_REGISTRY


def _normalise(value: object) -> str:
    """Lowercase, strip whitespace and IPv6 brackets. ``""`` if unusable."""
    if not isinstance(value, str):
        return ""
    return value.strip().strip("[]").lower()


def _fallback_snapshot(reason: str) -> FleetSnapshot:
    """The SSOT-configured core hosts, explicitly labelled as a degradation."""
    hosts = set()
    for attr in _FALLBACK_HOST_ATTRS:
        try:
            value = getattr(NetworkConstants, attr, "")
        except Exception:  # config unavailable — report nothing rather than guess
            continue
        normalised = _normalise(value)
        if normalised:
            hosts.add(normalised)
    logger.warning("Fleet membership degraded to SSOT config: %s", reason)
    return FleetSnapshot(
        hosts=frozenset(hosts),
        source=SOURCE_FALLBACK,
        node_count=len(hosts),
        degraded_reason=reason,
    )


def _hosts_from_nodes(nodes: list[dict]) -> frozenset[str]:
    """Every address and hostname the registry gave for these nodes.

    Hostnames are included alongside addresses because an operator reaches a
    node by the name the registry knows it by. This widens nothing: a name is
    only ever consulted after the DNS guard has already found the target
    non-public, and a name resolving into private space is a fleet node
    precisely when the registry says it is one.
    """
    hosts = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for key in ("ip_address", "hostname", "ansible_name"):
            normalised = _normalise(node.get(key))
            if normalised:
                hosts.add(normalised)
    return frozenset(hosts)


async def _fetch_registry_nodes() -> list[dict]:
    """Every node in the SLM registry.

    Raises ``RuntimeError`` when the control link is not up, and whatever
    ``aiohttp`` raises when the request itself fails — the caller turns either
    into a labelled fallback rather than an empty fleet.
    """
    from services.slm_client import get_slm_client

    client = get_slm_client()
    if client is None:
        raise RuntimeError("SLM control link is not initialised")

    # Routed through the client's own URL builder so the direct-uvicorn vs
    # nginx-prefix decision (#13584) is made in exactly one place; a second
    # copy of that rule here is how that bug came back the first time.
    session = await client._get_session()
    url = client._rest_url(NODES_PATH)

    collected: list[dict] = []
    page = 1
    while page <= _MAX_PAGES:
        async with session.get(url, params={"page": str(page), "per_page": str(_NODES_PER_PAGE)}) as response:
            response.raise_for_status()
            payload = await response.json()
        batch = payload.get("nodes") or []
        collected.extend(node for node in batch if isinstance(node, dict))
        total = payload.get("total")
        if not batch or not isinstance(total, int) or len(collected) >= total:
            break
        page += 1
    return collected


class _SnapshotCache:
    """One in-flight fetch at a time, and a TTL so navigate is not a fan-out."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._snapshot: FleetSnapshot | None = None
        self._read_at: float = 0.0

    def _fresh(self) -> FleetSnapshot | None:
        if self._snapshot is None:
            return None
        if (time.monotonic() - self._read_at) >= self._ttl:
            return None
        return self._snapshot

    def clear(self) -> None:
        """Drop the cached snapshot. Used by tests and by an explicit refresh."""
        self._snapshot = None
        self._read_at = 0.0

    async def get(self, *, force_refresh: bool = False) -> FleetSnapshot:
        if not force_refresh:
            cached = self._fresh()
            if cached is not None:
                return cached
        async with self._lock:
            if not force_refresh:
                cached = self._fresh()
                if cached is not None:
                    return cached
            snapshot = await self._read()
            # A degraded read is cached too, but only so a hard-down SLM does
            # not mean one HTTP attempt per navigate; the TTL still expires it.
            self._snapshot = snapshot
            self._read_at = time.monotonic()
            return snapshot

    async def _read(self) -> FleetSnapshot:
        try:
            nodes = await _fetch_registry_nodes()
        except Exception as exc:  # unreachable, unauthorised, malformed — all degrade
            return _fallback_snapshot(f"SLM node registry unreadable ({type(exc).__name__})")
        return FleetSnapshot(
            hosts=_hosts_from_nodes(nodes),
            source=SOURCE_REGISTRY,
            node_count=len(nodes),
        )


_cache = _SnapshotCache(FLEET_REGISTRY_TTL_SECONDS)


async def fleet_snapshot(*, force_refresh: bool = False) -> FleetSnapshot:
    """The fleet's membership, from the SLM node registry.

    Never raises: an unreadable registry comes back as a ``SOURCE_FALLBACK``
    snapshot whose ``degraded_reason`` says why, so a caller can report the
    degradation instead of silently treating it as the current fleet.
    """
    return await _cache.get(force_refresh=force_refresh)


def reset_fleet_cache() -> None:
    """Forget the cached snapshot (tests, and config reloads)."""
    _cache.clear()
