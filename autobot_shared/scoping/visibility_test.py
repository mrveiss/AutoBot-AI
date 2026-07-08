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
    assert is_visible(_p(user="stranger", company="c2"),
                      _r(owner="owner", scope=ScopeLevel.USER, company="c1"), True)
