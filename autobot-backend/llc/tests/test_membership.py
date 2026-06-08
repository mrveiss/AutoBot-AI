# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for LLC company membership service (GH#8223).

Verifies:
  1. add_member inserts a new membership row.
  2. add_member raises MemberAlreadyExistsError when duplicate.
  3. remove_member deletes the membership row.
  4. remove_member raises MemberNotFoundError when absent.
  5. list_members returns all members for the given company.
  6. is_member returns True/False correctly.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.services.membership_service import (
    MemberAlreadyExistsError,
    MemberNotFoundError,
    MembershipService,
)


def _make_membership(company_id=None, user_id=None, role=MembershipRole.MEMBER) -> MagicMock:
    m = MagicMock(spec=LLCCompanyMembership)
    m.id = uuid.uuid4()
    m.company_id = uuid.UUID(company_id) if company_id else uuid.uuid4()
    m.user_id = uuid.UUID(user_id) if user_id else uuid.uuid4()
    m.role = role
    return m


@pytest.fixture
def service():
    return MembershipService()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session._result = result
    return session


class TestAddMember:
    async def test_add_member_inserts_row(self, service, mock_session):
        company_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        mock_session._result.scalar_one_or_none.return_value = None  # no existing

        await service.add_member(mock_session, company_id, user_id, MembershipRole.ADMIN)

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert str(added.company_id) == company_id
        assert str(added.user_id) == user_id
        assert added.role == MembershipRole.ADMIN
        mock_session.flush.assert_called_once()

    async def test_add_member_duplicate_raises(self, service, mock_session):
        company_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        existing = _make_membership(company_id=company_id, user_id=user_id)
        mock_session._result.scalar_one_or_none.return_value = existing

        with pytest.raises(MemberAlreadyExistsError):
            await service.add_member(mock_session, company_id, user_id)


class TestRemoveMember:
    async def test_remove_member_deletes_row(self, service, mock_session):
        company_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        existing = _make_membership(company_id=company_id, user_id=user_id)
        mock_session._result.scalar_one_or_none.return_value = existing

        await service.remove_member(mock_session, company_id, user_id)

        # execute called twice: get_member + delete
        assert mock_session.execute.await_count == 2
        mock_session.flush.assert_called_once()

    async def test_remove_nonexistent_raises(self, service, mock_session):
        mock_session._result.scalar_one_or_none.return_value = None

        with pytest.raises(MemberNotFoundError):
            await service.remove_member(mock_session, str(uuid.uuid4()), str(uuid.uuid4()))


class TestListMembers:
    async def test_list_members_returns_all(self, service, mock_session):
        company_id = str(uuid.uuid4())
        members = [_make_membership(company_id=company_id) for _ in range(3)]
        mock_session._result.scalars.return_value.all.return_value = members

        result = await service.list_members(mock_session, company_id)

        assert len(result) == 3


class TestIsMember:
    async def test_is_member_true(self, service, mock_session):
        existing = _make_membership()
        mock_session._result.scalar_one_or_none.return_value = existing
        assert await service.is_member(mock_session, str(uuid.uuid4()), str(uuid.uuid4())) is True

    async def test_is_member_false(self, service, mock_session):
        mock_session._result.scalar_one_or_none.return_value = None
        assert await service.is_member(mock_session, str(uuid.uuid4()), str(uuid.uuid4())) is False
