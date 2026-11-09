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
``kb.admin_read`` entry the route commits names every record the admin is shown. An admin is bound to
the caller's own tenant; only a superadmin crosses tenants.

Access by section kind: ``public`` is the product's own documentation and code analysis (no per-user
owner, api/knowledge_search_documentation.py module docstring), ``owner`` holds per-user records, and
``tenant_admin`` holds per-company/project/work-item/agent buckets for admins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from knowledge.quarantine import not_quarantined
from knowledge.root_read import is_superadmin_user
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
    """The caller of one graph read: identity, tenant, and the admin ledger (False for a non-admin)."""

    user_id: str
    company_id: str | None
    group_ids: tuple
    is_superadmin: bool
    ledger: Any = False

    @property
    def is_admin(self) -> bool:
        return bool(self.ledger)


def viewer_for(current_user, ledger) -> Viewer:
    """The :class:`Viewer` of an authenticated caller; *ledger* is the route's ``admin_read_audit`` value."""
    user_id, org_id, group_ids = extract_user_context_from_request(current_user)
    return Viewer(user_id, org_id, tuple(group_ids), is_superadmin_user(current_user), ledger)


def first_of(meta: Dict[str, Any], keys: tuple) -> str | None:
    """The first non-empty value of *keys* in *meta*, as a string."""
    found = next((meta[k] for k in keys if meta.get(k)), None)
    return str(found) if found else None


def tenant_of(meta: Dict[str, Any]) -> str | None:
    """The tenant a record names, or None for an untenanted record."""
    return first_of(meta, _TENANT_KEYS)


def as_fact(collection: str, record_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """A bucket record in the shape the fact filter reads: ``id`` plus ownership ``metadata``."""
    metadata = dict(meta)
    metadata["owner_id"] = first_of(meta, _OWNER_KEYS)
    metadata["organization_id"] = tenant_of(meta)
    return {"id": f"bucket:{collection}:{record_id}", "metadata": metadata}


def is_company_collection(collection: str) -> bool:
    """A ``company:<id>`` collection, in its logical or ChromaDB-stored (``company_<id>``) form (#10743)."""
    return collection.startswith(("company:", "company_"))


# A company id is a UUID or ``-`` slug: ``_`` is excluded because ``_chroma_safe_name`` maps ``:`` to ``_``, so an id
# holding one could not be told from its suffix once stored (#20945).
_COMPANY_ID = r"[A-Za-z0-9-]+"
_LOGICAL_COMPANY = re.compile(rf"^company:({_COMPANY_ID})(?::.+)?$")
_STORED_COMPANY = re.compile(rf"^company_({_COMPANY_ID})(?:_.+)?$")


def company_of_collection(collection: str) -> str | None:
    """The company id a company collection names, from its logical or stored name; None when it is not exactly one.

    Logical ``company:<id>[:<suffix>]``; stored (``_chroma_safe_name``: ``:`` -> ``_``) ``company_<id>[_<suffix>]``.
    Anything else, or an id outside ``[A-Za-z0-9-]``, is None, so a tenant admin is never granted a collection
    that cannot be attributed to exactly their company.
    """
    match = _LOGICAL_COMPANY.match(collection) or _STORED_COMPANY.match(collection)
    return match.group(1) if match else None


def within_admin_tenant(meta: Dict[str, Any], is_admin: bool, is_superadmin: bool, company_id: str | None) -> bool:
    """An admin bypass stays in the caller's tenant; a record of another tenant is out (a superadmin crosses)."""
    if is_superadmin or not is_admin:
        return True
    tenant = tenant_of(meta)
    return tenant is None or tenant == company_id


def _within_tenant(kind: str, collection: str, fact: Dict[str, Any], viewer: Viewer) -> bool:
    """An admin (not a superadmin) sees their own tenant: untenanted ``owner`` records, never another tenant's.

    A ``company:<id>`` collection is already tenant-scoped by its name (:func:`collection_in_scope`); the other
    per-entity buckets name no tenant, so their records must carry the caller's.
    """
    if viewer.is_superadmin or not viewer.is_admin or is_company_collection(collection):
        return True
    tenant = fact["metadata"]["organization_id"]
    return tenant == viewer.company_id if tenant or kind == TENANT_ADMIN else True


def collection_in_scope(kind: str, collection: str, viewer: Viewer) -> bool:
    """False for a ``company:<id>`` collection of another tenant, before any record is read."""
    if kind != TENANT_ADMIN or viewer.is_superadmin or not is_company_collection(collection):
        return True
    return company_of_collection(collection) == viewer.company_id


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


async def _readable_public(collection: str, rows: List[Dict[str, Any]], viewer: Viewer) -> List[Dict[str, Any]]:
    """Public rows minus quarantined ones, and minus those of a code source the viewer may not read."""
    rows = [r for r in rows if not_quarantined(as_fact(collection, r["id"], r.get("metadata") or {}))]
    named = {(r.get("metadata") or {}).get("source_id") for r in rows} - {None, "", UNSCOPED_SOURCE}
    allowed = {sid for sid in named if await _may_read_source(sid, viewer)}
    return [r for r in rows if (r.get("metadata") or {}).get("source_id") in allowed | {None, "", UNSCOPED_SOURCE}]


async def visible_records(
    kind: str, collection: str, rows: List[Dict[str, Any]], viewer: Viewer, ownership_manager
) -> List[Dict[str, Any]]:
    """The *rows* (``id``, ``metadata``) the viewer may read; an admin's are recorded in the ledger."""
    if kind == PUBLIC:
        return await _readable_public(collection, rows, viewer)
    facts = [as_fact(collection, r["id"], r.get("metadata") or {}) for r in rows]
    facts = [f for f in facts if not_quarantined(f) and _within_tenant(kind, collection, f, viewer)]
    kept = await filter_search_results_by_permission(
        facts,
        viewer.user_id,
        viewer.company_id,
        list(viewer.group_ids),
        ownership_manager=ownership_manager,
        is_admin=viewer.is_admin,  # the ledger records only the page the route returns
    )
    allowed = {f["id"] for f in kept}
    return [r for r in rows if f"bucket:{collection}:{r['id']}" in allowed]


def record_page(viewer: Viewer, section_access: str, page: List[tuple]) -> None:
    """Record the admin-gated records of a returned page (``(collection, id, metadata)``) in the ledger (#19860)."""
    if viewer.is_admin and section_access != PUBLIC:
        viewer.ledger.record([{"id": f"bucket:{name}:{rid}"} for name, rid, _ in page])
