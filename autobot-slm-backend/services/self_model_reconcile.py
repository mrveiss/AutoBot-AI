# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure reconcile_observations of the self-model against what a producer just observed (#22277).

No database, no clock, no I/O: ``reconcile_observations`` takes the existing entity rows and one batch of
observations and returns the rows to upsert and the history to append, so install, removal,
upgrade and node silence are tested from fixtures. A removed entity is never deleted: it becomes
``absent`` with ``removed_at``. Producers record what they claim in ``attrs["source"]``; a batch
may only mark absent the entities whose source is its own, so one producer's silence never
erases another producer's entity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from autobot_shared.self_model_constants import ENTITY_KINDS

KINDS = ENTITY_KINDS

DECLARED = "declared"
PROBED_OK = "probed_ok"
PROBED_FAILED = "probed_failed"
ABSENT = "absent"
STALE = "stale"
STATUSES = (DECLARED, PROBED_OK, PROBED_FAILED, ABSENT, STALE)
#: What a producer may claim; ``absent`` and ``stale`` are only ever derived here.
OBSERVED_STATUSES = (DECLARED, PROBED_OK, PROBED_FAILED)
_PROBED = (PROBED_OK, PROBED_FAILED)
_UNAVAILABLE = (ABSENT, STALE)

_WHITESPACE = re.compile(r"\s+")


def _normal(text: str) -> str:
    """Canonical form of a name: trimmed, whitespace collapsed, case-folded."""
    return _WHITESPACE.sub(" ", text.strip()).casefold()


def entity_key(kind: str, name: str, parent_key: Optional[str] = None) -> str:
    """The stable identity of an entity, from its kind, normalised name and parent key."""
    if kind not in KINDS:
        raise ValueError(f"unknown self-model kind {kind!r}")
    base = f"{kind}:{_normal(name)}"
    return f"{parent_key}/{base}" if parent_key else base


@dataclass(frozen=True)
class Observation:
    """One producer's claim about one entity."""

    kind: str
    name: str
    status: str
    parent_key: Optional[str] = None
    node_id: Optional[str] = None
    version: Optional[str] = None
    attrs: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return entity_key(self.kind, self.name, self.parent_key)


@dataclass
class InventoryPlan:
    """Rows to upsert and history rows to append; ``changed`` is true when any status or version moved."""

    upserts: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.history)


def _history(key: str, event: str, old: Mapping[str, Any] | None, new: Mapping[str, Any], now: datetime) -> dict:
    return {
        "entity_key": key,
        "event": event,
        "old_status": old["status"] if old else None,
        "new_status": new["status"],
        "old_version": old.get("version") if old else None,
        "new_version": new.get("version"),
        "observed_at": now,
    }


def _created(obs: Observation, source: str, now: datetime) -> dict:
    return {
        "entity_key": obs.key,
        "kind": obs.kind,
        "name": obs.name,
        "parent_key": obs.parent_key,
        "node_id": obs.node_id,
        "status": obs.status,
        "version": obs.version,
        "first_seen": now,
        "last_seen": now,
        "removed_at": None,
        "attrs": {**obs.attrs, "source": source},
    }


def _next_status(existing: str, observed: str) -> str:
    """A probe sets the status; a declaration never downgrades a probed one, but revives an absent one."""
    if observed in _PROBED:
        return observed
    return DECLARED if existing == ABSENT else existing


def _updated(row: Mapping[str, Any], obs: Observation, source: str, now: datetime) -> dict:
    status = _next_status(row["status"], obs.status)
    owner = source if obs.status in _PROBED else row.get("attrs", {}).get("source", source)
    attrs = {**row.get("attrs", {}), **obs.attrs, "source": owner}
    return {
        **row,
        "node_id": obs.node_id or row.get("node_id"),
        "status": status,
        "version": obs.version if obs.version is not None else row.get("version"),
        "last_seen": now,
        "removed_at": None if status != ABSENT else row.get("removed_at"),
        "attrs": attrs,
    }


def _event(old: Mapping[str, Any], new: Mapping[str, Any]) -> Optional[str]:
    """The history event a row transition earns, or None when only ``last_seen`` moved."""
    if new["status"] != old["status"]:
        return "reappeared" if old["status"] == ABSENT else "status_changed"
    if new.get("version") != old.get("version"):
        return "version_changed"
    return None


