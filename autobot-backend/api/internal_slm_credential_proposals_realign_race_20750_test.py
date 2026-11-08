# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20750: a lost race on the one-pending-realign-per-node index returns the winner's proposal, not a 503."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from api import internal_slm_credential_proposals as route
from api.schemas_slm_credential_proposals import CredentialProposal
from autobot_shared.slm_credential_actions import INTERNAL_KEY_REALIGN
from testkit.fake_async_session import FakeAsyncSession

_WINNER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
_NEW_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")


def _body() -> CredentialProposal:
    return CredentialProposal(action=INTERNAL_KEY_REALIGN.name, node_id="node-1")


async def _propose(list_approvals, create):
    gate = MagicMock()
    gate.return_value.list_approvals = list_approvals
    gate.return_value.create_approval = create
    db = FakeAsyncSession()
    with (
        patch.object(route, "ApprovalGateService", gate),
        patch.object(route, "record_realign_proposal", AsyncMock(return_value=True)) as proposed,
        patch.object(route, "record_realign_proposal_failed", AsyncMock(return_value=True)) as compensated,
    ):
        # service_opt_in wraps the handler; the undecorated coroutine is what the route runs.
        handler = getattr(route.propose_credential_change, "__wrapped__", route.propose_credential_change)
        reply = await handler(_body(), db)
    return reply, db, proposed, compensated


async def test_a_lost_insert_race_returns_the_winning_realign_proposal() -> None:
    winner = SimpleNamespace(id=_WINNER_ID, status="pending")
    lost = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique")))
    # realign reuses an approved approval too: two lookups (pending, approved) before the insert, two after
    lookups = AsyncMock(side_effect=[[], [], [winner]])
    reply, db, proposed, compensated = await _propose(lookups, lost)
    assert (reply.approval_id, reply.created) == (str(_WINNER_ID), False)
    assert db.rollbacks == 1
    proposed.assert_awaited_once()
    compensated.assert_awaited_once()  # the "proposed" row has no approval behind it, so it is compensated


async def test_a_conflict_with_no_winner_is_not_swallowed() -> None:
    lost = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("other")))
    with pytest.raises(IntegrityError):
        await _propose(AsyncMock(return_value=[]), lost)


async def test_contrast_no_conflict_creates() -> None:
    created = AsyncMock(return_value=SimpleNamespace(id=_NEW_ID, status="pending"))
    reply, *_ = await _propose(AsyncMock(return_value=[]), created)
    assert (reply.approval_id, reply.created) == (str(_NEW_ID), True)
