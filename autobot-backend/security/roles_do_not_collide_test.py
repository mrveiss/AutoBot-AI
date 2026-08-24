# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Three 'role' vocabularies share literals; the overlap must stay deliberate (#14024).

Three unrelated vocabularies use the word "role" and share string values, with
nothing at the type level keeping them apart:

    platform RBAC       autobot_shared.auth.permissions.Role
    company membership  llc.models.enums.MembershipRole
    chat message role   autobot_shared.ssot_constants.CategoryDefaults.ROLE_*

**They are correctly separate concepts and are deliberately not merged.** This
file is not a step toward collapsing them — it is the guard that keeps the
collision surface from growing silently.

The failure mode is real and already happened. ``tools/tool_registry`` set
``"user_role": "user"`` — an RBAC input read by ``worker_node._validate_user_role``.
The hardcoded-value guard suggested ``CategoryDefaults.ROLE_USER``, the *chat*
constant, which holds ``"user"`` too. Applying that suggestion would have tied
an authorization decision to a presentation constant, gone green, and been
invisible in review (#13934). Any later re-tuning of the chat vocabulary would
then have silently changed an authz value.

A same-NAME search finds nothing here: the three types have different names. The
comparison that matters is between their MEMBER SETS, which is what this file
does.
"""

from llc.models.enums import MembershipRole

from autobot_shared.auth.permissions import Role
from autobot_shared.ssot_constants import CategoryDefaults

RBAC_ROLES = frozenset(role.value for role in Role)
MEMBERSHIP_ROLES = frozenset(role.value for role in MembershipRole)
CHAT_ROLES = frozenset(
    {
        CategoryDefaults.ROLE_USER,
        CategoryDefaults.ROLE_ASSISTANT,
        CategoryDefaults.ROLE_SYSTEM,
    }
)

# The overlaps that exist today, each one reviewed and accepted. A new collision
# fails the tests below with the offending value named, instead of waiting for
# someone to notice.
KNOWN_RBAC_MEMBERSHIP_OVERLAP = frozenset({"admin"})
KNOWN_RBAC_CHAT_OVERLAP = frozenset({"user"})
KNOWN_MEMBERSHIP_CHAT_OVERLAP = frozenset()


# ------------------------------------------- the subjects exist and are whole
#
# Without these, every overlap assertion below is satisfiable by an empty set —
# an import that silently resolved to nothing would read as "no collisions".


def test_each_vocabulary_is_populated():
    assert RBAC_ROLES, "platform RBAC vocabulary resolved empty"
    assert MEMBERSHIP_ROLES, "company membership vocabulary resolved empty"
    assert CHAT_ROLES, "chat message vocabulary resolved empty"


def test_each_vocabulary_holds_the_members_it_is_supposed_to():
    """Written out, so a rename or a removal is caught here and not downstream."""
    assert RBAC_ROLES == {"admin", "superadmin", "operator", "analyst", "editor", "user", "readonly"}
    assert MEMBERSHIP_ROLES == {"owner", "admin", "member", "guest", "lead"}
    assert CHAT_ROLES == {"user", "assistant", "system"}


# ------------------------------------------------ the overlap is exactly known


def test_rbac_and_membership_share_only_the_known_value():
    """``admin`` means "platform administrator" in one and "company admin" in the other."""
    overlap = RBAC_ROLES & MEMBERSHIP_ROLES
    assert overlap == KNOWN_RBAC_MEMBERSHIP_OVERLAP, (
        f"platform RBAC and company membership now share {sorted(overlap)}; "
        f"previously {sorted(KNOWN_RBAC_MEMBERSHIP_OVERLAP)}. A value in both type-checks in "
        "either position. Confirm the new collision is deliberate and add it here, or rename it."
    )


def test_rbac_and_chat_share_only_the_known_value():
    """``user`` is an authorization subject in one and a message author in the other."""
    overlap = RBAC_ROLES & CHAT_ROLES
    assert overlap == KNOWN_RBAC_CHAT_OVERLAP, (
        f"platform RBAC and chat message roles now share {sorted(overlap)}; "
        f"previously {sorted(KNOWN_RBAC_CHAT_OVERLAP)}. This is the pair that produced #13934 — "
        "a chat constant suggested for an RBAC field. Confirm and record it here, or rename it."
    )


def test_membership_and_chat_do_not_collide_at_all():
    overlap = MEMBERSHIP_ROLES & CHAT_ROLES
    assert overlap == KNOWN_MEMBERSHIP_CHAT_OVERLAP, (
        f"company membership and chat message roles now share {sorted(overlap)}, "
        "which they never did before. Confirm and record it here, or rename it."
    )


def test_the_new_rbac_member_collides_with_nothing():
    """``superadmin`` was added by #13854 into a namespace with two neighbours.

    Stated separately so the addition is visibly checked against both other
    vocabularies rather than only against the aggregate overlap.
    """
    assert "superadmin" in RBAC_ROLES
    assert "superadmin" not in MEMBERSHIP_ROLES
    assert "superadmin" not in CHAT_ROLES


# ------------------------------------------------ the values stay distinguishable


def test_a_chat_role_is_not_a_valid_rbac_role_except_where_known():
    """The concrete consequence, asserted as behaviour rather than as set algebra.

    ``assistant`` and ``system`` must not resolve as RBAC roles at all. ``user``
    does, and that is the known collision — asserted explicitly so it stays a
    recorded fact rather than an accident.
    """
    for chat_role in (CategoryDefaults.ROLE_ASSISTANT, CategoryDefaults.ROLE_SYSTEM):
        try:
            Role(chat_role)
        except ValueError:
            continue
        raise AssertionError(f"chat role {chat_role!r} now resolves as a platform RBAC role")

    assert Role(CategoryDefaults.ROLE_USER) is Role.USER
