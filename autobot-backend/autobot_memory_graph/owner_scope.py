# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Owner scoping for the memory graph (#18825).

Every entity is stamped with ``owner_user_id`` / ``owner_org_id`` at write time and every
read takes a REQUIRED :class:`OwnerScope`. The only way to read without one is the
explicit :data:`UNSCOPED_ALL_USERS` sentinel (same pattern as
``memory/verbatim_store.py``, #16701); omitting the argument raises
:class:`OwnerScopeRequired` instead of silently returning every user's data.

ADMINS: there is no admin bypass. ``OwnerScope.from_tenant`` / ``from_auth_user`` never read a role
or ``is_platform_admin``, so an admin's scope is their own and they see no other user's entity.
Cross-user reads are the explicit :data:`UNSCOPED_ALL_USERS` sentinel for system callers only.

NOT THE KB MODEL: this is a per-owner model, deliberately different from the knowledge base's
visibility/ownership model in ``knowledge/search_filters.py`` -- see "Memory graph vs knowledge-base
visibility" in ``docs/developer/ARCHITECTURE_EXCEPTIONS.md``.

Entities that carry no owner (everything written before #18825) are invisible to scoped
reads. They are never rewritten here -- a backfill is a human-approved action (#17038).

ORG RULE (one rule, applied on write and read):

* WRITE: the org is the principal's org from its TenantContext / JWT (``org_id``), under the
  one key ``owner_org_id``. A principal with no org stamps the sentinel :data:`NO_ORG`
  (a real tag value, because RediSearch cannot match a missing or null TAG).
* READ: an entity owned by user U with no org is visible to U in ANY org context. An entity
  stamped with org X is visible only in org X. ``__shared__`` entities are visible to everyone.
  The same rule is built into the RediSearch query (:func:`redis_owner_clause`) and enforced
  again in Python (:func:`entity_visible`), so the two cannot disagree.
  A document stored earlier with a null org is read by the Python path only (the scan fallback);
  RediSearch cannot match a null TAG, and nothing here rewrites stored entities (#17038).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

OWNER_USER_FIELD = "owner_user_id"
OWNER_ORG_FIELD = "owner_org_id"
#: Tag stamped in ``owner_org_id`` when the owner has no org (RediSearch cannot index a null TAG).
NO_ORG = "__no_org__"

#: Entities every authenticated principal may read (explicit, never a default).
SHARED_OWNER_ID = "__shared__"
#: Entities written by the platform on nobody's behalf (e.g. admin security assessments):
#: visible only to an UNSCOPED_ALL_USERS read.
SYSTEM_OWNER_ID = "__system__"
_RESERVED_OWNER_IDS = frozenset({SHARED_OWNER_ID, SYSTEM_OWNER_ID})


class OwnerScopeRequired(ValueError):
    """A memory-graph read or write was attempted without an owner scope."""


class _UnscopedAllUsersSentinel:
    """Type of :data:`UNSCOPED_ALL_USERS` -- deliberately not ``str`` so a user id can never equal it."""

    def __repr__(self) -> str:
        return "UNSCOPED_ALL_USERS"


#: The one legitimate way to read across owners (system callers, the stdio MCP transport
#: which has no per-user identity). Callers must pass it explicitly and say why.
UNSCOPED_ALL_USERS = _UnscopedAllUsersSentinel()


@dataclass(frozen=True)
class OwnerScope:
    """Who an entity belongs to / whose entities a read may see."""

    user_id: str
    org_id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id or not str(self.user_id).strip():
            raise OwnerScopeRequired("OwnerScope.user_id must be non-empty")

    @classmethod
    def for_user(cls, user_id: Any, org_id: Any = None) -> "OwnerScope":
        """Scope for an authenticated principal (ids are normalised to ``str``)."""
        if user_id is None or not str(user_id).strip():
            raise OwnerScopeRequired("OwnerScope.user_id must be non-empty")
        if str(user_id) in _RESERVED_OWNER_IDS:
            raise OwnerScopeRequired("user_id collides with a reserved owner id")
        return cls(str(user_id), str(org_id) if org_id else None)

    @classmethod
    def from_auth_user(cls, user: Dict[str, Any] | None) -> "OwnerScope":
        """Scope from the authenticated-principal dict (``get_current_user``), never a request body.

        Same identity chat sessions are written under: ``user_id``, else ``username``.
        """
        user = user or {}
        identity = user.get("user_id") or user.get("username")
        if not identity:
            raise OwnerScopeRequired("authenticated principal has no user id")
        return cls.for_user(identity, user.get("org_id"))

    @classmethod
    def from_tenant(cls, tenant: Any) -> "OwnerScope":
        """Scope from a ``TenantContext``; an unauthenticated context fails closed."""
        if getattr(tenant, "user_id", None) is None:
            raise OwnerScopeRequired("TenantContext has no authenticated user")
        return cls.for_user(tenant.user_id, getattr(tenant, "org_id", None))

    @classmethod
    def shared(cls) -> "OwnerScope":
        """Marker for system entities every authenticated user may read."""
        return cls(SHARED_OWNER_ID)

    @classmethod
    def system(cls) -> "OwnerScope":
        """Marker for platform-owned entities no user-scoped read can see."""
        return cls(SYSTEM_OWNER_ID)


def owner_from_source(source: Dict[str, Any] | None) -> OwnerScope | None:
    """Owner scope carried by a prefetch context / sync turn / search filters (#18825).

    An explicit ``owner`` (OwnerScope) wins, else ``user_id`` (+ optional ``org_id``).
    None means the caller supplied no principal; readers then return nothing (fail closed).
    """
    source = source or {}
    if isinstance(source.get("owner"), OwnerScope):
        return source["owner"]
    if not source.get("user_id"):
        return None
    try:
        return OwnerScope.for_user(source["user_id"], source.get("org_id"))
    except OwnerScopeRequired:
        return None


def require_scope(owner: Any) -> Any:
    """Return ``owner`` if it is a usable scope, else raise (fail closed)."""
    if owner is UNSCOPED_ALL_USERS or isinstance(owner, OwnerScope):
        return owner
    raise OwnerScopeRequired("an OwnerScope (or UNSCOPED_ALL_USERS for system callers) is required")


def require_writer(owner: Any) -> OwnerScope:
    """Writes need a concrete owner; the unscoped sentinel is read-only."""
    if isinstance(owner, OwnerScope):
        return owner
    raise OwnerScopeRequired("entity writes need an OwnerScope (use OwnerScope.shared()/system() for platform data)")


def owner_fields(owner: OwnerScope) -> Dict[str, Any]:
    """The top-level document fields that record ownership."""
    return {OWNER_USER_FIELD: owner.user_id, OWNER_ORG_FIELD: owner.org_id or NO_ORG}


def entity_visible(entity: Dict[str, Any] | None, owner: Any) -> bool:
    """True if ``owner`` may read ``entity``. Ownerless entities are invisible to scoped reads."""
    if not entity:
        return False
    if require_scope(owner) is UNSCOPED_ALL_USERS:
        return True
    entity_user = entity.get(OWNER_USER_FIELD)
    if not entity_user:
        return False
    if entity_user == SHARED_OWNER_ID:
        return True
    if entity_user != owner.user_id:
        return False
    entity_org = entity.get(OWNER_ORG_FIELD)
    return entity_org in (None, "", NO_ORG) or entity_org == owner.org_id


def redis_owner_clause(owner: Any) -> str:
    """RediSearch filter for the owner (empty when unscoped); same rule as :func:`entity_visible`.

    ``(own entities in an org the owner may see) | shared``. Entities written without an org
    carry the :data:`NO_ORG` tag, so they match in every org context. Python re-checks every hit.
    """
    from autobot_shared.security.input_sanitizer import escape_redisearch_tag

    if require_scope(owner) is UNSCOPED_ALL_USERS:
        return ""
    orgs = [NO_ORG] + ([owner.org_id] if owner.org_id else [])
    org_tags = "|".join(escape_redisearch_tag(o) for o in orgs)
    own = f"(@{OWNER_USER_FIELD}:{{{escape_redisearch_tag(owner.user_id)}}} @{OWNER_ORG_FIELD}:{{{org_tags}}})"
    return f"({own} | @{OWNER_USER_FIELD}:{{{escape_redisearch_tag(SHARED_OWNER_ID)}}})"
