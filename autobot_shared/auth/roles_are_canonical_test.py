# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The canonical role vocabulary has no members outside it (#13854, #12786).

``superadmin`` was administrative — ``ADMIN_ROLES`` held it, ``is_admin_role``
returned True for it, 17 ``require_role`` guards admitted it — while not being a
``Role`` member and holding no ``ROLE_PERMISSIONS`` entry. It therefore resolved
four different ways at once: allow-all through ``role_has_permission``, deny-all
through ``SecurityLayer.check_permission``, admitted by ``require_role``, and
``ValueError`` through ``Role()``.

These tests pin the properties that made that state possible, so it cannot
reassemble itself:

1. every administrative role is a real ``Role`` with a real grant list;
2. being administrative is not, by itself, a grant;
3. every ``Role`` member has an entry, so no lookup falls off the mapping.

Each test asserts the PRESENCE of what it expects, never merely the absence of a
failure — an empty vocabulary would otherwise satisfy every "nothing is wrong"
assertion here.
"""

from enum import Enum

import pytest

from autobot_shared.auth.permissions import (
    _ROLE_META,
    ADMIN_ROLES,
    ROLE_PERMISSIONS,
    Permission,
    Role,
    is_admin_role,
    role_has_permission,
    role_value,
)


class _ForeignRole(str, Enum):
    """Stands in for ``MembershipRole`` — a *different* vocabulary, same literal.

    Declared here rather than imported so this file keeps no dependency on the
    LLC package, and so the test states the shape it is guarding against
    (``(str, Enum)`` with the value ``"admin"``) rather than pointing at
    something that could be changed out from under it.
    """

    ADMIN = "admin"


# The vocabulary as of #13854, written out. A rename or a removal fails here
# first, with a message naming the member — rather than silently shrinking the
# sets every other test in this file derives from the enum.
EXPECTED_ROLE_VALUES = {
    "admin",
    "superadmin",
    "operator",
    "analyst",
    "editor",
    "user",
    "readonly",
}
EXPECTED_ADMIN_ROLE_VALUES = {"admin", "superadmin"}


# --------------------------------------------------- the vocabulary is present


def test_the_role_enum_holds_exactly_the_expected_members():
    """Presence, not absence. Guards against both a dropped and an added role."""
    assert {role.value for role in Role} == EXPECTED_ROLE_VALUES


def test_superadmin_is_a_member():
    """Stated on its own because it is the member #13854 exists to add.

    A regression that removes it would still pass a test comparing two derived
    sets to each other.
    """
    assert Role.SUPERADMIN in Role
    assert Role("superadmin") is Role.SUPERADMIN
    assert Role.SUPERADMIN.value == "superadmin"


# ------------------------------------- AC: every ADMIN_ROLES member is canonical


def test_admin_roles_is_not_empty():
    """The guard below is vacuous over an empty set — check the subject exists."""
    assert ADMIN_ROLES == EXPECTED_ADMIN_ROLE_VALUES
    assert len(ADMIN_ROLES) == 2


@pytest.mark.parametrize("role_value", sorted(EXPECTED_ADMIN_ROLE_VALUES))
def test_every_administrative_role_is_a_role_member_with_a_grant_list(role_value):
    """#13854 AC: ``ADMIN_ROLES`` may not name a role the enum does not have.

    This is the assertion that would have failed before #13854 —
    ``Role("superadmin")`` raised — and it is parametrised over the literal
    expected set rather than over ``ADMIN_ROLES`` itself, so an ADMIN_ROLES that
    lost a member cannot make its own guard pass by shrinking.
    """
    role = Role(role_value)
    assert role in ROLE_PERMISSIONS, f"{role_value} is administrative but has no ROLE_PERMISSIONS entry"
    assert is_admin_role(role_value) is True


def test_admin_roles_cannot_name_a_non_role():
    """Derived from the enum, so a bare string cannot be added to it."""
    for value in ADMIN_ROLES:
        assert Role(value) in Role


# ------------------------------ AC: ADMIN_ROLES is not a permission source


def test_being_administrative_grants_nothing_by_itself():
    """The core #13854 AC, asserted through the role that separates the two.

    ``superadmin`` is in ``ADMIN_ROLES`` and holds an empty grant list. If any
    resolver ever again short-circuits on the administrative predicate, this
    fails. Asserted over the WHOLE Permission enum, not a sample, so a partial
    reintroduction cannot slip through.
    """
    assert is_admin_role("superadmin") is True
    assert ROLE_PERMISSIONS[Role.SUPERADMIN] == []

    granted = [p.value for p in Permission if role_has_permission("superadmin", p.value)]
    assert granted == [], f"ADMIN_ROLES membership leaked {len(granted)} permissions: {granted}"


def test_admin_holds_every_permission_from_its_own_entry():
    """The invariant that made removing the short-circuit safe (#13854).

    ``role_has_permission`` used to return True for anything ``is_admin_role``
    accepted. Removing that is only behaviour-preserving for ``admin`` because
    admin's own ROLE_PERMISSIONS entry already covers every Permission member.
    That was measured once; this asserts it continuously, because a future
    permission added to the enum but not granted to admin would silently make
    the removal a regression.
    """
    admin_grants = {p.value for p in ROLE_PERMISSIONS[Role.ADMIN]}
    every_permission = {p.value for p in Permission}

    assert every_permission, "Permission enum is empty — this guard would be vacuous"
    assert every_permission - admin_grants == set(), "admin no longer holds every Permission"

    for permission in Permission:
        assert role_has_permission("admin", permission.value) is True, permission.value


# ------------------------------------------- no member falls off the mapping


def test_every_role_has_a_role_permissions_entry():
    """A missing entry used to raise ``KeyError`` at request time.

    ``role_has_permission`` subscripted ``_ROLE_PERMISSION_VALUES`` directly, so
    a ``Role`` member added without a grant list crashed the permission check
    instead of denying it.
    """
    assert set(Role), "Role enum is empty — this guard would be vacuous"
    missing = {role.value for role in Role if role not in ROLE_PERMISSIONS}
    assert missing == set(), f"Role members with no ROLE_PERMISSIONS entry: {missing}"


def test_every_role_has_role_metadata():
    """A missing ``_ROLE_META`` entry silently seeds priority 0 — below readonly."""
    missing = {role.value for role in Role if role not in _ROLE_META}
    assert missing == set(), f"Role members with no _ROLE_META entry: {missing}"


@pytest.mark.parametrize("unknown", ["not-a-role", "", None, "platform_admin", "guest"])
def test_an_unresolvable_role_is_denied_rather_than_raising(unknown):
    """Fail closed, and fail quietly — never a 500 from the permission gate."""
    assert role_has_permission(unknown, Permission.API_READ.value) is False


# ------------------------------------- a Role MEMBER resolves like its value


# The population these guards run over, derived rather than hand-listed, with a
# floor asserted AT the real number so a shrunken enum cannot make them vacuous.
_ADMIN_MEMBERS = sorted((r for r in Role if r.value in ADMIN_ROLES), key=lambda r: r.value)


def test_the_member_population_these_guards_run_over_is_the_real_one():
    """A guard over an empty or shrunken set passes by holding nothing."""
    assert len(_ADMIN_MEMBERS) == 2, f"expected 2 administrative Role members, got {_ADMIN_MEMBERS}"
    assert len(list(Role)) == 7, f"expected 7 Role members, got {len(list(Role))}"
    assert {r.value for r in _ADMIN_MEMBERS} == EXPECTED_ADMIN_ROLE_VALUES


@pytest.mark.parametrize("member", _ADMIN_MEMBERS, ids=lambda r: r.value)
def test_is_admin_role_accepts_the_enum_member_itself(member):
    """#14944: the case no test covered, because every test passed ``.value``.

    ``Role`` is the ``(str, Enum)`` mixin shape, so ``str(Role.ADMIN)`` is
    ``"Role.ADMIN"`` — while ``f"{Role.ADMIN}"``, ``Role.ADMIN == "admin"`` and
    ``Role.ADMIN in ADMIN_ROLES`` all say ``"admin"``. The member therefore
    behaved correctly everywhere except under ``str()``, which is the one
    construct ``is_admin_role`` used. It returned **False for an administrator**.

    Deliberately passes the member, never ``member.value`` — an assertion with
    ``.value`` on both sides cannot fail here.
    """
    assert is_admin_role(member) is True, f"{member!r} is administrative but is_admin_role said False"


@pytest.mark.parametrize("member", list(Role), ids=lambda r: r.value)
def test_every_role_resolves_identically_as_member_and_as_value(member):
    """The invariant, not one instance of it (#14944).

    Whatever a role string resolves to, the enum member spelling of that same
    role must resolve to exactly the same thing — through every function that
    takes a role. That is the property the ``str()`` bug broke, and asserting it
    over the whole vocabulary means a newly added role is covered on arrival.
    """
    assert role_value(member) == member.value
    assert is_admin_role(member) is is_admin_role(member.value)
    for permission in Permission:
        assert role_has_permission(member, permission.value) is role_has_permission(
            member.value, permission.value
        ), f"{member!r} disagrees with {member.value!r} on {permission.value}"


def test_admin_holds_its_whole_grant_list_when_passed_as_a_member():
    """Presence, not parity alone — parity is also satisfied by two Falses."""
    granted = [p.value for p in Permission if role_has_permission(Role.ADMIN, p.value)]
    assert len(granted) == len(list(Permission)), f"Role.ADMIN resolved {len(granted)} of {len(list(Permission))}"


# --------------------------- a role from a DIFFERENT vocabulary is not coerced


def test_a_foreign_role_enum_is_rejected_rather_than_lowercased():
    """The trap in the obvious fix (#14944, #14024, #13934).

    ``MembershipRole`` (company membership) and the chat-role constants share
    literals with this vocabulary, and a ``(str, Enum)`` member *is* a ``str`` —
    so ``role.lower()`` answers with the **value**. Fixing ``is_admin_role`` with
    a bare ``.lower()`` would therefore have admitted a company-membership admin
    as a platform administrator: a silent authorization widening introduced by
    the fix for an authorization narrowing.

    The two assertions matter together. The first proves the hazard is real —
    without it, the second passes for any implementation that happens to reject
    everything. ``str()`` rejected this case by accident; this rejects it on
    purpose.
    """
    assert _ForeignRole.ADMIN.lower() in ADMIN_ROLES, "the hazard this guards is not present — test is vacuous"

    with pytest.raises(TypeError):
        role_value(_ForeignRole.ADMIN)
    with pytest.raises(TypeError):
        is_admin_role(_ForeignRole.ADMIN)


@pytest.mark.parametrize("bad", [42, 3.5, ["admin"], {"role": "admin"}, object(), Permission.API_READ])
def test_a_non_role_argument_is_rejected_rather_than_stringified(bad):
    """An authorization predicate should not answer a question nobody asked.

    Every call site passes a ``str`` or ``None`` off an authenticated session, so
    any other type is a programming error. Stringifying it produced a confident
    ``False`` — a claim about the caller, which two call sites forward as an
    ``is_platform_admin`` flag.
    """
    with pytest.raises(TypeError):
        is_admin_role(bad)


@pytest.mark.parametrize("empty", [None, ""])
def test_the_absent_role_is_still_answered_quietly(empty):
    """``current_user.get("role")`` returns None routinely — that is data, not a bug."""
    assert role_value(empty) == ""
    assert is_admin_role(empty) is False
    assert role_has_permission(empty, Permission.API_READ.value) is False


@pytest.mark.parametrize("falsy", [0, False, [], {}, set()])
def test_a_FALSY_non_role_is_rejected_like_any_other_non_role(falsy):
    """The case the existing parametrisation missed — it only covered strings and None.

    ``role_has_permission`` tested ``if not role`` *before* coercing, so a falsy
    non-role returned a quiet ``False`` while ``_normalise_role`` and
    ``canonical_role_permissions`` raised on the very same input. Truthiness is
    not the question being asked; the resolved role string's emptiness is, so
    the type is resolved first and the emptiness test moved after it.

    ``0`` and ``False`` matter most: both are plausible JSON values, and both are
    the kind of input for which an authorization helper answering ``False``
    confidently is worse than refusing to answer.
    """
    with pytest.raises(TypeError):
        role_value(falsy)
    with pytest.raises(TypeError):
        is_admin_role(falsy)
    with pytest.raises(TypeError):
        role_has_permission(falsy, Permission.API_READ.value)


def test_every_role_taking_function_agrees_on_how_it_refuses():
    """The uniformity this PR claims, asserted rather than described.

    All three take a role and must dispose of a non-role the same way. Asserted
    as a property across the set, so a function added later that quietly returns
    False instead of raising is caught by the same test.
    """
    refusers = (
        role_value,
        is_admin_role,
        lambda r: role_has_permission(r, Permission.API_READ.value),
    )
    assert len(refusers) == 3, "the set of role-taking entry points changed"
    for refuse in refusers:
        with pytest.raises(TypeError):
            refuse(0)
        with pytest.raises(TypeError):
            refuse(_ForeignRole.ADMIN)
