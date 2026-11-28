# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one permission decision (#18263): strict role grant UNION DB grants, AND key narrowing."""

import uuid
from unittest.mock import AsyncMock

import pytest

from autobot_shared.auth.permission_evaluator import (
    caller_user_id,
    db_grant,
    evaluate_any,
    evaluate_permission,
    permission_allowed,
    role_grant,
)
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

_UID = uuid.UUID("00000000-0000-0000-0000-0000000000b2")


class TestRoleGrant:
    @pytest.mark.parametrize("role", list(Role))
    def test_an_exact_role_value_gets_its_role_permissions(self, role):
        assert role_grant({"role": role.value}) == frozenset(ROLE_PERMISSIONS.get(role, ()))

    @pytest.mark.parametrize(
        "caller",
        [{}, {"role": ""}, {"role": "Admin"}, {"role": "bogus"}, {"role": None}, {"role": 1}, {"admin": True}, None],
    )
    def test_anything_else_gets_nothing(self, caller):
        assert role_grant(caller) == frozenset()


class TestDbGrant:
    def test_only_permission_values_count(self):
        names = ["chat.use", "allow_all", "users:read", 7]
        assert db_grant(names) == frozenset({Permission.CHAT_USE})


class TestCallerUserId:
    @pytest.mark.parametrize(
        ("caller", "expected"),
        [({"user_id": str(_UID)}, _UID), ({"user_id": _UID}, _UID), ({"user_id": "admin"}, None), ({}, None)],
    )
    def test_only_a_uuid_is_a_user_id(self, caller, expected):
        assert caller_user_id(caller) == expected


class TestPermissionAllowed:
    def test_the_role_grant_allows(self):
        assert permission_allowed({"role": "admin"}, Permission.ADMIN_SYSTEM)

    def test_a_db_grant_is_unioned_in(self):
        caller = {"role": "readonly"}
        assert not permission_allowed(caller, Permission.KNOWLEDGE_WRITE)
        assert permission_allowed(caller, Permission.KNOWLEDGE_WRITE, ["knowledge.write"])

    def test_a_key_is_narrowed_even_over_a_db_grant(self):
        key = {"role": "admin", "api_key_id": "k", "scopes": ["knowledge:read"]}
        assert permission_allowed(key, Permission.KNOWLEDGE_READ)
        assert not permission_allowed(key, Permission.KNOWLEDGE_WRITE, ["knowledge.write"])

    def test_a_key_never_exceeds_its_owner_role(self):
        key = {"role": "readonly", "api_key_id": "k", "scopes": ["admin:*"]}
        assert not permission_allowed(key, Permission.ADMIN_SYSTEM)

    @pytest.mark.parametrize("bad", ["admin.system", None, 3])
    def test_contrast_a_non_member_argument_raises(self, bad):
        with pytest.raises(TypeError, match="Permission member"):
            permission_allowed({"role": "admin"}, bad)


class TestEvaluate:
    async def test_db_grants_are_not_loaded_when_the_role_decides(self):
        loader = AsyncMock(return_value=[])
        assert await evaluate_permission({"role": "admin", "user_id": str(_UID)}, Permission.API_READ, loader)
        loader.assert_not_awaited()

    async def test_db_grants_decide_when_the_role_does_not(self):
        loader = AsyncMock(return_value=["knowledge.write"])
        caller = {"role": "readonly", "user_id": str(_UID)}
        assert await evaluate_permission(caller, Permission.KNOWLEDGE_WRITE, loader)
        loader.assert_awaited_once_with(_UID, None)

    async def test_the_loader_is_asked_for_the_callers_org(self):
        """#18338: company-role grants are looked up for the org the caller acts in."""
        org = "00000000-0000-0000-0000-0000000000c9"
        loader = AsyncMock(return_value=[])
        await evaluate_permission(
            {"role": "readonly", "user_id": str(_UID), "org_id": org}, Permission.API_WRITE, loader
        )
        loader.assert_awaited_once_with(_UID, uuid.UUID(org))

    async def test_a_caller_without_a_user_id_is_never_looked_up(self):
        loader = AsyncMock(return_value=["knowledge.write"])
        assert not await evaluate_permission({"role": "readonly"}, Permission.KNOWLEDGE_WRITE, loader)
        loader.assert_not_awaited()

    async def test_any_loads_once_for_all_permissions(self):
        loader = AsyncMock(return_value=["files.delete"])
        caller = {"role": "readonly", "user_id": str(_UID)}
        assert await evaluate_any(caller, (Permission.ADMIN_SYSTEM, Permission.FILES_DELETE), loader)
        loader.assert_awaited_once()
