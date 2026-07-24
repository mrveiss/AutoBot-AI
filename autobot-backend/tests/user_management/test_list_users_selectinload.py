# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #12315: UserService.list_users must not 500 on a bad selectinload target.

The paginated list path used ``selectinload(User.roles)`` while the model's
relationship is named ``user_roles`` (three sibling single-user queries get it
right). Accessing the non-existent ``User.roles`` attribute raised
``AttributeError`` while the paginated query was being *constructed* — before
any row was fetched — so ``GET /api/user-management/users`` returned HTTP 500
and the admin User Management page could not load at all.

These tests pin two things:

* ``User.user_roles`` is the real relationship and ``User.roles`` does not
  exist (guards against the exact typo silently reappearing).
* ``list_users`` builds its eager-load query and returns ``(users, total)``
  without raising — i.e. a 200-shaped result, not a 500.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from user_management.models import User
from user_management.services.base_service import TenantContext
from user_management.services.user_service import UserService


def test_user_has_user_roles_relationship_not_roles():
    """The relationship is ``user_roles``; the typo target ``roles`` must not exist."""
    assert hasattr(User, "user_roles"), "User.user_roles relationship is missing"
    assert not hasattr(User, "roles"), "User.roles must not exist (selectinload typo target)"


def _mock_session(users):
    """AsyncSession stand-in: count query then paginated query.

    ``list_users`` executes the count query first, then constructs the
    eager-load paginated query (the line that used to raise), then executes it.
    """
    count_result = MagicMock()
    count_result.scalar.return_value = len(users)

    page_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = users
    page_result.scalars.return_value = scalars

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[count_result, page_result])
    return session


@pytest.mark.asyncio
async def test_list_users_returns_page_without_raising():
    """list_users builds the selectinload query and returns (users, total) — no 500."""
    users = [
        User(id=uuid.uuid4(), email="a@example.com", username="alice"),
        User(id=uuid.uuid4(), email="b@example.com", username="bob"),
    ]
    service = UserService(_mock_session(users), TenantContext())

    result, total = await service.list_users(limit=100, offset=0, include_inactive=False)

    assert total == 2
    assert [u.username for u in result] == ["alice", "bob"]


@pytest.mark.asyncio
async def test_list_users_empty_is_ok():
    """Empty result set still returns a well-formed (empty list, 0) tuple."""
    service = UserService(_mock_session([]), TenantContext())

    result, total = await service.list_users()

    assert result == []
    assert total == 0
