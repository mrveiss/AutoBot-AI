# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``get_user_permissions`` resolves a DB role's permissions (#18259).

The contrast tests pin why the fix was needed: the line both forks carried,
``role.Permission``, raises on a real ``Role``.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.grant_scope import encode_grant, grant_scope, grants_in_scope
from autobot_shared.user_management.models.role import Role
from autobot_shared.user_management.user_service import UserService


class _Bound(UserService):
    user_model = MagicMock()


async def test_fixed_query_returns_the_roles_permissions(grant_db):
    await grant_db.add_role("auditor", ["audit:read", "users:read"])
    user_id = await grant_db.add_user("ann", ["auditor"])
    service = _Bound(grant_db.session, TenantContext())
    assert await service.get_user_permissions(user_id) == {"audit:read", "users:read"}


async def test_permissions_are_the_union_of_every_role(grant_db):
    await grant_db.add_role("reader", ["users:read", "teams:read"])
    await grant_db.add_role("writer", ["users:read", "users:write"])
    await grant_db.add_role("empty", [])
    user_id = await grant_db.add_user("bob", ["reader", "writer", "empty"])
    service = _Bound(grant_db.session, TenantContext())
    assert await service.get_user_permissions(user_id) == {"users:read", "users:write", "teams:read"}


async def test_a_user_without_roles_gets_nothing(grant_db):
    await grant_db.add_role("reader", ["users:read"])
    user_id = await grant_db.add_user("cid", [])
    assert await _Bound(grant_db.session, TenantContext()).get_user_permissions(user_id) == set()


_ORG = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
_OTHER_ORG = uuid.UUID("00000000-0000-0000-0000-0000000000a2")


async def test_a_company_role_grants_only_inside_its_company(grant_db):
    """#18338: a company role's permissions never become platform-wide."""
    await grant_db.add_role("platform", ["users:read"])
    await grant_db.add_role("company-admin", ["admin.system"], org_id=_ORG)
    user_id = await grant_db.add_user("dee", ["platform", "company-admin"])
    service = _Bound(grant_db.session, TenantContext())
    assert await service.get_user_permissions(user_id) == {"users:read"}
    assert await service.get_user_permissions(user_id, _OTHER_ORG) == {"users:read"}
    assert await service.get_user_permissions(user_id, _ORG) == {"users:read", "admin.system"}


async def test_a_role_with_no_company_that_is_not_a_system_role_grants_nothing(grant_db):
    await grant_db.add_role("custom", ["admin.system"], is_system=False)
    user_id = await grant_db.add_user("eve", ["custom"])
    assert await _Bound(grant_db.session, TenantContext()).get_user_permissions(user_id) == set()


@pytest.mark.parametrize(
    ("org_id", "is_system", "scope"),
    [(None, True, "platform"), (_ORG, False, f"org:{_ORG}"), (_ORG, True, f"org:{_ORG}"), (None, False, None)],
)
def test_grant_scope(org_id, is_system, scope):
    assert grant_scope(org_id, is_system) == scope


def test_grants_in_scope_round_trip():
    grants = {encode_grant("a", None, True), encode_grant("b", _ORG, False)}
    assert None not in grants and encode_grant("c", None, False) is None
    assert grants_in_scope(grants, None) == {"a"}
    assert grants_in_scope(grants, _OTHER_ORG) == {"a"}
    assert grants_in_scope(grants, _ORG) == {"a", "b"}


def test_contrast_the_legacy_line_raises():
    """``role.Permission`` -- the pre-#18259 lookup -- is not an attribute of ``Role``.

    Instance lookup falls through to the class, so the class-level access is the
    same failure without configuring every mapper in the registry.
    """
    with pytest.raises(AttributeError, match="Permission"):
        Role.Permission  # noqa: B018  # the legacy line's attribute access
