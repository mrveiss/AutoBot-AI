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
    # Hermetic: a host whose security config defines roles would otherwise make
    # the cross-check tests below depend on ambient configuration.
    layer.roles = {}
    return layer


# ------------------------------------------------- the defect, stated directly


@pytest.mark.parametrize("role", ["admin", "user"])
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


def test_superadmin_is_not_a_role_member_and_is_not_silently_treated_as_one():
    """``Role("superadmin")`` raises, and this resolver does not paper over it.

    An earlier version of this change mapped it onto admin's set via
    ``ADMIN_ROLES``. That reads as a fix and is an authorisation expansion: it
    granted 54 permissions including shell execution to a role that held none of
    them. The genuine fix is a first-class ``Role`` member with its own
    ``ROLE_PERMISSIONS`` entry — #13854.
    """
    with pytest.raises(ValueError):
        Role("superadmin")

    assert canonical_role_permissions("superadmin") == []


@pytest.mark.parametrize("role", ["Admin", "ADMIN", "  admin  ", "aDmIn"])
def test_role_resolution_is_case_and_whitespace_insensitive(gate, role):
    """Every other role check in this codebase is; this one has to match."""
    assert gate.check_permission(role, Permission.MCP_BROWSER_CONTROL.value) is True


@pytest.mark.parametrize("role", ["Admin", "ADMIN", "  admin  "])
def test_normalisation_is_shared_by_every_source_not_just_the_canonical_one(gate, role):
    """``allow_voice_speak`` exists **only** in ``_get_default_role_permissions``.

    So this can only pass if ``check_permission`` normalises once for all three
    sources. Asserting a canonical permission would not prove it — that resolver
    normalises internally and would answer correctly even with the shared step
    removed, which is exactly how a partial normalisation hid here before: one
    identity holding some grants and not others.
    """
    assert gate.check_permission(role, "allow_voice_speak") is True


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


# --------------------------------- the permission gate and the approval gate agree


HIGH_RISK_COMMAND = "sudo apt-get install curl"


@pytest.mark.parametrize("role", ["admin", "Admin", "ADMIN", "  admin  ", "god", "root", "superuser"])
def test_a_role_that_may_run_a_shell_command_is_also_subject_to_approval(gate, role):
    """The two gates must resolve the same identity, or one of them is bypassed.

    ``_should_force_approval`` keys on the role string exactly. A normalisation
    applied to the permission gate alone creates a second identity that clears
    shell execution and then finds an empty permission list here, so no approval
    branch can fire and a HIGH-risk command runs unapproved.

    ``god``/``root``/``superuser`` had this gap before this change: the permission
    gate downgrades them to admin, the approval gate did not.
    """
    assert gate.check_permission(role, "allow_shell_execute") is True
    assert gate._should_force_approval(HIGH_RISK_COMMAND, role) is True


@pytest.mark.parametrize("role", ["superadmin", "user", "readonly", "not-a-role"])
def test_a_role_that_may_not_run_a_shell_command_is_denied_at_the_gate(gate, role):
    assert gate.check_permission(role, "allow_shell_execute") is False


def test_superadmin_gains_no_permissions_from_this_change(gate):
    """It is administrative via ``ADMIN_ROLES`` but holds no canonical grants.

    Mapping it onto admin's set would hand it 54 permissions including shell
    execution that it did not previously have — an authorisation expansion, not
    the resolver fix #13820 decided. Tracked separately in #13854.
    """
    assert gate.check_permission("superadmin", "allow_shell_execute") is False
    assert gate.check_permission("superadmin", "admin.system") is False
    assert canonical_role_permissions("superadmin") == []


@pytest.mark.parametrize("role", ["god", "root", "superuser"])
def test_a_deprecated_alias_does_not_gain_the_full_admin_set(gate, role):
    """``_handle_deprecated_role`` documents a downgrade to *granular* permissions.

    Resolving the canonical set from the rebound role would have made that
    downgrade a near-no-op, handing these aliases all 54 admin permissions in
    place of the 8 defaults they had.
    """
    assert gate.check_permission(role, "admin.system") is False
    assert gate.check_permission(role, Permission.MCP_BROWSER_CONTROL.value) is False


def test_a_deprecated_alias_keeps_the_shell_access_it_already_had(gate):
    """The downgrade is not a revocation — it must not break these roles either."""
    assert gate.check_permission("god", "allow_shell_execute") is True


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
