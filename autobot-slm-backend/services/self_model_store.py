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
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.self_model_constants import STALE_AFTER
from models.database import Node
from models.self_model import MAX_NAME_LENGTH, MAX_VERSION_LENGTH
from models.self_model import self_model_entities as entities
from models.self_model import self_model_history as history
from services.db_transaction_errors import write_in_savepoint
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


async def load_rows(db: AsyncSession, *conditions: Any, lock: bool = False) -> Dict[str, Dict[str, Any]]:
    """Entity rows matching *conditions*, keyed by entity key.

    ``lock`` takes a row lock on each match until the transaction ends, skipping rows another transaction holds:
    a row in someone else's write is being refreshed by them, so it is not this caller's to rewrite from a
    snapshot. The lock order is the database's ``ORDER BY`` collation, which need not equal ``persist``'s
    Python sort; ``skip_locked`` is what keeps the two from waiting on each other.
    """
    query = select(entities).where(*conditions)
    if lock:
        query = query.order_by(entities.c.entity_key).with_for_update(skip_locked=True)
    result = await db.execute(query)
    return {row.entity_key: dict(row._mapping) for row in result}


async def load_page(
    db: AsyncSession, conditions: List[Any], offset: int, limit: int
) -> Tuple[int, List[Dict[str, Any]]]:
    """``(total, rows)``: the match count and one ``entity_key``-ordered page, both counted and cut in the database.

    The key is unique and a heartbeat never changes it, so ``offset`` paging neither repeats nor skips a row.
    """
    total = (await db.execute(select(func.count()).select_from(entities).where(*conditions))).scalar_one()
    page = select(entities).where(*conditions).order_by(entities.c.entity_key).offset(offset).limit(limit)
    return int(total), [dict(row._mapping) for row in await db.execute(page)]


async def persist(db: AsyncSession, plan: InventoryPlan) -> None:
    """Upsert the plan's entity rows (one batched statement) and append its history rows."""
    by_key = {r["entity_key"]: {k: v for k, v in r.items() if k != "id"} for r in plan.upserts}
    if by_key:
        rows = [by_key[k] for k in sorted(by_key)]  # one lock order for every writer: no deadlock between batches
        stmt = pg_insert(entities)
        update = {c: stmt.excluded[c] for c in rows[0] if c != "entity_key"}
        await db.execute(stmt.on_conflict_do_update(index_elements=["entity_key"], set_=update), rows)
    if plan.history:
        await db.execute(history.insert(), plan.history)


async def revision(db: AsyncSession) -> int:
    """Id of the newest history row: it moves whenever any status or version changed."""
    return int((await db.execute(select(func.coalesce(func.max(history.c.id), 0)))).scalar_one())


async def _node_ids_by_host(db: AsyncSession, hosts: set) -> Dict[str, str]:
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
    observed = rename_hosts(observed, await _node_ids_by_host(db, {o.node_id for o in observed if o.node_id}))
    # Rows of the removal scope, plus a row for every observed key: a declaration outside the scope must still
    # meet the probed row it would otherwise overwrite.
    keys = [o.key for o in observed]
    existing = await load_rows(db, or_(entities.c.kind.in_(kinds), entities.c.entity_key.in_(keys)))
    plan = reconcile_observations(existing, observed, now, source=source, scope_kinds=kinds)
    await persist(db, plan)
    return plan


def _readable(node_id: str, inventory: Any) -> Optional[Dict[str, Any]]:
    """The readable part of *inventory*, or None when its shape is wrong (#22280).

    A mapping whose ``packages`` is a mapping and ``commands`` a list. Members that are not storable names
    are dropped and logged, so one bad member never blocks the rest or the hash and ack advancing.
    """
    if not isinstance(inventory, dict):
        return None
    packages, commands = inventory.get("packages") or {}, inventory.get("commands") or []
    if not isinstance(packages, dict) or not isinstance(commands, list):
        return None
    kept = {
        "packages": {name: version for name, version in packages.items() if _is_name(name)},
        "commands": [name for name in commands if _is_name(name)],
    }
    dropped = len(packages) + len(commands) - len(kept["packages"]) - len(kept["commands"])
    if dropped:
        logger.warning("node %s sent %d inventory members that are not storable names; dropped them", node_id, dropped)
    return kept


