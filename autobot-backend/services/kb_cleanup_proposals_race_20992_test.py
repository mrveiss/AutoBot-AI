# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A concurrent loser of the pending-proposal insert returns the winner's proposal (#20992)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from services.kb_cleanup_proposals import create_proposal_once


def _service(found: list, session):
    return SimpleNamespace(list_approvals=AsyncMock(side_effect=found), session=session)


def _lost() -> IntegrityError:
    return IntegrityError("insert", {}, Exception("unique"))


@pytest.mark.asyncio
async def test_the_loser_rolls_back_and_returns_the_winner():
    winner = SimpleNamespace(id="w")
    session = SimpleNamespace(rollback=AsyncMock())
    create = AsyncMock(side_effect=_lost())
    got = await create_proposal_once(_service([[], [winner]], session), "a", "k", "v", create)
    assert got is winner
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_integrity_error_with_no_winner_is_raised():
    session = SimpleNamespace(rollback=AsyncMock())
    with pytest.raises(IntegrityError):
        await create_proposal_once(_service([[], []], session), "a", "k", "v", AsyncMock(side_effect=_lost()))


@pytest.mark.asyncio
async def test_an_open_proposal_is_returned_without_creating():
    open_one = SimpleNamespace(id="o")
    create = AsyncMock()
    session = SimpleNamespace(rollback=AsyncMock())
    assert await create_proposal_once(_service([[open_one]], session), "a", "k", "v", create) is open_one
    create.assert_not_awaited()


def test_the_model_declares_both_partial_unique_indexes():
    from models.approval import PENDING_CONNECTOR_CREDENTIAL_INDEX, PENDING_EMPTY_COLLECTION_INDEX, Approval

    by_name = {i.name: i for i in Approval.__table__.indexes}
    for name in (PENDING_CONNECTOR_CREDENTIAL_INDEX, PENDING_EMPTY_COLLECTION_INDEX):
        assert by_name[name].unique
