# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared UserService's merged hunks (#15068).

Each test pins one decision recorded in the module docstrings: the two hooks are
no-ops by default, ``change_password`` writes the UNION of both forks' audit keys,
and ``delete_user`` keeps the backend's fail-closed reassignment on hard delete.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.user_management import user_service_lifecycle
from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.models.audit import IdentityAuditAction
from autobot_shared.user_management.user_service import UserService
from autobot_shared.user_management.user_service_errors import DuplicateUserError, UserServiceError


class _Bound(UserService):
    user_model = MagicMock()


class _WithHooks(_Bound):
    async def invalidate_other_sessions(self, user_id, current_token):
        return 3

    async def reassign_memory(self, user_id, reassign_to):
        raise RuntimeError("store down")


def _service(cls=_Bound):
    session = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    svc = cls(session, TenantContext())
    user = MagicMock(username="alice", password_hash=None)
    svc.get_user = AsyncMock(return_value=user)
    svc._audit_log = AsyncMock()
    return svc


def test_an_unbound_subclass_fails_at_construction():
    with pytest.raises(TypeError, match="user_model"):
        UserService(MagicMock(), TenantContext())


def test_duplicate_user_error_carries_its_field():
    err = DuplicateUserError("taken", field="email")
    assert err.field == "email" and isinstance(err, UserServiceError)


@pytest.mark.asyncio
async def test_hooks_are_no_ops_by_default():
    svc = _service()
    assert await svc.invalidate_other_sessions(uuid.uuid4(), None) == 0
    assert await svc.reassign_memory(uuid.uuid4(), uuid.uuid4()) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,expected_invalidated", [(_Bound, 0), (_WithHooks, 3)])
async def test_change_password_audits_the_union_of_both_forks_keys(cls, expected_invalidated):
    svc = _service(cls)
    with patch.object(user_service_lifecycle, "set_password_epoch", AsyncMock(return_value=1234)) as epoch:
        assert await svc.change_password(uuid.uuid4(), None, "new-secret", require_current=False)
    epoch.assert_awaited_once_with("alice")
    action, _rtype, _rid, details = svc._audit_log.await_args.args
    assert action == IdentityAuditAction.PASSWORD_CHANGED
    assert details == {
        "method": "user_initiated",
        "sessions_revoked_from": 1234,
        "sessions_invalidated": expected_invalidated,
    }


@pytest.mark.asyncio
async def test_a_failed_reassignment_aborts_a_hard_delete():
    svc = _service(_WithHooks)
    with pytest.raises(RuntimeError, match="store down"):
        await svc.delete_user(uuid.uuid4(), hard_delete=True, reassign_to=uuid.uuid4())
    svc.session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_reassignment_does_not_block_a_soft_delete():
    svc = _service(_WithHooks)
    assert await svc.delete_user(uuid.uuid4(), hard_delete=False, reassign_to=uuid.uuid4())
    details = svc._audit_log.await_args.args[3]
    assert details["hard_delete"] is False and details["reassign_counts"] == {}