def _is_name(name: Any) -> bool:
    """A string the entity table can hold as a name: reconciliation strips it, and the column is bounded."""
    return isinstance(name, str) and 0 < len(name.strip()) <= MAX_NAME_LENGTH


def _inventory_observations(node_id: str, inventory: Dict[str, Any]) -> List[Observation]:
    parent = entity_key("node", node_id)
    packages = [
        Observation(
            "package",
            name,
            PROBED_OK,
            parent_key=parent,
            node_id=node_id,
            version=str(version)[:MAX_VERSION_LENGTH] if version is not None else None,
        )
        for name, version in (inventory.get("packages") or {}).items()
    ]
    commands = [
        Observation("command", name, PROBED_OK, parent_key=parent, node_id=node_id)
        for name in inventory.get("commands") or []
    ]
    return [*packages, *commands]


async def _inventory_plan(
    db: AsyncSession,
    node_id: str,
    extra: Dict[str, Any],
    readable: Optional[Dict[str, Any]],
    previous: Optional[str],
    now: datetime,
) -> InventoryPlan:
    """The inventory plan for one heartbeat: full reconcile, a touch when the hash is unchanged, else nothing.

    *readable* is the full inventory after ``_readable``; None when the report carried none or a misshapen one.
    """
    parent = entity_key("node", node_id)
    rows = await load_rows(db, entities.c.parent_key == parent)
    if "inventory" in extra:
        if readable is None:
            logger.warning("node %s sent a malformed inventory; ignoring it", node_id)
            return InventoryPlan()
        observed = _inventory_observations(node_id, readable)
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
    readable = _readable(node_id, extra["inventory"]) if "inventory" in extra else None
    plan = await _inventory_plan(db, node_id, extra, readable, previous, now)
    # The stored hash advances only when the inventory it describes was actually folded in.
    reported = extra.get("inventory_hash")
    # A malformed inventory is ignored by _inventory_plan, so it is not folded either (#22280).
    folded = readable is not None or reported == previous
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
    # Locked, so a heartbeat committing a fresh ``last_seen`` between this read and the write is not overwritten:
    # the lock re-checks the filter against the newest row, and a row mid-write is skipped.
    rows = await load_rows(db, probed, entities.c.last_seen < now - STALE_AFTER, lock=True)
    plan = mark_stale(rows.values(), now, STALE_AFTER)
    await persist(db, plan)
    return plan


async def acknowledged_inventory_hash(db: AsyncSession, node_id: str) -> Optional[str]:
    """The inventory hash folded into the model for *node_id*: the agent's proof its full report landed (#22280).

    Read separately from the heartbeat's own commit, so an inventory that failed to persist is simply not
    acknowledged while liveness is. An unreadable row is not acknowledged either.
    """
    try:
        rows = await load_rows(db, entities.c.entity_key == entity_key("node", node_id))
    except SQLAlchemyError as exc:
        logger.warning("cannot read the inventory ack of node %s: %r", node_id, exc)
        return None
    return rows.get(entity_key("node", node_id), {}).get("attrs", {}).get("inventory_hash")


async def apply_heartbeat_extra_data(db: AsyncSession, node_id: str, extra_data: dict) -> None:
    """Everything one heartbeat's ``extra_data`` feeds: the capability profile, then the self-model (#22277).

    Each in its own SAVEPOINT (#22280), so a failed self-model fold never rolls back the capability profile.
    """
    await write_in_savepoint(db, node_id, apply_capability_profile, extra_data)
    await write_in_savepoint(db, node_id, _fold_heartbeat, extra_data)


async def _fold_heartbeat(db: AsyncSession, node_id: str, extra_data: dict) -> None:
    """The self-model half of a heartbeat: node liveness and inventory, then the stale sweep."""
    now = datetime.now(timezone.utc)
    plan = await apply_heartbeat_inventory(db, node_id, extra_data, now)
    swept = await sweep_stale(db, now)
    if plan.changed or swept.changed:
        moves = len(plan.history) + len(swept.history)
        logger.info("self-model changed by node %s heartbeat (%d transitions)", node_id, moves)
