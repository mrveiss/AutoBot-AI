# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who owns a batch job, template or schedule, and who may act on it (#21650).

Ownership is one Redis hash per kind, ``batch:{kind}:owners`` (record id -> owner id),
written when ``api/batch_jobs.py`` creates a record and removed when it deletes one. It
sits beside the ``batch:{kind}:all`` index sets that module already keeps rather than in
the record JSON: the job schema is shared with the Celery executor
(``services/batch_job_store.py``), and an owner kept outside it cannot be lost by a
worker that rewrites a job.

The access rule is not new. The owner id is :func:`resolve_principal_id` (the one claim
order, #13688) and the decision is :func:`autobot_shared.scoping.is_visible` on a PRIVATE
resource, with an administrator's role as the grant -- the rule the knowledge base
applies in ``knowledge/ownership.py``.

A record with no owner -- every record created before this change -- is visible to
administrators only. Nothing here assigns an owner to an existing record or deletes one:
that is a data change, and data changes go through the approval queue (#17038).

A refused caller gets the same 404 as a record that does not exist, so a user cannot
learn that someone else's id is real.
"""

from collections.abc import Iterable

from fastapi import HTTPException

from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.principal import resolve_principal_id
from autobot_shared.redis_utils import decode_redis_value
from autobot_shared.scoping import Principal, ResourceDescriptor, ScopeLevel, is_visible

JOBS = "jobs"
TEMPLATES = "templates"
SCHEDULES = "schedules"


def owners_key(kind: str) -> str:
    """Redis hash holding record id -> owner id for one kind of batch record."""
    return f"batch:{kind}:owners"


def record_owner(redis_client, kind: str, record_id: str, user: dict | None) -> str | None:
    """Store the caller as the owner of a new record; return the owner id written.

    A caller with no user identity (an internal service key) writes no owner, so the
    record is administrators-only -- the same as one created before #21650.
    """
    owner = resolve_principal_id(user)
    if owner:
        redis_client.hset(owners_key(kind), record_id, owner)
    return owner


def create_record(
    redis_client,
    kind: str,
    record_id: str,
    record_key: str,
    payload: str,
    user: dict | None,
    created_at: float | None = None,
) -> None:
    """Write a new record, its ``all``-set membership and its owner entry in one transaction.

    A crash between separate writes would leave a record in the index with no owner
    (administrators-only) or an owner with no record. ``created_at`` also adds the id to the
    ``batch:{kind}:created`` time index.
    """
    pipe = redis_client.pipeline(transaction=True)
    pipe.set(record_key, payload)
    pipe.sadd(f"batch:{kind}:all", record_id)
    owner = resolve_principal_id(user)
    if owner:
        pipe.hset(owners_key(kind), record_id, owner)
    if created_at is not None:
        pipe.zadd(f"batch:{kind}:created", {record_id: created_at})
    pipe.execute()


def forget_owner(redis_client, kind: str, record_id: str) -> None:
    """Drop a deleted record's owner entry."""
    redis_client.hdel(owners_key(kind), record_id)


def may_access(owner: str | None, user: dict | None) -> bool:
    """Whether *user* owns the record or is an administrator; no owner admits admins only."""
    principal = Principal(
        user_id=resolve_principal_id(user) or "",
        company_id=None,
        group_ids=frozenset(),
        is_authenticated=bool(user),
    )
    resource = ResourceDescriptor(owner_id=owner or None, company_id=None, scope=ScopeLevel.PRIVATE)
    return is_visible(principal, resource, lambda: user is not None and is_admin_role(user.get("role")))


def owner_of(redis_client, kind: str, record_id: str) -> str | None:
    """The recorded owner id of one record, or None."""
    return decode_redis_value(redis_client.hget(owners_key(kind), record_id)) or None


def require_access(redis_client, kind: str, record_id: str, user: dict | None, label: str) -> None:
    """Raise the record's not-found 404 unless *user* may access it."""
    if not may_access(owner_of(redis_client, kind, record_id), user):
        raise HTTPException(status_code=404, detail=f"{label} {record_id} not found")


def visible_ids(redis_client, kind: str, raw_ids: Iterable, user: dict | None) -> list[str]:
    """The ids, decoded, that *user* may see: their own, or all of them for an administrator."""
    ids = [decode_redis_value(raw) for raw in raw_ids]
    if not ids:
        return []
    owners = redis_client.hmget(owners_key(kind), ids)
    return [rid for rid, owner in zip(ids, owners) if may_access(decode_redis_value(owner), user)]
