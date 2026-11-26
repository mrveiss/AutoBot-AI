# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Persistence of the self-model in SLM Postgres, the system of record (#22277).

The decisions live in the pure ``services/self_model_reconcile``; this module loads the rows a
batch can touch, runs the decision and writes its plan. Nothing is deleted: removals are
``absent`` rows and every transition appends to ``self_model_history``.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.self_model_constants import STALE_AFTER
from models.database import Node
from models.self_model import self_model_entities as entities
from models.self_model import self_model_history as history
from services.node_capability import apply_capability_profile
from services.self_model_reconcile import (
    PROBED_FAILED,
    PROBED_OK,
    InventoryPlan,
    Observation,
    entity_key,
    mark_stale,
    reconcile_observations,
    rename_hosts,
    touch,
)

logger = get_logger(__name__)

INVENTORY_SOURCE = "inventory"
HEARTBEAT_SOURCE = "heartbeat"
_INVENTORY_KINDS = ("command", "package")
_SWEEP_MIN_GAP_S = 30.0
_last_sweep = 0.0


async def load_rows(db: AsyncSession, *conditions: Any) -> Dict[str, Dict[str, Any]]:
    """Entity rows matching *conditions*, keyed by entity key."""
    result = await db.execute(select(entities).where(*conditions))
    return {row.entity_key: dict(row._mapping) for row in result}


async def persist(db: AsyncSession, plan: InventoryPlan) -> None:
    """Upsert the plan's entity rows (one batched statement) and append its history rows."""
    by_key = {r["entity_key"]: {k: v for k, v in r.items() if k != "id"} for r in plan.upserts}
    if by_key:
        rows = list(by_key.values())
        stmt = pg_insert(entities)
        update = {c: stmt.excluded[c] for c in rows[0] if c != "entity_key"}
        await db.execute(stmt.on_conflict_do_update(index_elements=["entity_key"], set_=update), rows)
    if plan.history:
        await db.execute(history.insert(), plan.history)


async def revision(db: AsyncSession) -> int:
    """Id of the newest history row: it moves whenever any status or version changed."""
    return int((await db.execute(select(func.coalesce(func.max(history.c.id), 0)))).scalar_one())


async def node_ids_by_host(db: AsyncSession, hosts: set) -> Dict[str, str]:
    """The SLM node id of each of *hosts* (addresses) that is a managed node."""
    if not hosts:
        return {}
    found = await db.execute(select(Node.ip_address, Node.node_id).where(Node.ip_address.in_(hosts)))
    by_host: Dict[str, str] = {}
    for ip, node_id in sorted(found.all(), key=lambda pair: pair[1], reverse=True):
        if ip in by_host:
            logger.warning(
                "host %s is shared by nodes %s and %s; the self-model uses %s", ip, node_id, by_host[ip], node_id
            )
        by_host[ip] = (
            node_id  # reverse order, so the lowest node id wins and a shared address maps the same way each time
        )
    return by_host


async def apply_observations(
    db: AsyncSession, source: str, scope_kinds: Iterable[str], observed: List[Observation], now: datetime
) -> InventoryPlan:
    """Fold one producer's complete batch into the model and persist the result."""
    kinds = tuple(scope_kinds)
    observed = rename_hosts(observed, await node_ids_by_host(db, {o.node_id for o in observed if o.node_id}))
    existing = await load_rows(db, entities.c.kind.in_(kinds))
    plan = reconcile_observations(existing, observed, now, source=source, scope_kinds=kinds)
    await persist(db, plan)
    return plan


def _inventory_observations(node_id: str, inventory: Dict[str, Any]) -> List[Observation]:
    parent = entity_key("node", node_id)
    packages = [
        Observation(
            "package",
            name,
            PROBED_OK,
            parent_key=parent,
            node_id=node_id,
            version=str(version) if version is not None else None,
        )
        for name, version in (inventory.get("packages") or {}).items()
    ]
    commands = [
        Observation("command", name, PROBED_OK, parent_key=parent, node_id=node_id)
        for name in inventory.get("commands") or []
    ]
    return [*packages, *commands]


