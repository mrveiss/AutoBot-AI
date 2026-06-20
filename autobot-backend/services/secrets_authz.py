# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure RBAC authorization policy for the unified secrets store (#10088 / Task 2.3).

Decides, for a principal, **which vaults they can reach** and **whether an action
on a vault is allowed** — over already-fetched ``PrincipalFacts``, so the policy
is pure and unit-testable. The DB resolver that builds ``PrincipalFacts`` from
``user_roles`` / ``team_memberships`` / ``llc_company_memberships`` + the RBAC
permission registry (and seeding the ``secrets:*`` permissions) is part 2.

Two authority domains, dispatched on :class:`VaultKind`:
- **Instance/user RBAC** governs system / user / team / role / node vaults
  (admin flag + ``secrets:<kind>:<action>`` permissions + team/role membership).
- **LLC membership** governs company vaults: the principal's
  :class:`MembershipRole` in that company maps directly to allowed actions.

The output ``accessible_vaults`` set is exactly what
``UnifiedSecretsService.read``/``list_for_vaults`` take; ``authorize`` gates the
mutating operations (write/share/revoke) before the service acts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from autobot_shared.secrets_vault import VaultKind, VaultRef
from llc.models.enums import MembershipRole

#: Actions a caller can request against a vault.
ACTIONS = frozenset({"read", "write", "share", "revoke"})

#: LLC company-vault authority: a member's role → the actions it permits.
_COMPANY_ACTIONS: dict[MembershipRole, frozenset[str]] = {
    MembershipRole.OWNER: frozenset({"read", "write", "share", "revoke"}),
    MembershipRole.ADMIN: frozenset({"read", "write", "share", "revoke"}),
    MembershipRole.LEAD: frozenset({"read", "write", "share"}),
    MembershipRole.MEMBER: frozenset({"read", "write"}),
    MembershipRole.GUEST: frozenset({"read"}),
}


def secrets_permission(kind: VaultKind, action: str) -> str:
    """Canonical RBAC permission name for an action on a vault kind."""
    return f"secrets:{kind.value}:{action}"


@dataclass(frozen=True)
class PrincipalFacts:
    """Membership/permission facts about a principal, already fetched from the DB."""

    user_id: str
    is_admin: bool = False
    team_ids: frozenset[str] = frozenset()
    role_names: frozenset[str] = frozenset()
    company_roles: Mapping[str, MembershipRole] = field(default_factory=dict)
    granted_permissions: frozenset[str] = frozenset()
    active: bool = True  # False for a deactivated/soft-deleted principal → reaches no vault

    def accessible_vaults(self) -> set[VaultRef]:
        """Every vault this principal can reach (feeds ``read`` / ``list_for_vaults``)."""
        if not self.active:
            return set()
        vaults: set[VaultRef] = {VaultRef(VaultKind.USER, self.user_id)}
        if self.is_admin:
            vaults.add(VaultRef(VaultKind.SYSTEM))
        vaults |= {VaultRef(VaultKind.TEAM, t) for t in self.team_ids}
        vaults |= {VaultRef(VaultKind.ROLE, r) for r in self.role_names}
        vaults |= {VaultRef(VaultKind.COMPANY, c) for c in self.company_roles}
        return vaults

    def _has_perm(self, kind: VaultKind, action: str) -> bool:
        return secrets_permission(kind, action) in self.granted_permissions


def authorize(facts: PrincipalFacts, action: str, vault: VaultRef) -> bool:
    """True if *facts* permits *action* on *vault*."""
    if not facts.active:  # deactivated/soft-deleted principal → denied everywhere
        return False
    kind = vault.kind
    if kind == VaultKind.SYSTEM:
        return facts.is_admin
    if kind == VaultKind.USER:
        return facts.is_admin or vault.id == facts.user_id
    if kind == VaultKind.TEAM:
        return vault.id in facts.team_ids and facts._has_perm(kind, action)
    if kind == VaultKind.ROLE:
        return vault.id in facts.role_names and facts._has_perm(kind, action)
    if kind == VaultKind.COMPANY:
        role = facts.company_roles.get(vault.id or "")
        return role is not None and action in _COMPANY_ACTIONS[role]
    if kind == VaultKind.NODE:
        return facts.is_admin
    # agent / service principals are refined in Task 9.2; default closed.
    return facts.is_admin