def _absent(row: Mapping[str, Any], now: datetime) -> dict:
    return {**row, "status": ABSENT, "removed_at": now}


def reconcile_observations(
    existing: Mapping[str, Mapping[str, Any]],
    observed: Iterable[Observation],
    now: datetime,
    *,
    source: str,
    scope_kinds: Sequence[str],
    scope_parent: Optional[str] = None,
) -> InventoryPlan:
    """Fold *observed* (the complete batch of one producer's scope) into *existing* rows keyed by entity key.

    Entities of ``scope_kinds`` (under ``scope_parent`` when given) that this ``source`` owns and the batch no
    longer contains become ``absent``; an entity another source owns, or one never probed and declared elsewhere,
    is untouched, so a declared entity that is never probed stays ``declared``. Nothing is deleted.
    """
    plan = InventoryPlan()
    seen = set()
    for obs in observed:
        seen.add(obs.key)
        _fold(plan, existing.get(obs.key), obs, source, now)
    for key, row in existing.items():
        owned = row["kind"] in scope_kinds and row.get("attrs", {}).get("source") == source
        in_scope = scope_parent is None or row.get("parent_key") == scope_parent
        if owned and in_scope and key not in seen and row["status"] != ABSENT:
            gone = _absent(row, now)
            plan.upserts.append(gone)
            plan.history.append(_history(key, "removed", row, gone, now))
    return plan


def _fold(plan: InventoryPlan, row: Optional[Mapping[str, Any]], obs: Observation, source: str, now: datetime) -> None:
    if row is None:
        new = _created(obs, source, now)
        plan.upserts.append(new)
        plan.history.append(_history(new["entity_key"], "created", None, new, now))
        return
    new = _updated(row, obs, source, now)
    plan.upserts.append(new)
    event = _event(row, new)
    if event:
        plan.history.append(_history(new["entity_key"], event, row, new, now))


def mark_stale(rows: Iterable[Mapping[str, Any]], now: datetime, stale_after: timedelta) -> InventoryPlan:
    """Probed entities not seen within *stale_after* become ``stale``; declared and absent ones are left alone."""
    plan = InventoryPlan()
    for row in rows:
        if row["status"] in _PROBED and row["last_seen"] < now - stale_after:
            new = {**row, "status": STALE}
            plan.upserts.append(new)
            plan.history.append(_history(row["entity_key"], "status_changed", row, new, now))
    return plan


def touch(rows: Iterable[Mapping[str, Any]], now: datetime, source: str) -> InventoryPlan:
    """A node reported an unchanged inventory: its live ``source`` entities are seen now; ``stale`` ones revive."""
    plan = InventoryPlan()
    for row in rows:
        if row.get("attrs", {}).get("source") != source or row["status"] in (ABSENT, DECLARED):
            continue
        new = {**row, "last_seen": now, "status": PROBED_OK if row["status"] == STALE else row["status"]}
        plan.upserts.append(new)
        if new["status"] != row["status"]:
            plan.history.append(_history(row["entity_key"], "status_changed", row, new, now))
    return plan


def unavailable_because(row: Mapping[str, Any], by_key: Mapping[str, Mapping[str, Any]]) -> List[str]:
    """Names of commands an entity ``requires`` that are ``absent`` or ``stale`` on its node (empty: available)."""
    node_id = row.get("node_id")
    if not node_id:
        return []
    parent = entity_key("node", node_id)
    missing = []
    for name in row.get("attrs", {}).get("requires", []) or []:
        command = by_key.get(entity_key("command", name, parent))
        if command is not None and command["status"] in _UNAVAILABLE:
            missing.append(name)
    return missing


def rename_hosts(observed: List[Observation], node_ids_by_host: Mapping[str, str]) -> List[Observation]:
    """Observations that name their node by host address, renamed to the SLM's node id where the host is a node.

    A producer that knows a tool's placement from code only knows the SSOT host; the node entities are
    keyed by the node's own id. A host the SLM does not manage keeps the address it was given.
    """
    return [replace(o, node_id=node_ids_by_host.get(o.node_id or "", o.node_id)) for o in observed]
