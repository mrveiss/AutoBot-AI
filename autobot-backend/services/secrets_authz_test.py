# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the pure secrets RBAC authorization policy (#10113 / Task 2.3)."""

from __future__ import annotations

import pytest

from autobot_shared.secrets_vault import VaultKind, VaultRef
from llc.models.enums import MembershipRole
from services.secrets_authz import PrincipalFacts, authorize, secrets_permission

_TEAM_RW = {secrets_permission(VaultKind.TEAM, "read"), secrets_permission(VaultKind.TEAM, "write")}
_ROLE_RW = {secrets_permission(VaultKind.ROLE, "read"), secrets_permission(VaultKind.ROLE, "write")}


def _facts(**kw) -> PrincipalFacts:
    base = dict(user_id="alice")
    base.update(kw)
    return PrincipalFacts(**base)


class TestSecretsPermissionName:
    def test_canonical_form(self) -> None:
        assert secrets_permission(VaultKind.SYSTEM, "read") == "secrets:system:read"
        assert secrets_permission(VaultKind.COMPANY, "share") == "secrets:company:share"


class TestAccessibleVaults:
    def test_always_includes_own_user_vault(self) -> None:
        assert VaultRef(VaultKind.USER, "alice") in _facts().accessible_vaults()

    def test_admin_gets_system(self) -> None:
        assert VaultRef(VaultKind.SYSTEM) in _facts(is_admin=True).accessible_vaults()
        assert VaultRef(VaultKind.SYSTEM) not in _facts().accessible_vaults()

    def test_team_role_company_vaults(self) -> None:
        facts = _facts(
            team_ids=frozenset({"platform"}),
            role_names=frozenset({"engineer"}),
            company_roles={"acme": MembershipRole.MEMBER},
        )
        vaults = facts.accessible_vaults()
        assert VaultRef(VaultKind.TEAM, "platform") in vaults
        assert VaultRef(VaultKind.ROLE, "engineer") in vaults
        assert VaultRef(VaultKind.COMPANY, "acme") in vaults


class TestAuthorizeSystem:
    def test_admin_only(self) -> None:
        assert authorize(_facts(is_admin=True), "write", VaultRef(VaultKind.SYSTEM))
        assert not authorize(_facts(), "read", VaultRef(VaultKind.SYSTEM))


class TestAuthorizeUser:
    def test_own_vault(self) -> None:
        assert authorize(_facts(), "write", VaultRef(VaultKind.USER, "alice"))

    def test_other_user_vault_denied(self) -> None:
        assert not authorize(_facts(), "read", VaultRef(VaultKind.USER, "bob"))

    def test_admin_can_access_any_user_vault(self) -> None:
        assert authorize(_facts(is_admin=True), "read", VaultRef(VaultKind.USER, "bob"))


class TestAuthorizeTeamRole:
    def test_team_needs_membership_and_permission(self) -> None:
        member = _facts(team_ids=frozenset({"platform"}), granted_permissions=frozenset(_TEAM_RW))
        assert authorize(member, "read", VaultRef(VaultKind.TEAM, "platform"))
        # member but no permission → denied
        assert not authorize(_facts(team_ids=frozenset({"platform"})), "read", VaultRef(VaultKind.TEAM, "platform"))
        # permission but not a member → denied
        assert not authorize(
            _facts(granted_permissions=frozenset(_TEAM_RW)), "read", VaultRef(VaultKind.TEAM, "platform")
        )

    def test_team_action_scoped_by_permission(self) -> None:
        member = _facts(team_ids=frozenset({"platform"}), granted_permissions=frozenset(_TEAM_RW))
        assert not authorize(member, "share", VaultRef(VaultKind.TEAM, "platform"))  # no share perm granted

    def test_role_vault(self) -> None:
        facts = _facts(role_names=frozenset({"engineer"}), granted_permissions=frozenset(_ROLE_RW))
        assert authorize(facts, "write", VaultRef(VaultKind.ROLE, "engineer"))
        assert not authorize(facts, "read", VaultRef(VaultKind.ROLE, "other"))


class TestAuthorizeCompany:
    @pytest.mark.parametrize(
        "role,action,allowed",
        [
            (MembershipRole.OWNER, "revoke", True),
            (MembershipRole.ADMIN, "share", True),
            (MembershipRole.LEAD, "share", True),
            (MembershipRole.LEAD, "revoke", False),
            (MembershipRole.MEMBER, "write", True),
            (MembershipRole.MEMBER, "share", False),
            (MembershipRole.GUEST, "read", True),
            (MembershipRole.GUEST, "write", False),
        ],
    )
    def test_membership_role_action_map(self, role, action, allowed) -> None:
        facts = _facts(company_roles={"acme": role})
        assert authorize(facts, action, VaultRef(VaultKind.COMPANY, "acme")) is allowed

    def test_non_member_company_denied(self) -> None:
        assert not authorize(_facts(), "read", VaultRef(VaultKind.COMPANY, "acme"))


class TestAuthorizeNode:
    def test_admin_only(self) -> None:
        assert authorize(_facts(is_admin=True), "read", VaultRef(VaultKind.NODE, "node1"))
        assert not authorize(_facts(), "read", VaultRef(VaultKind.NODE, "node1"))