async def _inventory_plan(
    db: AsyncSession, node_id: str, extra: Dict[str, Any], previous: Optional[str], now
) -> InventoryPlan:
    """The inventory plan for one heartbeat: full reconcile, a touch when the hash is unchanged, else nothing."""
    parent = entity_key("node", node_id)
    rows = await load_rows(db, entities.c.parent_key == parent)
    if "inventory" in extra:
        if not isinstance(extra["inventory"], dict):
            logger.warning("node %s sent a malformed inventory; ignoring it", node_id)
            return InventoryPlan()
        observed = _inventory_observations(node_id, extra["inventory"])
        scope = {"source": INVENTORY_SOURCE, "scope_kinds": _INVENTORY_KINDS, "scope_parent": parent}
        return reconcile_observations(rows, observed, now, **scope)
    if extra.get("inventory_hash") == previous:
        return touch(rows.values(), now, INVENTORY_SOURCE)
    return InventoryPlan()


async def apply_heartbeat_inventory(
    db: AsyncSession, node_id: str, extra: Dict[str, Any], now: datetime
) -> InventoryPlan:
    """Fold one heartbeat's node liveness and inventory report into the model."""
    node_key = entity_key("node", node_id)
    node_rows = await load_rows(db, entities.c.entity_key == node_key)
    previous = node_rows.get(node_key, {}).get("attrs", {}).get("inventory_hash")
    plan = await _inventory_plan(db, node_id, extra, previous, now)
    # The stored hash advances only when the inventory it describes was actually folded in.
    reported = extra.get("inventory_hash")
    folded = "inventory" in extra or reported == previous
    attrs = {"inventory_hash": reported} if folded and reported else {}
    node_obs = Observation("node", node_id, PROBED_OK, node_id=node_id, attrs=attrs)
    node_plan = reconcile_observations(node_rows, [node_obs], now, source=HEARTBEAT_SOURCE, scope_kinds=())
    plan.upserts.extend(node_plan.upserts)
    plan.history.extend(node_plan.history)
    await persist(db, plan)
    return plan


async def sweep_stale(db: AsyncSession, now: datetime) -> InventoryPlan:
    """Mark probed entities that no producer has reported within the stale window ``stale``."""
    global _last_sweep
    if time.monotonic() - _last_sweep < _SWEEP_MIN_GAP_S:
        return InventoryPlan()
    _last_sweep = time.monotonic()
    probed = entities.c.status.in_((PROBED_OK, PROBED_FAILED))
    rows = await load_rows(db, probed, entities.c.last_seen < now - STALE_AFTER)
    plan = mark_stale(rows.values(), now, STALE_AFTER)
    await persist(db, plan)
    return plan


async def apply_heartbeat_extra_data(db: AsyncSession, node_id: str, extra_data: dict) -> None:
    """Everything one heartbeat's ``extra_data`` feeds: the capability profile, then the self-model (#22277)."""
    await apply_capability_profile(db, node_id, extra_data)
    now = datetime.now(timezone.utc)
    plan = await apply_heartbeat_inventory(db, node_id, extra_data, now)
    swept = await sweep_stale(db, now)
    if plan.changed or swept.changed:
        moves = len(plan.history) + len(swept.history)
        logger.info("self-model changed by node %s heartbeat (%d transitions)", node_id, moves)


def rows_for_response(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Entity rows without the surrogate id, in ``entity_key`` order.

    The key is unique and a heartbeat never changes it, so ``offset`` paging neither repeats nor skips a row
    when timestamps tie or move between page reads. A caller wanting newest-first sorts after the full read.
    """
    return sorted(({k: v for k, v in r.items() if k != "id"} for r in rows), key=lambda r: r["entity_key"])
