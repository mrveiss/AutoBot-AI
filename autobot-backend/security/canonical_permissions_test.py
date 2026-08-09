# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The live permission gate reads ``ROLE_PERMISSIONS`` (#13820).

Two resolvers existed and they disagreed. ``ROLE_PERMISSIONS`` is the dict both
backends import and where every ``Permission`` member is assigned;
``SecurityLayer.check_permission`` is what actually runs, and it never read it.
So a permission declared in the canonical place was held by **nobody** — every
``mcp.*`` grant added in #13228 resolved False for every role, admin included,
and the enforcement stage built on it would have denied everything.

The owner's decision was that ``ROLE_PERMISSIONS`` is authoritative. It is added
as a source rather than replacing the others, because SecurityLayer's configured
grants, wildcard matching, shell special-case and ``enable_auth`` bypass are live
semantics that something depends on — losing them silently would trade one
invisible gap for another.
"""

import pytest

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role
from security_layer import SecurityLayer, canonical_role_permissions


@pytest.fixture
def gate():
    layer = SecurityLayer()
    layer.enable_auth = True
    return layer


# ------------------------------------------------- the defect, stated directly


@pytest.mark.parametrize("role", ["admin", "superadmin", "user"])
def test_a_role_holds_the_mcp_permissions_assigned_to_it(gate, role):
    """These were False for every role before this change.

    ``MCP_BROWSER_READ`` and its siblings exist only in ``ROLE_PERMISSIONS``, so a
    resolver that never reads that dict answers False no matter who is asking.
    """
    assert gate.check_permission(role, Permission.MCP_BROWSER_READ.value) is True


def test_admin_holds_every_permission_the_canonical_mapping_grants_it(gate):
    """Not one sample: the whole set, so a partial wiring cannot pass."""
    missing = [p.value for p in ROLE_PERMISSIONS[Role.ADMIN] if not gate.check_permission("admin", p.value)]

    assert missing == [], f"admin is denied permissions the canonical mapping grants: {missing}"


# --------------------------------------------- it must not become permit-all


def test_a_weaker_role_is_still_denied_what_it_does_not_hold(gate):
    """Adding a source must widen nothing beyond what the mapping says."""
    assert gate.check_permission("readonly", Permission.MCP_BROWSER_CONTROL.value) is False
    assert gate.check_permission("readonly", Permission.MCP_DATABASE_WRITE.value) is False


def test_every_readonly_denial_matches_the_canonical_mapping(gate):
    """The full complement, so no grant leaks in from another source unnoticed."""
    held = {p.value for p in ROLE_PERMISSIONS[Role.READONLY]}
    control_grants = [
        Permission.MCP_BROWSER_CONTROL,
        Permission.MCP_DATABASE_WRITE,
        Permission.MCP_HTTP_WRITE,
        Permission.MCP_DESKTOP_CONTROL,
    ]

    for permission in control_grants:
        assert permission.value not in held, "fixture assumption broke: readonly now holds a control grant"
        assert gate.check_permission("readonly", permission.value) is False


def test_an_unknown_role_is_denied(gate):
    assert gate.check_permission("not-a-role", Permission.MCP_BROWSER_READ.value) is False


# ------------------------------------------- superadmin and case, at the root


def test_superadmin_resolves_despite_not_being_a_role_member():
    """``Role("superadmin")`` raises — it is administrative only via ADMIN_ROLES.

    That gap already produced a live misreport in #13228 stage 2, where the most
    privileged role in the system was reported as denied on every tool. Fixed
    here rather than at each consumer, so it cannot recur one seam at a time.
    """
    assert Permission.MCP_BROWSER_CONTROL.value in canonical_role_permissions("superadmin")

    with pytest.raises(ValueError):
        Role("superadmin")


@pytest.mark.parametrize("role", ["Admin", "ADMIN", "  admin  ", "SuperAdmin"])
def test_role_resolution_is_case_and_whitespace_insensitive(gate, role):
    """Every other role check in this codebase is; this one has to match."""
    assert gate.check_permission(role, Permission.MCP_BROWSER_CONTROL.value) is True


@pytest.mark.parametrize("role", ["", None, "  ", "not-a-role"])
def test_an_unresolvable_role_yields_no_grant_and_no_exception(role):
    assert canonical_role_permissions(role) == []


# --------------------------------------- the pre-existing semantics still hold


def test_the_enable_auth_bypass_is_unchanged(gate):
    """Preserved deliberately, not by omission.

    Turning it off here would be a silent, repo-wide authorisation change riding
    along with a resolver fix. It is recorded on #13820 as a separate decision.
    """
    gate.enable_auth = False

    assert gate.check_permission("not-a-role", "anything.at.all") is True


def test_wildcard_matching_still_works(gate):
    """SecurityLayer's configured grants support ``files.*``; the canonical
    mapping has no wildcards, so this could only regress by being dropped."""
    gate.roles = {"tester": {"permissions": ["files.*"]}}

    assert gate.check_permission("tester", "files.upload") is True
    assert gate.check_permission("tester", "database.drop") is False


def test_a_configured_grant_absent_from_the_canonical_mapping_still_grants(gate):
    """Security config remains a real source, not a decoration."""
    gate.roles = {"tester": {"permissions": ["some.bespoke.permission"]}}

    assert gate.check_permission("tester", "some.bespoke.permission") is True


def test_the_shell_execute_special_case_still_sees_every_source(gate):
    """It reads the combined list, which now has a third member."""
    gate.roles = {"tester": {"permissions": ["allow_shell_execute"]}}

    assert gate.check_permission("tester", "allow_shell_execute") is True


# ------------------------------------------------------ the two paths agree


def test_the_gate_never_denies_what_the_canonical_mapping_grants(gate):
    """The AC, stated as the property that actually matters.

    Exact equality between the two resolvers cannot hold and asserting it would
    be wrong: the gate expands wildcards (``files.*`` matches ``files.delete``)
    and ``_get_user_permissions`` returns literal strings. So the direction to
    pin is one-way — a permission the canonical mapping grants must never be
    denied by the gate. The reverse (the gate granting more, via a wildcard) is
    the configured-permissions feature working, not drift.
    """
    from auth_rbac import _get_user_permissions

    denied_despite_being_granted = []
    for role in Role:
        held = set(_get_user_permissions(role.value))
        for permission in Permission:
            if permission.value in held and not gate.check_permission(role.value, permission.value):
                denied_despite_being_granted.append((role.value, permission.value))

    assert (
        denied_despite_being_granted == []
    ), f"the gate denies permissions the canonical mapping grants: {denied_despite_being_granted[:5]}"


def test_any_extra_the_gate_grants_comes_from_a_wildcard(gate):
    """Names the excess instead of leaving it as an unexplained difference.

    Every case where the gate grants what the literal union does not must be
    covered by a wildcard in the configured or default permissions. An extra that
    is *not* wildcard-explained would mean a fourth source nobody has accounted
    for.
    """
    from auth_rbac import _get_user_permissions

    unexplained = []
    for role in Role:
        held = set(_get_user_permissions(role.value))
        wildcards = [p for p in gate._get_default_role_permissions(role.value) if p.endswith("*")]
        prefixes = tuple(w[:-1] for w in wildcards)
        for permission in Permission:
            if gate.check_permission(role.value, permission.value) and permission.value not in held:
                if not (prefixes and permission.value.startswith(prefixes)):
                    unexplained.append((role.value, permission.value))

    assert unexplained == [], f"granted by neither the mapping nor a wildcard: {unexplained[:5]}"
