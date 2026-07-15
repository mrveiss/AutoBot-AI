# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from autobot_shared.scoping.scope_level import ScopeLevel
from autobot_shared.scoping.visibility import Principal, ResourceDescriptor, is_visible


def _p(user="u1", company="c1", groups=()):
    return Principal(user_id=user, company_id=company, group_ids=frozenset(groups))


def _r(owner="owner", company="c1", scope=ScopeLevel.ORGANIZATION, group=None):
    return ResourceDescriptor(owner_id=owner, company_id=company, scope=scope, group_id=group)


def test_owner_always_sees_own_resource():
    assert is_visible(_p(user="me"), _r(owner="me", scope=ScopeLevel.USER, company="other"), False)


def test_organization_scope_visible_to_same_company():
    assert is_visible(_p(company="c1"), _r(scope=ScopeLevel.ORGANIZATION, company="c1"), False)


def test_organization_scope_hidden_from_other_company():
    assert not is_visible(_p(company="c2"), _r(scope=ScopeLevel.ORGANIZATION, company="c1"), False)


def test_group_scope_visible_to_member():
    assert is_visible(_p(groups={"g1"}), _r(scope=ScopeLevel.GROUP, group="g1"), False)


def test_group_scope_hidden_from_non_member():
    assert not is_visible(_p(groups={"g2"}), _r(scope=ScopeLevel.GROUP, group="g1"), False)


def test_user_scope_hidden_from_non_owner_without_grant():
    assert not is_visible(_p(user="stranger"), _r(owner="owner", scope=ScopeLevel.USER), False)


def test_explicit_grant_overrides_scope():
    assert is_visible(_p(user="stranger", company="c2"), _r(owner="owner", scope=ScopeLevel.USER, company="c1"), True)


def test_domain_specific_members_fail_closed_without_grant():
    """#11290: superset members from other subsystems deny by default here."""
    for scope in (ScopeLevel.WORKFLOW, ScopeLevel.PRIVATE, ScopeLevel.SYSTEM, ScopeLevel.PUBLIC):
        assert not is_visible(_p(user="stranger"), _r(owner="owner", scope=scope), False)
        assert is_visible(_p(user="owner"), _r(owner="owner", scope=scope), False)  # owner still wins
        assert is_visible(_p(user="stranger"), _r(owner="owner", scope=scope), True)  # grant still wins


def test_system_public_visible_to_authenticated_principal():
    """#11290: SYSTEM/PUBLIC grant any authenticated principal (knowledge rule)."""
    authed = Principal(user_id="stranger", company_id=None, group_ids=frozenset(), is_authenticated=True)
    for scope in (ScopeLevel.SYSTEM, ScopeLevel.PUBLIC):
        assert is_visible(authed, _r(owner="owner", scope=scope), False)
        assert not is_visible(_p(user="stranger"), _r(owner="owner", scope=scope), False)  # default: anon


def test_group_ids_multi_group_membership():
    """#11290: multi-group resources union with the deprecated single group_id."""
    r = ResourceDescriptor(
        owner_id="owner", company_id=None, scope=ScopeLevel.GROUP, group_id="g0", group_ids=frozenset({"g1", "g2"})
    )
    assert is_visible(_p(groups={"g2"}), r, False)
    assert is_visible(_p(groups={"g0"}), r, False)  # single-group form still honored
    assert not is_visible(_p(groups={"g9"}), r, False)


def test_has_grant_accepts_lazy_callback():
    """#11290: has_grant may be a subsystem grant-lookup closure."""
    assert is_visible(_p(user="stranger"), _r(owner="owner", scope=ScopeLevel.USER), lambda: True)
    assert not is_visible(_p(user="stranger"), _r(owner="owner", scope=ScopeLevel.USER), lambda: False)


def test_has_grant_callback_skipped_for_owner():
    """Owner short-circuits before the grant lookup runs (lazy evaluation)."""

    def _boom() -> bool:
        raise AssertionError("grant lookup must not run for the owner")

    assert is_visible(_p(user="owner"), _r(owner="owner", scope=ScopeLevel.USER), _boom)


def test_falsy_owner_id_never_matches():
    """#11290: resources without an owner (knowledge) grant no ownership access."""
    r = ResourceDescriptor(owner_id=None, company_id=None, scope=ScopeLevel.USER)
    assert not is_visible(_p(user="anyone"), r, False)
