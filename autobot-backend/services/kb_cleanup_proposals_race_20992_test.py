# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A concurrent loser of the pending-proposal insert returns the winner's proposal (#20992)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from services.kb_cleanup_proposals import create_proposal_once


def _service(found: list, session):
    return SimpleNamespace(list_approvals=AsyncMock(side_effect=found), session=session)


def _lost() -> IntegrityError:
    return IntegrityError("insert", {}, Exception("unique"))


_USER = {"username": "admin"}


async def _once(found: list, session, create, audit):
    with patch("services.kb_cleanup_proposals.audit_log", audit):
        return await create_proposal_once(
            _service(found, session), "a", "k", "v", create, current_user=_USER, resource="r:v"
        )


@pytest.mark.asyncio
async def test_the_loser_rolls_back_and_returns_the_winner():
    winner = SimpleNamespace(id="w")
    session = SimpleNamespace(rollback=AsyncMock())
    create = AsyncMock(side_effect=_lost())
    got = await _once([[], [winner]], session, create, AsyncMock(return_value=True))
    assert got is winner
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_loser_writes_exactly_one_lost_race_row_naming_both_ids():
    """The creation row (written inside ``create``) is the only other write; the loser adds one honest row."""
    winner = SimpleNamespace(id="w")
    audit = AsyncMock(return_value=True)
    create = AsyncMock(side_effect=_lost())
    await _once([[], [winner]], SimpleNamespace(rollback=AsyncMock()), create, audit)
    lost_id = create.await_args.args[0]
    audit.assert_awaited_once()
    assert audit.await_args.args == ("cleanup.proposal_lost_race",)  # the str-enum member
    details = audit.await_args.kwargs["details"]
    assert details == {"approval_id": str(lost_id), "winner_approval_id": "w"}
    assert audit.await_args.kwargs["durable"] is True


@pytest.mark.asyncio
async def test_a_failed_lost_race_row_does_not_fail_the_loser():
    winner = SimpleNamespace(id="w")
    got = await _once(
        [[], [winner]],
        SimpleNamespace(rollback=AsyncMock()),
        AsyncMock(side_effect=_lost()),
        AsyncMock(return_value=False),
    )
    assert got is winner


@pytest.mark.asyncio
async def test_the_winner_and_an_open_proposal_write_no_lost_race_row():
    audit = AsyncMock(return_value=True)
    created = SimpleNamespace(id="c")
    assert await _once([[]], SimpleNamespace(rollback=AsyncMock()), AsyncMock(return_value=created), audit) is created
    open_one = SimpleNamespace(id="o")
    create = AsyncMock()
    assert await _once([[open_one]], SimpleNamespace(rollback=AsyncMock()), create, audit) is open_one
    create.assert_not_awaited()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_integrity_error_with_no_winner_is_raised():
    audit = AsyncMock(return_value=True)
    with pytest.raises(IntegrityError):
        await _once([[], []], SimpleNamespace(rollback=AsyncMock()), AsyncMock(side_effect=_lost()), audit)
    audit.assert_not_awaited()


def test_the_model_declares_both_partial_unique_indexes():
    from models.approval import PENDING_CONNECTOR_CREDENTIAL_INDEX, PENDING_EMPTY_COLLECTION_INDEX, Approval

    by_name = {i.name: i for i in Approval.__table__.indexes}
    for name in (PENDING_CONNECTOR_CREDENTIAL_INDEX, PENDING_EMPTY_COLLECTION_INDEX):
        assert by_name[name].unique


def test_the_model_where_text_equals_the_migrations():
    import importlib

    from models import approval

    migration = importlib.import_module("migrations.versions.20261121_117b_approvals_pending_kb_cleanup_unique")
    expected = {
        "connector_credential_strip": approval.PENDING_CONNECTOR_CREDENTIAL_WHERE,
        "chroma_empty_collection_delete": approval.PENDING_EMPTY_COLLECTION_WHERE,
    }
    for _index, action, _key in migration._INDEXES:
        assert migration._where(action) == expected[action]
