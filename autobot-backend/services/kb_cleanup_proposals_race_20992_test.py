# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A concurrent loser of the pending-proposal insert returns the winner's proposal (#20992)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from services.kb_cleanup_proposals import cleanup_proposal, create_proposal_once, record_cleanup_proposed


def _service(found: list, session):
    return SimpleNamespace(list_approvals=AsyncMock(side_effect=found), session=session)


def _lost() -> IntegrityError:
    return IntegrityError("insert", {}, Exception("unique"))


_USER = {"username": "admin", "user_id": "user-id-1"}


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

    migration = importlib.import_module("migrations.versions.20261121_118_approvals_pending_kb_cleanup_unique")
    expected = {
        "connector_credential_strip": approval.PENDING_CONNECTOR_CREDENTIAL_WHERE,
        "chroma_empty_collection_delete": approval.PENDING_EMPTY_COLLECTION_WHERE,
    }
    for _index, action, _key in migration._INDEXES:
        assert migration._where(action) == expected[action]


@pytest.mark.asyncio
async def test_the_lost_race_row_records_the_principal_id_not_the_username():
    """#22222: the audit actor is the canonical id, which a user cannot rename."""
    audit = AsyncMock(return_value=True)
    await _once(
        [[], [SimpleNamespace(id="w")]], SimpleNamespace(rollback=AsyncMock()), AsyncMock(side_effect=_lost()), audit
    )
    assert audit.await_args.kwargs["user_id"] == "user-id-1"


@pytest.mark.asyncio
async def test_the_proposed_row_records_the_principal_id_not_the_username():
    """#22222: ``record_cleanup_proposed`` writes the id as ``user_id``."""
    audit = AsyncMock(return_value=True)
    with patch("services.kb_cleanup_proposals.audit_log", audit):
        await record_cleanup_proposed(uuid.uuid4(), _USER, operation="op", resource="r:v")
    assert audit.await_args.kwargs["user_id"] == "user-id-1"


def test_the_approval_requester_is_the_principal_id_not_the_username():
    """#22222: ``requested_by_agent`` carries the id."""
    kwargs = cleanup_proposal(_USER, title="t", description="d", context={})
    assert kwargs["requested_by_agent"] == "user-id-1"


@pytest.mark.asyncio
async def test_a_caller_without_an_identity_is_refused_and_nothing_is_audited():
    """#22222: a username alone is not an identity."""
    audit = AsyncMock(return_value=True)
    with patch("services.kb_cleanup_proposals.audit_log", audit), pytest.raises(HTTPException) as refused:
        await record_cleanup_proposed(uuid.uuid4(), {"username": "admin"}, operation="op", resource="r:v")
    assert refused.value.status_code == 401
    audit.assert_not_awaited()
