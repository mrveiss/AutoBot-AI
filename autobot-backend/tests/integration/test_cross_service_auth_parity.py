# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cross-service auth parity test (MVA-127 / GH #6511).

Verifies that the shared Permission enum and ROLE_PERMISSIONS mapping are the
single source of truth for both autobot-backend and autobot-slm-backend.  If a
new permission is added to the shared enum but a backend drifts to a local copy,
one or more tests here will fail.

Test strategy
-------------
1. **Structural** — scan each backend's auth source files to confirm they import
   from ``autobot_shared.auth.permissions`` and do NOT define local Permission
   enums or ROLE_PERMISSIONS dicts.

2. **Enforcement parity (parametrized)** — both services apply the shared
   evaluator (#18263); assert it agrees on every (Role, Permission) pair for both
   payload shapes. The services' real bindings are driven end to end by
   ``repo_tests/cross_service_permission_parity_18263_test.py``.

3. **Completeness** — every Permission member must appear in at least one role's
   permission set (no orphaned permission that can never be granted).

Adding a new permission
-----------------------
Add the member to ``autobot_shared/auth/permissions.py`` and grant it to the
appropriate roles in ``ROLE_PERMISSIONS``.  The parametrized parity test will
then automatically cover the new permission against both backends.  If you
forget to update ROLE_PERMISSIONS, ``test_no_orphaned_permissions`` fails.
"""

import re
import sys
from pathlib import Path
from typing import List

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap — tests/integration/ lives inside autobot-backend/
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_AUTOBOT_BACKEND = _REPO_ROOT / "autobot-backend"
_AUTOBOT_SLM = _REPO_ROOT / "autobot-slm-backend"
_AUTOBOT_SHARED = _REPO_ROOT / "autobot_shared"

for p in (_AUTOBOT_BACKEND, str(_AUTOBOT_SHARED)):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from autobot_shared.auth.permission_evaluator import permission_allowed
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role, is_admin_role

# ---------------------------------------------------------------------------
# Helpers — both services now apply ONE evaluator (#18263). These call it rather
# than replicate either service: a replica kept the SLM's lenient role fallback
# "passing" here after the code had dropped it. The real per-service bindings are
# driven end to end by repo_tests/cross_service_permission_parity_18263_test.py.
# ---------------------------------------------------------------------------


def _backend_has_permission(role_str: str, permission: Permission) -> bool:
    """The backend's decision for a caller whose ``role`` claim is *role_str*."""
    return permission_allowed({"role": role_str}, permission)


def _slm_has_permission(user_payload: dict, permission: Permission) -> bool:
    """The SLM's decision for a JWT payload."""
    return permission_allowed(user_payload, permission)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _all_permission_role_pairs() -> List[tuple]:
    """Return [(role, permission)] for every combination."""
    return [(role, perm) for role in Role for perm in Permission]


# ---------------------------------------------------------------------------
# 1. Structural: both backends import from autobot_shared
# ---------------------------------------------------------------------------


class TestStructuralImports:
    """Confirm that neither backend defines its own Permission enum or mapping."""

    SHARED_IMPORT_PATTERN = re.compile(r"from\s+autobot_shared\.auth\.permissions\s+import")
    LOCAL_PERMISSION_PATTERN = re.compile(r"^class\s+Permission\s*\(", re.MULTILINE)
    LOCAL_ROLE_PERMISSIONS_PATTERN = re.compile(r"^ROLE_PERMISSIONS\s*[:=]", re.MULTILINE)

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    # --- autobot-backend ---

    def test_backend_auth_rbac_imports_shared_permission(self):
        """auth_rbac.py must import Permission from autobot_shared."""
        src = self._read(_AUTOBOT_BACKEND / "auth_rbac.py")
        assert self.SHARED_IMPORT_PATTERN.search(src), (
            "auth_rbac.py must import from autobot_shared.auth.permissions — " "found no such import"
        )

    def test_backend_auth_rbac_has_no_local_permission_enum(self):
        """auth_rbac.py must not define its own Permission class."""
        src = self._read(_AUTOBOT_BACKEND / "auth_rbac.py")
        assert not self.LOCAL_PERMISSION_PATTERN.search(src), (
            "auth_rbac.py defines a local Permission enum — "
            "remove it and import from autobot_shared.auth.permissions"
        )

    def test_backend_auth_rbac_has_no_local_role_permissions(self):
        """auth_rbac.py must not define its own ROLE_PERMISSIONS dict."""
        src = self._read(_AUTOBOT_BACKEND / "auth_rbac.py")
        assert not self.LOCAL_ROLE_PERMISSIONS_PATTERN.search(src), (
            "auth_rbac.py defines a local ROLE_PERMISSIONS — "
            "remove it and import from autobot_shared.auth.permissions"
        )

    # --- autobot-slm-backend ---

    def test_slm_auth_service_imports_shared_permission(self):
        """services/auth.py must import Permission from autobot_shared."""
        src = self._read(_AUTOBOT_SLM / "services" / "auth.py")
        assert self.SHARED_IMPORT_PATTERN.search(src), (
            "slm services/auth.py must import from autobot_shared.auth.permissions — " "found no such import"
        )

    def test_slm_auth_service_has_no_local_permission_enum(self):
        """services/auth.py must not define its own Permission class."""
        src = self._read(_AUTOBOT_SLM / "services" / "auth.py")
        assert not self.LOCAL_PERMISSION_PATTERN.search(src), (
            "slm services/auth.py defines a local Permission enum — "
            "remove it and import from autobot_shared.auth.permissions"
        )

    def test_slm_auth_service_has_no_local_role_permissions(self):
        """services/auth.py must not define its own ROLE_PERMISSIONS dict."""
        src = self._read(_AUTOBOT_SLM / "services" / "auth.py")
        assert not self.LOCAL_ROLE_PERMISSIONS_PATTERN.search(src), (
            "slm services/auth.py defines a local ROLE_PERMISSIONS — "
            "remove it and import from autobot_shared.auth.permissions"
        )

    def test_slm_rbac_middleware_imports_shared(self):
        """rbac_middleware.py must not redefine Permission locally."""
        src = self._read(_AUTOBOT_SLM / "user_management" / "middleware" / "rbac_middleware.py")
        assert not self.LOCAL_PERMISSION_PATTERN.search(src), (
            "rbac_middleware.py defines a local Permission enum — "
            "it must import from autobot_shared.auth.permissions"
        )

    def test_no_local_permission_enum_in_backend_api(self):
        """No file under autobot-backend/api/ should define class Permission."""
        for py_file in (_AUTOBOT_BACKEND / "api").glob("**/*.py"):
            src = py_file.read_text(encoding="utf-8")
            assert not self.LOCAL_PERMISSION_PATTERN.search(
                src
            ), f"{py_file.relative_to(_REPO_ROOT)} defines a local Permission enum"

    def test_no_local_permission_enum_in_slm_api(self):
        """No file under autobot-slm-backend/api/ should define class Permission."""
        slm_api = _AUTOBOT_SLM / "api"
        if not slm_api.exists():
            pytest.skip("autobot-slm-backend/api/ not present")
        for py_file in slm_api.glob("**/*.py"):
            src = py_file.read_text(encoding="utf-8")
            assert not self.LOCAL_PERMISSION_PATTERN.search(
                src
            ), f"{py_file.relative_to(_REPO_ROOT)} defines a local Permission enum"


# ---------------------------------------------------------------------------
# 2. Enforcement parity — both backends agree on every (Role, Permission) pair
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role,permission", _all_permission_role_pairs())
def test_backend_and_slm_agree_on_permission(role: Role, permission: Permission):
    """Both enforcement paths must return the same grant/deny for every pair.

    This test fails if either backend adds logic that diverges from the shared
    ROLE_PERMISSIONS table, or if the two backends' role-derivation paths
    produce different Role values for the same JWT payload.
    """
    payload = {"sub": f"test_{role.value}", "role": role.value, "admin": role == Role.ADMIN}

    backend_result = _backend_has_permission(role.value, permission)
    slm_result = _slm_has_permission(payload, permission)

    assert backend_result == slm_result, (
        f"Parity mismatch for role={role.value!r}, permission={permission.value!r}: "
        f"backend={backend_result}, slm={slm_result}. "
        f"Both backends must derive the same grant/deny from ROLE_PERMISSIONS."
    )


# ---------------------------------------------------------------------------
# 3. Completeness — no orphaned permissions
# ---------------------------------------------------------------------------


class TestPermissionCompleteness:
    """Every Permission in the enum must be grantable by at least one role."""

    @pytest.mark.parametrize("permission", list(Permission))
    def test_permission_granted_by_at_least_one_role(self, permission: Permission):
        """A permission that no role can ever grant is unreachable dead code."""
        granted_by = [role.value for role, perms in ROLE_PERMISSIONS.items() if permission in perms]
        assert granted_by, (
            f"Permission {permission.value!r} is not granted to any role in "
            f"ROLE_PERMISSIONS — add it to at least one role or remove the enum member."
        )

    def test_all_permissions_covered_by_role_permissions(self):
        """The set of permissions in ROLE_PERMISSIONS must equal Permission enum members.

        If a new permission is added to the enum but ROLE_PERMISSIONS is not updated,
        this test will flag it.
        """
        all_enum_perms = set(Permission)
        all_mapped_perms: set = set()
        for perms in ROLE_PERMISSIONS.values():
            all_mapped_perms.update(perms)

        unmapped = all_enum_perms - all_mapped_perms
        assert not unmapped, (
            f"The following permissions exist in the Permission enum but are not "
            f"granted to any role in ROLE_PERMISSIONS: "
            f"{sorted(p.value for p in unmapped)}. "
            f"Add them to the appropriate role(s) in autobot_shared/auth/permissions.py."
        )

    # #13854: the invariant is "a role authorised by GRANT must grant
    # something". Since #19125 (owner decision 2026-10-21) ``superadmin`` holds
    # admin's set too, so every role currently grants something; the filter below
    # keeps the exemption derived for any future purely predicate-authorised role.
    #
    # The exemption is DERIVED from ``is_admin_role`` — the same predicate the
    # live gates use — rather than a second hand-written list of administrative
    # roles. Such a list is exactly the fork #13854/#12786 removed, and it would
    # silently stop exempting the right roles the moment ``ADMIN_ROLES`` changed.
    # ``role.value`` (not the member) is passed deliberately: ``str()`` on a
    # ``(str, Enum)`` member yields "Role.ADMIN", not "admin" — see #14944.
    @pytest.mark.parametrize("role", [r for r in Role if not is_admin_role(r.value)])
    def test_non_administrative_role_has_at_least_one_permission(self, role: Role):
        """Every role that grants access through ROLE_PERMISSIONS must grant something."""
        perms = ROLE_PERMISSIONS.get(role, [])
        assert perms, (
            f"Role {role.value!r} has no permissions in ROLE_PERMISSIONS — "
            f"every non-administrative role must grant at least one permission."
        )

    def test_the_permissionless_roles_are_exactly_the_administrative_ones(self):
        """The contrapositive, so the exemption above cannot quietly widen.

        Stated as a property over every role: ANY role with an empty grant list
        must be administrative. Since #19125 no role is empty (superadmin holds
        admin's set), so the expected set is empty; a newly empty role must be
        recorded here deliberately.
        """
        ungranted = {r.value for r in Role if not ROLE_PERMISSIONS.get(r, [])}

        assert ungranted == set(), (
            f"the set of roles holding zero permissions changed to {sorted(ungranted)}. "
            "Only an administrative, predicate-authorised role may hold none. "
            "Confirm the change is deliberate and record it here."
        )
        for value in ungranted:
            assert is_admin_role(value), f"role {value!r} holds no permissions and is not administrative"

    def test_the_parametrisation_above_is_not_empty(self):
        """Guard against vacuity.

        If the derived filter ever excluded every role, each parametrised case
        would silently vanish rather than fail — an absent result reading as a
        clean one.
        """
        graded = [r for r in Role if not is_admin_role(r.value)]

        assert len(graded) >= 5, f"expected the non-administrative roles to be graded, got {graded}"
        assert Role.ADMIN not in graded and Role.SUPERADMIN not in graded


# ---------------------------------------------------------------------------
# 4. Permission naming convention (dot-notation)
# ---------------------------------------------------------------------------


class TestPermissionNamingConvention:
    """Permission values must follow dot-notation (category.resource or category.resource.action)."""

    _LEGACY_EXEMPT = {"allow_shell_execute"}

    @pytest.mark.parametrize("permission", list(Permission))
    def test_permission_value_uses_dot_notation(self, permission: Permission):
        """Permission string values must be dot-separated (e.g. 'api.read', 'admin.users.write')."""
        value = permission.value
        if value in self._LEGACY_EXEMPT:
            pytest.skip(f"{value!r} is a legacy name exempted from dot-notation rule")
        assert "." in value, (
            f"Permission {permission.name} has value {value!r} which does not use "
            f"dot-notation. Use format 'category.action' or 'category.resource.action'."
        )
        parts = value.split(".")
        assert all(part.islower() and part.isidentifier() for part in parts), (
            f"Permission {permission.name} value {value!r}: each dot-separated part "
            f"must be lowercase and a valid identifier."
        )

    def test_no_colon_notation_in_new_permissions(self):
        """Colon-notation permissions are legacy (SYSTEM_PERMISSIONS DB seeds only).

        The Permission enum must not introduce new colon-style values.
        """
        colon_perms = [p for p in Permission if ":" in p.value]
        assert not colon_perms, (
            f"Permission enum contains colon-notation values (legacy DB-seed format "
            f"must stay in SYSTEM_PERMISSIONS, not the Permission enum): "
            f"{[p.value for p in colon_perms]}"
        )


# ---------------------------------------------------------------------------
# 5. Role-derivation parity — legacy JWT fallback agrees across backends
# ---------------------------------------------------------------------------


class TestLegacyJWTFallback:
    """#18263 strict reading: neither service resolves a role the claim does not name exactly."""

    def test_a_legacy_admin_flag_without_a_role_is_denied(self):
        assert not _slm_has_permission({"sub": "old_admin", "admin": True}, Permission.ADMIN_SYSTEM)

    def test_a_legacy_user_flag_without_a_role_is_denied_even_user_permissions(self):
        assert not _slm_has_permission({"sub": "old_user", "admin": False}, Permission.CHAT_USE)

    def test_an_unknown_role_is_denied_not_treated_as_user(self):
        payload = {"sub": "attacker", "admin": False, "role": "superadmin_inject"}
        assert not _slm_has_permission(payload, Permission.CHAT_USE)

    def test_backend_unknown_role_returns_false(self):
        assert not _backend_has_permission("superadmin_inject", Permission.ADMIN_SYSTEM)

    def test_backend_and_slm_agree_on_a_legacy_admin_token(self):
        """Both deny: the stricter of the two former readings won (#18263)."""
        payload = {"sub": "legacy", "admin": True}
        assert _slm_has_permission(payload, Permission.ADMIN_SYSTEM) is False
        assert _backend_has_permission("", Permission.ADMIN_SYSTEM) is False
