# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cross-service permission parity tests (GH #6511).

Verifies that:
1. Every Permission enum value is covered by ROLE_PERMISSIONS.
2. ROLE_PERMISSIONS does not reference unknown permission strings.
3. Every Role has a ROLE_PERMISSIONS entry.

The SLM-backend import tests (test_slm_*) are marked xfail when the SLM
package is not on sys.path so the shared test suite stays green in isolation
while still enforcing parity when run from the SLM backend directory.
"""


from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_perm_values() -> set[str]:
    return {p.value for p in Permission}


def _all_role_perm_values() -> set[str]:
    values: set[str] = set()
    for perms in ROLE_PERMISSIONS.values():
        for p in perms:
            values.add(p.value if isinstance(p, Permission) else p)
    return values


# ---------------------------------------------------------------------------
# Shared module internal consistency
# ---------------------------------------------------------------------------


def test_every_permission_assigned_to_at_least_one_role():
    """Every Permission enum value must appear in ROLE_PERMISSIONS for at least one role."""
    uncovered = _all_perm_values() - _all_role_perm_values()
    assert not uncovered, (
        "Permissions defined in the enum but not assigned to any role:\n"
        + "\n".join(f"  {p}" for p in sorted(uncovered))
        + "\nAdd them to at least one role in autobot_shared/auth/permissions.py."
    )


def test_role_permissions_only_reference_known_values():
    """ROLE_PERMISSIONS must not contain strings absent from the Permission enum."""
    unknown = _all_role_perm_values() - _all_perm_values()
    assert not unknown, f"ROLE_PERMISSIONS references strings not in Permission enum: {unknown}"


def test_all_roles_have_role_permissions_entry():
    """Every Role enum value must have a ROLE_PERMISSIONS key."""
    missing = {r for r in Role if r not in ROLE_PERMISSIONS}
    assert not missing, f"Roles with no ROLE_PERMISSIONS entry: {missing}"


def test_admin_role_contains_all_permissions():
    """ROLE_PERMISSIONS[Role.ADMIN] must cover every Permission except SHELL_EXECUTE."""
    admin_values = {p.value if isinstance(p, Permission) else p for p in ROLE_PERMISSIONS[Role.ADMIN]}
    required = _all_perm_values() - {Permission.SHELL_EXECUTE.value}
    missing = required - admin_values
    assert not missing, "ROLE_PERMISSIONS[Role.ADMIN] is missing permissions:\n" + "\n".join(
        f"  {p}" for p in sorted(missing)
    )


# ---------------------------------------------------------------------------
# SLM backend parity
# See autobot_shared/auth/test_slm_permission_parity.py for the full
# SLM-backend parity suite (GH #6511).
# ---------------------------------------------------------------------------
