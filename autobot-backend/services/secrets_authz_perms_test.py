# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The registered secrets:* RBAC permissions match the authz policy (#10088).

Guards the contract between the permission registry
(``autobot_shared.auth.permissions``) and the policy that consumes the names
(``services.secrets_authz``): the team/role vault permissions the policy checks
must all exist in ``SYSTEM_PERMISSIONS`` and be assigned to the right roles.
"""

from __future__ import annotations

from autobot_shared.auth.permissions import SYSTEM_PERMISSIONS, SYSTEM_ROLES
from autobot_shared.secrets_vault import VaultKind
from services.secrets_authz import secrets_permission

_REGISTERED = {row[0] for row in SYSTEM_PERMISSIONS}
# Only team and role vaults consult RBAC permissions in the policy.
_RBAC_VAULTS = (VaultKind.TEAM, VaultKind.ROLE)
_ACTIONS = ("read", "write", "share", "revoke")
_EXPECTED = {secrets_permission(k, a) for k in _RBAC_VAULTS for a in _ACTIONS}


def test_all_policy_permissions_are_registered():
    missing = _EXPECTED - _REGISTERED
    assert not missing, f"secrets:* permissions checked by the policy but not registered: {missing}"


def test_admin_role_has_full_secrets_control():
    admin = set(SYSTEM_ROLES["admin"]["permissions"])
    assert _EXPECTED <= admin, f"admin missing secrets perms: {_EXPECTED - admin}"


def test_user_role_has_readwrite_not_share_revoke():
    user = set(SYSTEM_ROLES["user"]["permissions"])
    for kind in _RBAC_VAULTS:
        assert secrets_permission(kind, "read") in user
        assert secrets_permission(kind, "write") in user
        assert secrets_permission(kind, "share") not in user
        assert secrets_permission(kind, "revoke") not in user


def test_readonly_role_has_no_secrets_write():
    readonly = set(SYSTEM_ROLES["readonly"]["permissions"])
    assert not any(p.startswith("secrets:") and p.endswith((":write", ":share", ":revoke")) for p in readonly)
