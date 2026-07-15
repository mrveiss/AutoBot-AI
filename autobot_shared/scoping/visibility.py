# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure visibility rule for scoped resources (#11277, #11290)."""

from collections.abc import Callable
from dataclasses import dataclass

from autobot_shared.scoping.scope_level import ScopeLevel

# Either the pre-computed fact "a matching grant row exists for this
# principal", or a lazy per-subsystem grant lookup evaluated only when
# ownership does not already decide. Closures let subsystems model their own
# grant semantics (secrets: session match + shared_with list; knowledge:
# shared_with list) without contorting Principal (#11290).
GrantCheck = bool | Callable[[], bool]


@dataclass(frozen=True)
class Principal:
    """Who is asking — the visibility projection of a principal (#11290).

    The canonical, richer principal is ``services.secrets_authz.PrincipalFacts``
    (admin flag, role names, multi-company roles, active flag); it cannot live
    here because ``autobot_shared`` must not import backend models. Build this
    projection from it via ``PrincipalFacts.scoping_principal(company_id)``
    instead of constructing a parallel principal by hand.

    ``is_authenticated`` defaults to False (fail closed): only the
    SYSTEM/PUBLIC platform-wide rule consumes it, so existing constructors
    keep denying those scopes unless they explicitly assert authentication.
    """

    user_id: str
    company_id: str | None
    group_ids: frozenset[str]
    is_authenticated: bool = False


@dataclass(frozen=True)
class ResourceDescriptor:
    """The resource's ownership + scope.

    ``group_id`` is the deprecated single-group form (#11290): prefer
    ``group_ids`` for multi-group resources (secrets ``team_ids``, knowledge
    fact ``group_ids``). Both are honored — the effective set is their union.
    """

    owner_id: str | None
    company_id: str | None
    scope: ScopeLevel
    group_id: str | None = None
    group_ids: frozenset[str] = frozenset()

    def effective_group_ids(self) -> frozenset[str]:
        """Union of the deprecated single group and the multi-group set."""
        if self.group_id is None:
            return self.group_ids
        return self.group_ids | {self.group_id}


def is_visible(principal: Principal, resource: ResourceDescriptor, has_grant: GrantCheck) -> bool:
    """Decide whether `principal` may access `resource`.

    `has_grant` is the result of "a matching resource_grants row exists for
    this principal" (Task 6) — pre-computed, or a lazy subsystem grant lookup
    called only when ownership does not already grant. An explicit grant
    always grants access.
    """
    if resource.owner_id and principal.user_id == resource.owner_id:
        return True
    granted = has_grant() if callable(has_grant) else has_grant
    if granted:
        return True
    if resource.scope is ScopeLevel.SYSTEM or resource.scope is ScopeLevel.PUBLIC:
        # Platform-wide knowledge: any authenticated principal (#11290).
        return principal.is_authenticated
    if resource.scope is ScopeLevel.ORGANIZATION:
        return resource.company_id is not None and resource.company_id == principal.company_id
    if resource.scope is ScopeLevel.GROUP:
        return bool(resource.effective_group_ids() & principal.group_ids)
    # USER / PRIVATE / SESSION / SHARED / WORKFLOW are private absent
    # ownership or an explicit grant.
    return False
