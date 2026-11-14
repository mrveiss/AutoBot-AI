# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who may read which knowledge-graph bucket record (#20945, #16665, #19860).

There is no second filter. A bucket record is shaped like a fact (``owner_id`` from the record's
``owner_id`` or ``user_id``, ``organization_id`` from its ``organization_id``/``company_id``/``tenant_id``)
and goes through ``filter_search_results_by_permission``, the one filter the facts path uses. A record
without an owner is therefore hidden from non-admins. An admin read passes ``is_admin``, and the records
on the returned page are recorded in the request's ``AdminReadLedger`` (``record_page``), so the
``kb.admin_read`` entry the route commits names every record the admin is shown. There is no graph-only
organisational-unit rule: ``KnowledgeOwnership.check_access`` returns True for an admin read, so an admin
sees in the graph what an admin sees everywhere else in the KB.

Access by section kind: ``public`` is the product's own documentation and code analysis (no per-user
owner, api/knowledge_search_documentation.py module docstring), ``owner`` holds per-user records, and
``tenant_admin`` holds per-company/project/work-item/agent buckets for admins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from knowledge.quarantine import not_quarantined
from knowledge.search_filters import extract_user_context_from_request, filter_search_results_by_permission

PUBLIC = "public"
OWNER = "owner"
TENANT_ADMIN = "tenant_admin"
_OWNER_KEYS = ("owner_id", "user_id")
_TENANT_KEYS = ("organization_id", "company_id", "tenant_id")
UNSCOPED_SOURCE = (
    "default"  # the source_id the code indexers write for AutoBot's own code (pattern_analysis/storage.py)
)


@dataclass(frozen=True)
class Viewer:
    """The caller of one graph read: identity, organisational unit, and the admin ledger (False for a non-admin)."""

    user_id: str
    company_id: str | None
    group_ids: tuple
    ledger: Any = False

    @property
    def admin_read(self) -> bool:
        """The route passed an ``AdminReadLedger``: an admin read decided upstream, not a second admin check."""
        return bool(self.ledger)


def viewer_for(current_user, ledger) -> Viewer:
    """The :class:`Viewer` of an authenticated caller; *ledger* is the route's ``admin_read_audit`` value."""
    user_id, org_id, group_ids = extract_user_context_from_request(current_user)
    return Viewer(user_id, org_id, tuple(group_ids), ledger)


def first_of(meta: Dict[str, Any], keys: tuple) -> str | None:
    """The first non-empty value of *keys* in *meta*, as a string."""
    found = next((meta[k] for k in keys if meta.get(k)), None)
    return str(found) if found else None


def tenant_of(meta: Dict[str, Any]) -> str | None:
    """The organisational unit a record names, or None for a unit-less record."""
    return first_of(meta, _TENANT_KEYS)


def as_fact(collection: str, record_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """A bucket record in the shape the fact filter reads: ``id`` plus ownership ``metadata``."""
    metadata = dict(meta)
    metadata["owner_id"] = first_of(meta, _OWNER_KEYS)
    metadata["organization_id"] = tenant_of(meta)
    return {"id": f"bucket:{collection}:{record_id}", "metadata": metadata}


async def _may_read_source(source_id: str, viewer: Viewer) -> bool:
    """Whether the viewer may read code source *source_id*: the codebase-analytics source authorisation (#12358).

    Not found or not visible is False; an unreachable registry (503) propagates, so the collection reads as unreadable.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    from api.codebase_analytics.endpoints.shared import authorize_source_access  # noqa: PLC0415 -- heavy router stack

    try:
        await authorize_source_access(source_id, {"id": viewer.user_id})
    except HTTPException as exc:
        if exc.status_code == 404:
            return False
        raise
    return True


async def _readable_sources(named: set, viewer: Viewer, decided: Dict[str, bool]) -> set:
    """The sources of *named* the viewer may read; each is asked once into *decided* (a registry read per source)."""
    for sid in named - decided.keys():
        decided[sid] = await _may_read_source(sid, viewer)  # a fault propagates and is never cached
    return {sid for sid in named if decided[sid]}


async def _readable_public(
    collection: str, rows: List[Dict[str, Any]], viewer: Viewer, decided: Dict[str, bool]
) -> List[Dict[str, Any]]:
    """Public rows minus quarantined ones, and minus those of a code source the viewer may not read."""
    rows = [r for r in rows if not_quarantined(as_fact(collection, r["id"], r.get("metadata") or {}))]
    named = {(r.get("metadata") or {}).get("source_id") for r in rows} - {None, "", UNSCOPED_SOURCE}
    allowed = await _readable_sources(named, viewer, decided)
    return [r for r in rows if (r.get("metadata") or {}).get("source_id") in allowed | {None, "", UNSCOPED_SOURCE}]


async def visible_records(
    kind: str,
    collection: str,
    rows: List[Dict[str, Any]],
    viewer: Viewer,
    ownership_manager,
    decided_sources: Dict[str, bool] | None = None,
) -> List[Dict[str, Any]]:
    """The *rows* (``id``, ``metadata``) the viewer may read; an admin's are recorded in the ledger.

    *decided_sources* carries the code-source decisions of one viewer across the windows of one scan, so a source
    is authorised once per scan, not once per window; the row filter itself still runs on every row.
    """
    if kind == PUBLIC:
        return await _readable_public(collection, rows, viewer, {} if decided_sources is None else decided_sources)
    facts = [as_fact(collection, r["id"], r.get("metadata") or {}) for r in rows]
    facts = [f for f in facts if not_quarantined(f)]
    kept = await filter_search_results_by_permission(
        facts,
        viewer.user_id,
        viewer.company_id,
        list(viewer.group_ids),
        ownership_manager=ownership_manager,
        is_admin=viewer.admin_read,  # the ledger records only the page the route returns
    )
    allowed = {f["id"] for f in kept}
    return [r for r in rows if f"bucket:{collection}:{r['id']}" in allowed]


def record_page(viewer: Viewer, section_access: str, page: List[tuple]) -> None:
    """Record the admin-gated records of a returned page (``(collection, id, metadata)``) in the ledger (#19860)."""
    if viewer.admin_read and section_access != PUBLIC:
        viewer.ledger.record([{"id": f"bucket:{name}:{rid}"} for name, rid, _ in page])
